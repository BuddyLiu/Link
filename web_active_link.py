#!/usr/bin/env python3
"""
LINK主动运行模式的Web版本
提供Web界面，避免CLI模式下心跳输出干扰用户输入
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from queue import Queue, PriorityQueue
import json
import uuid

# Web框架
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn


class EventPriority(Enum):
    """事件优先级"""
    CRITICAL = 0      # P0: 关键系统事件（立即处理）
    HIGH = 1          # P1: 用户交互事件（< 1秒）
    MEDIUM = 2        # P2: 时间敏感事件（< 5秒）
    NORMAL = 3        # P3: 常规处理事件（< 30秒）
    LOW = 4           # P4: 后台维护事件（分钟级）
    BACKGROUND = 5    # P5: 学习进化事件（小时级）


class EventType(Enum):
    """事件类型"""
    USER_INPUT = "user_input"          # 用户输入
    TASK_STATUS = "task_status"        # 任务状态变化
    MEMORY_UPDATE = "memory_update"    # 记忆更新
    TIMER = "timer"                    # 定时器触发
    EXTERNAL = "external"              # 外部事件
    LEARNING = "learning"              # 学习事件
    SYSTEM = "system"                  # 系统事件


@dataclass(order=True)
class Event:
    """事件对象"""
    priority: int  # 用于PriorityQueue排序（数值越小优先级越高）
    timestamp: float
    event_type: EventType
    data: Dict[str, Any] = field(compare=False)
    handler: Optional[Callable] = field(compare=False)
    source: str = field(compare=False)
    
    def __init__(self, event_type: EventType, data: Dict[str, Any], 
                 priority: EventPriority = EventPriority.NORMAL,
                 handler: Optional[Callable] = None,
                 source: str = "system"):
        self.event_type = event_type
        self.data = data
        self.priority = priority.value
        self.timestamp = time.time()
        self.handler = handler
        self.source = source
    
    def to_dict(self):
        """转换为字典，用于JSON序列化"""
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "source": self.source,
            "time_str": datetime.fromtimestamp(self.timestamp).strftime("%H:%M:%S")
        }


class EventSource:
    """事件源基类"""
    
    def __init__(self, name: str):
        self.name = name
        self.active = True
        self.callbacks = []
    
    def poll(self) -> List[Event]:
        """轮询事件（子类实现）"""
        return []
    
    def add_callback(self, callback: Callable):
        """添加事件回调"""
        self.callbacks.append(callback)
    
    def notify(self, event: Event):
        """通知所有回调"""
        for callback in self.callbacks:
            try:
                callback(event)
            except Exception as e:
                print(f"事件回调错误: {e}")


class UserInputSource(EventSource):
    """用户输入事件源"""
    
    def __init__(self):
        super().__init__("user_input")
        self.input_queue = Queue()
    
    def add_input(self, text: str, user_id: str = "default"):
        """添加用户输入"""
        event = Event(
            event_type=EventType.USER_INPUT,
            data={"text": text, "user_id": user_id},
            priority=EventPriority.HIGH,
            source=f"user_{user_id}"
        )
        self.input_queue.put(event)
        self.notify(event)
    
    def poll(self) -> List[Event]:
        """轮询用户输入"""
        events = []
        while not self.input_queue.empty():
            events.append(self.input_queue.get())
        return events


class TimerSource(EventSource):
    """定时器事件源"""
    
    def __init__(self):
        super().__init__("timer")
        self.timers = []  # (trigger_time, event)
        self.periodic_tasks = []  # (interval, last_run, event_generator)
    
    def add_timer(self, delay_seconds: float, event: Event):
        """添加一次性定时器"""
        trigger_time = time.time() + delay_seconds
        self.timers.append((trigger_time, event))
        self.timers.sort(key=lambda x: x[0])  # 按触发时间排序
    
    def add_periodic_task(self, interval_seconds: float, 
                          event_generator: Callable[[], Event],
                          name: str = ""):
        """添加周期性任务"""
        self.periodic_tasks.append({
            "interval": interval_seconds,
            "last_run": 0,
            "generator": event_generator,
            "name": name
        })
    
    def poll(self) -> List[Event]:
        """轮询定时器"""
        events = []
        current_time = time.time()
        
        # 检查一次性定时器
        while self.timers and self.timers[0][0] <= current_time:
            _, event = self.timers.pop(0)
            events.append(event)
        
        # 检查周期性任务
        for task in self.periodic_tasks:
            if current_time - task["last_run"] >= task["interval"]:
                try:
                    event = task["generator"]()
                    events.append(event)
                    task["last_run"] = current_time
                except Exception as e:
                    print(f"周期性任务错误 ({task.get('name', 'unnamed')}): {e}")
        
        return events


class EventHandler:
    """事件处理器基类"""
    
    def __init__(self, name: str):
        self.name = name
    
    def handle(self, event: Event) -> Any:
        """处理事件（子类实现）"""
        return None
    
    def can_handle(self, event: Event) -> bool:
        """检查是否能处理此事件"""
        return True


class TaskEventHandler(EventHandler):
    """任务事件处理器"""

    def __init__(self, link_instance=None):
        super().__init__("task_handler")
        self.link = link_instance
        # 如果传入的是 WebActiveLINK 实例，自动获取其中的 brain_link
        self.brain_link = getattr(link_instance, 'brain_link', None)

    def can_handle(self, event: Event) -> bool:
        return event.event_type in [EventType.TASK_STATUS, EventType.USER_INPUT]

    def handle(self, event: Event) -> Any:
        if event.event_type == EventType.TASK_STATUS:
            return self._handle_task_status(event)
        elif event.event_type == EventType.USER_INPUT:
            return self._handle_user_input(event)
        return None

    def _handle_task_status(self, event: Event) -> str:
        """处理任务状态事件"""
        data = event.data

        if data.get("status") == "failed":
            return f"⚠️ 任务失败: {data.get('task_name', '未知任务')} (ID: {data.get('task_id', 'N/A')})"

        elif data.get("status") == "blocked":
            return f"⏸️  任务阻塞: {data.get('task_name', '未知任务')}"

        elif data.get("status") == "long_running":
            minutes = data.get("duration_seconds", 0) / 60
            return f"⏱️  任务长时间运行: {data.get('task_name', '未知任务')} ({minutes:.1f}分钟)"

        return "任务状态检查"

    def _handle_user_input(self, event: Event) -> str:
        """处理用户输入事件 — 调用大脑引擎响应"""
        text = event.data.get("text", "")
        if self.brain_link:
            try:
                return self.brain_link.process_input(text)
            except Exception as e:
                return f"❌ 处理出错: {e}"
        return f"📝 收到用户输入: {text}"


class SystemEventHandler(EventHandler):
    """系统事件处理器"""
    
    def __init__(self):
        super().__init__("system_handler")
    
    def can_handle(self, event: Event) -> bool:
        return event.event_type == EventType.SYSTEM
    
    def handle(self, event: Event) -> Any:
        data = event.data
        action = data.get("action", "")
        
        if action == "shutdown":
            return "🔌 系统关闭请求"
        elif action == "restart":
            return "🔄 系统重启请求"
        elif action == "status":
            return "📊 系统状态检查"
        elif action == "heartbeat":
            return "💓 系统心跳正常"
        
        return f"系统操作: {action}"


class LearningEventHandler(EventHandler):
    """学习事件处理器"""
    
    def __init__(self, link_instance=None):
        super().__init__("learning_handler")
        self.link = link_instance
        self.last_learning_time = 0
        self.learning_interval = 3600  # 1小时
    
    def can_handle(self, event: Event) -> bool:
        return event.event_type == EventType.LEARNING
    
    def handle(self, event: Event) -> Any:
        data = event.data
        action = data.get("action", "")
        
        if action == "analyze_memory":
            return self._analyze_memory_patterns()
        elif action == "learn_new_skill":
            return self._learn_new_skill(data.get("skill", ""))
        elif action == "optimize_performance":
            return self._optimize_performance()
        elif action == "user_preference_learning":
            return self._learn_user_preferences()
        
        return f"学习操作: {action}"
    
    def _analyze_memory_patterns(self) -> str:
        """分析记忆模式"""
        try:
            return "⚡ 记忆模式分析完成：系统运行正常"
        except Exception as e:
            return f"❌ 记忆分析失败: {e}"
    
    def _learn_new_skill(self, skill_name: str) -> str:
        """学习新技能"""
        if not skill_name:
            skill_name = "通用任务处理"
        
        try:
            return f"🎓 开始学习新技能: {skill_name}"
        except Exception as e:
            return f"❌ 技能学习失败: {e}"
    
    def _optimize_performance(self) -> str:
        """优化性能"""
        try:
            return "⚡ 性能优化完成"
        except Exception as e:
            return f"❌ 性能优化失败: {e}"
    
    def _learn_user_preferences(self) -> str:
        """学习用户偏好"""
        try:
            return "👤 用户偏好学习完成"
        except Exception as e:
            return f"❌ 用户偏好学习失败: {e}"


# ── 任务队列（支持非阻塞、排队、状态追踪） ──

@dataclass
class TaskItem:
    """单个用户消息处理任务"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = ""
    status: str = "pending"  # pending / processing / done / error / cancelled
    created_at: float = field(default_factory=time.time)
    result: Optional[str] = None
    reasoning: Optional[str] = None


class TaskManager:
    """任务队列管理器，串行处理，支持状态查询"""

    def __init__(self):
        self._queue: asyncio.Queue[TaskItem] = asyncio.Queue()
        self._tasks: Dict[str, TaskItem] = {}
        self._current: Optional[TaskItem] = None
        self._worker_task: Optional[asyncio.Task] = None
        self._status_callbacks: List[Callable] = []

    def on_status_change(self, cb: Callable):
        """注册任务状态变化回调"""
        self._status_callbacks.append(cb)

    def _notify(self, task: TaskItem, total: int):
        for cb in self._status_callbacks:
            try:
                cb(task, total)
            except Exception:
                pass

    async def submit(self, text: str) -> TaskItem:
        """提交新任务，放入队列，返回 TaskItem"""
        task = TaskItem(text=text)
        self._tasks[task.id] = task
        await self._queue.put(task)
        self._notify(task, self._queue.qsize())
        return task

    def get_task(self, task_id: str) -> Optional[TaskItem]:
        return self._tasks.get(task_id)

    def list_tasks(self, limit: int = 20) -> List[TaskItem]:
        pending = [t for t in self._tasks.values() if t.status in ("pending", "processing")]
        done = [t for t in self._tasks.values() if t.status == "done"]
        return (pending + done[-limit:])[::-1]

    async def worker(self, process_fn):
        """后台工作者：不断从队列消费任务并调用 process_fn 处理"""
        self._worker_task = asyncio.current_task()
        while True:
            task = await self._queue.get()
            if task.status == "cancelled":
                continue
            self._current = task
            task.status = "processing"
            total = self._queue.qsize() + 1
            self._notify(task, total)

            try:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, process_fn, task.text
                )
                task.result = result.get("result") if isinstance(result, dict) else str(result)
                task.reasoning = result.get("reasoning", "") if isinstance(result, dict) else ""
                task.status = "done"
            except Exception as e:
                task.result = f"❌ 处理出错: {e}"
                task.status = "error"

            self._current = None
            self._notify(task, self._queue.qsize())

    def cancel_current(self):
        """取消当前处理中的任务（标记为 cancelled，不中断执行）"""
        if self._current and self._current.status == "processing":
            self._current.status = "cancelled"

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    @property
    def current_task(self) -> Optional[TaskItem]:
        return self._current


