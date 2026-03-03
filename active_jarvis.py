"""
JARVIS主动运行模式实现
基于事件驱动架构，类似iOS RunLoop的主动智能体系统
"""

import asyncio
import threading
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from queue import Queue, PriorityQueue
import random


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


class TaskStatusSource(EventSource):
    """任务状态监控事件源"""
    
    def __init__(self, planning_engine=None):
        super().__init__("task_status")
        self.planning_engine = planning_engine
        self.last_check = 0
        
    def poll(self) -> List[Event]:
        """轮询任务状态"""
        events = []
        current_time = time.time()
        
        # 每5秒检查一次
        if current_time - self.last_check < 5:
            return events
        
        self.last_check = current_time
        
        if not self.planning_engine:
            return events
        
        try:
            # 获取活跃任务
            tasks = self.planning_engine.list_active_tasks()
            
            for task in tasks:
                # 检查任务状态
                if task.status in ["failed", "blocked"]:
                    event = Event(
                        event_type=EventType.TASK_STATUS,
                        data={
                            "task_id": task.id,
                            "task_name": task.goal,
                            "status": task.status,
                            "steps_completed": sum(1 for s in task.steps if s.status == "completed"),
                            "total_steps": len(task.steps)
                        },
                        priority=EventPriority.MEDIUM,
                        source=f"task_{task.id}"
                    )
                    events.append(event)
                
                # 检查长时间运行的任务
                if hasattr(task, 'created_at'):
                    time_since_creation = (datetime.now() - task.created_at).total_seconds()
                    if time_since_creation > 300:  # 5分钟
                        event = Event(
                            event_type=EventType.TASK_STATUS,
                            data={
                                "task_id": task.id,
                                "task_name": task.goal,
                                "status": "long_running",
                                "duration_seconds": time_since_creation
                            },
                            priority=EventPriority.LOW,
                            source=f"task_{task.id}"
                        )
                        events.append(event)
                        
        except Exception as e:
            print(f"任务状态监控错误: {e}")
        
        return events


class MemoryUpdateSource(EventSource):
    """记忆更新事件源"""
    
    def __init__(self, memory_store=None):
        super().__init__("memory_update")
        self.memory_store = memory_store
        self.last_update_count = 0
        
    def poll(self) -> List[Event]:
        """轮询记忆更新"""
        events = []
        
        if not self.memory_store:
            return events
        
        try:
            # 模拟检查记忆更新（实际实现需要集成真实记忆系统）
            # 这里只是示例
            pass
            
        except Exception as e:
            print(f"记忆更新监控错误: {e}")
        
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
    
    def __init__(self, jarvis_instance):
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
            return f"⚠️ 任务失败: {data.get('task_name')} (ID: {data.get('task_id')})"
        
        elif data.get("status") == "blocked":
            return f"⏸️  任务阻塞: {data.get('task_name')}"
        
        elif data.get("status") == "long_running":
            minutes = data.get("duration_seconds", 0) / 60
            return f"⏱️  任务长时间运行: {data.get('task_name')} ({minutes:.1f}分钟)"
        
        return "未知任务状态"
    
    def _handle_user_input(self, event: Event) -> str:
        """处理用户输入事件"""
        if not self.jarvis:
            return "JARVIS实例未初始化"
        
        text = event.data.get("text", "")
        return self.jarvis.process_input(text)


class ReminderEventHandler(EventHandler):
    """提醒事件处理器"""
    
    def __init__(self, reminder_manager=None):
        super().__init__("reminder_handler")
        self.reminder_manager = reminder_manager
    
    def can_handle(self, event: Event) -> bool:
        return event.event_type == EventType.TIMER
    
    def handle(self, event: Event) -> Any:
        if not self.reminder_manager:
            return "提醒管理器未初始化"
        
        # 检查提醒触发器
        try:
            triggered_reminders = self.reminder_manager.check_triggers()
            if triggered_reminders:
                results = []
                for reminder in triggered_reminders:
                    # 发送通知
                    if hasattr(self.reminder_manager, 'send_notifications'):
                        self.reminder_manager.send_notifications([reminder])
                    results.append(f"⏰ 提醒: {reminder.title} - {reminder.content}")
                return "\n".join(results)
        except Exception as e:
            return f"提醒检查错误: {e}"
        
        return None


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
        
        return f"未知系统操作: {action}"


