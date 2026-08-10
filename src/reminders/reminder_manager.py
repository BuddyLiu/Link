"""
提醒管理器模块

管理所有提醒的创建、更新、删除和触发。
"""

from typing import Dict, Any, List, Optional, Union
from datetime import datetime, timedelta
from enum import Enum
import uuid
import json
import os
from dataclasses import dataclass, field
import sqlite3
from contextlib import contextmanager


class ReminderStatus(Enum):
    """提醒状态"""
    ACTIVE = "active"      # 活跃状态，等待触发
    TRIGGERED = "triggered"  # 已触发，等待处理
    CANCELLED = "cancelled"  # 已取消
    COMPLETED = "completed"  # 已完成
    EXPIRED = "expired"    # 已过期


class ReminderTrigger(Enum):
    """提醒触发器类型"""
    TIME = "time"          # 时间触发
    CONDITION = "condition"  # 条件触发
    LOCATION = "location"  # 位置触发
    EVENT = "event"        # 事件触发


@dataclass
class Reminder:
    """提醒数据结构"""
    id: str
    user_id: str
    title: str
    content: str
    trigger_type: ReminderTrigger
    trigger_config: Dict[str, Any]
    repeat_pattern: str  # once, daily, weekly, monthly, yearly, custom
    status: ReminderStatus
    created_at: datetime
    updated_at: datetime
    next_trigger_time: Optional[datetime] = None
    last_triggered_at: Optional[datetime] = None
    triggered_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "content": self.content,
            "trigger_type": self.trigger_type.value,
            "trigger_config": self.trigger_config,
            "repeat_pattern": self.repeat_pattern,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "next_trigger_time": self.next_trigger_time.isoformat() if self.next_trigger_time else None,
            "last_triggered_at": self.last_triggered_at.isoformat() if self.last_triggered_at else None,
            "triggered_count": self.triggered_count,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Reminder":
        """从字典创建"""
        # 转换字符串为枚举
        trigger_type = ReminderTrigger(data["trigger_type"])
        status = ReminderStatus(data["status"])
        
        # 转换时间字符串为datetime
        created_at = datetime.fromisoformat(data["created_at"])
        updated_at = datetime.fromisoformat(data["updated_at"])
        
        next_trigger_time = None
        if data.get("next_trigger_time"):
            next_trigger_time = datetime.fromisoformat(data["next_trigger_time"])
        
        last_triggered_at = None
        if data.get("last_triggered_at"):
            last_triggered_at = datetime.fromisoformat(data["last_triggered_at"])
        
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            title=data["title"],
            content=data["content"],
            trigger_type=trigger_type,
            trigger_config=data["trigger_config"],
            repeat_pattern=data["repeat_pattern"],
            status=status,
            created_at=created_at,
            updated_at=updated_at,
            next_trigger_time=next_trigger_time,
            last_triggered_at=last_triggered_at,
            triggered_count=data.get("triggered_count", 0),
            metadata=data.get("metadata", {}),
        )


