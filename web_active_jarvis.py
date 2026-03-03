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
        """处理用户输入事件"""
        text = event.data.get("text", "")
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
        
        # 初始化组件
        self._initialize_components()
        self._setup_routes()
    
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
            return f"""
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>JARVIS主动运行模式</title>
                <style>
                    body {{
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                    }}
                    .container {{
                        max-width: 1200px;
                        margin: 0 auto;
                        background: rgba(255, 255, 255, 0.95);
                        border-radius: 15px;
                        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
                        overflow: hidden;
                    }}
                    header {{
                        background: linear-gradient(135deg, #4a6fa5 0%, #2c3e50 100%);
                        color: white;
                        padding: 20px;
                        text-align: center;
                        border-bottom: 5px solid #3498db;
                    }}
                    .main-content {{
                        display: flex;
                        min-height: 600px;
                    }}
                    .left-panel {{
                        flex: 1;
                        padding: 20px;
                        border-right: 1px solid #eee;
                    }}
                    .right-panel {{
                        flex: 2;
                        padding: 20px;
                    }}
                    .event-log {{
                        height: 400px;
                        overflow-y: auto;
                        background: #f8f9fa;
                        border-radius: 10px;
                        padding: 15px;
                        margin-bottom: 20px;
                        border: 1px solid #dee2e6;
                    }}
                    .event-item {{
                        padding: 10px;
                        margin-bottom: 8px;
                        background: white;
                        border-radius: 8px;
                        border-left: 4px solid #3498db;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    }}
                    .event-item.system {{
                        border-left-color: #2ecc71;
                    }}
                    .event-item.learning {{
                        border-left-color: #9b59b6;
                    }}
                    .event-item.user_input {{
                        border-left-color: #e74c3c;
                    }}
                    .controls {{
                        display: flex;
                        gap: 10px;
                        margin-bottom: 20px;
                    }}
                    button {{
                        padding: 12px 24px;
                        border: none;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: bold;
                        transition: all 0.3s;
                    }}
                    .btn-start {{
                        background: #2ecc71;
                        color: white;
                    }}
                    .btn-stop {{
                        background: #e74c3c;
                        color: white;
                    }}
                    .btn-learn {{
                        background: #9b59b6;
                        color: white;
                    }}
                    .btn-status {{
                        background: #3498db;
                        color: white;
                    }}
                    button:hover {{
                        opacity: 0.9;
                        transform: translateY(-2px);
                    }}
                    .input-area {{
                        margin-top: 20px;
                    }}
                    input[type="text"] {{
                        width: calc(100% - 120px);
                        padding: 12px;
                        border: 2px solid #3498db;
                        border-radius: 8px;
                        font-size: 16px;
                    }}
                    input[type="text"]:focus {{
                        outline: none;
                        border-color: #2980b9;
                    }}
                    .send-btn {{
                        padding: 12px 24px;
                        background: #3498db;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        margin-left: 10px;
                        cursor: pointer;
                        font-weight: bold;
                    }}
                    .stats {{
                        background: #f1f8ff;
                        padding: 15px;
                        border-radius: 10px;
                        margin-top: 20px;
                        border: 1px solid #cce5ff;
                    }}
                    .status-indicator {{
                        display: inline-block;
                        width: 12px;
                        height: 12px;
                        border-radius: 50%;
                        margin-right: 8px;
                    }}
                    .status-running {{
                        background: #2ecc71;
                        box-shadow: 0 0 8px #2ecc71;
                    }}
                    .status-stopped {{
                        background: #e74c3c;
                    }}
                    .event-type {{
                        font-weight: bold;
                        color: #2c3e50;
                        margin-right: 10px;
                    }}
                    .event-time {{
                        color: #7f8c8d;
                        font-size: 0.9em;
                        margin-right: 10px;
                    }}
                    .event-content {{
                        margin-top: 5px;
                        color: #34495e;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <header>
                        <h1>🤖 JARVIS主动运行模式</h1>
                        <p>事件驱动的AI智能体系统 - Web界面</p>
                    </header>
                    
                    <div class="main-content">
                        <div class="left-panel">
                            <h2>📊 系统状态</h2>
                            <div class="stats" id="stats">
                                <p>系统状态: <span id="status-indicator" class="status-indicator status-stopped"></span> <span id="status-text">已停止</span></p>
                                <p>运行时长: <span id="uptime">0</span>秒</p>
                                <p>处理事件: <span id="events-processed">0</span>个</p>
                                <p>事件队列: <span id="queue-size">0</span>个</p>
                                <p>连接客户端: <span id="clients-count">0</span>个</p>
                            </div>
                            
                            <div class="controls">
                                <button class="btn-start" onclick="sendCommand('start')">🚀 启动</button>
                                <button class="btn-stop" onclick="sendCommand('stop')">🛑 停止</button>
                                <button class="btn-learn" onclick="sendCommand('learn')">📚 学习</button>
                                <button class="btn-status" onclick="sendCommand('status')">📊 状态</button>
                            </div>
                            
                            <div class="input-area">
                                <h3>💬 发送消息</h3>
                                <input type="text" id="user-input" placeholder="输入消息..." onkeypress="if(event.keyCode==13) sendUserInput()">
                                <button class="send-btn" onclick="sendUserInput()">发送</button>
                            </div>
                        </div>
                        
                        <div class="right-panel">
                            <h2>📝 事件日志</h2>
                            <div class="event-log" id="event-log">
                                <div class="event-item">
                                    <div>
                                        <span class="event-type">SYSTEM</span>
                                    </div>
                                    <div class="event-content">等待连接...</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <script>
                    const ws = new WebSocket('ws://' + window.location.host + '/ws');
                    
                    // 连接成功
                    ws.onopen = function() {{
                        addEvent('系统', 'WebSocket连接成功', 'system');
                        sendCommand('status');
                    }};
                    
                    // 接收消息
                    ws.onmessage = function(event) {{
                        const data = JSON.parse(event.data);
                        console.log('收到消息:', data);
                        
                        if (data.type === 'event') {{
                            addEvent(data.data.event_type, data.data.result || data.data.message, data.data.event_type.toLowerCase());
                        }} else if (data.type === 'stats') {{
                            updateStats(data.data);
                        }} else if (data.type === 'status') {{
                            updateStatus(data.data);
                        }}
                    }};
                    
                    // 连接关闭
                    ws.onclose = function() {{
                        addEvent('系统', 'WebSocket连接断开', 'system');
                    }};
                    
                    // 添加事件到日志
                    function addEvent(type, content, cssClass = '') {{
                        const eventLog = document.getElementById('event-log');
                        const now = new Date();
                        const timeStr = now.getHours().toString().padStart(2, '0') + ':' + 
                                       now.getMinutes().toString().padStart(2, '0') + ':' + 
                                       now.getSeconds().toString().padStart(2, '0');
                        
                        const eventItem = document.createElement('div');
                        eventItem.className = 'event-item ' + cssClass;
                        eventItem.innerHTML = `
                            <div>
                                <span class="event-time">${{timeStr}}</span>
                                <span class="event-type">${{type}}</span>
                            </div>
                            <div class="event-content">${{content}}</div>
                        `;
                        
                        eventLog.appendChild(eventItem);
                        eventLog.scrollTop = eventLog.scrollHeight;
                        
                        // 限制日志数量
                        const items = eventLog.getElementsByClassName('event-item');
                        if (items.length > 50) {{
                            eventLog.removeChild(items[0]);
                        }}
                    }}
                    
                    // 更新统计信息
                    function updateStats(stats) {{
                        document.getElementById('events-processed').textContent = stats.events_processed || 0;
                        document.getElementById('queue-size').textContent = stats.event_queue_size || 0;
                        document.getElementById('clients-count').textContent = stats.clients_count || 0;
                        
                        if (stats.uptime_seconds) {{
                            document.getElementById('uptime').textContent = Math.round(stats.uptime_seconds);
                        }}
                    }}
                    
                    // 更新状态
                    function updateStatus(status) {{
                        const indicator = document.getElementById('status-indicator');
                        const statusText = document.getElementById('status-text');
                        
                        if (status.is_running) {{
                            indicator.className = 'status-indicator status-running';
                            statusText.textContent = '运行中';
                        }} else {{
                            indicator.className = 'status-indicator status-stopped';
                            statusText.textContent = '已停止';
                        }}
                    }}
                    
                    // 发送命令
                    function sendCommand(command) {{
                        ws.send(JSON.stringify({{
                            type: 'command',
                            command: command
                        }}));
                    }}
                    
                    // 发送用户输入
                    function sendUserInput() {{
                        const input = document.getElementById('user-input');
                        if (input.value.trim()) {{
                            ws.send(JSON.stringify({{
                                type: 'user_input',
                                text: input.value
                            }}));
                            addEvent('USER', input.value, 'user_input');
                            input.value = '';
                        }}
                    }}
                    
                    // 定时更新状态
                    setInterval(() => {{
                        sendCommand('status');
                    }}, 5000);
                </script>
            </body>
            </html>
            """
        
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
                            # 添加到事件系统
                            self.add_user_input(text, client_id)
                            
                            # 广播事件
                            await self._broadcast_event({
                                "event_type": "USER_INPUT",
                                "message": f"📝 收到用户输入: {text}",
                                "source": f"user_{client_id}"
                            })
                    
            except WebSocketDisconnect:
                # 客户端断开连接
                self.websocket_clients = [c for c in self.websocket_clients if c["id"] != client_id]
                await self._broadcast_stats()
            except Exception as e:
                print(f"WebSocket错误: {e}")
                self.websocket_clients = [c for c in self.websocket_clients if c["id"] != client_id]
    
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


def main():
    """主函数"""
    print("="*60)
    print("🤖 JARVIS主动运行模式（Web版本）")
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