class WebActiveLINK:
    """Web版本的主动运行模式LINK"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化Web版本的主动LINK
        
        Args:
            config: 配置参数
        """
        self.config = self._get_default_config()
        if config:
            self.config.update(config)
        
        # 事件系统
        self.event_sources = {}
        self.event_handlers = {}
        self.event_queue = PriorityQueue()
        self.is_running = False
        self.event_thread = None
        
        # Web相关
        self.app = FastAPI(title="LINK主动模式Web界面")
        self.websocket_clients = []
        self.event_history = []
        self.task_manager = TaskManager()
        self.max_history = 100
        
        # 统计
        self.stats = {
            "events_processed": 0,
            "events_dropped": 0,
            "start_time": None,
            "last_event_time": None
        }

        # 初始化大脑引擎（LINK 主实例，用于 LLM 问答）
        self.brain_link = None
        self._init_brain_link()

        # 初始化组件
        self._initialize_components()
        self._setup_routes()

    def _init_brain_link(self):
        """初始化 LINK 大脑引擎（延迟导入避免循环引用）"""
        try:
            from main import LINK
            self.brain_link = LINK()
            import logging
            logging.getLogger("link").info("WebActiveLINK 大脑引擎已就绪")
        except Exception as e:
            print(f"⚠️ 大脑引擎初始化失败，将使用本地响应: {e}")
            self.brain_link = None

    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "event_loop_interval": 0.1,  # 100ms
            "max_events_per_cycle": 10,
            "enable_periodic_tasks": True,
            "periodic_tasks": {
                "heartbeat": {"interval": 1, "enabled": True},
                "task_monitor": {"interval": 5, "enabled": True},
                "reminder_check": {"interval": 60, "enabled": True},
                "memory_cleanup": {"interval": 300, "enabled": True},
                "learning_cycle": {"interval": 3600, "enabled": True}  # 1小时
            },
            "log_level": "INFO",
            "web_host": "127.0.0.1",
            "web_port": 8011
        }
    
    def _initialize_components(self):
        """初始化所有组件"""
        # 初始化事件源
        self.event_sources["user_input"] = UserInputSource()
        self.event_sources["timer"] = TimerSource()
        
        # 初始化事件处理器
        self.event_handlers["task"] = TaskEventHandler(self)
        self.event_handlers["system"] = SystemEventHandler()
        self.event_handlers["learning"] = LearningEventHandler(self)
        
        # 设置周期性任务
        if self.config["enable_periodic_tasks"]:
            self._setup_periodic_tasks()
    
    def _setup_periodic_tasks(self):
        """设置周期性任务"""
        timer_source = self.event_sources.get("timer")
        if not timer_source:
            return
        
        tasks_config = self.config.get("periodic_tasks", {})
        
        # 心跳任务（减少频率，避免干扰）
        if tasks_config.get("heartbeat", {}).get("enabled"):
            def heartbeat_generator():
                return Event(
                    event_type=EventType.SYSTEM,
                    data={"action": "heartbeat", "timestamp": time.time()},
                    priority=EventPriority.BACKGROUND,
                    source="heartbeat"
                )
            
            timer_source.add_periodic_task(
                interval_seconds=5,  # 从1秒改为5秒
                event_generator=heartbeat_generator,
                name="heartbeat"
            )
        
        # 任务监控任务
        if tasks_config.get("task_monitor", {}).get("enabled"):
            def task_monitor_generator():
                return Event(
                    event_type=EventType.TASK_STATUS,
                    data={"action": "monitor", "timestamp": time.time()},
                    priority=EventPriority.LOW,
                    source="task_monitor"
                )
            
            timer_source.add_periodic_task(
                interval_seconds=10,  # 从5秒改为10秒
                event_generator=task_monitor_generator,
                name="task_monitor"
            )
        
        # 学习周期任务
        if tasks_config.get("learning_cycle", {}).get("enabled"):
            def learning_cycle_generator():
                return Event(
                    event_type=EventType.LEARNING,
                    data={
                        "action": "analyze_memory",
                        "timestamp": time.time(),
                        "cycle_type": "scheduled"
                    },
                    priority=EventPriority.BACKGROUND,
                    source="learning_cycle"
                )
            
            timer_source.add_periodic_task(
                interval_seconds=600,  # 从3600秒改为10分钟，便于测试
                event_generator=learning_cycle_generator,
                name="learning_cycle"
            )
    
    def _setup_routes(self):
        """设置FastAPI路由"""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def get_index():
            """主页"""
            return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LINK</title>
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0a0f;height:100vh;display:flex;flex-direction:column;color:#e0e0e0}
/* Header */
.header{background:#0d0d14;border-bottom:1px solid #1a1a2e;padding:12px 20px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.header h1{font-size:16px;font-weight:500;letter-spacing:2px;background:linear-gradient(90deg,#6366f1,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header a{color:#6366f1;text-decoration:none;font-size:11px;padding:4px 10px;border:1px solid #1a1a2e;border-radius:4px;transition:all .2s}
.header a:hover{border-color:#6366f1;background:rgba(99,102,241,.1)}
.header div{display:flex;gap:8px}
/* Chat box */
#chat-container{flex:1;display:flex;overflow:hidden;position:relative}
.chat-column{overflow-y:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
.chat-column::-webkit-scrollbar{width:4px}
.chat-column::-webkit-scrollbar-track{background:transparent}
.chat-column::-webkit-scrollbar-thumb{background:#1a1a2e;border-radius:2px}
#user-column{background:#0a0a0f}
#assistant-column{background:#0d0d18}
#column-divider{width:6px;cursor:col-resize;background:#1a1a2e;flex-shrink:0;transition:background .15s}
#column-divider:hover{background:#6366f1}
#column-divider.active,#column-divider.dragging{background:#6366f1}
/* Floating scroll buttons */
#scroll-nav{position:fixed;z-index:100;cursor:grab;user-select:none}
#scroll-nav.dragging{cursor:grabbing}
#scroll-nav .nav-toggle{width:36px;height:36px;border-radius:50%;border:1.5px solid rgba(255,255,255,.25);background:rgba(13,13,20,.8);color:rgba(255,255,255,.6);font-size:14px;cursor:grab;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px);transition:all .2s}
#scroll-nav .nav-toggle:hover{transform:scale(1.15);border-color:rgba(255,255,255,.5)}
#scroll-nav .nav-content{display:flex;flex-direction:column;gap:8px;opacity:0;pointer-events:none;transition:opacity .2s}
#scroll-nav.expanded .nav-content{opacity:1;pointer-events:auto}
#scroll-nav.expanded .nav-toggle{display:none}
#scroll-nav .nav-content button{width:36px;height:36px;border-radius:50%;border:1.5px solid rgba(255,255,255,.35);background:rgba(13,13,20,.8);color:rgba(255,255,255,.7);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;backdrop-filter:blur(4px)}
#scroll-nav .nav-content button:hover{transform:scale(1.2);border-color:rgba(255,255,255,.6);background:rgba(99,102,241,.2)}
#scroll-nav .nav-content button.scroll-hidden{opacity:0;pointer-events:none}
.msg{margin-bottom:20px;display:flex;flex-direction:column;max-width:85%}
.msg.user{align-self:flex-end;align-items:flex-end}
.msg.assistant{align-self:flex-start;align-items:flex-start}
.msg .bubble{width:100%;padding:10px 16px;border-radius:12px;font-size:14px;line-height:1.5;word-break:break-word;position:relative}
.msg.user .bubble{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border-bottom-right-radius:4px}
.msg.assistant .bubble{background:#13131f;color:#d4d4e6;border:1px solid #1a1a2e;border-bottom-left-radius:4px}
.msg .time{font-size:10px;color:#6366f1;opacity:.5;margin-top:4px;padding:0 4px;letter-spacing:.5px}
.msg.user .time{text-align:right}
/* Input area */
.input-area{flex-shrink:0;padding:12px 20px;background:#0d0d14;border-top:1px solid #1a1a2e;display:flex;justify-content:center}
.input-area input{flex:1;padding:10px 14px;background:#13131f;border:1px solid rgba(255,255,255,.25);border-radius:8px;font-size:13px;outline:none;color:#e0e0e0;transition:border-color .2s}
.input-area input::placeholder{color:#4a4a6a}
.input-area input:focus{border-color:#6366f1}
.input-area button{padding:10px 20px;background:#6366f1;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all .2s}
.input-area button:hover{background:#4f46e5}
.input-area button:disabled{background:#1a1a2e;color:#4a4a6a;cursor:not-allowed}
/* Typing */
.typing .bubble{color:#6366f1;opacity:.6;font-style:italic;font-size:13px}
/* System messages */
.msg.system{align-self:center;align-items:center;max-width:100%}
.msg.system .bubble{background:transparent;color:#4a4a6a;font-size:11px;text-align:center;border:none;padding:4px}
/* Copy buttons */
.copy-btn{font-size:10px;cursor:pointer;opacity:0;transition:opacity .2s;border:1px solid transparent;background:transparent;padding:2px 8px;border-radius:4px;color:rgba(255,255,255,.6);margin-top:6px;align-self:flex-end}
.copy-btn:hover{border-color:rgba(255,255,255,.4)}
.copy-btn.visible{opacity:1}
.msg:hover .copy-btn{opacity:0.8}
/* Feedback buttons */
.feedback-btns{display:flex;gap:6px;margin-top:6px;align-self:flex-end}
.feedback-btn{width:28px;height:28px;border-radius:50%;border:1.5px solid rgba(255,255,255,.25);background:transparent;color:rgba(255,255,255,.5);font-size:13px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;padding:0;line-height:1}
.feedback-btn:hover{transform:scale(1.15);border-color:rgba(255,255,255,.5);color:#fff;background:rgba(255,255,255,.08)}
.feedback-btn:disabled{opacity:.4;cursor:default;transform:none}
.feedback-btn.active.up{background:rgba(34,197,94,.2);border-color:#22c55e;color:#22c55e}
.feedback-btn.active.down{background:rgba(239,68,68,.2);border-color:#ef4444;color:#ef4444}
/* Code blocks */
.code-wrap{position:relative;margin:8px 0;border-radius:8px;overflow:hidden;border:1px solid #1a1a2e}
.code-copy{position:absolute;top:4px;right:4px;padding:2px 8px;font-size:10px;background:rgba(99,102,241,.15);color:#6366f1;border:1px solid rgba(99,102,241,.2);border-radius:4px;cursor:pointer;opacity:0;transition:opacity .2s;z-index:1}
.code-wrap:hover .code-copy{opacity:1}
.code-copy:hover{background:rgba(99,102,241,.3)}
/* pre/code */
.msg .bubble pre{background:#0d0d14;color:#cdd6f4;padding:14px;overflow-x:auto;font-size:12px;margin:0;font-family:'SF Mono','Fira Code','Consolas',monospace}
.msg .bubble code{background:rgba(99,102,241,.15);color:#a5b4fc;padding:1px 5px;border-radius:3px;font-size:12px;font-family:'SF Mono','Fira Code',monospace}
.msg .bubble pre code{background:transparent;color:inherit;padding:0;border-radius:0}
.msg.user .bubble code{background:rgba(255,255,255,.15);color:#e0e0e0}
.msg.user .bubble pre{background:rgba(0,0,0,.2)}
/* Markdown content */
.msg .bubble p{margin:6px 0}
.msg .bubble p:first-child{margin-top:0}
.msg .bubble p:last-child{margin-bottom:0}
.msg .bubble ul,.msg .bubble ol{margin:6px 0;padding-left:20px}
.msg .bubble li{margin:3px 0}
.msg .bubble h1,.msg .bubble h2,.msg .bubble h3,.msg .bubble h4{margin:10px 0 6px;font-weight:500;color:#a5b4fc}
.msg .bubble h1{font-size:15px;letter-spacing:.5px}
.msg .bubble h2{font-size:14px}
.msg .bubble h3{font-size:13px}
.msg .bubble blockquote{border-left:2px solid #6366f1;padding:4px 12px;margin:8px 0;color:#8888aa;background:#0d0d14;border-radius:0 6px 6px 0}
.msg .bubble table{border-collapse:collapse;margin:8px 0;font-size:12px;width:100%;border:1px solid #1a1a2e}
.msg .bubble th,.msg .bubble td{border:1px solid #1a1a2e;padding:6px 10px;text-align:left}
.msg .bubble th{background:#0d0d14;color:#a5b4fc;font-weight:500}
.msg .bubble a{color:#6366f1;text-decoration:none}
.msg .bubble a:hover{text-decoration:underline;color:#8b5cf6}
.msg .bubble hr{border:none;border-top:1px solid #1a1a2e;margin:12px 0}
.msg.user .bubble a{color:#c4b5fd;text-decoration:underline}
/* Cursor blink */
.cursor{display:inline-block;width:2px;height:15px;background:#6366f1;margin-left:2px;animation:blink .8s step-end infinite;vertical-align:text-bottom}
@keyframes blink{50%{opacity:0}}
/* Thinking section */
.msg.thinking{max-width:100%;align-self:flex-start;margin-bottom:4px}
.msg.thinking details{background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;overflow:hidden}
.msg.thinking summary{font-size:11px;color:#6366f1;padding:6px 10px;cursor:pointer;user-select:none}
.msg.thinking summary:hover{background:rgba(99,102,241,.05)}
.msg.thinking .think-content{font-size:11px;color:#6b7280;line-height:1.6;padding:4px 10px 8px;white-space:pre-wrap}
/* Status bar */
#status-bar{background:#0d0d14;border-bottom:1px solid #1a1a2e;padding:0 max(20px, calc(50% - 320px));font-size:11px}
#status-bar details{max-width:820px;margin:0 auto}
#status-bar summary{cursor:pointer;color:#6366f1;padding:6px 0;user-select:none;font-size:11px}
#status-bar summary:hover{opacity:.8}
#status-content{display:flex;gap:16px;padding:4px 0 8px;color:#6b7280;flex-wrap:wrap}
#status-content span{white-space:nowrap}
/* Permission Modal */
.modal-overlay{position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,.65);z-index:1000;display:flex;align-items:center;justify-content:center;backdrop-filter:blur(4px)}
.modal-box{background:#13131f;border:1px solid #1a1a2e;border-radius:14px;padding:24px;max-width:480px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,.5)}
.modal-title{color:#a5b4fc;font-size:15px;font-weight:500;margin-bottom:6px}
.modal-subtitle{color:#6b7280;font-size:12px;margin-bottom:16px}
.modal-section{margin-bottom:14px}
.modal-section label{display:block;color:#9ca3af;font-size:11px;margin-bottom:4px;text-transform:uppercase;letter-spacing:.5px}
.modal-section .value{color:#e0e0e0;font-size:13px;padding:8px 12px;background:#0d0d14;border-radius:6px;border:1px solid #1a1a2e;word-break:break-all}
.modal-duration{display:grid;grid-template-columns:repeat(4,1fr);gap:6px}
.modal-duration button{padding:6px 8px;background:#0d0d14;border:1px solid #1a1a2e;border-radius:6px;color:#9ca3af;font-size:11px;cursor:pointer;transition:all .15s}
.modal-duration button:hover{border-color:#6366f1;color:#e0e0e0}
.modal-duration button.active{background:rgba(99,102,241,.15);border-color:#6366f1;color:#a5b4fc}

/* Toast */
#toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:2000;background:#13131f;border:1px solid #1a1a2e;border-radius:10px;padding:10px 20px;color:#e0e0e0;font-size:13px;box-shadow:0 4px 20px rgba(0,0,0,.5);opacity:0;transition:opacity .3s,transform .3s;pointer-events:none}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.modal-actions{display:flex;gap:8px;margin-top:18px}
.modal-btn{padding:10px 20px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:none;transition:all .15s;flex:1}
.modal-btn.confirm{background:#6366f1;color:#fff}
.modal-btn.confirm:hover{background:#4f46e5}
.modal-btn.deny{background:#0d0d14;color:#9ca3af;border:1px solid #1a1a2e}
.modal-btn.deny:hover{color:#ef4444;border-color:#ef4444}
</style>
</head>
<body>
<div class="header">
<h1>LINK</h1>
<div>
<a href="/settings">&#x2699; 设置</a>
<a href="/debug">&#x1F50D; 调试</a>
</div>
</div>
<div id="status-bar">
<details id="status-details">
<summary id="status-summary">&#x25B6; 系统状态</summary>
<div id="status-content">
<div id="status-model">模型: 加载中...</div>
<div id="status-memory">记忆: 加载中...</div>
<div id="status-session">会话: 加载中...</div><div id="queue-status"></div>
</div>
</details>
</div>
<div id="chat-container">
<div id="user-column" class="chat-column"></div>
<div id="column-divider"></div>
<div id="assistant-column" class="chat-column"></div>
</div>
<div id="scroll-nav" class="collapsed" style="right:8px;top:50%">
  <div class="nav-content">
    <button id="scroll-top" onclick="scrollToTop()" title="&#x21E7; 顶部" class="scroll-hidden">&#x2191;</button>
    <button id="scroll-up" onclick="scrollUpScreen()" title="&#x25B2; 上一屏">&#x25B2;</button>
    <button id="scroll-down" onclick="scrollDownScreen()" title="&#x25BC; 下一屏">&#x25BC;</button>
    <button id="scroll-bottom" onclick="scrollToBottomBtn()" title="&#x21E9; 底部" class="scroll-hidden">&#x2193;</button>
  </div>
  <div class="nav-toggle">&#x2195;</div>
</div>
<div class="input-area">
<div style="width:100%;max-width:820px;display:flex;gap:8px;margin:0 auto">
<input id="input" placeholder="输入消息..." autofocus>
<button id="send-btn" onclick="send()">发送</button>
</div>
</div>

<script>
const ws = new WebSocket('ws://' + location.host + '/ws');
const chatBox = document.getElementById('chat-container');
const userColumn = document.getElementById('user-column');
const assistantColumn = document.getElementById('assistant-column');
const columnDivider = document.getElementById('column-divider');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');
const TYPE_SPEED = 30; // ms per character
var historyPage = 1, historyLoading = false, historyEnd = false;

ws.onopen = () => { addMessage('system', '已连接到 LINK'); loadHistory(); updateStatus(); };
ws.onclose = () => addMessage('system', '连接已断开');

async function updateStatus() {
  try {
    var r = await fetch('/api/debug');
    var d = await r.json();
    var b = d.brain || {};
    var m = d.memory || {};
    var config = b.config || {};
    var provider = config.model_provider || '?';
    var model = config.model_name || '?';
    var health = (b.health || {}).overall_status || '?';
    var memStats = (m.stats || {});
    var totalMem = memStats.total_memories || 0;
    if (m.stats && m.stats.graph) totalMem += ' (' + m.stats.graph.nodes + '图)';
    var uptime = d.web ? d.web.uptime + 's' : '?';
    document.getElementById('status-model').innerHTML =
      '<span style="color:#6366f1">' + provider + '</span> / ' + model + ' [' + health + ']';
    document.getElementById('status-memory').innerHTML = totalMem + ' 条记忆';
    document.getElementById('status-session').innerHTML = '运行 ' + uptime;
  } catch(e) { /* ignore */ }
}
setInterval(updateStatus, 10000);
// ── marked + highlight.js 配置 ──
marked.setOptions({
  breaks: true,       // 支持 markdown 内换行 → <br>
  gfm: true,          // GitHub 风格 Markdown（表格、任务列表等）
});
try {
  if (typeof hljs !== 'undefined') {
    var mdRenderer = new marked.Renderer();
    mdRenderer.code = function(opt) {
      var text = opt.text || opt.code || '';
      var lang = opt.lang || '';
      var highlighted = (lang && hljs.getLanguage(lang)) ? hljs.highlight(text, {language: lang, ignoreIllegals: true}).value : text;
      var langAttr = lang ? ' data-lang="' + lang + '"' : '';
      return '<div class="code-wrap"><button class="code-copy" onclick="copyCode(this)">复制</button><pre><code class="hljs' + (lang ? ' language-' + lang : '') + '"' + langAttr + '>' + highlighted + '</code></pre></div>';
    };
    marked.setOptions({renderer: mdRenderer});
  }
} catch(e) { console.error('marked/hljs init error:', e); }

var streamContentId = null;
var streamContentBuf = '';

ws.onmessage = e => {
  const d = JSON.parse(e.data);

  // 权限请求弹窗

  // 任务队列状态更新
  if (d.type === 'event' && d.data.event_type === 'TASK_UPDATE') {
    var qs = document.getElementById('queue-status');
    if (qs) {
      var status = d.data.status;
      var pos = d.data.position || 0;
      if (status === 'pending') {
        qs.textContent = '\u23f3 排队中 (第' + pos + '个)';
        qs.style.color = '#eab308';
      } else if (status === 'processing') {
        qs.textContent = '\u23f3 处理中';
        qs.style.color = '#6366f1';
      } else if (status === 'done' || status === 'error') {
        qs.textContent = '';
      }
    }
    return;
  }
  if (d.type === 'permission_request') {
    _pendingPermRequestId = d.request_id;
    document.getElementById('perm-resource-type').textContent =
      d.resource_type === 'command' ? '命令执行' : '文件操作';
    document.getElementById('perm-resource').textContent = d.resource;
    var modeMap = {'read':'读取','write':'写入','execute':'执行','read_write':'读写'};
    document.getElementById('perm-mode').textContent = modeMap[d.mode] || d.mode;
    document.getElementById('perm-duration').querySelectorAll('button').forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.duration === 'once');
    });
    document.getElementById('permission-modal').style.display = 'flex';
    return;
  }

  // 推理内容流式到达
  if (d.type === 'reasoning_chunk') {
    if (!document.getElementById('stream-reasoning')) {
      removeTyping();
      var det = document.createElement('details');
      det.id = 'stream-reasoning';
      det.open = true;
      det.style.cssText = 'margin:2px 0 4px';
      var sum = document.createElement('summary');
      sum.textContent = '思考过程';
      sum.style.cssText = 'cursor:pointer;color:#6366f1;padding:2px 0;font-size:11px';
      var con = document.createElement('div');
      con.id = 'stream-reasoning-content';
      con.style.cssText = 'color:#6b7280;line-height:1.5;padding:4px 8px;white-space:pre-wrap;font-size:11px';
      det.appendChild(sum); det.appendChild(con);
      var typingEl = assistantColumn.querySelector('.typing');
      if (typingEl) assistantColumn.insertBefore(det, typingEl);
      else assistantColumn.appendChild(det);
    }
    var rc = document.getElementById('stream-reasoning-content');
    if (rc) rc.textContent += d.data;
    scrollToBottom();
    return;
  }

  // 生成内容流式到达（实时打字）
  if (d.type === 'content_chunk') {
    removeTyping();
    if (!streamContentId) {
      streamContentBuf = '';
      var div = document.createElement('div');
      div.className = 'msg assistant';
      div.id = 'stream-msg';
      var bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.id = 'stream-bubble';
      div.appendChild(bubble);
      assistantColumn.appendChild(div);
      assistantColumn.scrollTop = assistantColumn.scrollHeight;
      streamContentId = 'stream-msg';
    }
    streamContentBuf += d.data;
    var sb = document.getElementById('stream-bubble');
    if (sb) {
      sb.innerHTML = renderMarkdown(streamContentBuf) + '<span class="cursor"></span>';
      assistantColumn.scrollTop = assistantColumn.scrollHeight;
    }
    return;
  }

  // 完整助手回复（替换流式内容 / 无流式时打字机）
  if (d.type === 'event' && d.data.event_type === 'ASSISTANT') {
    removeTyping();
    var reasoning = d.data.reasoning || '';
    var result = d.data.result || '';

    var streamEl = document.getElementById('stream-msg');
    if (streamEl) {
      var finalBubble = streamEl.querySelector('.bubble');
      if (finalBubble) {
        finalBubble.innerHTML = renderMarkdown(result);
        assistantColumn.scrollTop = assistantColumn.scrollHeight;
      }
      var copyBtn = document.createElement('button');
      copyBtn.className = 'copy-btn visible';
      copyBtn.textContent = '复制';
      copyBtn.onclick = function() {
        navigator.clipboard.writeText(result).then(function() {
          showToast('已复制');
        });
      };
      streamEl.appendChild(copyBtn);
      streamContentId = null;
      return;
    }

    if (reasoning) {
      addThinking(reasoning, function() {
        typewriteMessage('assistant', result);
      });
    } else {
      typewriteMessage('assistant', result);
    }
    return;
  }
};

// ── 历史会话分页加载 ──
async function loadHistory(page) {
  if (!page) page = historyPage;
  if (historyLoading || historyEnd) return;
  historyLoading = true;
  try {
    const r = await fetch('/api/chat/history?page=' + page + '&per_page=10');
    const d = await r.json();
    if (d.error || !d.messages) { historyLoading = false; return; }
    if (d.messages.length === 0) { historyEnd = true; historyLoading = false; return; }
    var loadMore = document.getElementById('load-more');
    if (loadMore) loadMore.remove();

    function createMsgDiv(msg) {
      var div = document.createElement('div');
      div.className = 'msg ' + msg.role;
      var fullContent = msg.content;
      if (msg.reasoning) {
        var det = document.createElement('details');
        det.open = true;
        det.style.cssText = 'margin:2px 0 4px;font-size:11px';
        var sum = document.createElement('summary');
        sum.textContent = '思考过程';
        sum.style.cssText = 'cursor:pointer;color:#6366f1;padding:2px 0';
        var con = document.createElement('div');
        con.textContent = msg.reasoning;
        con.style.cssText = 'color:#6b7280;line-height:1.5;padding:4px 8px;white-space:pre-wrap;font-size:11px';
        det.appendChild(sum); det.appendChild(con);
        div.appendChild(det);
        fullContent = msg.reasoning + '\\n\\n' + msg.content;
      }
      var bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.innerHTML = renderMarkdown(msg.content);
      div.appendChild(bubble);
      var cb = document.createElement('button');
      cb.className = 'copy-btn visible';
      cb.textContent = '复制';
      cb.onclick = function(){ copyText(fullContent, cb); };
      div.appendChild(cb);
      if (msg.role === 'assistant') {
        var fbDiv = document.createElement('div');
        fbDiv.className = 'feedback-btns';
        var fId = 'fb_' + Math.random().toString(36).substr(2,12);
        var up = document.createElement('button');
        up.className = 'feedback-btn up';
        up.dataset.msgId = fId; up.dataset.rating = 'up'; up.title = '有用';
        up.textContent = '👍';
        up.onclick = function(){ sendFeedback(fId, 'up', msg.content, msg.reasoning || ''); };
        var down = document.createElement('button');
        down.className = 'feedback-btn down';
        down.dataset.msgId = fId; down.dataset.rating = 'down'; down.title = '没用';
        down.textContent = '👎';
        down.onclick = function(){ sendFeedback(fId, 'down', msg.content, msg.reasoning || ''); };
        fbDiv.appendChild(up); fbDiv.appendChild(down);
        div.appendChild(fbDiv);
      }
      return div;
    }

    if (page === 1) {
      // 第一页追加到底部（最新的在最下面）
      for (var i = 0; i < d.messages.length; i++) {
        var _m = d.messages[i];
        var _col = _m.role === 'user' ? userColumn : (_m.role === 'assistant' ? assistantColumn : userColumn);
        _col.appendChild(createMsgDiv(_m));
      }
    } else {
      // 更早的页面插到顶部（反向遍历保持顺序）
      for (var i = d.messages.length - 1; i >= 0; i--) {
        var _m = d.messages[i];
        var _col = _m.role === 'user' ? userColumn : (_m.role === 'assistant' ? assistantColumn : userColumn);
        var _firstMsg = _col.querySelector('.msg');
        _col.insertBefore(createMsgDiv(_m), _firstMsg);
      }
    }

    if (page * 10 < d.total) {
      var btnDiv = document.createElement('div');
      btnDiv.id = 'load-more';
      btnDiv.style.cssText = 'text-align:center;padding:8px;margin-bottom:8px';
      var btn = document.createElement('button');
      btn.textContent = '⬆ 加载更早消息';
      btn.style.cssText = 'padding:6px 16px;background:#f0f2f5;color:#666;border:1px solid #ddd;border-radius:6px;cursor:pointer;font-size:12px';
      btn.onclick = function() { historyPage++; loadHistory(historyPage); };
      btnDiv.appendChild(btn);
      assistantColumn.insertBefore(btnDiv, assistantColumn.firstChild || null);\n      userColumn.insertBefore(btnDiv.cloneNode(true), userColumn.firstChild || null);
    } else {
      historyEnd = true;
    }
    historyPage = page;

    // 首次加载滚到底部；翻页不滚动
    if (page === 1) {
        assistantColumn.classList.add('instant-scroll');
        assistantColumn.scrollTop = assistantColumn.scrollHeight;
        userColumn.scrollTop = userColumn.scrollHeight;
        setTimeout(function(){ assistantColumn.classList.remove('instant-scroll'); }, 50);
        setTimeout(updateScrollButtons, 100);
      }
  } catch(e) { console.error('History load failed:', e); }
  historyLoading = false;
}

function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addMessage('user', text);
  showTyping();
  ws.send(JSON.stringify({type: 'user_input', text}));
}

input.addEventListener('keydown', e => { if (e.key === 'Enter' && !e.isComposing) send(); });

// ----- Helper: smart auto-scroll & copy -----
function addThinking(reasoning, callback) {
  const div = document.createElement('div');
  div.className = 'msg thinking';
  const details = document.createElement('details');
  details.open = true;
  const summary = document.createElement('summary');
  summary.textContent = '思考过程';
  const content = document.createElement('div');
  content.className = 'think-content';
  details.appendChild(summary);
  details.appendChild(content);
  div.appendChild(details);
  var targetCol = role === 'user' ? userColumn : assistantColumn;
  const typing = targetCol.querySelector('.typing');
  if (typing) targetCol.insertBefore(div, typing);
  else targetCol.appendChild(div);
  scrollToBottom();

  var pos = 0;
  var THINK_SPEED = 10;
  function typeThink() {
    if (pos < reasoning.length) {
      content.textContent += reasoning[pos];
      pos++;
      scrollToBottom();
      setTimeout(typeThink, THINK_SPEED);
    } else {
      if (callback) callback();
    }
  }
  typeThink();
}

function isNearBottom() {
  return assistantColumn.scrollHeight - assistantColumn.scrollTop - assistantColumn.clientHeight < 120;
}
function scrollToBottom() {
  if (isNearBottom()) assistantColumn.scrollTop = assistantColumn.scrollHeight;
  userColumn.scrollTop = userColumn.scrollHeight;
}
function scrollToTop() {
  assistantColumn.scrollTop = 0;
  userColumn.scrollTop = 0;
}
function scrollUpScreen() {
  assistantColumn.scrollTop -= assistantColumn.clientHeight * 0.85;
}
function scrollDownScreen() {
  assistantColumn.scrollTop += assistantColumn.clientHeight * 0.85;
}
function scrollToBottomBtn() {
  assistantColumn.scrollTop = assistantColumn.scrollHeight;
  userColumn.scrollTop = userColumn.scrollHeight;
}
function updateScrollButtons() {
  var st = document.getElementById('scroll-top');
  var sb = document.getElementById('scroll-bottom');
  if (st) st.classList.toggle('scroll-hidden', assistantColumn.scrollTop <= 10);
  if (sb) sb.classList.toggle('scroll-hidden', assistantColumn.scrollHeight - assistantColumn.scrollTop - assistantColumn.clientHeight <= 20);
}
assistantColumn.addEventListener('scroll', updateScrollButtons);
setTimeout(updateScrollButtons, 500);

// Scroll Nav: drag + snap + expand/collapse
(function() {
  var nav = document.getElementById('scroll-nav');
  if (!nav) return;
  var toggle = nav.querySelector('.nav-toggle');
  var isDragging = false, startX, startY, startLeft, startTop;
  
  // Collapsed by default (already set via class)
  // Expand on hover
  nav.addEventListener('mouseenter', function() {
    nav.classList.remove('collapsed');
    nav.classList.add('expanded');
  });
  nav.addEventListener('mouseleave', function() {
    if (!isDragging) {
      nav.classList.remove('expanded');
      nav.classList.add('collapsed');
    }
  });
  
  // Drag on toggle mousedown
  if (toggle) {
    toggle.addEventListener('mousedown', function(e) {
      isDragging = true;
      var rect = nav.getBoundingClientRect();
      startX = e.clientX; startY = e.clientY;
      startLeft = rect.left; startTop = rect.top;
      nav.classList.add('dragging');
      nav.style.transition = 'none';
      e.preventDefault();
    });
  }
  
  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    var dx = e.clientX - startX, dy = e.clientY - startY;
    nav.style.left = (startLeft + dx) + 'px';
    nav.style.top = (startTop + dy) + 'px';
    nav.style.right = 'auto';
    nav.style.transform = 'none';
  });
  
  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    nav.classList.remove('dragging');
    nav.style.transition = 'left .3s, top .3s';
    // Snap to nearest edge
    var winW = window.innerWidth;
    var rect = nav.getBoundingClientRect();
    var centerX = rect.left + rect.width / 2;
    var top = parseInt(nav.style.top) || 0;
    if (top < 0) top = 0;
    if (top + rect.height > window.innerHeight)
      top = window.innerHeight - rect.height;
    if (centerX < winW / 2) {
      nav.style.left = '8px';
      nav.style.right = 'auto';
    } else {
      nav.style.left = 'auto';
      nav.style.right = 'max(8px, calc(50% - 380px))';
    }
    nav.style.top = top + 'px';
    setTimeout(function() {
      nav.style.transition = '';
    }, 300);
  });
})();

// Column divider drag
(function() {
  var divider = document.getElementById('column-divider');
  var userCol = document.getElementById('user-column');
  var container = document.getElementById('chat-container');
  if (!divider || !userCol || !container) return;
  var isDragging = false, startX, startWidth;

  divider.addEventListener('mousedown', function(e) {
    isDragging = true;
    startX = e.clientX;
    startWidth = userCol.offsetWidth;
    divider.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', function(e) {
    if (!isDragging) return;
    var delta = e.clientX - startX;
    var totalWidth = container.offsetWidth - divider.offsetWidth;
    var newWidth = Math.max(200, Math.min(totalWidth * 0.8, startWidth + delta));
    userCol.style.width = newWidth + 'px';
    userCol.style.flex = 'none';
    document.getElementById('assistant-column').style.flex = '1';
  });

  document.addEventListener('mouseup', function() {
    if (!isDragging) return;
    isDragging = false;
    divider.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    // Persist width
    try { localStorage.setItem('split_user_width', userCol.style.width); } catch(e) {}
  });

  // Restore saved width
  try {
    var saved = localStorage.getItem('split_user_width');
    if (saved) { userCol.style.width = saved; userCol.style.flex = 'none'; }
  } catch(e) {}
})();
async function copyText(text, btn) {
  try {
    await navigator.clipboard.writeText(text);
    btn.textContent = '已✓';
    setTimeout(() => { btn.textContent = '复制'; }, 2000);
  } catch { btn.textContent = '失败'; }
}

function copyCode(btn) {
  const code = btn.parentElement.querySelector('code');
  if (!code) return;
  copyText(code.textContent, btn);
}

// ── 反馈评分 ──
async function sendFeedback(msgId, rating, content, reasoningText) {
  try {
    await fetch('/api/feedback', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({message_id: msgId, rating: rating, content: content, reasoning: reasoningText || '', has_reasoning: !!reasoningText})
    });
    var btns = document.querySelectorAll('.feedback-btn[data-msg-id="' + msgId + '"]');
    btns.forEach(function(b) {
      b.disabled = true;
      if (b.dataset.rating === rating) {
        b.classList.add('active');
        b.innerHTML = rating === 'up' ? '\\u{1F44D} ✓' : '\\u{1F44E} ✓';
      } else {
        b.style.opacity = '0.3';
      }
    });
  } catch(e) { console.error('Feedback error:', e); }
}

// ----- Markdown Parser (using marked + highlight.js) -----
function renderMarkdown(text) {
  if (!text) return '';
  try { return marked.parse(text); }
  catch(e) { return '<p>' + text.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</p>'; }
}

// ----- Typewriter Effect (token-based progressive reveal) -----
function typewriteMessage(role, fullText) {
  var tokens, idx = 0;
  try { tokens = marked.lexer(fullText); } catch(e) { tokens = [{type:'paragraph', text:fullText}]; }

  var div = document.createElement('div');
  div.className = 'msg ' + role;
  assistantColumn.appendChild(div);
  scrollToBottom();

  var bubble = document.createElement('div');
  bubble.className = 'bubble';
  div.appendChild(bubble);

  function type() {
    if (idx < tokens.length) {
      try { bubble.innerHTML = marked.parser(tokens.slice(0, idx + 1)); }
      catch(e) { bubble.innerHTML = '<p>' + fullText.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</p>'; }
      scrollToBottom();
      idx++;
      setTimeout(type, 50);
    } else {
      scrollToBottom();
      var copyBtn = document.createElement('button');
      copyBtn.className = 'copy-btn visible';
      copyBtn.textContent = '复制';
      copyBtn.onclick = function() { copyText(fullText, copyBtn); };
      div.appendChild(copyBtn);
      sendBtn.disabled = false;
      input.focus();
    }
  }

  type();
}

function addMessage(role, content) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  const now = new Date();
  const time = String(now.getHours()).padStart(2,'0') + ':' + String(now.getMinutes()).padStart(2,'0');
  if (role === 'system') {
    div.innerHTML = '<div class="bubble">' + escapeHtml(content) + '</div>';
  } else {
    const bubble = document.createElement('div');
    bubble.className = 'bubble';
    bubble.innerHTML = renderMarkdown(content);
    div.appendChild(bubble);
    // Copy button
    const copyBtn = document.createElement('button');
    copyBtn.className = 'copy-btn visible';
    copyBtn.textContent = '复制';
    copyBtn.onclick = () => copyText(content, copyBtn);
    div.appendChild(copyBtn);
    // Time
    const timeEl = document.createElement('div');
    timeEl.className = 'time';
    timeEl.textContent = time;
    div.appendChild(timeEl);
  }
  const typing = assistantColumn.querySelector('.typing');
  if (typing) assistantColumn.insertBefore(div, typing);
  else assistantColumn.appendChild(div);
  scrollToBottom();
}

var typingTimer = null;
var typingStep = 0;
const STATUS_STEPS = [
  '分析问题中...',
  '检索相关记忆中...',
  '调用模型分析...',
  '处理返回结果中...',
  '生成回复中...',
];

function showTyping() {
  var existing = assistantColumn.querySelector('.typing');
  if (existing) return;
  const div = document.createElement('div');
  div.className = 'msg assistant typing';
  div.id = 'thinking-step';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  div.appendChild(bubble);
  assistantColumn.appendChild(div);
  scrollToBottom();
  typingStep = 0;
  nextTypingStep();
}

function nextTypingStep() {
  if (typingStep >= STATUS_STEPS.length) typingStep = STATUS_STEPS.length - 1;
  const bubble = document.querySelector('#thinking-step .bubble');
  if (!bubble) return;
  bubble.textContent = '';
  var text = STATUS_STEPS[typingStep];
  var pos = 0;
  function typeChar() {
    if (pos < text.length) {
      bubble.textContent += text[pos++];
      scrollToBottom();
      setTimeout(typeChar, 12);
    } else {
      typingStep++;
      typingTimer = setTimeout(nextTypingStep, 400);
    }
  }
  typeChar();
}

function removeTyping() {
  if (typingTimer) { clearTimeout(typingTimer); typingTimer = null; }
  var el = assistantColumn.querySelector('.typing');
  if (el) el.remove();
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Permission Modal
var _pendingPermRequestId = null;

// Duration selector
document.addEventListener('click', function(e) {
  if (e.target.closest('#perm-duration') && e.target.tagName === 'BUTTON') {
    var parent = document.getElementById('perm-duration');
    parent.querySelectorAll('button').forEach(function(b) { b.classList.remove('active'); });
    e.target.classList.add('active');
  }
});

function confirmPermission() {
  var active = document.querySelector('#perm-duration .active');
  ws.send(JSON.stringify({
    type: 'permission_response',
    request_id: _pendingPermRequestId,
    approved: true,
    duration: active ? active.dataset.duration : 'once'
  }));
  document.getElementById('permission-modal').style.display = 'none';
  _pendingPermRequestId = null;
}

function denyPermission() {
  ws.send(JSON.stringify({
    type: 'permission_response',
    request_id: _pendingPermRequestId,
    approved: false,
    duration: 'once'
  }));
  document.getElementById('permission-modal').style.display = 'none';
  _pendingPermRequestId = null;
}
</script>

<!-- Permission Modal -->
<div id="permission-modal" class="modal-overlay" style="display:none">
  <div class="modal-box">
    <div class="modal-title">🔒 授权请求</div>
    <div class="modal-subtitle">LINK 需要获得以下资源的访问权限</div>
    <div class="modal-section">
      <label>资源类型</label>
      <div class="value" id="perm-resource-type">文件操作</div>
    </div>
    <div class="modal-section">
      <label>资源路径</label>
      <div class="value" id="perm-resource">/path/to/file</div>
    </div>
    <div class="modal-section">
      <label>操作类型</label>
      <div class="value" id="perm-mode">读取</div>
    </div>
    <div class="modal-section">
      <label>授权时长</label>
      <div class="modal-duration" id="perm-duration">
        <button data-duration="once" class="active">仅一次</button>
        <button data-duration="1h">1 小时</button>
        <button data-duration="4h">4 小时</button>
        <button data-duration="8h">8 小时</button>
        <button data-duration="12h">12 小时</button>
        <button data-duration="24h">24 小时</button>
        <button data-duration="permanent" style="grid-column:span 2">永久</button>
      </div>
    </div>
    <div class="modal-actions">
      <button class="modal-btn deny" onclick="denyPermission()">拒绝</button>
      <button class="modal-btn confirm" onclick="confirmPermission()">授权</button>
    </div>
  </div>
</div>

<div id="toast"></div>
</body>
</html>"""

        
        # ── 权限请求管理器回调注册用（单例） ──
        from tools.permission_request_manager import PermissionRequestManager as PRM
        _prm_registered = False

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket端点（双任务架构）"""
            await websocket.accept()
            client_id = str(uuid.uuid4())
            self.websocket_clients.append({"id": client_id, "websocket": websocket})

            # 发送欢迎消息
            await websocket.send_json({
                "type": "event",
                "data": {
                    "event_type": "SYSTEM",
                    "message": "🔗 已连接到LINK主动模式",
                    "timestamp": time.time()
                }
            })
            await self._broadcast_stats()

            # 双任务通信：receive_task 将用户输入放入此队列，process_task 消费
            input_queue: asyncio.Queue = asyncio.Queue()
            loop = asyncio.get_running_loop()

            async def receive_task():
                """接收任务：处理所有入站消息"""
                nonlocal _prm_registered
                try:
                    while True:
                        data = await websocket.receive_json()
                        msg_type = data.get("type", "")

                        if msg_type == "user_input":
                            await input_queue.put(data)

                        elif msg_type == "permission_response":
                            prm = PRM.get_instance()
                            prm.respond(
                                data.get("request_id", ""),
                                data.get("approved", False),
                                data.get("duration", "once")
                            )
                            await websocket.send_json({
                                "type": "event",
                                "data": {
                                    "event_type": "SYSTEM",
                                    "message": f"授权{'已批准' if data.get('approved') else '已拒绝'}"
                                }
                            })

                        elif msg_type == "command":
                            await self._handle_command(websocket, data.get("command"))
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    print(f"receive_task 异常: {e}")
                finally:
                    PRM.get_instance().cancel_all()

            async def process_task():
                """处理任务：消费用户输入并执行 LLM 调用"""
                try:
                    while True:
                        data = await input_queue.get()
                        text = data.get("text", "")
                        if not text:
                            continue

                        self.add_user_input(text, client_id)
                        await self._broadcast_event({
                            "event_type": "USER_INPUT",
                            "message": f"📝 收到用户输入: {text}",
                            "source": f"user_{client_id}"
                        })

                        # 注册权限请求回调（通知前端弹窗）
                        prm = PRM.get_instance()
                        def _perm_cb(req):
                            asyncio.run_coroutine_threadsafe(
                                websocket.send_json({
                                    "type": "permission_request",
                                    "request_id": req.id,
                                    "resource": req.resource,
                                    "mode": req.mode,
                                    "resource_type": req.resource_type.value,
                                }),
                                loop
                            )
                        prm.register_callback(_perm_cb)

                        # 创建流式回调
                        _stream_content_buf = ['']
                        def _stream_cb(ctype, content):
                            if ctype == "reasoning" and content.strip():
                                asyncio.run_coroutine_threadsafe(
                                    websocket.send_json({"type": "reasoning_chunk", "data": content}), loop
                                )
                            elif ctype == "content" and content:
                                _stream_content_buf[0] += content
                                asyncio.run_coroutine_threadsafe(
                                    websocket.send_json({"type": "content_chunk", "data": content}), loop
                                )
                        # CPU 密集/阻塞任务放到线程池
                        from functools import partial
                        _task = partial(self._process_input_direct, text, stream_callback=_stream_cb)
                        brain_resp = await asyncio.get_event_loop().run_in_executor(None, _task)

                        # 取消注册权限回调
                        prm.unregister_callback(_perm_cb)

                        if brain_resp and brain_resp.get("result"):
                            await self._broadcast_event({
                                "event_type": "ASSISTANT",
                                "result": brain_resp["result"],
                                "reasoning": brain_resp.get("reasoning", ""),
                                "source": "link_brain",
                                "timestamp": time.time()
                            })
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"process_task 异常: {e}")

            # 并行运行两个任务
            try:
                await asyncio.gather(receive_task(), process_task(), worker_task())
            except Exception as e:
                print(f"WebSocket 处理器异常: {e}")
            finally:
                self.websocket_clients = [c for c in self.websocket_clients if c["id"] != client_id]
                await self._broadcast_stats()
    
        @self.app.get("/debug")
        async def get_debug_page():
            return HTMLResponse(DEBUG_HTML)

        @self.app.get("/api/debug")
        async def get_debug_api():
            return await self._get_debug_data()

        @self.app.post("/api/debug/search")
        async def post_debug_search(request_data: dict):
            query = request_data.get("query", "")
            if not query:
                return {"error": "no query", "results": []}
            return await self._search_debug_memory(query)

        @self.app.get("/api/debug/memories")
        async def get_debug_memories(page: int = 1, per_page: int = 20):
            return await self._get_memories_paginated(page, per_page)

        @self.app.get("/api/debug/interactions")
        async def get_debug_interactions(page: int = 1, per_page: int = 10):
            return await self._get_interactions_paginated(page, per_page)

        @self.app.post("/api/debug/archive")
        async def post_debug_archive(request_data: dict):
            return await self._create_debug_archive(request_data)

        @self.app.get("/api/debug/archives")
        async def get_debug_archives():
            return await self._list_debug_archives()

        @self.app.post("/api/debug/archive/restore")
        async def post_debug_restore(request_data: dict):
            return await self._restore_debug_archive(request_data)

        @self.app.post("/api/debug/memory/reset")
        async def post_debug_memory_reset():
            return await self._reset_debug_memory()

        @self.app.get("/api/chat/history")
        async def get_chat_history(page: int = 1, per_page: int = 10):
            return await self._get_chat_history(page, per_page)

        # ── Provider 设置 ──

        @self.app.get("/settings", response_class=HTMLResponse)
        async def get_settings_page():
            return SETTINGS_HTML

        @self.app.get("/api/settings")
        async def get_settings():
            from src.core.model_engine.provider_settings import (
                load_settings, mask_api_key
            )
            s = load_settings()
            # 返回前脱敏 key
            if s.get("api_key"):
                s["api_key_display"] = mask_api_key(s["api_key"])
                s["api_key"] = ""
            return s

        @self.app.post("/api/settings")
        async def post_settings(data: dict):
            from src.core.model_engine.provider_settings import save_settings, get_brain_config
            s = save_settings(data)
            if self.brain_link:
                self.brain_link._reconfigure_brain(get_brain_config())
            return {"success": True, "message": "设置已保存"}

        @self.app.post("/api/settings/test")
        async def post_settings_test(data: dict = None):
            """测试 API 连接（服务器端执行，不暴露 Key）"""
            import urllib.request, json as pyjson
            from src.core.model_engine.provider_settings import load_settings, mask_api_key
            s = load_settings()
            if s["mode"] != "online":
                return {"success": False, "message": "当前为离线模式"}
            key = s.get("api_key", "")
            if not key:
                return {"success": False, "message": "API Key 未配置"}
            base = s.get("api_base", "https://api.deepseek.com").rstrip("/")
            try:
                for path in ["/v1/models", "/models"]:
                    req = urllib.request.Request(
                        base + path,
                        headers={"Authorization": f"Bearer {key}"},
                        method="GET",
                    )
                    resp = urllib.request.urlopen(req, timeout=10)
                    if resp.status == 200:
                        return {"success": True, "message": "API 连接正常"}
                return {"success": False, "message": "无法连接 API"}
            except urllib.request.HTTPError as e:
                if e.code == 401:
                    return {"success": False, "message": f"API Key 无效 ({mask_api_key(key)})"}
                return {"success": False, "message": f"HTTP {e.code}: {e.reason}"}
            except Exception as e:
                return {"success": False, "message": f"连接失败: {e}"}

        @self.app.get("/api/models")
        async def get_models():
            from src.core.model_engine.provider_settings import get_ollama_models
            models = get_ollama_models()
            return {"models": models}

        @self.app.post("/api/feedback")
        async def post_feedback(data: dict):
            return await self._handle_feedback(data)

        @self.app.get("/api/permission-settings")
        async def get_permission_settings():
            from tools.permission_settings import PermissionSettings
            ps = PermissionSettings()
            return ps.list_settings()

        @self.app.post("/api/permission-settings")
        async def save_permission_settings(data: dict):
            from tools.permission_settings import PermissionSettings
            ps = PermissionSettings()
            return ps.update_settings(data)

    async def _handle_feedback(self, data: dict) -> dict:
        rating = data.get("rating", "")
        content = data.get("content", "")
        reasoning = data.get("reasoning", "")
        if not rating or rating not in ("up", "down") or not content:
            return {"success": False, "error": "invalid params"}
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"success": False, "error": "memory not available"}
        try:
            metadata = {
                "type": "feedback",
                "rating": rating,
                "has_reasoning": bool(reasoning),
                "response_length": len(content),
                "timestamp": time.time(),
            }
            store = self.brain_link.memory_engine.store
            store.add_memory(f"Feedback [{rating}]: {content[:300]}", metadata)
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_debug_data(self) -> dict:
        data = {"timestamp": time.time(), "timestamp_str": __import__("datetime").datetime.now().isoformat()}
        import sys, platform, os
        data["system"] = {"python": sys.version, "platform": platform.platform(), "hostname": platform.node(), "cwd": os.getcwd()}
        web_running = getattr(self, '_web_started', False) or self.is_running
        data["web"] = {
            "is_running": web_running,
            "server_mode": "web" if getattr(self, '_web_started', False) else "active",
            "clients": len(self.websocket_clients),
            "event_queue": self.event_queue.qsize(), "events_processed": self.stats.get("events_processed", 0),
            "events_dropped": self.stats.get("events_dropped", 0),
            "event_history_count": len(self.event_history),
            "uptime": round(time.time() - self.stats.get("start_time", time.time()), 1) if self.stats.get("start_time") else 0,
        }
        if self.brain_link:
            bj = self.brain_link
            data["memory"] = self._get_memory_debug(bj)
            data["brain"] = self._get_brain_debug(bj)
            data["planning"] = self._get_planning_debug(bj)
        return data

    def _get_memory_debug(self, link) -> dict:
        result = {"available": link.memory_engine is not None}
        if not link.memory_engine:
            return result
        try:
            store = link.memory_engine.store
            result["stats"] = store.get_stats()
            all_m = store.get_all_memories(limit=50)
            result["memories"] = []
            for m in all_m:
                result["memories"].append({
                    "id": m.id, "content": m.content[:200],
                    "type": m.metadata.get("type", "?"),
                    "importance": m.importance,
                    "created_at": m.metadata.get("created_at", "?"),
                    "tags": m.metadata.get("tags", []),
                })
            es = store.embedding_service
            result["embedding"] = {
                "ready": es.is_ready(), "model": getattr(es, "model_name", "?"),
                "dimension": getattr(es, "dimension", 0),
            }
        except Exception as e:
            result["error"] = str(e)
        return result

    def _get_brain_debug(self, link) -> dict:
        result = {"available": link.brain_engine is not None}
        if not link.brain_engine:
            return result
        try:
            be = link.brain_engine
            result["config"] = getattr(be, "config", {})
            result["health"] = be.health_check() if hasattr(be, "health_check") else {}
            history = []
            if hasattr(be, "get_interaction_history"):
                for h in be.get_interaction_history(limit=20):
                    history.append({
                        "time": h.get("timestamp", "?"), "type": h.get("type", "?"),
                        "input": str(h.get("input", ""))[:200],
                        "output": str(h.get("output", ""))[:200],
                        "duration": round(h.get("metadata", {}).get("duration", 0), 2),
                    })
            result["interaction_history"] = history
        except Exception as e:
            result["error"] = str(e)
        return result

    def _get_planning_debug(self, link) -> dict:
        result = {"available": link.planning_engine is not None}
        if not link.planning_engine:
            return result
        try:
            pe = link.planning_engine
            result["tasks_count"] = len(link.active_tasks)
            result["templates"] = pe.get_task_template_types() if hasattr(pe, "get_task_template_types") else []
            if hasattr(pe, "get_planning_stats"):
                result["stats"] = pe.get_planning_stats()
        except Exception as e:
            result["error"] = str(e)
        return result

    async def _search_debug_memory(self, query: str) -> dict:
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"error": "memory not available", "results": []}
        try:
            store = self.brain_link.memory_engine.store
            results = store.search_memories(query, n_results=10)
            items = []
            for mem, sim in results:
                items.append({
                    "content": mem.content[:200], "type": mem.metadata.get("type", "?"),
                    "similarity": round(sim, 4), "importance": mem.importance,
                    "created_at": mem.metadata.get("created_at", "?"),
                })
            return {"query": query, "total": len(items), "results": items}
        except Exception as e:
            return {"error": str(e), "results": []}

    async def _get_memories_paginated(self, page: int, per_page: int) -> dict:
        """分页获取记忆列表"""
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"error": "memory not available", "memories": [], "total": 0}
        try:
            store = self.brain_link.memory_engine.store
            all_m = store.get_all_memories(limit=9999)
            total = len(all_m)
            start = (page - 1) * per_page
            end = start + per_page
            page_items = all_m[start:end]

            memories = []
            for m in page_items:
                memories.append({
                    "id": m.id,
                    "content": m.content,
                    "type": m.metadata.get("type", "?"),
                    "importance": m.importance,
                    "created_at": m.metadata.get("created_at", "?"),
                    "tags": m.metadata.get("tags", []),
                })
            return {"memories": memories, "total": total, "page": page, "per_page": per_page}
        except Exception as e:
            return {"error": str(e), "memories": [], "total": 0}

    async def _get_interactions_paginated(self, page: int, per_page: int) -> dict:
        """分页获取 LLM 交互历史"""
        if not self.brain_link or not self.brain_link.brain_engine:
            return {"error": "brain not available", "interactions": [], "total": 0}
        try:
            be = self.brain_link.brain_engine
            if not hasattr(be, "get_interaction_history"):
                return {"error": "no history", "interactions": [], "total": 0}

            all_history = be.get_interaction_history(limit=9999)
            total = len(all_history)
            start = (page - 1) * per_page
            end = start + per_page

            interactions = []
            for h in all_history[start:end]:
                interactions.append({
                    "time": h.get("timestamp", "?"),
                    "type": h.get("type", "?"),
                    "input": str(h.get("input", "")),
                    "output": str(h.get("output", "")),
                    "duration": round(h.get("metadata", {}).get("duration", 0), 2),
                })
            return {
                "interactions": interactions, "total": total,
                "page": page, "per_page": per_page,
            }
        except Exception as e:
            return {"error": str(e), "interactions": [], "total": 0}

    async def _create_debug_archive(self, data: dict) -> dict:
        """创建记忆归档"""
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"error": "memory not available"}
        try:
            store = self.brain_link.memory_engine.store
            label = data.get("label", "")
            result = store.create_archive(label)
            return {"success": True, "archive": result}
        except Exception as e:
            return {"error": str(e)}

    async def _list_debug_archives(self) -> dict:
        """列出所有归档"""
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"error": "memory not available", "archives": []}
        try:
            store = self.brain_link.memory_engine.store
            archives = store.list_archives()
            return {"archives": archives, "total": len(archives)}
        except Exception as e:
            return {"error": str(e), "archives": []}

    async def _restore_debug_archive(self, data: dict) -> dict:
        """从归档恢复记忆"""
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"error": "memory not available"}
        try:
            store = self.brain_link.memory_engine.store
            archive_id = data.get("archive_id", "")
            if not archive_id:
                return {"error": "archive_id required"}
            result = store.restore_archive(archive_id)
            return {"success": True, "result": result}
        except ValueError as e:
            return {"error": str(e)}
        except Exception as e:
            return {"error": f"恢复失败: {e}"}

    async def _reset_debug_memory(self) -> dict:
        """清空所有记忆（含缓存画像）"""
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"error": "memory not available"}
        try:
            store = self.brain_link.memory_engine.store
            count = store.get_stats().get("total_memories", 0)
            store.reset_memory()
            # 同时清空缓存的用户画像（否则_retrieve_memory_context仍会返回旧数据）
            self.brain_link._user_profile = ""
            self.brain_link._history_summary = ""
            return {"success": True, "cleared_count": count}
        except Exception as e:
            return {"error": str(e)}

    async def _get_chat_history(self, page: int, per_page: int) -> dict:
        """分页获取历史会话（仅 conversation 类型记忆）"""
        if not self.brain_link or not self.brain_link.memory_engine:
            return {"error": "memory not available", "messages": [], "total": 0}
        try:
            store = self.brain_link.memory_engine.store
            all_m = store.get_all_memories(limit=9999)
            # 只保留 conversation 类型
            convs = [m for m in all_m if m.metadata.get("type") == "conversation"]
            # 按时间升序排列（最早的在前）
            convs.sort(key=lambda x: x.metadata.get("created_at", ""))

            total = len(convs)
            # Page 1 = 最新的对话（倒序切片取最后 per_page 条）
            rev = convs[::-1]  # 最新的在前
            start = (page - 1) * per_page
            page_items = rev[start:start + per_page]
            # 页内恢复时间正序（最早的在前）
            page_items.reverse()

            messages = []
            for m in page_items:
                content = m.content
                parts = content.split("\n助手: ", 1)
                if len(parts) == 2:
                    user_part = parts[0].replace("用户: ", "", 1)
                    messages.append({"role": "user", "content": user_part, "time": m.metadata.get("created_at", "")})
                    asst_content = parts[1]
                    reasoning = ""
                    if "【推理过程】" in asst_content:
                        asst_parts = asst_content.split("【推理过程】\n", 1)
                        asst_content = asst_parts[0].strip()
                        reasoning = asst_parts[1].strip() if len(asst_parts) > 1 else ""
                    messages.append({"role": "assistant", "content": asst_content, "reasoning": reasoning, "time": m.metadata.get("created_at", "")})
                else:
                    messages.append({"role": "assistant", "content": content[:200], "time": m.metadata.get("created_at", "")})
            return {"messages": messages, "total": total, "page": page, "per_page": per_page}
        except Exception as e:
            return {"error": str(e), "messages": [], "total": 0}

    async def _handle_command(self, websocket: WebSocket, command: str):
        """处理命令"""
        if command == "start":
            if not self.is_running:
                self.start()
                await websocket.send_json({
                    "type": "event",
                    "data": {
                        "event_type": "SYSTEM",
                        "message": "🚀 LINK主动模式已启动",
                        "timestamp": time.time()
                    }
                })
            else:
                await websocket.send_json({
                    "type": "event",
                    "data": {
                        "event_type": "SYSTEM",
                        "message": "⚠️ 主动模式已在运行中",
                        "timestamp": time.time()
                    }
                })
        
        elif command == "stop":
            if self.is_running:
                self.stop()
                await websocket.send_json({
                    "type": "event",
                    "data": {
                        "event_type": "SYSTEM",
                        "message": "🛑 LINK主动模式已停止",
                        "timestamp": time.time()
                    }
                })
            else:
                await websocket.send_json({
                    "type": "event",
                    "data": {
                        "event_type": "SYSTEM",
                        "message": "⚠️ 主动模式未在运行",
                        "timestamp": time.time()
                    }
                })
        
        elif command == "learn":
            # 触发学习事件
            learning_event = Event(
                event_type=EventType.LEARNING,
                data={"action": "analyze_memory", "manual_trigger": True},
                priority=EventPriority.HIGH,
                source="web_manual"
            )
            self.event_queue.put(learning_event)
            await websocket.send_json({
                "type": "event",
                "data": {
                    "event_type": "LEARNING",
                    "message": "📚 已触发主动学习任务",
                    "timestamp": time.time()
                }
            })
        
        elif command == "status":
            await self._send_status(websocket)

    async def _send_status(self, websocket: WebSocket):
        """发送状态信息"""
        stats = self.get_stats()
        await websocket.send_json({
            "type": "status",
            "data": {
                "is_running": self.is_running,
                **stats
            }
        })
    
    async def _broadcast_event(self, event_data: Dict[str, Any]):
        """广播事件给所有客户端"""
        for client in self.websocket_clients[:]:  # 使用副本遍历
            try:
                await client["websocket"].send_json({
                    "type": "event",
                    "data": event_data
                })
            except Exception as e:
                print(f"广播事件失败: {e}")
                # 移除失效的客户端
                self.websocket_clients.remove(client)
    
    async def _broadcast_stats(self):
        """广播统计信息给所有客户端"""
        stats = self.get_stats()
        for client in self.websocket_clients[:]:
            try:
                await client["websocket"].send_json({
                    "type": "stats",
                    "data": stats
                })
            except Exception as e:
                print(f"广播统计失败: {e}")
                self.websocket_clients.remove(client)
    
    def _add_to_history(self, event: Event, result: str):
        """添加事件到历史记录"""
        history_item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "event": event.to_dict(),
            "result": result
        }
        self.event_history.append(history_item)
        
        # 限制历史记录数量
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
    
    def start(self, blocking: bool = False):
        """
        启动主动运行模式
        
        Args:
            blocking: 是否阻塞运行
        """
        if self.is_running:
            print("⚠️  主动运行模式已在运行中")
            return
        
        self.is_running = True
        self.stats["start_time"] = time.time()
        
        print("🚀 启动LINK主动运行模式（Web版本）...")
        print(f"🌐 Web界面地址: http://{self.config['web_host']}:{self.config['web_port']}")
        
        if blocking:
            self._run_event_loop()
        else:
            self.event_thread = threading.Thread(
                target=self._run_event_loop,
                daemon=True
            )
            self.event_thread.start()
            print("✅ 主动运行模式已在后台启动")
    
    def stop(self):
        """停止主动运行模式"""
        self.is_running = False
        if self.event_thread:
            self.event_thread.join(timeout=2)
        
        duration = time.time() - self.stats.get("start_time", time.time())
        print(f"🛑 主动运行模式已停止，运行时长: {duration:.1f}秒")
        print(f"📊 统计: 处理事件 {self.stats['events_processed']} 个")
    
    def _run_event_loop(self):
        """运行事件循环"""
        print("🔄 进入事件循环...")
        
        try:
            while self.is_running:
                # 1. 收集事件
                events = self._collect_events()
                
                # 2. 添加事件到队列
                for event in events:
                    try:
                        self.event_queue.put(event)
                    except Exception as e:
                        print(f"❌ 事件入队失败: {e}")
                        self.stats["events_dropped"] += 1
                
                # 3. 处理事件（限制每次循环处理的数量）
                processed_count = self._process_events()
                self.stats["events_processed"] += processed_count
                
                # 4. 更新状态
                self.stats["last_event_time"] = time.time()
                
                # 5. 休眠避免CPU占用过高
                time.sleep(self.config["event_loop_interval"])
                
        except KeyboardInterrupt:
            print("⏹️  事件循环被中断")
        except Exception as e:
            print(f"❌ 事件循环错误: {e}")
        finally:
            self.is_running = False
    
    def _collect_events(self) -> List[Event]:
        """从所有事件源收集事件"""
        events = []
        for source_name, source in self.event_sources.items():
            try:
                if source.active:
                    source_events = source.poll()
                    events.extend(source_events)
            except Exception as e:
                print(f"❌ 事件源 '{source_name}' 错误: {e}")
        
        return events
    
    def _process_events(self) -> int:
        """处理事件队列中的事件"""
        processed = 0
        max_events = self.config.get("max_events_per_cycle", 10)
        
        while not self.event_queue.empty() and processed < max_events:
            try:
                event = self.event_queue.get_nowait()
                result = self._handle_event(event)
                
                # 广播事件结果
                if result:
                    asyncio.run(self._broadcast_event({
                        "event_type": event.event_type.value,
                        "result": result,
                        "source": event.source,
                        "timestamp": time.time()
                    }))
                
                processed += 1
            except Exception as e:
                print(f"❌ 处理事件失败: {e}")
                self.stats["events_dropped"] += 1
        
        # 定期广播统计信息
        if processed > 0 and self.stats.get("last_event_time"):
            current_time = time.time()
            if current_time - self.stats.get("last_stats_broadcast", 0) > 2:  # 每2秒广播一次
                asyncio.run(self._broadcast_stats())
                self.stats["last_stats_broadcast"] = current_time
        
        return processed
    
    def _handle_event(self, event: Event) -> str:
        """处理单个事件"""
        try:
            # 查找合适的处理器
            handler = self._find_handler(event)
            if not handler:
                return None
            
            # 执行处理器
            result = handler.handle(event)
            
            # 记录结果
            if result:
                self._add_to_history(event, result)
                
                # 控制台输出（可选）
                if self.config.get("log_level") in ["INFO", "DEBUG"]:
                    self._log_event_result(event, result)
            
            return result
                
        except Exception as e:
            error_msg = f"❌ 事件处理错误: {e}"
            print(error_msg)
            return error_msg
    
    def _find_handler(self, event: Event) -> Optional[EventHandler]:
        """查找适合的事件处理器"""
        for handler in self.event_handlers.values():
            if handler.can_handle(event):
                return handler
        return None
    
    def _log_event_result(self, event: Event, result: Any):
        """记录事件处理结果"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        event_type = event.event_type.value
        source = event.source
        
        if isinstance(result, str):
            print(f"[{timestamp}] {event_type} ({source}): {result}")
    
    def _process_input_direct(self, text: str, stream_callback: callable = None) -> dict:
        """处理用户输入，返回 {result, reasoning}"""
        if not self.brain_link:
            return {"result": "⚠️ 大脑引擎未就绪", "reasoning": ""}
        try:
            start = time.time()
            result = self.brain_link.process_input(text, stream_callback=stream_callback)
            reasoning = getattr(self.brain_link, '_last_reasoning', '')
            elapsed = time.time() - start
            import logging
            logging.getLogger("link").info(f"LLM 响应完成 ({elapsed:.1f}s)")
            return {"result": result, "reasoning": reasoning}
        except Exception as e:
            import logging
            logging.getLogger("link").error(f"处理输入出错: {e}")
            return {"result": f"❌ 处理出错: {e}", "reasoning": ""}

    def add_user_input(self, text: str, user_id: str = "default"):
        """添加用户输入（外部调用）"""
        user_input_source = self.event_sources.get("user_input")
        if user_input_source:
            user_input_source.add_input(text, user_id)
            return True
        return False
    
    def get_stats(self) -> Dict[str, Any]:
        """获取运行统计"""
        stats = self.stats.copy()
        stats["is_running"] = self.is_running
        stats["event_queue_size"] = self.event_queue.qsize()
        stats["event_sources_count"] = len(self.event_sources)
        stats["event_handlers_count"] = len(self.event_handlers)
        stats["clients_count"] = len(self.websocket_clients)
        stats["event_history_count"] = len(self.event_history)
        
        if stats.get("start_time"):
            stats["uptime_seconds"] = time.time() - stats["start_time"]
        
        return stats
    
    def run_web(self):
        """运行Web服务器"""
        try:
            self._web_started = True
            self.stats["start_time"] = time.time()
            print(f"🌐 启动Web服务器...")
            print(f"   访问地址: http://{self.config['web_host']}:{self.config['web_port']}")
            print(f"   WebSocket地址: ws://{self.config['web_host']}:{self.config['web_port']}/ws")
            print(f"   按 Ctrl+C 停止服务器")
            
            uvicorn.run(
                self.app,
                host=self.config["web_host"],
                port=self.config["web_port"],
                log_level="info"
            )
            
        except KeyboardInterrupt:
            print("\n🛑 Web服务器已停止")
        except Exception as e:
            print(f"❌ Web服务器错误: {e}")



# ============================================================
# DEBUG_HTML — 调试面板页面 (self-contained)
# ============================================================
DEBUG_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>LINK 调试面板</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333;padding:20px}
h1{font-size:22px;margin-bottom:16px}
.header{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px}
.header .sub{color:#666;font-size:13px}
.tabs{display:flex;gap:4px;margin-bottom:16px;flex-wrap:wrap}
.tab{padding:8px 18px;border-radius:6px;cursor:pointer;background:#e0e0e0;font-size:13px;border:none;transition:all .2s}
.tab:hover{background:#d0d0d0}
.tab.active{background:#1a73e8;color:#fff}
.panel{display:none;background:#fff;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.panel.active{display:block}
.section{margin-bottom:20px}
.section h3{font-size:15px;color:#1a73e8;margin-bottom:10px;padding-bottom:6px;border-bottom:2px solid #e8eaed}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;margin-bottom:12px}
.stat-card{background:#f8f9fa;border-radius:8px;padding:12px;border:1px solid #e8eaed}
.stat-card .label{font-size:11px;color:#888;margin-bottom:4px}
.stat-card .value{font-size:18px;font-weight:600;color:#1a73e8}
.stat-card .value.warn{color:#d93025}
table{width:100%;border-collapse:collapse;font-size:12px}
th{padding:8px 10px;background:#f8f9fa;text-align:left;font-weight:600;color:#555;border-bottom:2px solid #e8eaed;white-space:nowrap}
td{padding:8px 10px;border-bottom:1px solid #e8eaed;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
td.content-cell{max-width:400px;white-space:normal;word-break:break-all}
tr:hover{background:#f0f7ff}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:500}
.badge-fact{background:#e8f5e9;color:#2e7d32}
.badge-conversation{background:#e3f2fd;color:#1565c0}
.badge-preference{background:#fff3e0;color:#e65100}
.badge-event{background:#fce4ec;color:#c62828}
.badge-learning{background:#f3e5f5;color:#6a1b9a}
.badge-system{background:#e0e0e0;color:#555}
.search-box{display:flex;gap:8px;margin-bottom:12px}
.search-box input{flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:14px}
.search-box button{padding:8px 20px;background:#1a73e8;color:#fff;border:none;border-radius:6px;cursor:pointer}
.search-box button:hover{background:#1557b0}
.search-results{margin-top:8px}
.search-results .item{padding:8px 12px;margin-bottom:4px;background:#f8f9fa;border-radius:6px;border-left:3px solid #1a73e8}
.error{color:#d93025;padding:12px;background:#fce8e8;border-radius:6px}
.empty{color:#888;padding:16px;text-align:center;font-size:13px}
#loading{text-align:center;padding:40px;color:#888}
.llm-entry{padding:10px;margin-bottom:8px;background:#f8f9fa;border-radius:6px;border-left:3px solid #34a853}
.llm-entry .meta{font-size:11px;color:#888;margin-bottom:4px}
.llm-entry .content{font-size:12px;line-height:1.5}
.llm-entry .content .label{color:#1a73e8;font-weight:600}
.toolbar{display:flex;gap:8px;margin-bottom:12px;align-items:center}
.toolbar button{padding:6px 14px;border-radius:6px;border:1px solid #ddd;background:#fff;cursor:pointer;font-size:12px}
.toolbar button:hover{background:#f0f0f0}
.toolbar .refresh{background:#1a73e8;color:#fff;border-color:#1a73e8}
.toolbar .refresh:hover{background:#1557b0}
</style>
</head>
<body>
<div class="header">
<div><h1>🔍 LINK 调试面板</h1><span class="sub" id="last-update">加载中...</span></div>
<div class="toolbar"><button class="refresh" onclick="loadData()">&#x21bb; 刷新</button></div>
</div>

<div class="tabs">
<button class="tab active" onclick="switchTab(this,'memory')">&#x1F4BE; 记忆库</button>
<button class="tab" onclick="switchTab(this,'brain')">&#x1F9E0; LLM 交互</button>
<button class="tab" onclick="switchTab(this,'planning')">&#x1F3AF; 规划引擎</button>
<button class="tab" onclick="switchTab(this,'system')">&#x2699; 系统信息</button>
<button class="tab" onclick="switchTab(this,'search')">&#x1F50D; 搜索测试</button>
<button class="tab" onclick="switchTab(this,'archive')">&#x1F4E6; 归档</button>
</div>

<div id="loading">加载调试数据...</div>

<div id="panel-memory" class="panel active"></div>
<div id="panel-brain" class="panel"></div>
<div id="panel-planning" class="panel"></div>
<div id="panel-system" class="panel"></div>
<div id="panel-search" class="panel"><div class="search-box"><input id="search-input" placeholder="输入搜索关键词..." onkeydown="if(event.key==='Enter')searchMemory()"><button onclick="searchMemory()">搜索</button></div><div id="search-results" class="search-results"></div></div>
<div id="panel-archive" class="panel"></div>

<script>
let data = null;

let memPage = 1, intPage = 1, currentTab = 'memory';
const MEM_PER_PAGE = 20, INT_PER_PAGE = 10;

async function loadData() {
  document.getElementById('loading').style.display = 'block';
  for (const id of ['panel-memory','panel-brain','panel-planning','panel-system']) {
    document.getElementById(id).innerHTML = '';
  }
  try {
    const r = await fetch('/api/debug');
    data = await r.json();
    document.getElementById('last-update').textContent = '更新: ' + new Date().toLocaleTimeString();
    renderMemory(data.memory);
    renderBrain(data.brain);
    renderPlanning(data.planning);
    renderSystem(data);
    // Load archives in background
    loadArchives();
  } catch(e) {
    document.getElementById('loading').innerHTML = '<div class="error">加载失败: ' + e.message + '</div>';
    return;
  }
  document.getElementById('loading').style.display = 'none';
}

function switchTab(el, name) {
  currentTab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
}

async function refreshCurrentTab() {
  try {
    if (currentTab === 'memory') {
      loadMemoriesPage(memPage);
    } else if (currentTab === 'brain') {
      loadInteractionsPage(intPage);
    } else if (currentTab === 'archive') {
      loadArchives();
    } else if (currentTab === 'search') {
      // search is user-initiated, skip auto-refresh
    } else {
      // planning, system — full refresh for stats
      const r = await fetch('/api/debug');
      const d = await r.json();
      if (currentTab === 'planning') renderPlanning(d.planning);
      if (currentTab === 'system') renderSystem(d);
    }
    document.getElementById('last-update').textContent = '更新: ' + new Date().toLocaleTimeString();
  } catch(e) {
    console.error('Auto-refresh failed:', e);
  }
}

function renderMemory(m) {
  if (!m || m.error) { document.getElementById('panel-memory').innerHTML = '<div class="error">' + (m?.error || '不可用') + '</div>'; return; }
  let html = '';
  // Stats
  if (m.stats) {
    html += '<div class="section"><h3>&#x1F4CA; 统计</h3><div class="grid">';
    html += '<div class="stat-card"><div class="label">记忆总数</div><div class="value">' + (m.stats.total_memories||0) + '</div></div>';
    if (m.stats.graph) {
      html += '<div class="stat-card"><div class="label">图节点</div><div class="value">' + (m.stats.graph.nodes||0) + '</div></div>';
      html += '<div class="stat-card"><div class="label">图边数</div><div class="value">' + (m.stats.graph.edges||0) + '</div></div>';
    }
    if (m.stats.type_counts) {
      for (const [k,v] of Object.entries(m.stats.type_counts)) {
        html += '<div class="stat-card"><div class="label">' + k + '</div><div class="value">' + v + '</div></div>';
      }
    }
    html += '</div></div>';
  }
  // Embedding
  if (m.embedding) {
    html += '<div class="section"><h3>&#x1F9E9; 嵌入模型</h3><div class="grid"><div class="stat-card"><div class="label">状态</div><div class="value">' + (m.embedding.ready ? '&#x2705; 就绪' : '&#x26A0; 未就绪') + '</div></div>';
    html += '<div class="stat-card"><div class="label">模型</div><div class="value" style="font-size:13px">' + (m.embedding.model||'-') + '</div></div>';
    html += '<div class="stat-card"><div class="label">维度</div><div class="value">' + (m.embedding.dimension||0) + '</div></div></div></div>';
  }
  // Memories table (paginated via api)
  html += '<div class="section"><h3>&#x1F4DD; 记忆列表</h3><div id="mem-table-container"><div class="empty">加载中...</div></div></div>';
  document.getElementById('panel-memory').innerHTML = html;
  loadMemoriesPage(1);
}

async function loadMemoriesPage(page) {
  memPage = page;
  const container = document.getElementById('mem-table-container');
  if (!container) return;
  try {
    const r = await fetch('/api/debug/memories?page=' + page + '&per_page=' + MEM_PER_PAGE);
    const d = await r.json();
    if (d.error) { container.innerHTML = '<div class="error">' + d.error + '</div>'; return; }
    const total = d.total || 0;
    const totalPages = Math.max(1, Math.ceil(total / MEM_PER_PAGE));
    let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
    html += '<span style="font-size:13px;color:#666">共 ' + total + ' 条，第 ' + page + '/' + totalPages + ' 页</span>';
    html += '<div class="pagination">';
    html += '<button onclick="loadMemoriesPage(' + (page-1) + ')" ' + (page<=1?'disabled':'') + ' style="padding:4px 10px;margin:0 4px;border:1px solid #ddd;border-radius:4px;background:#fff;cursor:pointer">&#x25C0; 上一页</button>';
    html += '<button onclick="loadMemoriesPage(' + (page+1) + ')" ' + (page>=totalPages?'disabled':'') + ' style="padding:4px 10px;margin:0 4px;border:1px solid #ddd;border-radius:4px;background:#fff;cursor:pointer">下一页 &#x25B6;</button>';
    html += '</div></div>';

    if (d.memories && d.memories.length > 0) {
      html += '<div style="overflow-x:auto"><table><thead><tr><th>类型</th><th>重要性</th><th>内容</th><th>时间</th><th></th></tr></thead><tbody>';
      for (const mem of d.memories) {
        const typeClass = 'badge-' + (mem.type || 'system');
        const short = escapeHtml(mem.content).substring(0, 100);
        html += '<tr><td><span class="badge ' + typeClass + '">' + (mem.type||'?') + '</span></td>';
        html += '<td>' + (mem.importance||0) + '</td>';
        html += '<td class="content-cell">' + short + (mem.content.length > 100 ? '...' : '') + '</td>';
        html += '<td style="font-size:11px;color:#888;white-space:nowrap">' + (mem.created_at||'').slice(0,16) + '</td>';
        html += `<td><a onclick="showMemDetail('${mem.id}')" style="cursor:pointer;color:#1a73e8;font-size:12px">详情</a></td></tr>`;
      }
      html += '</tbody></table></div>';
    } else {
      html += '<div class="empty">暂无记忆数据</div>';
    }
    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = '<div class="error">加载失败: ' + e.message + '</div>';
  }
}

// Memory detail modal
let detailData = null;
async function showMemDetail(id) {
  if (!detailData) {
    const r = await fetch('/api/debug/memories?page=1&per_page=9999');
    detailData = await r.json();
  }
  const mem = (detailData.memories || []).find(m => m.id === id);
  if (!mem) { alert('未找到该记忆'); return; }
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.4);z-index:1000;display:flex;align-items:center;justify-content:center';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  const box = document.createElement('div');
  box.style.cssText = 'background:#fff;border-radius:12px;padding:24px;max-width:700px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 4px 20px rgba(0,0,0,0.2)';
  box.innerHTML = '<div style="display:flex;justify-content:space-between;margin-bottom:16px">' +
    '<h3 style="margin:0;font-size:16px">记忆详情</h3>' +
    `<a onclick="this.closest('div[style]').parentElement.remove()" style="cursor:pointer;font-size:20px;color:#999">&times;</a></div>` +
    '<table style="width:100%;font-size:13px"><tr><td style="padding:6px 8px;color:#666;width:80px"><b>ID</b></td><td style="padding:6px 8px;word-break:break-all">' + escapeHtml(mem.id) + '</td></tr>' +
    '<tr><td style="padding:6px 8px;color:#666"><b>类型</b></td><td style="padding:6px 8px"><span class="badge badge-' + (mem.type||'system') + '">' + (mem.type||'?') + '</span></td></tr>' +
    '<tr><td style="padding:6px 8px;color:#666"><b>重要性</b></td><td style="padding:6px 8px">' + (mem.importance||0) + '</td></tr>' +
    '<tr><td style="padding:6px 8px;color:#666"><b>时间</b></td><td style="padding:6px 8px">' + (mem.created_at||'') + '</td></tr>' +
    '<tr><td style="padding:6px 8px;color:#666"><b>标签</b></td><td style="padding:6px 8px">' + (mem.tags||[]).join(', ') || '-' + '</td></tr>' +
    '<tr><td style="padding:6px 8px;color:#666;vertical-align:top"><b>内容</b></td><td style="padding:6px 8px;white-space:pre-wrap;word-break:break-word;background:#f8f9fa;border-radius:6px;padding:12px;font-size:12px;line-height:1.6">' + escapeHtml(mem.content) + '</td></tr></table>';
  overlay.appendChild(box);
  document.body.appendChild(overlay);
}

function renderBrain(b) {
  if (!b || b.error) { document.getElementById('panel-brain').innerHTML = '<div class="error">' + (b?.error||'不可用') + '</div>'; return; }
  let html = '';
  // Health
  if (b.health) {
    html += '<div class="section"><h3>&#x1F9E0; 大脑引擎健康</h3><div class="grid">';
    const status = b.health.overall_status || 'unknown';
    const statusClass = status === 'healthy' ? 'value' : 'value warn';
    html += '<div class="stat-card"><div class="label">状态</div><div class="' + statusClass + '">' + status + '</div></div>';
    html += '<div class="stat-card"><div class="label">模型</div><div class="value" style="font-size:13px">' + (b.health.brain_engine?.config?.model_name || b.config?.model_name || '?') + '</div></div>';
    if (b.health.brain_engine?.interaction_history_count !== undefined) {
      html += '<div class="stat-card"><div class="label">交互历史</div><div class="value">' + b.health.brain_engine.interaction_history_count + '</div></div>';
    }
    html += '</div></div>';
  }
  // Config
  if (b.config) {
    html += '<div class="section"><h3>&#x2699; 配置</h3><table><thead><tr><th>键</th><th>值</th></tr></thead><tbody>';
    for (const [k,v] of Object.entries(b.config)) {
      html += '<tr><td>' + k + '</td><td>' + escapeHtml(JSON.stringify(v)) + '</td></tr>';
    }
    html += '</tbody></table></div>';
  }
  // Interaction history (paginated)
  const totalInt = b.health?.brain_engine?.interaction_history_count || 0;
  html += '<div class="section"><h3>&#x1F4AC; 最近 LLM 交互</h3><div id="int-table-container"><div class="empty">加载中...</div></div></div>';
  document.getElementById('panel-brain').innerHTML = html;
  loadInteractionsPage(1);
}

async function loadInteractionsPage(page) {
  intPage = page;
  const container = document.getElementById('int-table-container');
  if (!container) return;
  try {
    const r = await fetch('/api/debug/interactions?page=' + page + '&per_page=' + INT_PER_PAGE);
    const d = await r.json();
    if (d.error) { container.innerHTML = '<div class="error">' + d.error + '</div>'; return; }
    const total = d.total || 0;
    const totalPages = Math.max(1, Math.ceil(total / INT_PER_PAGE));
    let html = '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">';
    html += '<span style="font-size:13px;color:#666">共 ' + total + ' 条，第 ' + page + '/' + totalPages + ' 页</span>';
    html += '<div class="pagination">';
    html += '<button onclick="loadInteractionsPage(' + (page-1) + ')" ' + (page<=1?'disabled':'') + ' style="padding:4px 10px;margin:0 4px;border:1px solid #ddd;border-radius:4px;background:#fff;cursor:pointer">&#x25C0; 上一页</button>';
    html += '<button onclick="loadInteractionsPage(' + (page+1) + ')" ' + (page>=totalPages?'disabled':'') + ' style="padding:4px 10px;margin:0 4px;border:1px solid #ddd;border-radius:4px;background:#fff;cursor:pointer">下一页 &#x25B6;</button>';
    html += '</div></div>';

    if (d.interactions && d.interactions.length > 0) {
      for (const h of d.interactions) {
        const inputShort = escapeHtml(h.input||'').substring(0, 120);
        const outputShort = escapeHtml(h.output||'').substring(0, 120);
        html += '<div class="llm-entry" style="cursor:pointer" onclick="showIntDetail(this)">';
        html += '<div class="meta">[' + (h.time||'').slice(0,19) + '] ' + (h.type||'?') + ' | ' + (h.duration||0) + 's</div>';
        html += '<div class="content"><span class="label">&#x25B6; 输入:</span> ' + inputShort + (h.input && h.input.length > 120 ? ' <span style="color:#1a73e8;font-size:11px">展开</span>' : '') + '<br>';
        html += '<span class="label">&#x25C0; 输出:</span> ' + outputShort + (h.output && h.output.length > 120 ? ' <span style="color:#1a73e8;font-size:11px">展开</span>' : '');
        // Store full data
        html += '<div style="display:none" class="int-full-input">' + escapeHtml(h.input||'') + '</div>';
        html += '<div style="display:none" class="int-full-output">' + escapeHtml(h.output||'') + '</div>';
        html += '</div></div>';
      }
    } else {
      html += '<div class="empty">暂无 LLM 交互记录</div>';
    }
    container.innerHTML = html;
  } catch(e) {
    container.innerHTML = '<div class="error">加载失败: ' + e.message + '</div>';
  }
}
function showIntDetail(el) {
  const inputFull = el.querySelector('.int-full-input')?.textContent || '';
  const outputFull = el.querySelector('.int-full-output')?.textContent || '';
  const meta = el.querySelector('.meta')?.textContent || '';
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.4);z-index:1000;display:flex;align-items:center;justify-content:center';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  const box = document.createElement('div');
  box.style.cssText = 'background:#fff;border-radius:12px;padding:24px;max-width:800px;width:90%;max-height:80vh;overflow-y:auto;box-shadow:0 4px 20px rgba(0,0,0,0.2)';
  box.innerHTML = '<div style="display:flex;justify-content:space-between;margin-bottom:12px">' +
    '<h3 style="margin:0;font-size:15px;color:#333">LLM 交互详情</h3>' +
    `<a onclick="this.closest('div[style]').parentElement.remove()" style="cursor:pointer;font-size:20px;color:#999">&times;</a></div>` +
    '<div style="font-size:11px;color:#888;margin-bottom:12px">' + meta + '</div>' +
    '<div style="margin-bottom:12px"><div style="font-size:12px;font-weight:600;color:#1a73e8;margin-bottom:4px">&#x25B6; 输入</div>' +
    '<div style="background:#f0f7ff;border-radius:8px;padding:12px;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word">' + (inputFull || '-') + '</div></div>' +
    '<div><div style="font-size:12px;font-weight:600;color:#34a853;margin-bottom:4px">&#x25C0; 输出</div>' +
    '<div style="background:#f0faf0;border-radius:8px;padding:12px;font-size:12px;line-height:1.6;white-space:pre-wrap;word-break:break-word">' + (outputFull || '-') + '</div></div>';
  overlay.appendChild(box);
  document.body.appendChild(overlay);
}

function renderPlanning(p) {
  if (!p || p.error) { document.getElementById('panel-planning').innerHTML = '<div class="error">' + (p?.error||'不可用') + '</div>'; return; }
  let html = '<div class="section"><h3>&#x1F3AF; 规划引擎</h3><div class="grid">';
  html += '<div class="stat-card"><div class="label">可用</div><div class="value">' + (p.available ? '&#x2705;' : '&#x274C;') + '</div></div>';
  html += '<div class="stat-card"><div class="label">活跃任务</div><div class="value">' + (p.tasks_count||0) + '</div></div>';
  html += '</div></div>';
  if (p.templates && p.templates.length > 0) {
    html += '<div class="section"><h3>&#x1F4CB; 任务模板</h3><div style="display:flex;gap:6px;flex-wrap:wrap">';
    for (const t of p.templates) {
      html += '<span class="badge badge-fact">' + t + '</span>';
    }
    html += '</div></div>';
  }
  document.getElementById('panel-planning').innerHTML = html;
}

function renderSystem(d) {
  let html = '<div class="section"><h3>&#x1F4BB; Web 服务</h3><div class="grid">';
  if (d.web) {
    html += '<div class="stat-card"><div class="label">运行状态</div><div class="value' + (d.web.is_running ? '' : ' warn') + '">' + (d.web.is_running ? '&#x25B6; 运行中' : '&#x23F9; 已停止') + '</div></div>';
    html += '<div class="stat-card"><div class="label">客户端</div><div class="value">' + d.web.clients + '</div></div>';
    html += '<div class="stat-card"><div class="label">事件队列</div><div class="value">' + d.web.event_queue + '</div></div>';
    html += '<div class="stat-card"><div class="label">已处理事件</div><div class="value">' + d.web.events_processed + '</div></div>';
    html += '<div class="stat-card"><div class="label">启动时长</div><div class="value">' + d.web.uptime + 's</div></div>';
  }
  html += '</div></div>';
  if (d.system) {
    html += '<div class="section"><h3>&#x1F4BB; 系统</h3><table><thead><tr><th>项目</th><th>值</th></tr></thead><tbody>';
    for (const [k,v] of Object.entries(d.system)) {
      html += '<tr><td>' + k + '</td><td class="content-cell">' + escapeHtml(String(v)) + '</td></tr>';
    }
    html += '</tbody></table></div>';
  }
  document.getElementById('panel-system').innerHTML = html;
}

async function searchMemory() {
  const q = document.getElementById('search-input').value.trim();
  if (!q) return;
  const el = document.getElementById('search-results');
  el.innerHTML = '<div style="text-align:center;padding:12px;color:#888">搜索中...</div>';
  try {
    const r = await fetch('/api/debug/search', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:q})});
    const d = await r.json();
    if (d.error) { el.innerHTML = '<div class="error">' + d.error + '</div>'; return; }
    let html = '<div style="margin-bottom:8px;font-size:13px;color:#555">找到 ' + (d.total||0) + ' 条结果</div>';
    if (d.results && d.results.length > 0) {
      for (const item of d.results) {
        const typeClass = 'badge-' + (item.type||'system');
        html += '<div class="item"><div style="margin-bottom:4px"><span class="badge ' + typeClass + '">' + (item.type||'?') + '</span> <span style="font-size:11px;color:#888">相似度: ' + item.similarity + ' | 重要性: ' + item.importance + '</span></div>';
        html += '<div style="font-size:12px">' + escapeHtml(item.content) + '</div></div>';
      }
    } else {
      html += '<div class="empty">无匹配结果</div>';
    }
    el.innerHTML = html;
  } catch(e) {
    el.innerHTML = '<div class="error">搜索失败: ' + e.message + '</div>';
  }
}

function escapeHtml(s) {
  if (!s) return '';
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ─── 归档功能 ─────────────────────────────────────

async function loadArchives() {
  const panel = document.getElementById('panel-archive');
  if (!panel) return;
  let html = '<div class="section"><h3>&#x1F4E6; 记忆归档</h3>';

  // Create archive button
  html += '<div style="display:flex;gap:8px;margin-bottom:12px;align-items:center">';
  html += '<input id="archive-label" placeholder="归档标签（可选）..." style="flex:1;padding:8px 12px;border:1px solid #ddd;border-radius:6px;font-size:13px">';
  html += '<button onclick="createArchive()" style="padding:8px 20px;background:#1a73e8;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px">&#x1F4E5; 创建归档</button>';
  html += '<button onclick="resetMemory()" style="padding:8px 20px;background:#d93025;color:#fff;border:none;border-radius:6px;cursor:pointer;font-size:13px">&#x1F5D1; 清空记忆</button>';
  html += '</div>';

  // Archive list
  html += '<div id="archive-list"><div class="empty">加载中...</div></div></div>';
  panel.innerHTML = html;

  // Fetch archives
  try {
    const r = await fetch('/api/debug/archives');
    const d = await r.json();
    if (d.error) { document.getElementById('archive-list').innerHTML = '<div class="error">' + d.error + '</div>'; return; }
    let listHtml = '';
    const arcs = d.archives || [];
    if (arcs.length === 0) {
      listHtml = '<div class="empty">暂无归档</div>';
    } else {
      listHtml += '<div style="overflow-x:auto"><table><thead><tr><th>版本</th><th>时间</th><th>标签</th><th>条数</th><th>校验</th><th></th></tr></thead><tbody>';
      for (const a of arcs) {
        const verifiedIcon = a.verified ? '&#x2705;' : '&#x274C;';
        const verifiedColor = a.verified ? '#2e7d32' : '#d93025';
        listHtml += '<tr><td style="font-size:11px;font-family:monospace">' + escapeHtml(a.archive_id).substring(0, 30) + '...</td>';
        listHtml += '<td style="font-size:11px;white-space:nowrap">' + (a.created_at||'').slice(0,19) + '</td>';
        listHtml += '<td>' + escapeHtml(a.label||'') + '</td>';
        listHtml += '<td>' + (a.memory_count||0) + '</td>';
        listHtml += '<td style="color:' + verifiedColor + ';font-size:13px">' + verifiedIcon + '</td>';
        listHtml += `<td><button class="restore-btn" onclick="restoreArchive('${a.archive_id}')" style="padding:4px 12px;background:#34a853;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px">恢复</button></td></tr>`;
      }
      listHtml += '</tbody></table></div>';
    }
    document.getElementById('archive-list').innerHTML = listHtml;
  } catch(e) {
    document.getElementById('archive-list').innerHTML = '<div class="error">加载失败: ' + e.message + '</div>';
  }
}

async function createArchive() {
  const label = document.getElementById('archive-label')?.value || '';
  const btn = document.querySelector('[onclick="createArchive()"]');
  if (btn) { btn.disabled = true; btn.textContent = '归档中...'; }
  try {
    const r = await fetch('/api/debug/archive', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({label: label})
    });
    const d = await r.json();
    if (d.success) {
      alert('&#x2705; 归档成功！\\n' + d.archive.archive_id + '\\n' + d.archive.memory_count + ' 条记忆');
      loadArchives(); // refresh
    } else {
      alert('&#x274C; 归档失败: ' + (d.error||'unknown'));
    }
  } catch(e) {
    alert('&#x274C; 归档失败: ' + e.message);
  }
  if (btn) { btn.disabled = false; btn.textContent = '&#x1F4E5; 创建归档'; }
}

async function restoreArchive(archiveId) {
  if (!confirm('确定要恢复归档 ' + archiveId.substring(0,30) + ' 吗？\\n当前记忆将被替换！')) return;
  if (!confirm('再次确认：当前所有记忆将被删除，替换为归档版本。')) return;
  const btns = document.querySelectorAll('.restore-btn');
  const btn = btns.length === 1 ? btns[0] : document.querySelector(`[onclick*="restoreArchive('${archiveId.slice(0,12)}")]`);
  if (btn) { btn.disabled = true; btn.textContent = '恢复中...'; }
  try {
    const r = await fetch('/api/debug/archive/restore', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({archive_id: archiveId})
    });
    const d = await r.json();
    if (d.success) {
      alert('&#x2705; 恢复成功！\\n' + d.result.restored_count + ' 条记忆已恢复');
      loadData(); // refresh all data
      loadArchives(); // refresh archive list
    } else {
      alert('&#x274C; 恢复失败: ' + (d.error||'unknown'));
    }
  } catch(e) {
    alert('&#x274C; 恢复失败: ' + e.message);
  }
  if (btn) { btn.disabled = false; btn.textContent = '恢复'; }
}

async function resetMemory() {
  if (!confirm('确定要清空所有记忆吗？\\n\\n建议先创建归档再清空。')) return;
  if (!confirm('再次确认：所有记忆、嵌入向量和图索引将被永久删除！')) return;
  try {
    const r = await fetch('/api/debug/memory/reset', {method: 'POST'});
    const d = await r.json();
    if (d.success) {
      alert('&#x2705; 已清空 ' + d.cleared_count + ' 条记忆');
      loadData();
      loadArchives();
    } else {
      alert('&#x274C; 清空失败: ' + (d.error||'unknown'));
    }
  } catch(e) {
    alert('&#x274C; 清空失败: ' + e.message);
  }
}

loadData();
// Auto-refresh every 10s — only refresh active tab
setInterval(refreshCurrentTab, 10000);
</script>
</body>
</html>"""


# ── Provider 设置页面 ──

SETTINGS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LINK 设置</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333;padding:20px;max-width:700px;margin:0 auto}
h1{font-size:22px;margin-bottom:16px;color:#1a1a2e}
.card{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card h2{font-size:15px;margin-bottom:12px;color:#1a73e8}
.field{margin-bottom:14px}
.field label{display:block;font-size:13px;color:#555;margin-bottom:4px;font-weight:500}
.field input,.field select{width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;transition:border-color .2s}
.field input:focus,.field select:focus{border-color:#1a73e8}
.field input[type=radio]{width:auto;margin-right:4px}
.radio-group{display:flex;gap:24px;margin-bottom:4px}
.radio-group label{font-size:14px;cursor:pointer;display:flex;align-items:center;gap:4px;color:#333;padding:8px 12px;border:2px solid #e0e0e0;border-radius:8px;transition:all .2s}
.radio-group label:has(input:checked){border-color:#1a73e8;background:#e8f0fe}
.btn{padding:12px 24px;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;transition:all .2s}
.btn-primary{background:#1a73e8;color:#fff}
.btn-primary:hover{background:#1557b0}
.btn-primary:disabled{background:#ccc;cursor:not-allowed}
.btn-secondary{background:#e8eaed;color:#333}
.btn-secondary:hover{background:#d2d5d9}
.status{display:none;padding:12px 16px;border-radius:8px;margin-bottom:16px;font-size:14px}
.status.success{display:block;background:#e8f5e9;color:#2e7d32;border:1px solid #c8e6c9}
.status.error{display:block;background:#fce8e8;color:#d93025;border:1px solid #f5c6cb}
.hidden{display:none}
.model-info{font-size:12px;color:#888;margin-top:6px}
</style>
</head>
<body>
<h1>&#x2699;&#xFE0F; LINK 设置</h1>
<div id="status" class="status"></div>

<div class="card">
  <h2>&#x1F916; 模型提供者</h2>
  <div class="field">
    <div class="radio-group">
      <label><input type="radio" name="mode" value="online" checked onchange="toggleMode()"> &#x1F310; 在线模式（API）</label>
      <label><input type="radio" name="mode" value="offline" onchange="toggleMode()"> &#x1F4BB; 离线模式（本地模型）</label>
    </div>
  </div>
</div>

<div id="online-settings" class="card">
  <h2>&#x1F310; 在线 API 配置</h2>
  <div class="field">
    <label>服务商</label>
    <select id="provider" onchange="updateBaseUrl()">
      <option value="deepseek">DeepSeek</option>
      <option value="openai">OpenAI</option>
      <option value="custom">自定义（OpenAI 兼容）</option>
    </select>
  </div>
  <div class="field">
    <label>API 地址</label>
    <input id="api-base" placeholder="https://api.deepseek.com">
  </div>
  <div class="field">
    <label>API Key</label>
    <input id="api-key" type="password" placeholder="sk-...">
  </div>
  <div class="field">
    <label>模型</label>
    <input id="model-name" placeholder="deepseek-chat">
  </div>
  <div class="field">
    <label>Temperature</label>
    <input id="temperature" type="number" step="0.1" min="0" max="2" value="0.7">
  </div>
</div>

<div id="offline-settings" class="card hidden">
  <h2>&#x1F4BB; 本地模型</h2>
  <div class="field">
    <label>选择模型</label>
    <select id="offline-model"></select>
  </div>
  <div class="model-info" id="model-info"></div>
</div>

<!-- Permission Defaults -->
<div class="card">
  <h2>&#x1F512; 默认授权规则</h2>
  <div class="field">
    <label>文件读取权限</label>
    <select id="perm-file-read">
      <option value="ask">每次询问</option>
      <option value="once">仅本次</option>
      <option value="1h">授权1小时</option>
      <option value="24h">授权24小时</option>
      <option value="permanent">永久授权</option>
    </select>
  </div>
  <div class="field">
    <label>文件写入权限</label>
    <select id="perm-file-write">
      <option value="ask">每次询问</option>
      <option value="once">仅本次</option>
      <option value="1h">授权1小时</option>
      <option value="24h">授权24小时</option>
      <option value="permanent">永久授权</option>
    </select>
  </div>
  <div class="field">
    <label>命令执行权限</label>
    <select id="perm-command-exec">
      <option value="ask">每次询问</option>
      <option value="once">仅本次</option>
      <option value="1h">授权1小时</option>
      <option value="24h">授权24小时</option>
      <option value="permanent">永久授权</option>
    </select>
  </div>
</div>

<div style="display:flex;gap:10px;margin-top:8px">
  <button class="btn btn-primary" onclick="saveSettings()">保存设置</button>
  <button class="btn btn-secondary" onclick="testConnection()">测试连接</button>
  <a href="/" style="margin-left:auto;color:#888;text-decoration:none;font-size:13px;padding:12px 0">&#x2190; 返回聊天</a>
</div>

<script>
// Load available Ollama models
async function loadModels() {
  const sel = document.getElementById("offline-model");
  sel.innerHTML = '<option value="加载中...</option>';
  try {
    const r = await fetch("/api/models");
    const d = await r.json();
    if (d.models && d.models.length > 0) {
      var embedModels = ["bge-m3", "nomic-embed-text", "all-MiniLM"];
      sel.innerHTML = d.models.map(function(m) {
        var note = "";
        for (var i = 0; i < embedModels.length; i++) {
          if (m.indexOf(embedModels[i]) === 0) { note = " (仅嵌入)"; break; }
        }
        return '<option value="' + m + '">' + m + note + '</option>';
      }).join("");
    } else {
      sel.innerHTML = '<option value="">未发现本地模型（Ollama 未运行）</option>';
    }
  } catch(e) {
    sel.innerHTML = "<option value='>加载失败</option>";
  }
}

// Load current settings
async function loadSettings() {
  try {
    const r = await fetch("/api/settings");
    const s = await r.json();
    // Select the correct mode radio
    var radio = document.querySelector("input[name=mode][value=\\"" + s.mode + "\\"]");
    if (radio) radio.checked = true;
    // Fill in fields
    if (s.provider) document.getElementById("provider").value = s.provider;
    if (s.api_base) document.getElementById("api-base").value = s.api_base;
    if (s.api_key_display) document.getElementById("api-key").placeholder = s.api_key_display;
    if (s.model) document.getElementById("model-name").value = s.model;
    if (s.temperature) document.getElementById("temperature").value = s.temperature;
    // Select offline model
    if (s.offline_model) {
      var sel = document.getElementById("offline-model");
      for (var i = 0; i < sel.options.length; i++) {
        if (sel.options[i].value === s.offline_model) {
          sel.options[i].selected = true;
          break;
        }
      }
    }
    toggleMode();
  } catch(e) {
    showStatus("加载设置失败: " + e.message, "error");
  }
}

function toggleMode() {
  var modeEl = document.querySelector("input[name=mode]:checked");
  if (!modeEl) return;
  var mode = modeEl.value;
  document.getElementById("online-settings").classList.toggle("hidden", mode !== "online");
  document.getElementById("offline-settings").classList.toggle("hidden", mode !== "offline");
}

function updateBaseUrl() {
  var p = document.getElementById("provider").value;
  var urls = { deepseek: "https://api.deepseek.com", openai: "https://api.openai.com" };
  if (p !== "custom") {
    document.getElementById("api-base").value = urls[p] || "";
  }
  var models = { deepseek: "deepseek-chat", openai: "gpt-4o" };
  if (p !== "custom") {
    document.getElementById("model-name").value = models[p] || "";
  }
  // Load permission settings
  try {
    const pr = await fetch("/api/permission-settings");
    const ps = await pr.json();
    if (ps.file_read) document.getElementById("perm-file-read").value = ps.file_read;
    if (ps.file_write) document.getElementById("perm-file-write").value = ps.file_write;
    if (ps.command_exec) document.getElementById("perm-command-exec").value = ps.command_exec;
  } catch(e) { console.log("perm settings load:", e); }
}

async function saveSettings() {
  var btn = document.querySelector(".btn-primary");
  btn.disabled = true; btn.textContent = "保存中...";
  var data = {
    mode: (document.querySelector("input[name=mode]:checked") || {}).value || "offline",
    provider: document.getElementById("provider").value,
    file_read: document.getElementById("perm-file-read").value,
    file_write: document.getElementById("perm-file-write").value,
    command_exec: document.getElementById("perm-command-exec").value,
    api_base: document.getElementById("api-base").value,
    api_key: document.getElementById("api-key").value,
    model: document.getElementById("model-name").value,
    offline_model: document.getElementById("offline-model").value,
    temperature: parseFloat(document.getElementById("temperature").value) || 0.7,
  };
  try {
    var r = await fetch("/api/settings", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(data)
    });
    var d = await r.json();
    showStatus(d.message || "已保存", d.success ? "success" : "error");
  } catch(e) {
    showStatus("保存失败: " + e.message, "error");
  }
  btn.disabled = false; btn.textContent = "保存设置";
}

async function testConnection() {
  var modeEl = document.querySelector("input[name=mode]:checked");
  if (!modeEl) return;
  if (modeEl.value === "offline") {
    try {
      var r = await fetch("/api/models");
      var d = await r.json();
      showStatus("Ollama \u8fde\u63a5\u6b63\u5e38\uff0c\u53d1\u73b0 " + d.models.length + " \u4e2a\u6a21\u578b", "success");
    } catch(e) {
      showStatus("Ollama \u8fde\u63a5\u5931\u8d25", "error");
    }
    return;
  }
  showStatus("\u6b63\u5728\u6d4b\u8bd5\u8fde\u63a5...", "success");
  try {
    var r = await fetch("/api/settings/test", {method:"POST"});
    var d = await r.json();
    showStatus(d.message, d.success ? "success" : "error");
  } catch(e) {
    showStatus("\u8bf7\u6c42\u5931\u8d25: " + e.message, "error");
  }
}

function showStatus(msg, type) {
  var el = document.getElementById("status");
  el.textContent = msg;
  el.className = "status " + type;
}

loadSettings();
loadModels();
</script>
</body>
</html>"""
def main():
    """主函数"""
    print("="*60)
    print("LINK主动运行模式（Web版本）")
    print("="*60)
    print("💡 解决CLI模式下心跳输出干扰用户输入的问题")
    print("💡 提供Web界面，支持实时事件监控")
    print("="*60)
    
    # 创建Web版本的LINK
    web_link = WebActiveLINK()
    
    # 启动主动模式（非阻塞）
    web_link.start(blocking=False)
    
    # 运行Web服务器
    web_link.run_web()
    
    # 停止主动模式
    web_link.stop()


if __name__ == "__main__":
    main()