class ReminderManager:
    """提醒管理器主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化提醒管理器
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "enable_active_reminders": True,
            "reminder_check_interval": 60,  # 检查间隔（秒）
            "max_reminders_per_user": 100,
            "reminder_types_enabled": ["time", "condition"],
            "notification_channels": ["cli"],
            "storage_type": "sqlite",  # sqlite, memory, file
            "database_path": "./data/reminders/reminders.db",
            "auto_cleanup_days": 30,  # 自动清理过期提醒的天数
            "max_concurrent_triggers": 10,  # 最大并发触发数
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 组件引用
        self.trigger_checker = None
        self.notification_sender = None
        self.logger = None
        
        # 数据库连接
        self.db_conn = None
        self._initialize_database()
        
        # 状态跟踪
        self.last_check_time = datetime.now()
        self.active_reminders_cache = {}  # 用户ID -> 提醒列表缓存
    
    def set_components(self, trigger_checker=None, notification_sender=None):
        """设置依赖组件"""
        self.trigger_checker = trigger_checker
        self.notification_sender = notification_sender
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def _log(self, level: str, message: str):
        """记录日志"""
        if self.logger:
            if level == "debug":
                self.logger.debug(message)
            elif level == "info":
                self.logger.info(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
    
    def _initialize_database(self):
        """初始化数据库"""
        if self.config["storage_type"] != "sqlite":
            # 内存存储，简化实现
            self.db_conn = None
            self._in_memory_storage = {}
            return
        
        # SQLite数据库
        db_path = self.config["database_path"]
        db_dir = os.path.dirname(db_path)
        if db_dir:  # 裸文件名时无需创建目录
            os.makedirs(db_dir, exist_ok=True)
        
        try:
            self.db_conn = sqlite3.connect(db_path, check_same_thread=False)
            self.db_conn.row_factory = sqlite3.Row
            
            # 创建表
            self._create_tables()
            self._log("info", f"提醒数据库已初始化: {db_path}")
            
        except Exception as e:
            self._log("error", f"初始化数据库失败: {str(e)}")
            # 回退到内存存储
            self.config["storage_type"] = "memory"
            self.db_conn = None
            self._in_memory_storage = {}
    
    def _create_tables(self):
        """创建数据库表"""
        if not self.db_conn:
            return
        
        cursor = self.db_conn.cursor()

        # 创建提醒表（索引需单独 CREATE INDEX，不能写在列定义中）
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                trigger_type TEXT NOT NULL,
                trigger_config TEXT NOT NULL,
                repeat_pattern TEXT NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                next_trigger_time TEXT,
                last_triggered_at TEXT,
                triggered_count INTEGER DEFAULT 0,
                metadata TEXT
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_id ON reminders(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_status ON reminders(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_next_trigger_time ON reminders(next_trigger_time)")

        self.db_conn.commit()
    
    @contextmanager
    def _get_cursor(self):
        """获取数据库游标的上下文管理器"""
        if self.db_conn:
            cursor = self.db_conn.cursor()
            try:
                yield cursor
                self.db_conn.commit()
            finally:
                cursor.close()
        else:
            # 内存存储，不返回游标
            yield None
    
    def add_reminder(self, 
                     user_id: str, 
                     title: str, 
                     content: str, 
                     trigger_type: ReminderTrigger,
                     trigger_config: Dict[str, Any],
                     repeat_pattern: str = "once",
                     metadata: Optional[Dict[str, Any]] = None) -> Optional[Reminder]:
        """
        添加新提醒
        
        Args:
            user_id: 用户ID
            title: 提醒标题
            content: 提醒内容
            trigger_type: 触发器类型
            trigger_config: 触发器配置
            repeat_pattern: 重复模式
            metadata: 元数据
            
        Returns:
            Reminder: 创建的提醒，如果失败则返回None
        """
        # 检查是否启用提醒功能
        if not self.config["enable_active_reminders"]:
            self._log("warning", "提醒功能已禁用")
            return None
        
        # 检查触发器类型是否启用
        if trigger_type.value not in self.config["reminder_types_enabled"]:
            self._log("warning", f"触发器类型 {trigger_type.value} 未启用")
            return None
        
        # 检查用户提醒数量限制
        user_reminders = self.get_user_reminders(user_id)
        if len(user_reminders) >= self.config["max_reminders_per_user"]:
            self._log("warning", f"用户 {user_id} 的提醒数量已达上限")
            return None
        
        # 生成提醒ID
        reminder_id = f"reminder_{uuid.uuid4().hex[:8]}"
        
        # 计算下一次触发时间
        next_trigger_time = self._calculate_next_trigger_time(trigger_type, trigger_config, repeat_pattern)
        
        # 创建提醒对象
        now = datetime.now()
        reminder = Reminder(
            id=reminder_id,
            user_id=user_id,
            title=title,
            content=content,
            trigger_type=trigger_type,
            trigger_config=trigger_config,
            repeat_pattern=repeat_pattern,
            status=ReminderStatus.ACTIVE,
            created_at=now,
            updated_at=now,
            next_trigger_time=next_trigger_time,
            metadata=metadata or {},
        )
        
        # 保存提醒
        if self._save_reminder(reminder):
            self._log("info", f"提醒已添加: {reminder_id} - {title}")
            
            # 清除缓存
            if user_id in self.active_reminders_cache:
                del self.active_reminders_cache[user_id]
            
            return reminder
        else:
            self._log("error", f"保存提醒失败: {reminder_id}")
            return None
    
    def _calculate_next_trigger_time(self, 
                                     trigger_type: ReminderTrigger, 
                                     trigger_config: Dict[str, Any],
                                     repeat_pattern: str) -> Optional[datetime]:
        """计算下一次触发时间"""
        now = datetime.now()
        
        if trigger_type == ReminderTrigger.TIME:
            # 时间触发
            if "datetime" in trigger_config:
                try:
                    trigger_time = datetime.fromisoformat(trigger_config["datetime"])
                    if trigger_time > now:
                        return trigger_time
                except (ValueError, TypeError):
                    pass
            
            elif "time_of_day" in trigger_config:
                # 每天特定时间
                time_str = trigger_config["time_of_day"]
                try:
                    from datetime import time as dt_time
                    hour, minute = map(int, time_str.split(":"))
                    trigger_time = datetime.combine(now.date(), dt_time(hour, minute))
                    if trigger_time <= now:
                        # 如果今天的时间已过，改为明天
                        trigger_time += timedelta(days=1)
                    return trigger_time
                except (ValueError, TypeError):
                    pass
        
        elif trigger_type == ReminderTrigger.CONDITION:
            # 条件触发，由条件检查器决定
            return None
        
        elif trigger_type == ReminderTrigger.LOCATION:
            # 位置触发，由位置服务决定
            return None
        
        elif trigger_type == ReminderTrigger.EVENT:
            # 事件触发，由事件系统决定
            return None
        
        # 默认：立即触发
        return now
    
    def _save_reminder(self, reminder: Reminder) -> bool:
        """保存提醒到存储"""
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    cursor.execute("""
                        INSERT INTO reminders 
                        (id, user_id, title, content, trigger_type, trigger_config, 
                         repeat_pattern, status, created_at, updated_at, next_trigger_time,
                         last_triggered_at, triggered_count, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        reminder.id,
                        reminder.user_id,
                        reminder.title,
                        reminder.content,
                        reminder.trigger_type.value,
                        json.dumps(reminder.trigger_config, ensure_ascii=False),
                        reminder.repeat_pattern,
                        reminder.status.value,
                        reminder.created_at.isoformat(),
                        reminder.updated_at.isoformat(),
                        reminder.next_trigger_time.isoformat() if reminder.next_trigger_time else None,
                        reminder.last_triggered_at.isoformat() if reminder.last_triggered_at else None,
                        reminder.triggered_count,
                        json.dumps(reminder.metadata, ensure_ascii=False),
                    ))
                return True
            except Exception as e:
                self._log("error", f"保存提醒到数据库失败: {str(e)}")
                return False
        else:
            # 内存存储
            if reminder.user_id not in self._in_memory_storage:
                self._in_memory_storage[reminder.user_id] = []
            self._in_memory_storage[reminder.user_id].append(reminder)
            return True
    
    def get_reminder(self, reminder_id: str, user_id: Optional[str] = None) -> Optional[Reminder]:
        """
        获取提醒
        
        Args:
            reminder_id: 提醒ID
            user_id: 用户ID（可选，用于验证权限）
            
        Returns:
            Reminder: 提醒对象，如果不存在则返回None
        """
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    if user_id:
                        cursor.execute(
                            "SELECT * FROM reminders WHERE id = ? AND user_id = ?", 
                            (reminder_id, user_id)
                        )
                    else:
                        cursor.execute("SELECT * FROM reminders WHERE id = ?", (reminder_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        return self._row_to_reminder(row)
            except Exception as e:
                self._log("error", f"从数据库获取提醒失败: {str(e)}")
        
        else:
            # 内存存储
            for user_reminders in self._in_memory_storage.values():
                for reminder in user_reminders:
                    if reminder.id == reminder_id:
                        if user_id is None or reminder.user_id == user_id:
                            return reminder
        
        return None
    
    def _row_to_reminder(self, row) -> Reminder:
        """将数据库行转换为Reminder对象"""
        data = {
            "id": row["id"],
            "user_id": row["user_id"],
            "title": row["title"],
            "content": row["content"],
            "trigger_type": row["trigger_type"],
            "trigger_config": json.loads(row["trigger_config"]),
            "repeat_pattern": row["repeat_pattern"],
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "next_trigger_time": row["next_trigger_time"],
            "last_triggered_at": row["last_triggered_at"],
            "triggered_count": row["triggered_count"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
        }
        
        return Reminder.from_dict(data)
    
    def get_user_reminders(self, user_id: str, status: Optional[ReminderStatus] = None) -> List[Reminder]:
        """
        获取用户的所有提醒
        
        Args:
            user_id: 用户ID
            status: 状态过滤（可选）
            
        Returns:
            List[Reminder]: 提醒列表
        """
        # 检查缓存
        cache_key = f"{user_id}_{status.value if status else 'all'}"
        if cache_key in self.active_reminders_cache:
            return self.active_reminders_cache[cache_key].copy()
        
        reminders = []
        
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    if status:
                        cursor.execute(
                            "SELECT * FROM reminders WHERE user_id = ? AND status = ? ORDER BY created_at DESC", 
                            (user_id, status.value)
                        )
                    else:
                        cursor.execute(
                            "SELECT * FROM reminders WHERE user_id = ? ORDER BY created_at DESC", 
                            (user_id,)
                        )
                    
                    rows = cursor.fetchall()
                    for row in rows:
                        reminders.append(self._row_to_reminder(row))
            except Exception as e:
                self._log("error", f"从数据库获取用户提醒失败: {str(e)}")
        
        else:
            # 内存存储
            if user_id in self._in_memory_storage:
                user_reminders = self._in_memory_storage[user_id]
                if status:
                    reminders = [r for r in user_reminders if r.status == status]
                else:
                    reminders = user_reminders.copy()
        
        # 更新缓存
        self.active_reminders_cache[cache_key] = reminders.copy()
        
        return reminders
    
    def update_reminder(self, 
                        reminder_id: str, 
                        user_id: str,
                        updates: Dict[str, Any]) -> bool:
        """
        更新提醒
        
        Args:
            reminder_id: 提醒ID
            user_id: 用户ID（用于验证权限）
            updates: 更新字段
            
        Returns:
            bool: 是否成功更新
        """
        reminder = self.get_reminder(reminder_id, user_id)
        if not reminder:
            self._log("warning", f"提醒不存在或无权限: {reminder_id}")
            return False
        
        # 应用更新
        updated = False
        
        if "title" in updates:
            reminder.title = updates["title"]
            updated = True
        
        if "content" in updates:
            reminder.content = updates["content"]
            updated = True
        
        if "trigger_config" in updates:
            reminder.trigger_config = updates["trigger_config"]
            # 重新计算触发时间
            reminder.next_trigger_time = self._calculate_next_trigger_time(
                reminder.trigger_type, 
                reminder.trigger_config, 
                reminder.repeat_pattern
            )
            updated = True
        
        if "repeat_pattern" in updates:
            reminder.repeat_pattern = updates["repeat_pattern"]
            updated = True
        
        if "status" in updates:
            try:
                new_status = ReminderStatus(updates["status"])
                reminder.status = new_status
                updated = True
            except ValueError:
                self._log("warning", f"无效的状态值: {updates['status']}")
        
        if "metadata" in updates:
            reminder.metadata.update(updates["metadata"])
            updated = True
        
        if updated:
            reminder.updated_at = datetime.now()
            
            # 保存更新
            if self._update_reminder_in_storage(reminder):
                self._log("info", f"提醒已更新: {reminder_id}")
                
                # 清除缓存
                cache_key = f"{user_id}_all"
                if cache_key in self.active_reminders_cache:
                    del self.active_reminders_cache[cache_key]
                
                return True
        
        return False
    
    def _update_reminder_in_storage(self, reminder: Reminder) -> bool:
        """在存储中更新提醒"""
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    cursor.execute("""
                        UPDATE reminders SET
                            title = ?,
                            content = ?,
                            trigger_config = ?,
                            repeat_pattern = ?,
                            status = ?,
                            updated_at = ?,
                            next_trigger_time = ?,
                            last_triggered_at = ?,
                            triggered_count = ?,
                            metadata = ?
                        WHERE id = ? AND user_id = ?
                    """, (
                        reminder.title,
                        reminder.content,
                        json.dumps(reminder.trigger_config, ensure_ascii=False),
                        reminder.repeat_pattern,
                        reminder.status.value,
                        reminder.updated_at.isoformat(),
                        reminder.next_trigger_time.isoformat() if reminder.next_trigger_time else None,
                        reminder.last_triggered_at.isoformat() if reminder.last_triggered_at else None,
                        reminder.triggered_count,
                        json.dumps(reminder.metadata, ensure_ascii=False),
                        reminder.id,
                        reminder.user_id,
                    ))
                return True
            except Exception as e:
                self._log("error", f"更新数据库提醒失败: {str(e)}")
                return False
        else:
            # 内存存储，对象已更新
            return True
    
    def delete_reminder(self, reminder_id: str, user_id: str) -> bool:
        """
        删除提醒
        
        Args:
            reminder_id: 提醒ID
            user_id: 用户ID（用于验证权限）
            
        Returns:
            bool: 是否成功删除
        """
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    cursor.execute(
                        "DELETE FROM reminders WHERE id = ? AND user_id = ?", 
                        (reminder_id, user_id)
                    )
                    deleted = cursor.rowcount > 0
            except Exception as e:
                self._log("error", f"从数据库删除提醒失败: {str(e)}")
                return False
        else:
            # 内存存储
            deleted = False
            if user_id in self._in_memory_storage:
                for i, reminder in enumerate(self._in_memory_storage[user_id]):
                    if reminder.id == reminder_id:
                        self._in_memory_storage[user_id].pop(i)
                        deleted = True
                        break
        
        if deleted:
            self._log("info", f"提醒已删除: {reminder_id}")
            
            # 清除缓存
            cache_key = f"{user_id}_all"
            if cache_key in self.active_reminders_cache:
                del self.active_reminders_cache[cache_key]
            
            return True
        else:
            self._log("warning", f"提醒不存在或无权限: {reminder_id}")
            return False
    
    def check_triggers(self) -> List[Reminder]:
        """
        检查所有待触发的提醒
        
        Returns:
            List[Reminder]: 需要触发的提醒列表
        """
        if not self.config["enable_active_reminders"]:
            return []
        
        current_time = datetime.now()
        
        # 检查时间间隔
        time_since_last = (current_time - self.last_check_time).total_seconds()
        if time_since_last < self.config["reminder_check_interval"]:
            return []
        
        self.last_check_time = current_time
        self._log("debug", f"检查提醒触发器...")
        
        triggered_reminders = []
        
        # 获取所有活跃提醒
        active_reminders = self._get_all_active_reminders()
        
        for reminder in active_reminders:
            # 检查是否应该触发
            should_trigger = self._should_trigger_now(reminder, current_time)
            
            if should_trigger:
                # 标记为已触发
                reminder.status = ReminderStatus.TRIGGERED
                reminder.last_triggered_at = current_time
                reminder.triggered_count += 1
                reminder.updated_at = current_time
                
                # 处理重复提醒
                if reminder.repeat_pattern != "once":
                    # 计算下一次触发时间
                    reminder.next_trigger_time = self._calculate_next_repeat_time(
                        reminder, current_time
                    )
                    reminder.status = ReminderStatus.ACTIVE
                else:
                    reminder.next_trigger_time = None
                
                # 保存更新
                self._update_reminder_in_storage(reminder)
                
                triggered_reminders.append(reminder)
                
                self._log("info", f"提醒已触发: {reminder.id} - {reminder.title}")
        
        return triggered_reminders
    
    def _get_all_active_reminders(self) -> List[Reminder]:
        """获取所有活跃提醒"""
        reminders = []
        
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    cursor.execute(
                        "SELECT * FROM reminders WHERE status = 'active' ORDER BY next_trigger_time ASC"
                    )
                    
                    rows = cursor.fetchall()
                    for row in rows:
                        reminders.append(self._row_to_reminder(row))
            except Exception as e:
                self._log("error", f"获取活跃提醒失败: {str(e)}")
        
        else:
            # 内存存储
            for user_reminders in self._in_memory_storage.values():
                for reminder in user_reminders:
                    if reminder.status == ReminderStatus.ACTIVE:
                        reminders.append(reminder)
        
        return reminders
    
    def _should_trigger_now(self, reminder: Reminder, current_time: datetime) -> bool:
        """检查提醒是否应该现在触发"""
        if reminder.status != ReminderStatus.ACTIVE:
            return False
        
        # 检查时间触发器
        if reminder.trigger_type == ReminderTrigger.TIME:
            if not reminder.next_trigger_time:
                return False
            
            # 检查是否到达触发时间（到期即触发，防止60s轮询漏掉1s窗口）
            time_diff = (current_time - reminder.next_trigger_time).total_seconds()
            return time_diff >= 0
        
        # 其他类型的触发器由相应的检查器处理
        elif self.trigger_checker:
            return self.trigger_checker.check_condition(reminder, current_time)
        
        return False
    
    def _calculate_next_repeat_time(self, reminder: Reminder, current_time: datetime) -> Optional[datetime]:
        """计算重复提醒的下一次触发时间"""
        if reminder.repeat_pattern == "daily":
            return current_time + timedelta(days=1)
        
        elif reminder.repeat_pattern == "weekly":
            return current_time + timedelta(weeks=1)
        
        elif reminder.repeat_pattern == "monthly":
            # 简单实现：下个月的同一天
            try:
                next_month = current_time.month + 1
                next_year = current_time.year
                if next_month > 12:
                    next_month = 1
                    next_year += 1
                return current_time.replace(year=next_year, month=next_month)
            except ValueError:
                # 如果下个月没有这一天，则使用当月最后一天
                from calendar import monthrange
                _, last_day = monthrange(next_year, next_month)
                return current_time.replace(year=next_year, month=next_month, day=last_day)
        
        elif reminder.repeat_pattern == "yearly":
            return current_time.replace(year=current_time.year + 1)
        
        # 自定义重复模式（简化实现）
        elif reminder.repeat_pattern == "custom":
            # 从trigger_config中获取自定义设置
            config = reminder.trigger_config
            if "repeat_interval_days" in config:
                days = config["repeat_interval_days"]
                return current_time + timedelta(days=days)
        
        # 默认：不重复
        return None
    
    def send_notifications(self, reminders: List[Reminder]) -> Dict[str, Any]:
        """
        发送提醒通知
        
        Args:
            reminders: 需要通知的提醒列表
            
        Returns:
            Dict[str, Any]: 发送结果统计
        """
        if not self.notification_sender:
            self._log("warning", "通知发送器未设置，无法发送通知")
            return {"sent": 0, "failed": len(reminders), "details": []}
        
        results = {
            "sent": 0,
            "failed": 0,
            "details": []
        }
        
        for reminder in reminders:
            try:
                # 发送通知
                success = self.notification_sender.send(
                    reminder=reminder,
                    channels=self.config["notification_channels"]
                )
                
                if success:
                    if reminder.repeat_pattern == "once":
                        # 一次性提醒：标记为已完成
                        reminder.status = ReminderStatus.COMPLETED
                        reminder.updated_at = datetime.now()
                        self._update_reminder_in_storage(reminder)
                    else:
                        # 重复提醒：保持 ACTIVE（check_triggers 已计算下次触发时间），
                        # 勿覆盖为 COMPLETED，否则重复提醒在首次发送后即失效
                        self._log("debug", f"重复提醒 {reminder.id} 保持活跃，下次: {reminder.next_trigger_time}")

                    results["sent"] += 1
                    results["details"].append({
                        "reminder_id": reminder.id,
                        "status": "sent",
                        "timestamp": datetime.now().isoformat()
                    })

                    self._log("info", f"提醒通知已发送: {reminder.id}")
                else:
                    # 发送失败：重置为 ACTIVE，使下次 check_triggers 能重新取出重试，
                    # 避免状态卡在 TRIGGERED 导致通知被静默丢弃
                    if reminder.status == ReminderStatus.TRIGGERED:
                        reminder.status = ReminderStatus.ACTIVE
                        reminder.updated_at = datetime.now()
                        self._update_reminder_in_storage(reminder)
                    results["failed"] += 1
                    results["details"].append({
                        "reminder_id": reminder.id,
                        "status": "failed",
                        "timestamp": datetime.now().isoformat()
                    })

                    self._log("warning", f"发送提醒通知失败，已重置为活跃待重试: {reminder.id}")

            except Exception as e:
                # 异常时也重置为 ACTIVE 以便重试
                try:
                    if reminder.status == ReminderStatus.TRIGGERED:
                        reminder.status = ReminderStatus.ACTIVE
                        reminder.updated_at = datetime.now()
                        self._update_reminder_in_storage(reminder)
                except Exception as storage_e:
                    self._log("error", f"重置提醒状态失败: {reminder.id} - {storage_e}")
                results["failed"] += 1
                results["details"].append({
                    "reminder_id": reminder.id,
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.now().isoformat()
                })

                self._log("error", f"发送提醒通知时出错: {reminder.id} - {str(e)}")
        
        return results
    
    def cleanup_expired_reminders(self, days_threshold: Optional[int] = None) -> int:
        """
        清理过期提醒
        
        Args:
            days_threshold: 过期天数阈值（默认使用配置）
            
        Returns:
            int: 清理的提醒数量
        """
        if days_threshold is None:
            days_threshold = self.config.get("auto_cleanup_days", 30)
        
        cutoff_date = datetime.now() - timedelta(days=days_threshold)
        cleaned_count = 0
        
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    # 清理过期提醒（创建时间早于阈值且状态为已完成或已取消）
                    cursor.execute("""
                        DELETE FROM reminders 
                        WHERE created_at < ? 
                        AND status IN ('completed', 'cancelled')
                    """, (cutoff_date.isoformat(),))
                    
                    cleaned_count = cursor.rowcount
            except Exception as e:
                self._log("error", f"清理过期提醒失败: {str(e)}")
                return 0
        else:
            # 内存存储
            for user_id, reminders in list(self._in_memory_storage.items()):
                to_remove = []
                for i, reminder in enumerate(reminders):
                    if (reminder.status in [ReminderStatus.COMPLETED, ReminderStatus.CANCELLED] and
                        reminder.created_at < cutoff_date):
                        to_remove.append(i)
                
                # 反向删除，避免索引问题
                for i in reversed(to_remove):
                    reminders.pop(i)
                    cleaned_count += 1
                
                # 如果用户没有提醒了，删除用户条目
                if not reminders:
                    del self._in_memory_storage[user_id]
        
        if cleaned_count > 0:
            self._log("info", f"清理了 {cleaned_count} 个过期提醒")
            # 清除所有缓存
            self.active_reminders_cache.clear()
        
        return cleaned_count
    
    def get_stats(self) -> Dict[str, Any]:
        """获取提醒统计信息"""
        stats = {
            "total_reminders": 0,
            "by_status": {},
            "by_trigger_type": {},
            "by_user": {},
            "storage_type": self.config["storage_type"],
        }
        
        if self.db_conn:
            # SQLite存储
            try:
                with self._get_cursor() as cursor:
                    # 总数
                    cursor.execute("SELECT COUNT(*) as count FROM reminders")
                    stats["total_reminders"] = cursor.fetchone()["count"]
                    
                    # 按状态统计
                    cursor.execute("SELECT status, COUNT(*) as count FROM reminders GROUP BY status")
                    for row in cursor.fetchall():
                        stats["by_status"][row["status"]] = row["count"]
                    
                    # 按触发器类型统计
                    cursor.execute("SELECT trigger_type, COUNT(*) as count FROM reminders GROUP BY trigger_type")
                    for row in cursor.fetchall():
                        stats["by_trigger_type"][row["trigger_type"]] = row["count"]
                    
                    # 按用户统计
                    cursor.execute("SELECT user_id, COUNT(*) as count FROM reminders GROUP BY user_id")
                    for row in cursor.fetchall():
                        stats["by_user"][row["user_id"]] = row["count"]
                    
            except Exception as e:
                self._log("error", f"获取统计信息失败: {str(e)}")
        
        else:
            # 内存存储
            for user_id, reminders in self._in_memory_storage.items():
                stats["by_user"][user_id] = len(reminders)
                stats["total_reminders"] += len(reminders)
                
                for reminder in reminders:
                    # 状态统计
                    status = reminder.status.value
                    stats["by_status"][status] = stats["by_status"].get(status, 0) + 1
                    
                    # 触发器类型统计
                    trigger_type = reminder.trigger_type.value
                    stats["by_trigger_type"][trigger_type] = stats["by_trigger_type"].get(trigger_type, 0) + 1
        
        return stats
    
    def close(self):
        """关闭管理器，释放资源"""
        if self.db_conn:
            self.db_conn.close()
            self.db_conn = None
        
        self._log("info", "提醒管理器已关闭")


# 便捷函数
def create_reminder_manager(config: Dict[str, Any] = None) -> ReminderManager:
    """
    创建提醒管理器的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        提醒管理器实例
    """
    return ReminderManager(config)