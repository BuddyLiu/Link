#!/usr/bin/env python3
"""
JARVIS主动运行模式的Web版本
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

    def __init__(self, jarvis_instance=None):
        super().__init__("task_handler")
        self.jarvis = jarvis_instance
        # 如果传入的是 WebActiveJARVIS 实例，自动获取其中的 brain_jarvis
        self.brain_jarvis = getattr(jarvis_instance, 'brain_jarvis', None)

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
        if self.brain_jarvis:
            try:
                return self.brain_jarvis.process_input(text)
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
    
    def __init__(self, jarvis_instance=None):
        super().__init__("learning_handler")
        self.jarvis = jarvis_instance
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
            return "🧠 记忆模式分析完成：系统运行正常"
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


class WebActiveJARVIS:
    """Web版本的主动运行模式JARVIS"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化Web版本的主动JARVIS
        
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
        self.app = FastAPI(title="JARVIS主动模式Web界面")
        self.websocket_clients = []
        self.event_history = []
        self.max_history = 100
        
        # 统计
        self.stats = {
            "events_processed": 0,
            "events_dropped": 0,
            "start_time": None,
            "last_event_time": None
        }

        # 初始化大脑引擎（JARVIS 主实例，用于 LLM 问答）
        self.brain_jarvis = None
        self._init_brain_jarvis()

        # 初始化组件
        self._initialize_components()
        self._setup_routes()

    def _init_brain_jarvis(self):
        """初始化 JARVIS 大脑引擎（延迟导入避免循环引用）"""
        try:
            from main import JARVIS
            self.brain_jarvis = JARVIS()
            import logging
            logging.getLogger("jarvis").info("WebActiveJARVIS 大脑引擎已就绪")
        except Exception as e:
            print(f"⚠️ 大脑引擎初始化失败，将使用本地响应: {e}")
            self.brain_jarvis = None

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
<title>JARVIS</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f5f5f5;height:100vh;display:flex;flex-direction:column}
.header{background:linear-gradient(135deg,#1a1a2e,#16213e);color:#fff;padding:14px 20px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.header h1{font-size:18px;font-weight:600}
.header a{color:rgba(255,255,255,.6);text-decoration:none;font-size:12px;padding:4px 10px;border:1px solid rgba(255,255,255,.2);border-radius:4px;transition:all .2s}
.header a:hover{color:#fff;border-color:rgba(255,255,255,.5)}
#chat-box{flex:1;overflow-y:auto;padding:20px;background:#fff}
.msg{margin-bottom:16px;display:flex;flex-direction:column}
.msg.user{align-items:flex-end}
.msg.assistant{align-items:flex-start}
.msg .bubble{max-width:80%;padding:12px 16px;border-radius:12px;font-size:14px;line-height:1.6;word-break:break-word}
.msg.user .bubble{background:#1a73e8;color:#fff;border-bottom-right-radius:4px}
.msg.assistant .bubble{background:#f0f2f5;color:#333;border-bottom-left-radius:4px}
.msg .time{font-size:11px;color:#999;margin-top:4px;padding:0 4px}
.msg.user .time{text-align:right}
.input-area{flex-shrink:0;padding:16px 20px;background:#fff;border-top:1px solid #e0e0e0;display:flex;gap:10px}
.input-area input{flex:1;padding:12px 16px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;transition:border-color .2s}
.input-area input:focus{border-color:#1a73e8}
.input-area button{padding:12px 24px;background:#1a73e8;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:14px;font-weight:500;transition:background .2s}
.input-area button:hover{background:#1557b0}
.input-area button:disabled{background:#ccc;cursor:not-allowed}
.typing .bubble{color:#999;font-style:italic}
.msg.system{align-items:center}
.msg.system .bubble{background:transparent;color:#999;font-size:12px;max-width:100%;text-align:center}
/* Markdown Styles */
.msg .bubble pre{background:#1e1e2e;color:#cdd6f4;padding:12px;border-radius:8px;overflow-x:auto;font-size:13px;margin:6px 0;font-family:'SF Mono','Fira Code','Consolas',monospace}
.msg .bubble code{background:#e8eaed;color:#d63384;padding:2px 6px;border-radius:4px;font-size:13px;font-family:'SF Mono','Fira Code',monospace}
.msg .bubble pre code{background:transparent;color:inherit;padding:0;border-radius:0}
.msg .bubble p{margin:6px 0}
.msg .bubble p:first-child{margin-top:0}
.msg .bubble p:last-child{margin-bottom:0}
.msg .bubble ul,.msg .bubble ol{margin:6px 0;padding-left:20px}
.msg .bubble li{margin:3px 0}
.msg .bubble h1,.msg .bubble h2,.msg .bubble h3,.msg .bubble h4{margin:10px 0 6px;font-weight:600}
.msg .bubble h1{font-size:16px;border-bottom:1px solid #e0e0e0;padding-bottom:4px}
.msg .bubble h2{font-size:15px}
.msg .bubble h3{font-size:14px}
.msg .bubble blockquote{border-left:3px solid #1a73e8;padding:4px 12px;margin:6px 0;color:#666;background:#f8f9fa;border-radius:0 6px 6px 0}
.msg .bubble table{border-collapse:collapse;margin:6px 0;font-size:13px;width:100%}
.msg .bubble th,.msg .bubble td{border:1px solid #ddd;padding:6px 10px;text-align:left}
.msg .bubble th{background:#f5f5f5;font-weight:600}
.msg .bubble a{color:#1a73e8;text-decoration:none}
.msg .bubble a:hover{text-decoration:underline}
.msg .bubble hr{border:none;border-top:1px solid #e0e0e0;margin:10px 0}
.msg.user .bubble code{background:rgba(255,255,255,.2);color:#fff}
.msg.user .bubble a{color:#fff;text-decoration:underline}
.msg.user .bubble pre{background:rgba(0,0,0,.2)}
.cursor{display:inline-block;width:2px;height:16px;background:#666;margin-left:2px;animation:blink .8s step-end infinite;vertical-align:text-bottom}
@keyframes blink{50%{opacity:0}}
</style>
</head>
<body>
<div class="header">
<h1>&#x1F916; JARVIS</h1>
<a href="/debug">&#x2699; 调试</a>
</div>
<div id="chat-box"></div>
<div class="input-area">
<input id="input" placeholder="输入消息..." autofocus>
<button id="send-btn" onclick="send()">发送</button>
</div>

<script>
const ws = new WebSocket('ws://' + location.host + '/ws');
const chatBox = document.getElementById('chat-box');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');
const TYPE_SPEED = 30; // ms per character

ws.onopen = () => addMessage('system', '已连接到 JARVIS');
ws.onclose = () => addMessage('system', '连接已断开');
ws.onmessage = e => {
  const d = JSON.parse(e.data);
  if (d.type === 'event' && d.data.event_type === 'ASSISTANT') {
    removeTyping();
    typewriteMessage('assistant', d.data.result || '');
  }
};

function send() {
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addMessage('user', text);
  showTyping();
  sendBtn.disabled = true;
  ws.send(JSON.stringify({type: 'user_input', text}));
}

input.addEventListener('keydown', e => { if (e.key === 'Enter') send(); });

// ----- Markdown Parser (lightweight, no dependencies) -----
function renderMarkdown(text) {
  return text
    // Code block
    .replace(/```(?:\\w*)\\n([\\s\\S]*?)```/g, '<pre><code>$1</code></pre>')
    // Inline code
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    // Headers
    .replace(/^### (.+)$/gm, '<h3>$1</h3>')
    .replace(/^## (.+)$/gm, '<h2>$1</h2>')
    .replace(/^# (.+)$/gm, '<h1>$1</h1>')
    // Bold & italic
    .replace(/\\*\\*\\*(.+?)\\*\\*\\*/g, '<strong><em>$1</em></strong>')
    .replace(/\\*\\*(.+?)\\*\\*/g, '<strong>$1</strong>')
    .replace(/\\*(.+?)\\*/g, '<em>$1</em>')
    // Strikethrough
    .replace(/~~(.+?)~~/g, '<del>$1</del>')
    // Links
    .replace(/\\[(.+?)\\]\\((.+?)\\)/g, '<a href="$2" target="_blank">$1</a>')
    // Images
    .replace(/!\\[(.*?)\\]\\((.+?)\\)/g, '<img src="$2" alt="$1" style="max-width:100%">')
    // Unordered list
    .replace(/^[*\\-] (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*<\\/li>\\n?)+/g, '<ul>$&</ul>')
    // Ordered list
    .replace(/^\\d+\\. (.+)$/gm, '<li>$1</li>')
    .replace(/(<li>.*?<\\/li>(?:\\n?<li>.*?<\\/li>)*)/g, '<ol>$1</ol>')
    // Blockquote
    .replace(/^> (.+)$/gm, '<blockquote>$1</blockquote>')
    // Horizontal rule
    .replace(/^(---|\\*\\*\\*)$/gm, '<hr>')
    // Paragraphs (double newline)
    .replace(/\\n\\n/g, '</p><p>')
    // Single newline => line break
    .replace(/\\n/g, '<br>')
    // Wrap entire content in paragraph if it is plain text
    .replace(/^(<p>.*)/, '$1')
    .replace(/^([^<].+)/, '<p>$1</p>')
    // Clean up empty paragraphs
    .replace(/<p><\\/p>/g, '');
}

// ----- Typewriter Effect -----
function typewriteMessage(role, fullText) {
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;

  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  div.appendChild(bubble);

  let pos = 0;
  let htmlBuffer = '';
  const rendered = renderMarkdown(fullText);

  function type() {
    if (pos < rendered.length) {
      // Fast-forward through HTML tags (render them instantly)
      if (rendered[pos] === '<') {
        const tagEnd = rendered.indexOf('>', pos);
        if (tagEnd >= 0) {
          htmlBuffer += rendered.slice(pos, tagEnd + 1);
          pos = tagEnd + 1;
          bubble.innerHTML = htmlBuffer + '<span class="cursor"></span>';
          chatBox.scrollTop = chatBox.scrollHeight;
          requestAnimationFrame(type);
          return;
        }
      }
      // Normal character
      htmlBuffer += rendered[pos];
      pos++;
      bubble.innerHTML = htmlBuffer + '<span class="cursor"></span>';
      chatBox.scrollTop = chatBox.scrollHeight;
      setTimeout(type, TYPE_SPEED);
    } else {
      // Done
      bubble.innerHTML = htmlBuffer;
      chatBox.scrollTop = chatBox.scrollHeight;
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
    div.innerHTML = '<div class="bubble">' + renderMarkdown(escapeHtml(content)) + '</div><div class="time">' + time + '</div>';
  }
  const typing = chatBox.querySelector('.typing');
  if (typing) chatBox.insertBefore(div, typing);
  else chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function showTyping() {
  const existing = chatBox.querySelector('.typing');
  if (existing) return;
  const div = document.createElement('div');
  div.className = 'msg assistant typing';
  div.innerHTML = '<div class="bubble">&#x1F916; 思考中...</div>';
  chatBox.appendChild(div);
  chatBox.scrollTop = chatBox.scrollHeight;
}

function removeTyping() {
  const el = chatBox.querySelector('.typing');
  if (el) el.remove();
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
</script>
</body>
</html>"""

        
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket端点"""
            await websocket.accept()
            client_id = str(uuid.uuid4())
            self.websocket_clients.append({"id": client_id, "websocket": websocket})
            
            try:
                # 发送欢迎消息
                await websocket.send_json({
                    "type": "event",
                    "data": {
                        "event_type": "SYSTEM",
                        "message": "🔗 已连接到JARVIS主动模式",
                        "timestamp": time.time()
                    }
                })
                
                # 发送当前状态
                await self._broadcast_stats()
                
                while True:
                    # 接收消息
                    data = await websocket.receive_json()
                    
                    if data.get("type") == "command":
                        await self._handle_command(websocket, data.get("command"))
                    elif data.get("type") == "user_input":
                        text = data.get("text", "")
                        if text:
                            # 加入事件系统（用于历史记录）
                            self.add_user_input(text, client_id)

                            # 广播"收到输入"事件
                            await self._broadcast_event({
                                "event_type": "USER_INPUT",
                                "message": f"📝 收到用户输入: {text}",
                                "source": f"user_{client_id}"
                            })

                            # 直接在 WebSocket 处理器中调用大脑引擎
                            # （避免事件循环 thread 的 asyncio.run() 无法发送 WebSocket 消息）
                            brain_response = self._process_input_direct(text)
                            if brain_response:
                                await self._broadcast_event({
                                    "event_type": "ASSISTANT",
                                    "result": brain_response,
                                    "source": "jarvis_brain",
                                    "timestamp": time.time()
                                })
                    
            except WebSocketDisconnect:
                # 客户端断开连接
                self.websocket_clients = [c for c in self.websocket_clients if c["id"] != client_id]
                await self._broadcast_stats()
            except Exception as e:
                print(f"WebSocket错误: {e}")
                self.websocket_clients = [c for c in self.websocket_clients if c["id"] != client_id]
    
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
        if self.brain_jarvis:
            bj = self.brain_jarvis
            data["memory"] = self._get_memory_debug(bj)
            data["brain"] = self._get_brain_debug(bj)
            data["planning"] = self._get_planning_debug(bj)
        return data

    def _get_memory_debug(self, jarvis) -> dict:
        result = {"available": jarvis.memory_engine is not None}
        if not jarvis.memory_engine:
            return result
        try:
            store = jarvis.memory_engine.store
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

    def _get_brain_debug(self, jarvis) -> dict:
        result = {"available": jarvis.brain_engine is not None}
        if not jarvis.brain_engine:
            return result
        try:
            be = jarvis.brain_engine
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

    def _get_planning_debug(self, jarvis) -> dict:
        result = {"available": jarvis.planning_engine is not None}
        if not jarvis.planning_engine:
            return result
        try:
            pe = jarvis.planning_engine
            result["tasks_count"] = len(jarvis.active_tasks)
            result["templates"] = pe.get_task_template_types() if hasattr(pe, "get_task_template_types") else []
            if hasattr(pe, "get_planning_stats"):
                result["stats"] = pe.get_planning_stats()
        except Exception as e:
            result["error"] = str(e)
        return result

    async def _search_debug_memory(self, query: str) -> dict:
        if not self.brain_jarvis or not self.brain_jarvis.memory_engine:
            return {"error": "memory not available", "results": []}
        try:
            store = self.brain_jarvis.memory_engine.store
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
        if not self.brain_jarvis or not self.brain_jarvis.memory_engine:
            return {"error": "memory not available", "memories": [], "total": 0}
        try:
            store = self.brain_jarvis.memory_engine.store
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
        if not self.brain_jarvis or not self.brain_jarvis.brain_engine:
            return {"error": "brain not available", "interactions": [], "total": 0}
        try:
            be = self.brain_jarvis.brain_engine
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
        if not self.brain_jarvis or not self.brain_jarvis.memory_engine:
            return {"error": "memory not available"}
        try:
            store = self.brain_jarvis.memory_engine.store
            label = data.get("label", "")
            result = store.create_archive(label)
            return {"success": True, "archive": result}
        except Exception as e:
            return {"error": str(e)}

    async def _list_debug_archives(self) -> dict:
        """列出所有归档"""
        if not self.brain_jarvis or not self.brain_jarvis.memory_engine:
            return {"error": "memory not available", "archives": []}
        try:
            store = self.brain_jarvis.memory_engine.store
            archives = store.list_archives()
            return {"archives": archives, "total": len(archives)}
        except Exception as e:
            return {"error": str(e), "archives": []}

    async def _restore_debug_archive(self, data: dict) -> dict:
        """从归档恢复记忆"""
        if not self.brain_jarvis or not self.brain_jarvis.memory_engine:
            return {"error": "memory not available"}
        try:
            store = self.brain_jarvis.memory_engine.store
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
        """清空所有记忆"""
        if not self.brain_jarvis or not self.brain_jarvis.memory_engine:
            return {"error": "memory not available"}
        try:
            store = self.brain_jarvis.memory_engine.store
            count = store.get_stats().get("total_memories", 0)
            store.reset_memory()
            return {"success": True, "cleared_count": count}
        except Exception as e:
            return {"error": str(e)}

    async def _handle_command(self, websocket: WebSocket, command: str):
        """处理命令"""
        if command == "start":
            if not self.is_running:
                self.start()
                await websocket.send_json({
                    "type": "event",
                    "data": {
                        "event_type": "SYSTEM",
                        "message": "🚀 JARVIS主动模式已启动",
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
                        "message": "🛑 JARVIS主动模式已停止",
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
        
        print("🚀 启动JARVIS主动运行模式（Web版本）...")
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
    
    def _process_input_direct(self, text: str) -> str:
        """直接在调用线程中处理用户输入（避免事件循环的 asyncio.run 问题）"""
        if not self.brain_jarvis:
            return "⚠️ 大脑引擎未就绪"
        try:
            start = time.time()
            response = self.brain_jarvis.process_input(text)
            elapsed = time.time() - start
            import logging
            logging.getLogger("jarvis").info(f"LLM 响应完成 ({elapsed:.1f}s)")
            return response
        except Exception as e:
            import logging
            logging.getLogger("jarvis").error(f"处理输入出错: {e}")
            return f"❌ 处理出错: {e}"

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
<title>JARVIS 调试面板</title>
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
<div><h1>🔍 JARVIS 调试面板</h1><span class="sub" id="last-update">加载中...</span></div>
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

<div id="panel-memory" class="panel"></div>
<div id="panel-brain" class="panel"></div>
<div id="panel-planning" class="panel"></div>
<div id="panel-system" class="panel"></div>
<div id="panel-search" class="panel"><div class="search-box"><input id="search-input" placeholder="输入搜索关键词..." onkeydown="if(event.key==='Enter')searchMemory()"><button onclick="searchMemory()">搜索</button></div><div id="search-results" class="search-results"></div></div>
<div id="panel-archive" class="panel"></div>

<script>
let data = null;

let memPage = 1, intPage = 1;
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
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.querySelectorAll('.panel').forEach(p => p.classList.remove('active'));
  document.getElementById('panel-' + name).classList.add('active');
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
      alert('&#x2705; 归档成功！\n' + d.archive.archive_id + '\n' + d.archive.memory_count + ' 条记忆');
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
// Auto-refresh every 10s
setInterval(loadData, 10000);
</script>
</body>
</html>"""


def main():
    """主函数"""
    print("="*60)
    print("JARVIS主动运行模式（Web版本）")
    print("="*60)
    print("💡 解决CLI模式下心跳输出干扰用户输入的问题")
    print("💡 提供Web界面，支持实时事件监控")
    print("="*60)
    
    # 创建Web版本的JARVIS
    web_jarvis = WebActiveJARVIS()
    
    # 启动主动模式（非阻塞）
    web_jarvis.start(blocking=False)
    
    # 运行Web服务器
    web_jarvis.run_web()
    
    # 停止主动模式
    web_jarvis.stop()


if __name__ == "__main__":
    main()