class ActiveJARVIS:
    """主动运行模式的JARVIS"""
    
    def __init__(self, legacy_jarvis=None, config: Dict[str, Any] = None):
        """
        初始化主动JARVIS
        
        Args:
            legacy_jarvis: 传统JARVIS实例（用于兼容）
            config: 配置参数
        """
        self.legacy_jarvis = legacy_jarvis
        self.config = self._get_default_config()
        if config:
            self.config.update(config)
        
        # 事件系统
        self.event_sources = {}
        self.event_handlers = {}
        self.event_queue = PriorityQueue()
        self.is_running = False
        self.event_thread = None
        
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
                "heartbeat": {"interval": 1, "enabled": True},
                "task_monitor": {"interval": 5, "enabled": True},
                "reminder_check": {"interval": 60, "enabled": True},
                "memory_cleanup": {"interval": 300, "enabled": True}
            },
            "log_level": "INFO"
        }
    
    def _initialize_components(self):
        """初始化所有组件"""
        # 初始化事件源
        self.event_sources["user_input"] = UserInputSource()
        self.event_sources["timer"] = TimerSource()
        
        if self.legacy_jarvis and hasattr(self.legacy_jarvis, 'planning_engine'):
            self.event_sources["task_status"] = TaskStatusSource(
                self.legacy_jarvis.planning_engine
            )
        
        # 初始化事件处理器
        self.event_handlers["task"] = TaskEventHandler(self.legacy_jarvis)
        self.event_handlers["reminder"] = ReminderEventHandler()
        self.event_handlers["system"] = SystemEventHandler()
        
        # 设置周期性任务
        if self.config["enable_periodic_tasks"]:
            self._setup_periodic_tasks()
    
    def _setup_periodic_tasks(self):
        """设置周期性任务"""
        timer_source = self.event_sources.get("timer")
        if not timer_source:
            return
        
        tasks_config = self.config.get("periodic_tasks", {})
        
        # 心跳任务
        if tasks_config.get("heartbeat", {}).get("enabled"):
            def heartbeat_generator():
                return Event(
                    event_type=EventType.SYSTEM,
                    data={"action": "heartbeat", "timestamp": time.time()},
                    priority=EventPriority.BACKGROUND,
                    source="heartbeat"
                )
            
            timer_source.add_periodic_task(
                interval_seconds=tasks_config["heartbeat"]["interval"],
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
                interval_seconds=tasks_config["task_monitor"]["interval"],
                event_generator=task_monitor_generator,
                name="task_monitor"
            )
        
        # 提醒检查任务
        if tasks_config.get("reminder_check", {}).get("enabled"):
            def reminder_check_generator():
                return Event(
                    event_type=EventType.TIMER,
                    data={"action": "check_reminders", "timestamp": time.time()},
                    priority=EventPriority.MEDIUM,
                    source="reminder_check"
                )
            
            timer_source.add_periodic_task(
                interval_seconds=tasks_config["reminder_check"]["interval"],
                event_generator=reminder_check_generator,
                name="reminder_check"
            )
    
    def start(self, blocking: bool = True):
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
        
        print("🚀 启动JARVIS主动运行模式...")
        print(f"📊 配置: {self.config}")
        
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
                self._handle_event(event)
                processed += 1
            except Exception as e:
                print(f"❌ 处理事件失败: {e}")
                self.stats["events_dropped"] += 1
        
        return processed
    
    def _handle_event(self, event: Event):
        """处理单个事件"""
        try:
            # 查找合适的处理器
            handler = self._find_handler(event)
            if not handler:
                if self.config.get("log_level") == "DEBUG":
                    print(f"⚠️  未找到事件处理器: {event.event_type}")
                return
            
            # 执行处理器
            result = handler.handle(event)
            
            # 记录结果
            if result and self.config.get("log_level") in ["INFO", "DEBUG"]:
                self._log_event_result(event, result)
                
        except Exception as e:
            print(f"❌ 事件处理错误: {e}")
    
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
        else:
            print(f"[{timestamp}] {event_type} ({source}): 已处理")
    
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
        
        if stats.get("start_time"):
            stats["uptime_seconds"] = time.time() - stats["start_time"]
        
        return stats
    
    def run_cli(self):
        """运行交互式CLI（兼容原有接口）"""
        print("\n" + "="*60)
        print("🤖 JARVIS主动运行模式 - 交互式CLI")
        print("="*60)
        print("输入 '退出' 或 'exit' 返回")
        print("输入 '状态' 或 'status' 查看运行状态")
        print("输入 '停止' 或 'stop' 停止主动模式")
        print("="*60 + "\n")
        
        # 确保主动模式已启动
        if not self.is_running:
            self.start(blocking=False)
        
        while True:
            try:
                user_input = input(">>> ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ["退出", "exit", "quit"]:
                    print("返回上级...")
                    break
                
                elif user_input.lower() in ["状态", "status"]:
                    stats = self.get_stats()
                    print(f"📊 运行状态:")
                    print(f"   运行中: {'✅' if stats['is_running'] else '❌'}")
                    print(f"   运行时长: {stats.get('uptime_seconds', 0):.1f}秒")
                    print(f"   处理事件: {stats.get('events_processed', 0)}个")
                    print(f"   事件队列: {stats.get('event_queue_size', 0)}个")
                    continue
                
                elif user_input.lower() in ["停止", "stop"]:
                    self.stop()
                    print("主动运行模式已停止")
                    break
                
                # 处理用户输入
                if self.add_user_input(user_input):
                    print(f"📥 已接收: {user_input}")
                else:
                    print("❌ 无法处理输入")
                
            except KeyboardInterrupt:
                print("\n⏹️  CLI被中断")
                break
            except EOFError:
                print("\n🔚 输入结束")
                break
            except Exception as e:
                print(f"❌ 错误: {e}")


def create_active_jarvis(legacy_jarvis=None, config: Dict[str, Any] = None) -> ActiveJARVIS:
    """
    创建主动JARVIS的便捷函数
    
    Args:
        legacy_jarvis: 传统JARVIS实例
        config: 配置参数
        
    Returns:
        ActiveJARVIS实例
    """
    return ActiveJARVIS(legacy_jarvis, config)


if __name__ == "__main__":
    # 测试代码
    print("🧪 测试主动JARVIS...")
    
    # 创建实例
    active_jarvis = ActiveJARVIS()
    
    # 启动主动模式（非阻塞）
    active_jarvis.start(blocking=False)
    
    # 运行CLI
    active_jarvis.run_cli()
    
    # 停止
    active_jarvis.stop()