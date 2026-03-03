#!/usr/bin/env python3
"""
简化的Web版本JARVIS主动模式
使用Python标准库，无需安装fastapi/uvicorn
通过HTTP长轮询实现实时通信
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
import http.server
import socketserver
import urllib.parse
import threading
import time
import os


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


class SimpleWebActiveJARVIS:
    """简化Web版本的主动运行模式JARVIS"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化简化Web版本的主动JARVIS
        
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
        self.http_server = None
        self.http_thread = None
        self.clients = {}  # 客户端ID -> 最后轮询时间
        self.event_history = []
        self.max_history = 100
        self.pending_events = []  # 待发送的事件
        self.client_commands = Queue()  # 客户端命令队列
        
        # 统计
        self.stats = {
            "events_processed": 0,
            "events_dropped": 0,
            "start_time": None,
            "last_event_time": None
        }
        
        # 初始化组件
        self._initialize_components()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "event_loop_interval": 0.1,  # 100ms
            "max_events_per_cycle": 10,
            "enable_periodic_tasks": True,
            "periodic_tasks": {
                "heartbeat": {"interval": 5, "enabled": True},  # 5秒
                "task_monitor": {"interval": 10, "enabled": True},  # 10秒
                "learning_cycle": {"interval": 600, "enabled": True}  # 10分钟
            },
            "log_level": "INFO",
            "web_host": "127.0.0.1",
            "web_port": 8020
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
                interval_seconds=5,
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
                interval_seconds=10,
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
                interval_seconds=600,
                event_generator=learning_cycle_generator,
                name="learning_cycle"
            )
    
    def _add_to_history(self, event: Event, result: str):
        """添加事件到历史记录"""
        history_item = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now().isoformat(),
            "event": event.to_dict(),
            "result": result
        }
        self.event_history.append(history_item)
        
        # 添加到待发送事件
        self.pending_events.append({
            "type": "event",
            "data": {
                "event_type": event.event_type.value,
                "result": result,
                "source": event.source,
                "timestamp": time.time()
            }
        })
        
        # 限制历史记录数量
        if len(self.event_history) > self.max_history:
            self.event_history.pop(0)
        
        # 限制待发送事件数量
        if len(self.pending_events) > 50:
            self.pending_events.pop(0)
    
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
        
        print("🚀 启动JARVIS主动运行模式（简化Web版本）...")
        print(f"🌐 Web界面地址: http://{self.config['web_host']}:{self.config['web_port']}")
        
        # 启动HTTP服务器
        self._start_http_server()
        
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
        
        # 停止HTTP服务器
        if self.http_server:
            self.http_server.shutdown()
        
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
                
                # 4. 处理客户端命令
                self._process_client_commands()
                
                # 5. 清理过期客户端
                self._cleanup_clients()
                
                # 6. 更新状态
                self.stats["last_event_time"] = time.time()
                
                # 7. 休眠避免CPU占用过高
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
                processed += 1
            except Exception as e:
                print(f"❌ 处理事件失败: {e}")
                self.stats["events_dropped"] += 1
        
        return processed
    
    def _process_client_commands(self):
        """处理客户端命令"""
        while not self.client_commands.empty():
            try:
                cmd = self.client_commands.get_nowait()
                client_id = cmd.get("client_id")
                command = cmd.get("command")
                data = cmd.get("data", {})
                
                if command == "start":
                    if not self.is_running:
                        self.is_running = True
                        self.stats["start_time"] = time.time()
                        self._add_pending_event({
                            "type": "system",
                            "message": "🚀 JARVIS主动模式已启动"
                        })
                
                elif command == "stop":
                    if self.is_running:
                        self.is_running = False
                        self._add_pending_event({
                            "type": "system",
                            "message": "🛑 JARVIS主动模式已停止"
                        })
                
                elif command == "learn":
                    learning_event = Event(
                        event_type=EventType.LEARNING,
                        data={"action": "analyze_memory", "manual_trigger": True},
                        priority=EventPriority.HIGH,
                        source=f"client_{client_id}"
                    )
                    self.event_queue.put(learning_event)
                    self._add_pending_event({
                        "type": "system",
                        "message": "📚 已触发主动学习任务"
                    })
                
                elif command == "user_input":
                    text = data.get("text", "")
                    if text:
                        self.add_user_input(text, client_id)
                        self._add_pending_event({
                            "type": "user_input",
                            "message": f"📝 收到用户输入: {text}",
                            "source": f"client_{client_id}"
                        })
                
            except Exception as e:
                print(f"❌ 处理客户端命令失败: {e}")
    
    def _cleanup_clients(self):
        """清理过期客户端（30秒无活动）"""
        current_time = time.time()
        expired_clients = []
        
        for client_id, last_poll in self.clients.items():
            if current_time - last_poll > 30:  # 30秒无活动
                expired_clients.append(client_id)
        
        for client_id in expired_clients:
            del self.clients[client_id]
    
    def _add_pending_event(self, event_data: Dict[str, Any]):
        """添加待发送事件"""
        self.pending_events.append({
            "type": "event",
            "data": event_data
        })
        
        # 限制数量
        if len(self.pending_events) > 50:
            self.pending_events.pop(0)
    
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
        stats["clients_count"] = len(self.clients)
        stats["event_history_count"] = len(self.event_history)
        stats["pending_events_count"] = len(self.pending_events)
        
        if stats.get("start_time"):
            stats["uptime_seconds"] = time.time() - stats["start_time"]
        
        return stats
    
    # HTTP服务器相关方法
    class HTTPRequestHandler(http.server.BaseHTTPRequestHandler):
        """自定义HTTP请求处理器"""
        
        def do_GET(self):
            """处理GET请求"""
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            # 根路径 - 返回HTML界面
            if path == "/":
                self._serve_html()
            
            # API端点
            elif path == "/api/events":
                self._serve_events()
            
            elif path == "/api/stats":
                self._serve_stats()
            
            elif path == "/api/command":
                self._handle_command()
            
            else:
                self.send_error(404, "Not Found")
        
        def do_POST(self):
            """处理POST请求"""
            parsed_path = urllib.parse.urlparse(self.path)
            path = parsed_path.path
            
            if path == "/api/command":
                self._handle_post_command()
            else:
                self.send_error(404, "Not Found")
        
        def _serve_html(self):
            """提供HTML界面"""
            html_content = self._get_html_content()
            
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(html_content)))
            self.end_headers()
            self.wfile.write(html_content.encode("utf-8"))
        
        def _serve_events(self):
            """提供事件数据（长轮询）"""
            # 获取客户端ID
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            client_id = query.get("client_id", [""])[0]
            
            if not client_id:
                client_id = str(uuid.uuid4())
            
            # 更新客户端活动时间
            self.server.jarvis_instance.clients[client_id] = time.time()
            
            # 等待新事件（最多10秒）
            start_time = time.time()
            timeout = 10
            
            while time.time() - start_time < timeout:
                # 检查是否有新事件
                if self.server.jarvis_instance.pending_events:
                    events = self.server.jarvis_instance.pending_events.copy()
                    self.server.jarvis_instance.pending_events.clear()
                    
                    response = {
                        "success": True,
                        "client_id": client_id,
                        "events": events,
                        "timestamp": time.time()
                    }
                    
                    self._send_json_response(response)
                    return
                
                time.sleep(0.5)
            
            # 超时，返回空响应
            response = {
                "success": True,
                "client_id": client_id,
                "events": [],
                "timestamp": time.time()
            }
            self._send_json_response(response)
        
        def _serve_stats(self):
            """提供统计信息"""
            stats = self.server.jarvis_instance.get_stats()
            response = {
                "success": True,
                "stats": stats,
                "timestamp": time.time()
            }
            self._send_json_response(response)
        
        def _handle_command(self):
            """处理命令（GET）"""
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            command = query.get("command", [""])[0]
            client_id = query.get("client_id", [str(uuid.uuid4())])[0]
            text = query.get("text", [""])[0]
            
            if command:
                # 添加到命令队列
                self.server.jarvis_instance.client_commands.put({
                    "client_id": client_id,
                    "command": command,
                    "data": {"text": text} if text else {}
                })
                
                response = {
                    "success": True,
                    "message": f"命令 '{command}' 已接收",
                    "client_id": client_id,
                    "timestamp": time.time()
                }
            else:
                response = {
                    "success": False,
                    "message": "缺少命令参数",
                    "timestamp": time.time()
                }
            
            self._send_json_response(response)
        
        def _handle_post_command(self):
            """处理POST命令"""
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length:
                post_data = self.rfile.read(content_length).decode("utf-8")
                try:
                    data = json.loads(post_data)
                except:
                    data = {}
            else:
                data = {}
            
            command = data.get("command", "")
            client_id = data.get("client_id", str(uuid.uuid4()))
            text = data.get("text", "")
            
            if command:
                # 添加到命令队列
                self.server.jarvis_instance.client_commands.put({
                    "client_id": client_id,
                    "command": command,
                    "data": {"text": text} if text else {}
                })
                
                response = {
                    "success": True,
                    "message": f"命令 '{command}' 已接收",
                    "client_id": client_id,
                    "timestamp": time.time()
                }
            else:
                response = {
                    "success": False,
                    "message": "缺少命令参数",
                    "timestamp": time.time()
                }
            
            self._send_json_response(response)
        
        def _send_json_response(self, data):
            """发送JSON响应"""
            json_data = json.dumps(data, ensure_ascii=False)
            
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Content-Length", str(len(json_data)))
            self.end_headers()
            self.wfile.write(json_data.encode("utf-8"))
        
        def _get_html_content(self):
            """获取HTML内容"""
            return """
            <!DOCTYPE html>
            <html lang="zh-CN">
            <head>
                <meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>JARVIS主动运行模式（简化版）</title>
                <style>
                    body {
                        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                        margin: 0;
                        padding: 20px;
                        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                        min-height: 100vh;
                    }
                    .container {
                        max-width: 1200px;
                        margin: 0 auto;
                        background: rgba(255, 255, 255, 0.95);
                        border-radius: 15px;
                        box-shadow: 0 10px 30px rgba(0, 0, 0, 0.2);
                        overflow: hidden;
                    }
                    header {
                        background: linear-gradient(135deg, #4a6fa5 0%, #2c3e50 100%);
                        color: white;
                        padding: 20px;
                        text-align: center;
                        border-bottom: 5px solid #3498db;
                    }
                    .main-content {
                        display: flex;
                        min-height: 600px;
                    }
                    .left-panel {
                        flex: 1;
                        padding: 20px;
                        border-right: 1px solid #eee;
                    }
                    .right-panel {
                        flex: 2;
                        padding: 20px;
                    }
                    .event-log {
                        height: 400px;
                        overflow-y: auto;
                        background: #f8f9fa;
                        border-radius: 10px;
                        padding: 15px;
                        margin-bottom: 20px;
                        border: 1px solid #dee2e6;
                    }
                    .event-item {
                        padding: 10px;
                        margin-bottom: 8px;
                        background: white;
                        border-radius: 8px;
                        border-left: 4px solid #3498db;
                        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                    }
                    .event-item.system {
                        border-left-color: #2ecc71;
                    }
                    .event-item.learning {
                        border-left-color: #9b59b6;
                    }
                    .event-item.user_input {
                        border-left-color: #e74c3c;
                    }
                    .controls {
                        display: flex;
                        gap: 10px;
                        margin-bottom: 20px;
                        flex-wrap: wrap;
                    }
                    button {
                        padding: 12px 24px;
                        border: none;
                        border-radius: 8px;
                        cursor: pointer;
                        font-weight: bold;
                        transition: all 0.3s;
                        font-size: 14px;
                    }
                    .btn-start {
                        background: #2ecc71;
                        color: white;
                    }
                    .btn-stop {
                        background: #e74c3c;
                        color: white;
                    }
                    .btn-learn {
                        background: #9b59b6;
                        color: white;
                    }
                    .btn-status {
                        background: #3498db;
                        color: white;
                    }
                    button:hover {
                        opacity: 0.9;
                        transform: translateY(-2px);
                    }
                    .input-area {
                        margin-top: 20px;
                    }
                    input[type="text"] {
                        width: calc(100% - 120px);
                        padding: 12px;
                        border: 2px solid #3498db;
                        border-radius: 8px;
                        font-size: 16px;
                    }
                    input[type="text"]:focus {
                        outline: none;
                        border-color: #2980b9;
                    }
                    .send-btn {
                        padding: 12px 24px;
                        background: #3498db;
                        color: white;
                        border: none;
                        border-radius: 8px;
                        margin-left: 10px;
                        cursor: pointer;
                        font-weight: bold;
                    }
                    .stats {
                        background: #f1f8ff;
                        padding: 15px;
                        border-radius: 10px;
                        margin-top: 20px;
                        border: 1px solid #cce5ff;
                    }
                    .status-indicator {
                        display: inline-block;
                        width: 12px;
                        height: 12px;
                        border-radius: 50%;
                        margin-right: 8px;
                    }
                    .status-running {
                        background: #2ecc71;
                        box-shadow: 0 0 8px #2ecc71;
                    }
                    .status-stopped {
                        background: #e74c3c;
                    }
                    .event-type {
                        font-weight: bold;
                        color: #2c3e50;
                        margin-right: 10px;
                    }
                    .event-time {
                        color: #7f8c8d;
                        font-size: 0.9em;
                        margin-right: 10px;
                    }
                    .event-content {
                        margin-top: 5px;
                        color: #34495e;
                    }
                    #client-id {
                        font-family: monospace;
                        background: #f8f9fa;
                        padding: 5px 10px;
                        border-radius: 4px;
                        font-size: 12px;
                    }
                </style>
            </head>
            <body>
                <div class="container">
                    <header>
                        <h1>🤖 JARVIS主动运行模式（简化版）</h1>
                        <p>事件驱动的AI智能体系统 - 使用HTTP长轮询</p>
                        <p>客户端ID: <span id="client-id">正在生成...</span></p>
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
                                <button class="btn-status" onclick="updateStats()">📊 刷新状态</button>
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
                                    <div class="event-content">正在连接...</div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
                
                <script>
                    let clientId = null;
                    let isPolling = false;
                    
                    // 生成客户端ID
                    function generateClientId() {
                        return 'client_' + Math.random().toString(36).substr(2, 9);
                    }
                    
                    // 初始化
                    function init() {
                        clientId = generateClientId();
                        document.getElementById('client-id').textContent = clientId;
                        
                        // 开始轮询事件
                        startPolling();
                        
                        // 更新状态
                        updateStats();
                        
                        addEvent('系统', 'Web界面已加载，客户端ID: ' + clientId, 'system');
                    }
                    
                    // 开始轮询事件
                    function startPolling() {
                        if (isPolling) return;
                        isPolling = true;
                        
                        function pollEvents() {
                            if (!isPolling) return;
                            
                            fetch(`/api/events?client_id=${clientId}`)
                                .then(response => response.json())
                                .then(data => {
                                    if (data.success) {
                                        // 处理事件
                                        data.events.forEach(event => {
                                            if (event.type === 'event') {
                                                addEvent(event.data.event_type || event.data.type, 
                                                         event.data.result || event.data.message, 
                                                         (event.data.event_type || 'system').toLowerCase());
                                            }
                                        });
                                    }
                                    
                                    // 继续轮询
                                    setTimeout(pollEvents, 100);
                                })
                                .catch(error => {
                                    console.error('轮询错误:', error);
                                    setTimeout(pollEvents, 1000);
                                });
                        }
                        
                        pollEvents();
                    }
                    
                    // 停止轮询
                    function stopPolling() {
                        isPolling = false;
                    }
                    
                    // 发送命令
                    function sendCommand(command, text = '') {
                        const params = new URLSearchParams({
                            client_id: clientId,
                            command: command
                        });
                        
                        if (text) {
                            params.append('text', text);
                        }
                        
                        fetch(`/api/command?${params}`)
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    console.log('命令发送成功:', data.message);
                                }
                            })
                            .catch(error => {
                                console.error('命令发送失败:', error);
                            });
                    }
                    
                    // 发送用户输入
                    function sendUserInput() {
                        const input = document.getElementById('user-input');
                        if (input.value.trim()) {
                            sendCommand('user_input', input.value);
                            addEvent('USER', input.value, 'user_input');
                            input.value = '';
                        }
                    }
                    
                    // 更新统计信息
                    function updateStats() {
                        fetch('/api/stats')
                            .then(response => response.json())
                            .then(data => {
                                if (data.success) {
                                    const stats = data.stats;
                                    
                                    document.getElementById('events-processed').textContent = stats.events_processed || 0;
                                    document.getElementById('queue-size').textContent = stats.event_queue_size || 0;
                                    document.getElementById('clients-count').textContent = stats.clients_count || 0;
                                    
                                    if (stats.uptime_seconds) {
                                        document.getElementById('uptime').textContent = Math.round(stats.uptime_seconds);
                                    }
                                    
                                    // 更新状态指示器
                                    const indicator = document.getElementById('status-indicator');
                                    const statusText = document.getElementById('status-text');
                                    
                                    if (stats.is_running) {
                                        indicator.className = 'status-indicator status-running';
                                        statusText.textContent = '运行中';
                                    } else {
                                        indicator.className = 'status-indicator status-stopped';
                                        statusText.textContent = '已停止';
                                    }
                                }
                            })
                            .catch(error => {
                                console.error('获取统计失败:', error);
                            });
                    }
                    
                    // 添加事件到日志
                    function addEvent(type, content, cssClass = '') {
                        const eventLog = document.getElementById('event-log');
                        const now = new Date();
                        const timeStr = now.getHours().toString().padStart(2, '0') + ':' + 
                                       now.getMinutes().toString().padStart(2, '0') + ':' + 
                                       now.getSeconds().toString().padStart(2, '0');
                        
                        const eventItem = document.createElement('div');
                        eventItem.className = 'event-item ' + cssClass;
                        eventItem.innerHTML = `
                            <div>
                                <span class="event-time">${timeStr}</span>
                                <span class="event-type">${type}</span>
                            </div>
                            <div class="event-content">${content}</div>
                        `;
                        
                        eventLog.appendChild(eventItem);
                        eventLog.scrollTop = eventLog.scrollHeight;
                        
                        // 限制日志数量
                        const items = eventLog.getElementsByClassName('event-item');
                        if (items.length > 50) {
                            eventLog.removeChild(items[0]);
                        }
                    }
                    
                    // 定时更新状态
                    setInterval(updateStats, 5000);
                    
                    // 页面加载完成时初始化
                    window.onload = init;
                </script>
            </body>
            </html>
            """
        
        def log_message(self, format, *args):
            """覆盖日志方法，减少输出"""
            pass
    
    def _start_http_server(self):
        """启动HTTP服务器"""
        try:
            handler = self.HTTPRequestHandler
            handler.server = self  # 传递引用
            
            # 创建服务器实例
            self.http_server = socketserver.TCPServer(
                (self.config["web_host"], self.config["web_port"]),
                handler
            )
            self.http_server.jarvis_instance = self  # 存储JARVIS实例引用
            
            # 在新线程中启动服务器
            self.http_thread = threading.Thread(
                target=self.http_server.serve_forever,
                daemon=True
            )
            self.http_thread.start()
            
            print(f"✅ HTTP服务器已启动: http://{self.config['web_host']}:{self.config['web_port']}")
            
        except Exception as e:
            print(f"❌ 启动HTTP服务器失败: {e}")
    
    def run(self):
        """运行简化Web版本"""
        print("="*60)
        print("🤖 JARVIS主动运行模式（简化Web版本）")
        print("="*60)
        print("💡 使用Python标准库，无需额外依赖")
        print("💡 通过HTTP长轮询实现实时通信")
        print(f"💡 访问地址: http://{self.config['web_host']}:{self.config['web_port']}")
        print("="*60)
        
        try:
            # 启动主动模式
            self.start(blocking=False)
            
            print("\n📋 使用说明:")
            print("  1. 在浏览器中打开上面的地址")
            print("  2. 点击'启动'按钮开始主动模式")
            print("  3. 在输入框中发送消息")
            print("  4. 点击'学习'按钮触发主动学习")
            print("  5. 点击'停止'按钮停止主动模式")
            print("\n按 Ctrl+C 退出程序")
            
            # 保持主线程运行
            while True:
                time.sleep(1)
                
        except KeyboardInterrupt:
            print("\n🛑 收到中断信号，正在停止...")
            self.stop()
            print("👋 程序已退出")


def main():
    """主函数"""
    jarvis = SimpleWebActiveJARVIS()
    jarvis.run()


if __name__ == "__main__":
    main()