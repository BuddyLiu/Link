#!/usr/bin/env python3
"""
LINK主动运行模式的Web版本
提供Web界面，避免CLI模式下心跳输出干扰用户输入
"""

import asyncio
import threading
import time
import sys
import os
import base64
import hashlib
import hmac
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, List, Optional, Callable, Union
from dataclasses import dataclass, field
from queue import Queue, PriorityQueue
import json
import uuid

# 路径修复：直接运行本文件时，确保 src 优先于项目根（避免根目录 config/ 遮蔽 src/config）
_current_dir = os.path.dirname(os.path.abspath(__file__))
if _current_dir not in sys.path:
    sys.path.insert(0, _current_dir)
_src_dir = os.path.join(_current_dir, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

# Web框架
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response, JSONResponse
import uvicorn


# ── edge-tts 文字转语音（后端合成 mp3，前端 <audio> 播放） ──
# 用微软神经语音引擎替代浏览器 speechSynthesis：断句语义级、英文地道、中英分块各念各的。
# edge-tts 未安装/合成失败时，前端自动回退浏览器 speechSynthesis，不影响现有功能。
# 音色/语速默认值在下方，用户可在 /settings 页「语音」页签修改（存 data/settings/tts.json，
# 该目录已 gitignore，不入库）。默认放慢 10% 更接近真人聊天节奏。
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

# 语言 → 默认微软神经音色（与页面 voice-lang 下拉一一对应）
_TTS_VOICES = {
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "zh-TW": "zh-TW-HsiaoChenNeural",
    "en-US": "en-US-AriaNeural",
}
# 语言 → 默认语速（edge-tts 百分比；None 用微软默认。放慢 10% 更自然）
_TTS_RATES = {
    "zh-CN": "-10%",
    "zh-TW": "-10%",
    "en-US": "-10%",
}
# 设置页可选音色候选（voice_id, 显示名）——由 GET /api/tts-settings 下发给前端下拉
_TTS_VOICE_CANDIDATES: Dict[str, List[tuple]] = {
    "zh-CN": [
        ("zh-CN-XiaoxiaoNeural", "女声 · 晓晓（自然）"),
        ("zh-CN-XiaoyiNeural", "女声 · 晓伊（活泼）"),
        ("zh-CN-YunxiNeural", "男声 · 云希（少年）"),
        ("zh-CN-YunjianNeural", "男声 · 云健（沉稳）"),
        ("zh-CN-YunyangNeural", "男声 · 云扬（播音）"),
    ],
    "zh-TW": [
        ("zh-TW-HsiaoChenNeural", "女声 · 曉臻"),
        ("zh-TW-HsiaoYuNeural", "男声 · 曉雨"),
    ],
    "en-US": [
        ("en-US-AriaNeural", "Female · Aria"),
        ("en-US-JennyNeural", "Female · Jenny"),
        ("en-US-GuyNeural", "Male · Guy"),
        ("en-US-AndrewNeural", "Male · Andrew"),
    ],
}
_TTS_CACHE = {}       # key=lang|voice|rate|text → mp3 bytes（LRU 简单淘汰）
_TTS_CACHE_MAX = 200


def _tts_settings_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "data", "settings", "tts.json")


def load_tts_settings() -> Dict[str, Dict[str, str]]:
    """读取音色设置（data/settings/tts.json）；缺省/损坏时回退默认值"""
    out = {"voices": dict(_TTS_VOICES), "rates": dict(_TTS_RATES)}
    try:
        if os.path.exists(_tts_settings_path()):
            with open(_tts_settings_path(), encoding="utf-8") as f:
                saved = json.load(f) or {}
            out["voices"].update(saved.get("voices") or {})
            out["rates"].update(saved.get("rates") or {})
    except Exception as e:
        print(f"读取音色设置失败: {e}")
    return out


def _is_valid_rate(r: str) -> bool:
    """edge-tts 语速格式校验：±N%（如 -10%、+25%）"""
    import re as _re
    return bool(_re.fullmatch(r"[+-]?\d{1,3}%", r or ""))


def save_tts_settings(data: dict) -> Dict[str, Dict[str, str]]:
    """保存音色设置：只收候选名单内的音色，语速校验 % 格式，坏值一律回退默认"""
    voices, rates = {}, {}
    for lang in _TTS_VOICES:
        cand = {c[0] for c in _TTS_VOICE_CANDIDATES.get(lang, [])}
        v = (data.get("voices") or {}).get(lang)
        voices[lang] = v if v in cand else _TTS_VOICES[lang]
        r = (data.get("rates") or {}).get(lang) or ""
        rates[lang] = r if _is_valid_rate(r) else _TTS_RATES[lang]
    out = {"voices": voices, "rates": rates}
    try:
        os.makedirs(os.path.dirname(_tts_settings_path()), exist_ok=True)
        with open(_tts_settings_path(), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存音色设置失败: {e}")
        raise
    return out


def _tts_cache_key(text: str, lang: str, voice: str, rate: str) -> str:
    return "|".join((lang, voice, rate, text))


def synthesize_tts(text: str, lang: str = "zh-CN",
                   voice: Optional[str] = None,
                   rate: Optional[str] = None) -> bytes:
    """用 edge-tts 合成 mp3，返回音频字节；失败抛异常（前端会回退 speechSynthesis）。
    voice/rate 不传时读取 tts.json（设置页可改）；设置页试听可显式覆盖单个语言。"""
    if not EDGE_TTS_AVAILABLE:
        raise RuntimeError("edge-tts 未安装")
    cfg = load_tts_settings()
    voice = voice or cfg["voices"].get(lang, _TTS_VOICES.get(lang, "zh-CN-XiaoxiaoNeural"))
    rate = rate or cfg["rates"].get(lang) or None
    key = _tts_cache_key(text, lang, voice, rate or "")
    cached = _TTS_CACHE.get(key)
    if cached is not None:
        return cached
    chunks: list = []

    async def _collect():
        kw = {}
        if rate:
            kw["rate"] = rate
        communicate = edge_tts.Communicate(text, voice, **kw)
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])

    # sync 路由跑在 FastAPI 线程池，线程内无事件循环，asyncio.run 安全
    asyncio.run(_collect())
    mp3 = b"".join(chunks)
    if not mp3:
        raise RuntimeError("edge-tts 合成结果为空")
    if len(_TTS_CACHE) >= _TTS_CACHE_MAX:
        _TTS_CACHE.pop(next(iter(_TTS_CACHE)))
    _TTS_CACHE[key] = mp3
    return mp3


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
    
    def _get_brain(self):
        """获取 LINK 主实例（含反思/学习引擎）"""
        return getattr(self.link, "brain_link", None) if self.link else None

    def _analyze_memory_patterns(self) -> str:
        """分析记忆模式，并触发一次周期反思（Periodic Review）"""
        try:
            brain = self._get_brain()
            memory = getattr(brain, "memory_engine", None) if brain else None
            stats = {}
            if memory and memory.store:
                try:
                    stats = memory.store.get_stats()
                except Exception:
                    pass
            mem_count = stats.get("total_memories", 0)

            # 触发一次周期反思，沉淀失败经验到知识库
            reflect_msg = ""
            refl_engine = getattr(brain, "reflection_engine", None) if brain else None
            if refl_engine is not None:
                try:
                    import time as _t
                    task_id = f"periodic_{int(_t.time())}"
                    from src.reflection.reflection_engine import ReflectionTrigger
                    result = refl_engine.reflect(
                        task_id,
                        {"status": "success", "note": "periodic review"},
                        ReflectionTrigger.PERIODIC_REVIEW,
                        context={"memory_count": mem_count},
                    )
                    if result is not None:
                        reflect_msg = f"，沉淀 {len(getattr(result, 'suggestions', []))} 条改进建议"
                except Exception:
                    pass

            # 用知识库统计展示学习成果
            stats_msg = ""
            ku = getattr(brain, "knowledge_updater", None) if brain else None
            if ku is not None:
                try:
                    kstats = ku.get_knowledge_stats()
                    n = kstats.get("total_entries", 0) if isinstance(kstats, dict) else 0
                    stats_msg = f"，知识库 {n} 条"
                except Exception:
                    pass

            return f"⚡ 记忆模式分析完成：记忆 {mem_count} 条{stats_msg}{reflect_msg}"
        except Exception as e:
            return f"❌ 记忆分析失败: {e}"

    def _learn_new_skill(self, skill_name: str) -> str:
        """学习新技能（交给 LINK 大脑引擎，结果存入记忆）"""
        if not skill_name:
            skill_name = "通用任务处理"
        try:
            brain = self._get_brain()
            if brain is not None:
                result = brain._handle_learning_request(skill_name)
                return f"🎓 学习技能: {skill_name}\n{result[:200]}"
            return f"🎓 开始学习新技能: {skill_name}"
        except Exception as e:
            return f"❌ 技能学习失败: {e}"

    def _optimize_performance(self) -> str:
        """优化性能：基于反思统计输出学习/改进概览"""
        try:
            brain = self._get_brain()
            lm = getattr(brain, "learning_module", None) if brain else None
            refl = getattr(brain, "reflection_engine", None) if brain else None
            learn_stats = {}
            if lm is not None:
                try:
                    learn_stats = lm.get_learning_stats()
                except Exception:
                    pass
            refl_stats = {}
            if refl is not None:
                try:
                    refl_stats = refl.get_reflection_stats()
                except Exception:
                    pass
            n_learn = learn_stats.get("total_learnings", 0) if isinstance(learn_stats, dict) else 0
            n_refl = refl_stats.get("total_reflections", 0) if isinstance(refl_stats, dict) else 0
            return f"⚡ 性能优化完成：学习 {n_learn} 条，反思 {n_refl} 次"
        except Exception as e:
            return f"❌ 性能优化失败: {e}"

    def _learn_user_preferences(self) -> str:
        """学习用户偏好：从记忆中检索偏好类记忆"""
        try:
            brain = self._get_brain()
            memory = getattr(brain, "memory_engine", None) if brain else None
            prefs = []
            if memory and memory.store:
                try:
                    from src.memory.memory_entry import MemoryType
                    all_mem = memory.store.get_all_memories(limit=200) or []
                    for m in all_mem:
                        if getattr(m, "memory_type", None) == MemoryType.PREFERENCE:
                            prefs.append(getattr(m, "content", ""))
                        elif getattr(m, "memory_type", None) is not None and "preference" in str(getattr(m, "memory_type", "")).lower():
                            prefs.append(getattr(m, "content", ""))
                    if not prefs and all_mem:
                        # 退化：从 type_counts 判断
                        stats = memory.store.get_stats()
                        tc = stats.get("type_counts", {}) if isinstance(stats, dict) else {}
                        if isinstance(tc, dict):
                            prefs.append(f"偏好记忆 {tc.get('preference', 0)} 条")
                except Exception:
                    pass
            if prefs:
                return f"👤 用户偏好学习完成：发现 {len(prefs)} 条偏好\n" + "\n".join(f"- {p[:60]}" for p in prefs[:5])
            return "👤 用户偏好学习完成：暂无明确偏好记忆"
        except Exception as e:
            return f"❌ 用户偏好学习失败: {e}"


class ReminderEventHandler(EventHandler):
    """提醒事件处理器（Web 版：触发时广播到 WebSocket 客户端）"""

    def __init__(self, reminder_manager=None, broadcast_cb=None):
        super().__init__("reminder_handler")
        self.reminder_manager = reminder_manager
        self.broadcast_cb = broadcast_cb

    def can_handle(self, event: Event) -> bool:
        return event.event_type == EventType.TIMER

    def handle(self, event: Event) -> Any:
        if not self.reminder_manager:
            return "提醒管理器未初始化"
        try:
            triggered = self.reminder_manager.check_triggers()
            if not triggered:
                return None
            results = []
            for reminder in triggered:
                title = getattr(reminder, "title", "提醒")
                content = getattr(reminder, "content", "")
                results.append(f"⏰ {title}: {content}")
                # 广播到 WebSocket 客户端
                if self.broadcast_cb:
                    try:
                        self.broadcast_cb({
                            "event_type": "REMINDER",
                            "message": f"⏰ {title}: {content}",
                        })
                    except Exception:
                        pass
            # 发送桌面/CLI 通知
            try:
                self.reminder_manager.send_notifications(triggered)
            except Exception as e:
                results.append(f"(通知发送失败: {e})")
            return "\n".join(results)
        except Exception as e:
            return f"提醒检查错误: {e}"


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
    voice: bool = False  # 语音触发轮次：要求模型附『播报：』总结


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

    async def submit(self, text: str, voice: bool = False) -> TaskItem:
        """提交新任务，放入队列，返回 TaskItem"""
        task = TaskItem(text=text, voice=voice)
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
        # 讯飞识别会话（client_id → (音频队列, 会话任务)）
        self._xfyun_queues: Dict[str, Any] = {}
        
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
        
        # 初始化提醒系统
        self.reminder_manager = None
        try:
            from src.reminders.reminder_manager import create_reminder_manager
            from src.reminders.trigger_checker import create_trigger_checker
            from src.reminders.notification_sender import create_notification_sender
            rem_config = {
                "enable_active_reminders": True,
                "reminder_check_interval": 60,
                "notification_channels": ["cli", "desktop"],
                "storage_type": "sqlite",
                "database_path": "./data/reminders/reminders.db",
            }
            self.reminder_manager = create_reminder_manager(rem_config)
            trigger_checker = create_trigger_checker(rem_config)
            # 注入记忆源（供条件触发查询用户偏好/事实）
            try:
                mem_engine = getattr(self.brain_link, "memory_engine", None)
                mem_store = getattr(mem_engine, "store", None) if mem_engine else None
                if mem_store:
                    trigger_checker.set_components(memory_store=mem_store)
            except Exception:
                pass
            self.reminder_manager.set_components(
                trigger_checker=trigger_checker,
                notification_sender=create_notification_sender(rem_config)
            )
        except Exception as e:
            print(f"⚠️  提醒系统初始化失败: {e}")

        # 初始化事件处理器
        self.event_handlers["task"] = TaskEventHandler(self)
        self.event_handlers["system"] = SystemEventHandler()
        self.event_handlers["learning"] = LearningEventHandler(self)
        self.event_handlers["reminder"] = ReminderEventHandler(
            reminder_manager=self.reminder_manager,
            broadcast_cb=self._broadcast_reminder
        )
        
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
/* Chat box：左右分屏（用户消息左列 / LINK 回复右列） */
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
#scroll-nav.collapsed .nav-content{height:0;overflow:hidden;opacity:0;pointer-events:none}
#scroll-nav .nav-content{display:flex;flex-direction:column;gap:8px;opacity:0;pointer-events:none;transition:opacity .2s,height .2s}
#scroll-nav.expanded .nav-content{opacity:1;pointer-events:auto;height:auto}
#scroll-nav.expanded .nav-toggle{display:none}
#scroll-nav .nav-content button{width:36px;height:36px;border-radius:50%;border:1.5px solid rgba(255,255,255,.35);background:rgba(13,13,20,.8);color:rgba(255,255,255,.7);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;backdrop-filter:blur(4px)}
#scroll-nav .nav-content button:hover{transform:scale(1.2);border-color:rgba(255,255,255,.6);background:rgba(99,102,241,.2)}
#scroll-nav .nav-content button.scroll-hidden{opacity:0;pointer-events:none}
.msg{margin-bottom:20px;display:flex;flex-direction:column;max-width:85%}
.msg.user{align-self:flex-start;align-items:flex-start}
.msg.assistant{align-self:flex-start;align-items:flex-start}
.msg .bubble{width:100%;padding:10px 16px;border-radius:12px;font-size:14px;line-height:1.5;word-break:break-word;position:relative}
.msg.user .bubble{background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border-bottom-left-radius:4px}
.msg.assistant .bubble{background:#13131f;color:#d4d4e6;border:1px solid #1a1a2e;border-bottom-left-radius:4px}
.msg .time{font-size:10px;color:#6366f1;opacity:.5;margin-top:4px;padding:0 4px;letter-spacing:.5px}
.msg.user .time{text-align:left}
/* Input area */
.input-area{flex-shrink:0;padding:12px 20px;background:#0d0d14;border-top:1px solid #1a1a2e;display:flex;justify-content:center}
.input-area textarea{flex:1;padding:10px 14px;background:#13131f;border:1px solid rgba(255,255,255,.25);border-radius:8px;font-size:13px;outline:none;color:#e0e0e0;transition:border-color .2s;resize:none;font-family:inherit;line-height:1.5;max-height:120px;min-height:40px}
.input-area textarea::placeholder{color:#4a4a6a}
.input-area textarea:focus{border-color:#6366f1}
.input-area button{padding:10px 20px;background:#6366f1;color:#fff;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all .2s;align-self:flex-end;height:40px}
.input-area button:hover{background:#4f46e5}
.input-area button:disabled{background:#1a1a2e;color:#4a4a6a;cursor:not-allowed}
.input-area .send-hint{font-size:10px;color:#4a4a6a;align-self:flex-end;margin:0 8px 4px 0;white-space:nowrap;user-select:none}
/* Thinking 活跃动画（流式思考进行中） */
.think-active .think-scroll-wrap{border:1px solid rgba(99,102,241,.45);box-shadow:0 0 12px rgba(99,102,241,.08) inset}
.think-active summary{animation:thinkPulse 1.6s ease-in-out infinite}
@keyframes thinkPulse{0%,100%{color:#6366f1}50%{color:#a5b4fc}}
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
/* 思考内容滚动视图：max 200px，超出自动滚动吸附底部 */
.think-scroll-wrap{position:relative;max-height:200px;overflow-y:auto;overscroll-behavior:contain}
.think-scroll-wrap .think-content{padding:4px 10px 8px}
/* 思考字数统计 + 展开按钮 */
.think-meta{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 10px 6px;font-size:10px;color:#6b7280;border-top:1px dashed rgba(99,102,241,.15);margin-top:2px}
.think-count{user-select:none}
.think-expand-btn{background:none;border:1px solid rgba(99,102,241,.3);color:#6366f1;border-radius:4px;padding:1px 8px;font-size:10px;cursor:pointer;transition:all .15s;white-space:nowrap}
.think-expand-btn:hover{background:rgba(99,102,241,.1);border-color:#6366f1}
.think-expand-btn:active{transform:scale(.96)}
/* 展开模式：按真实高度展示 */
.think-scroll-wrap.expanded{max-height:none}
/* Status bar */
#status-bar{background:#0d0d14;border-bottom:1px solid #1a1a2e;padding:0 max(20px, calc(50% - 420px));font-size:11px}
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
.perm-grant-row{display:flex;align-items:center;cursor:pointer;color:#a5b4fc !important;font-size:12px !important;text-transform:none !important;letter-spacing:0 !important;padding:8px 0}
.perm-grant-row:hover{color:#c7d2fe !important}
#perm-grant-dir{margin-top:4px;background:rgba(99,102,241,.08) !important;border-color:rgba(99,102,241,.4) !important;color:#a5b4fc !important}

/* Toast */
#toast{position:fixed;top:16px;left:50%;transform:translateX(-50%);z-index:2000;background:#13131f;border:1px solid #1a1a2e;border-radius:10px;padding:10px 20px;color:#e0e0e0;font-size:13px;box-shadow:0 4px 20px rgba(0,0,0,.5);opacity:0;transition:opacity .3s,transform .3s;pointer-events:none}
#toast.show{opacity:1;transform:translateX(-50%) translateY(0)}
.modal-actions{display:flex;gap:8px;margin-top:18px}
.modal-btn{padding:10px 20px;border-radius:8px;font-size:13px;font-weight:500;cursor:pointer;border:none;transition:all .15s;flex:1}
.modal-btn.confirm{background:#6366f1;color:#fff}
.modal-btn.confirm:hover{background:#4f46e5}
.modal-btn.deny{background:#0d0d14;color:#9ca3af;border:1px solid #1a1a2e}
.modal-btn.deny:hover{color:#ef4444;border-color:#ef4444}
/* 问卷弹窗 */
.ob-modal{position:fixed;inset:0;background:rgba(0,0,0,.6);backdrop-filter:blur(4px);display:none;align-items:center;justify-content:center;z-index:3000}
.ob-modal.show{display:flex}
.ob-box{background:#13131f;border:1px solid #1a1a2e;border-radius:14px;width:min(640px,92vw);max-height:86vh;overflow:hidden;display:flex;flex-direction:column;box-shadow:0 20px 60px rgba(0,0,0,.5)}
.ob-head{padding:18px 24px;border-bottom:1px solid #1a1a2e}
.ob-head h3{margin:0;font-size:17px;color:#e0e0e0}
.ob-head p{margin:4px 0 0;font-size:12px;color:#6b7280}
.ob-body{flex:1;overflow-y:auto;padding:20px 24px}
.ob-step{display:none}
.ob-step.active{display:block}
.ob-q{margin-bottom:14px}
.ob-q label{display:block;font-size:13px;color:#c0c0c0;margin-bottom:6px}
.ob-q label .ob-desc{display:block;font-size:11px;color:#6b7280;margin-top:2px}
.ob-q input[type=text],.ob-q textarea{width:100%;background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;color:#e0e0e0;padding:10px 12px;font-size:13px;box-sizing:border-box;outline:none;transition:border-color .15s}
.ob-q input[type=text]:focus,.ob-q textarea:focus{border-color:#6366f1}
.ob-q textarea{min-height:70px;resize:vertical}
.ob-q .ob-chips{display:flex;flex-wrap:wrap;gap:8px}
.ob-chip{border:1px solid #1a1a2e;border-radius:20px;padding:6px 14px;font-size:12px;color:#9ca3af;cursor:pointer;background:#0d0d14;transition:all .15s;user-select:none}
.ob-chip:hover{border-color:#6366f1;color:#e0e0e0}
.ob-chip.sel{background:rgba(99,102,241,.15);border-color:#6366f1;color:#a5b4fc}
.ob-nav{display:flex;justify-content:space-between;padding:14px 24px;border-top:1px solid #1a1a2e;gap:8px}
.ob-btn{background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;color:#9ca3af;padding:9px 20px;font-size:13px;cursor:pointer;transition:all .15s}
.ob-btn:hover{border-color:#6366f1;color:#e0e0e0}
.ob-btn.primary{background:#6366f1;border-color:#6366f1;color:#fff}
.ob-btn.primary:hover{background:#4f46e5}
.ob-btn:disabled{opacity:.4;cursor:not-allowed}
.ob-dots{display:flex;gap:5px;justify-content:center;padding:10px 0 0}
.ob-dot{width:6px;height:6px;border-radius:50%;background:#1a1a2e;transition:background .2s}
.ob-dot.cur{background:#6366f1}
.ob-opt{margin-bottom:12px}
.ob-opt label{display:flex;gap:10px;align-items:flex-start;cursor:pointer;padding:10px 12px;border:1px solid #1a1a2e;border-radius:8px;background:#0d0d14;transition:all .15s}
.ob-opt label:hover{border-color:#6366f1}
.ob-opt input{accent-color:#6366f1;margin-top:2px}
.ob-opt label.sel{border-color:#6366f1;background:rgba(99,102,241,.08)}
.ob-progress{height:3px;background:#1a1a2e}
.ob-progress-inner{height:100%;background:linear-gradient(90deg,#6366f1,#8b5cf6);transition:width .3s;width:0}
/* Voice bar：语音对话（聆听线 + 思考线 + 播报线） */
.voice-bar{flex-shrink:0;background:#0d0d14;border-top:1px solid #1a1a2e;padding:8px max(20px, calc(50% - 420px));display:flex;gap:10px;align-items:center;flex-wrap:wrap}
.voice-btn{width:38px;height:38px;border-radius:50%;border:1.5px solid rgba(255,255,255,.25);background:#13131f;color:rgba(255,255,255,.85);font-size:16px;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:all .2s;line-height:1}
.voice-btn:hover{border-color:#6366f1;transform:scale(1.08)}
.voice-btn.off{color:rgba(255,255,255,.45)}
.voice-btn.active{border-color:#6366f1}
.voice-btn:disabled{opacity:.4;cursor:not-allowed;transform:none;animation:none}
/* 三态脉冲：聆听=红 / 思考=蓝 / 播报=绿（仅 opacity+transform，compositor 友好） */
.voice-btn.listening{background:rgba(239,68,68,.18);border-color:#ef4444;color:#fca5a5;animation:voicePulse 1.2s ease-in-out infinite}
.voice-btn.thinking{background:rgba(99,102,241,.18);border-color:#6366f1;color:#a5b4fc;animation:voicePulse 1.6s ease-in-out infinite}
.voice-btn.speaking{background:rgba(34,197,94,.18);border-color:#22c55e;color:#86efac;animation:voicePulse .9s ease-in-out infinite}
@keyframes voicePulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.55;transform:scale(.92)}}
.voice-mute{width:32px;height:32px;border-radius:8px;border:1px solid #1a1a2e;background:#13131f;color:rgba(255,255,255,.7);font-size:14px;cursor:pointer;transition:all .2s;line-height:1}
.voice-mute:hover{border-color:#6366f1;color:#fff}
.voice-mute.off{opacity:.45}
.voice-bar select{background:#13131f;border:1px solid #1a1a2e;border-radius:6px;color:#9ca3af;font-size:11px;padding:4px 6px;outline:none;cursor:pointer}
.voice-bar select:focus{border-color:#6366f1}
#voice-status{font-size:11px;color:#6b7280;white-space:nowrap}
.voice-interim{font-size:11px;color:#22c55e;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:380px;flex:1;min-width:0}
</style>
</head>
<body>
<div class="header">
<h1>LINK</h1>
<div>
<a href="javascript:void(0)" id="mode-btn" onclick="toggleExecMode()" title="任务执行模式">&#x2696;&#xFE0F; 手动</a>
<a href="javascript:void(0)" onclick="showTasks()" title="查看任务">&#x1F4CB; 任务</a>
<a href="javascript:void(0)" onclick="openOnboarding()" title="填写问卷，让LINK更了解你">&#x1F4DD; 问卷</a>
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
<div id="status-token">Token: 加载中...</div>
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
<div class="voice-bar">
<button id="voice-toggle" class="voice-btn off" title="语音对话：开/关麦克风（持续聆听）">&#x1F399;&#xFE0F;</button>
<button id="voice-mute" class="voice-mute" title="语音播报：开/静音">&#x1F50A;</button>
<select id="voice-lang" title="识别与播报语言">
<option value="zh-CN" selected>中文</option>
<option value="en-US">English</option>
<option value="zh-TW">&#x7E41;&#x9AD4;</option>
</select>
<span id="voice-status">语音未开启</span>
<span id="voice-interim" class="voice-interim"></span>
</div>
<div class="input-area">
<div style="width:100%;max-width:820px;display:flex;gap:8px;margin:0 auto">
<textarea id="input" placeholder="输入消息...（Enter 发送，Shift+Enter 换行）" autofocus rows="1"></textarea>
<span class="send-hint" id="send-hint">Enter 发送</span>
<button id="send-btn" onclick="send()">发送</button>
</div>
</div>

<script>
const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
const userColumn = document.getElementById('user-column');
const assistantColumn = document.getElementById('assistant-column');
const columnDivider = document.getElementById('column-divider');
const input = document.getElementById('input');
const sendBtn = document.getElementById('send-btn');
const TYPE_SPEED = 30; // ms per character
var historyPage = 1, historyLoading = false, historyEnd = false;

// WebSocket 自动重连：断线后指数退避重试，避免页面失去交互能力
var _wsReconnectTimer = null;
var _wsReconnectAttempts = 0;

function reconnectWS() {
  if (_wsReconnectTimer) { clearTimeout(_wsReconnectTimer); _wsReconnectTimer = null; }
  if (_wsReconnectAttempts >= 5) {
    addMessage('system', '⚠️ 多次重连失败，请手动刷新页面');
    return;
  }
  var delay = Math.min(1000 * Math.pow(2, _wsReconnectAttempts), 8000);
  _wsReconnectAttempts++;
  addMessage('system', '连接断开，' + (delay / 1000) + 's 后自动重连...');
  _wsReconnectTimer = setTimeout(function() {
    addMessage('system', '正在重新连接...');
    window.location.reload();
  }, delay);
}

ws.onopen = () => { _wsReconnectAttempts = 0; addMessage('system', '已连接到 LINK'); loadHistory(); updateStatus(); };
ws.onclose = () => { addMessage('system', '连接已断开'); reconnectWS(); };
ws.onerror = () => { /* onclose 会触发重连，此处避免重复提示 */ };

function fmtToken(n) {
  if (n >= 10000) return (n / 10000).toFixed(1) + '万';
  return String(n);
}

async function updateStatus() {
  try {
    var ctrl = new AbortController();
    var _stTimer = setTimeout(function(){ ctrl.abort(); }, 8000);
    var r = await fetch('/api/debug', {signal: ctrl.signal});
    clearTimeout(_stTimer);
    var d = await r.json();
    var b = d.brain || {};
    var m = d.memory || {};
    var config = b.config || {};
    var provider = config.model_provider || '?';
    var model = config.model_name || '?';
    var health = (b.health || {}).overall_status || '?';
    var memStats = (m.stats || {});
    var totalMem = memStats.total_memories || 0;
    if (memStats.graph) totalMem += ' (' + memStats.graph.nodes + '图)';
    var uptime = d.web ? d.web.uptime + 's' : '?';
    document.getElementById('status-model').innerHTML =
      '<span style="color:#6366f1">' + provider + '</span> / ' + model + ' [' + health + ']';
    document.getElementById('status-memory').innerHTML = totalMem + ' 条记忆';
    var ts = (d.brain || {}).token_stats || {};
    var tokenEl = document.getElementById('status-token');
    if (ts.total) {
      var avgStr = ts.avg ? ' / 均' + ts.avg : '';
      tokenEl.innerHTML = 'Token: ' + fmtToken(ts.total) + '（' + ts.calls + ' 次调用' + avgStr + '）';
    } else {
      tokenEl.innerHTML = 'Token: 0';
    }
    document.getElementById('status-session').innerHTML = '运行 ' + uptime;
  } catch(e) {
    // 状态刷新失败：状态栏提示连接中断，避免静默显示过期数据
    var el = document.getElementById('status-model');
    if (el) el.innerHTML = '<span style="color:#ef4444">⚠️ 连接中断</span>';
  }
}
setInterval(updateStatus, 10000);

// ── 任务执行模式切换 ──
async function loadExecMode() {
  try {
    var ctrl = new AbortController();
    var _mt = setTimeout(function(){ ctrl.abort(); }, 8000);
    var r = await fetch('/api/execution-mode', {signal: ctrl.signal});
    clearTimeout(_mt);
    var d = await r.json();
    var mode = d.mode || 'manual';
    var btn = document.getElementById('mode-btn');
    if (btn) {
      btn.textContent = mode === 'auto' ? '⚙️ 自动' : '⚙️ 手动';
      btn.style.color = mode === 'auto' ? '#22c55e' : '';
    }
  } catch(e) { /* 失败时保持默认手动模式 */ }
}
async function toggleExecMode() {
  var btn = document.getElementById('mode-btn');
  var cur = (btn && btn.textContent.indexOf('自动') >= 0) ? 'auto' : 'manual';
  var next = cur === 'auto' ? 'manual' : 'auto';
  try {
    var r = await fetch('/api/execution-mode', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({mode: next})
    });
    var d = await r.json();
    addMessage('system', d.message || '已切换');
    loadExecMode();
  } catch(e) { addMessage('system', '切换失败: ' + e); }
}
// ── 任务监控 ──
async function showTasks() {
  try {
    var r = await fetch('/api/tasks');
    var d = await r.json();
    var tasks = d.tasks || [];
    if (!tasks.length) { addMessage('system', '📭 当前没有任务'); return; }
    var lines = ['📋 任务列表：'];
    tasks.forEach(function(t, i) {
      var bar = '▓'.repeat(Math.round(t.progress / 20)) + '░'.repeat(5 - Math.round(t.progress / 20));
      lines.push((i+1) + '. [' + t.status + '] ' + t.goal);
      lines.push('   ' + bar + ' ' + t.progress + '% (' + t.completed_steps + '/' + t.total_steps + ' 步)');
      if (t.current_step) lines.push('   🔄 当前步骤: ' + t.current_step);
      if (t.last_result) lines.push('   📄 最近结果: ' + t.last_result.replace(/\\n/g, ' ').slice(0, 60));
    });
    addMessage('system', lines.join('\\n'));
  } catch(e) { addMessage('system', '任务查询失败: ' + e); }
}
loadExecMode();
checkOnboarding();

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
var _streamTyped = 0;      // 打字机已打出的字符数
var _streamTimer = null;   // 打字机 tick 定时器
var _streamRenderCounter = 0; // 渲染节流计数器（长内容降低渲染频率）
var _reasoningSpeed = 0;   // 思考内容接收速率（字符/tick，用于联动打字速度）
var _reasoningLastLen = 0; // 上次思考接收的字符数
var _streamAborted = false; // 流式终止标志：ASSISTANT 完成时置位，阻止残余 tick

// ── 流式打字机：速度跟随生成节奏动态调节 ──
// 核心：思考内容返回越快 → 答案打字越快；思考生成慢 → 答案打字慢（等思考）。
// 用"积压量"和"思考接收速率"两个信号共同驱动。
function streamTypeTick() {
  _streamTimer = null;
  // 流式已终止（ASSISTANT 完成/新消息开始）→ 丢弃残余 tick，避免竞态
  if (_streamAborted) return;
  var sb = document.getElementById('stream-bubble');
  if (!sb) { _streamTyped = 0; return; }
  var total = streamContentBuf.length;
  var pending = total - _streamTyped;

  if (pending <= 0) {
    // 已打完但 LLM 还没返回更多 → 慢等（生成慢）
    _streamTimer = setTimeout(streamTypeTick, 70);
    return;
  }

  // 动态步长：积压越多，每 tick 打的字符越多
  var step = 1;
  if (pending > 1500) step = 30;
  else if (pending > 900) step = 20;
  else if (pending > 600) step = 12;
  else if (pending > 300) step = 6;
  else if (pending > 120) step = 3;
  else if (pending > 50) step = 2;

  _streamTyped = Math.min(total, _streamTyped + step);

  // 渲染性能优化：内容很长时降低渲染频率（每 N 次 tick 渲染一次），
  // 避免长回复时每次全量 marked.parse 导致卡顿
  _streamRenderCounter = (_streamRenderCounter || 0) + 1;
  var renderEvery = 1;
  if (total > 8000) renderEvery = 4;
  else if (total > 3000) renderEvery = 3;
  else if (total > 1200) renderEvery = 2;

  if (_streamRenderCounter % renderEvery === 0 || _streamTyped >= total) {
    try { sb.innerHTML = renderMarkdownPartial(streamContentBuf.slice(0, _streamTyped)) + '<span class="cursor"></span>'; }
    catch(e) { sb.textContent = streamContentBuf.slice(0, _streamTyped) + '|'; }
    if (isNearBottom()) assistantColumn.scrollTop = assistantColumn.scrollHeight;
  }

  // 动态间隔：
  //   - 积压大（生成快跟上了）→ 间隔短，快速打
  //   - 思考还在快速接收 → 间隔短（追赶思考节奏）
  //   - 思考接收慢 → 间隔长（慢打，等思考/答案自然返回）
  var delay;
  if (pending > 500 || _reasoningSpeed > 3) delay = 8;
  else if (pending > 150 || _reasoningSpeed > 1) delay = 12;
  else if (pending > 40) delay = 18;
  else delay = 28;
  _streamTimer = setTimeout(streamTypeTick, delay);
}

// 记录思考接收速率（在 reasoning_chunk 中调用）
function trackReasoningSpeed(rc) {
  var len = (rc && rc.textContent) ? rc.textContent.length : _reasoningLastLen;
  var delta = len - _reasoningLastLen;
  // delta 大 → 思考生成快；delta 小 → 思考生成慢
  _reasoningSpeed = delta > 50 ? 4 : (delta > 10 ? 2 : 0.5);
  _reasoningLastLen = len;
}

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
    _pendingPermDir = d.suggest_dir || null;
    var isCmd = d.resource_type === 'command';
    document.getElementById('perm-resource-type').textContent =
      isCmd ? '命令执行' : '文件操作';
    document.getElementById('perm-resource').textContent = d.resource;
    var modeMap = {'read':'读取','write':'写入','execute':'执行','read_write':'读写'};
    document.getElementById('perm-mode').textContent = modeMap[d.mode] || d.mode;
    document.getElementById('perm-duration').querySelectorAll('button').forEach(function(btn) {
      btn.classList.toggle('active', btn.dataset.duration === 'once');
    });
    // 目录授权区：仅文件请求显示，且始终显示（目录继承是修复重点）
    var grantRow = document.getElementById('perm-grant-dir');
    var grantCb = document.getElementById('perm-grant-dir-cb');
    var grantLabel = document.getElementById('perm-grant-dir-label');
    if (!isCmd && _pendingPermDir) {
      grantCb.checked = false;
      grantRow.style.display = 'none';
      grantLabel.textContent = _pendingPermDir;
      document.querySelector('.perm-grant-row').style.display = 'block';
    } else {
      grantCb.checked = false;
      grantRow.style.display = 'none';
      document.querySelector('.perm-grant-row').style.display = 'none';
    }
    document.getElementById('permission-modal').style.display = 'flex';
    return;
  }

  // 推理内容流式到达
  if (d.type === 'reasoning_chunk') {
    if (voiceState !== 'off') setVoiceState('thinking');
    if (!document.getElementById('stream-reasoning')) {
      removeTyping();
      // 包一层 .msg.thinking 容器，避免 details 直接作为对话列的
      // flex 子项导致 open 内容区高度塌陷（overflow:hidden + flex 子项 bug）
      var thinkMsg = document.createElement('div');
      thinkMsg.className = 'msg thinking';
      thinkMsg.id = 'stream-reasoning-msg';
      var det = document.createElement('details');
      det.id = 'stream-reasoning';
      det.open = true;
      det.className = 'thinking';
      det.style.cssText = 'margin:2px 0 4px;background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;overflow:hidden';
      var sum = document.createElement('summary');
      sum.textContent = '思考过程';
      sum.style.cssText = 'cursor:pointer;color:#6366f1;padding:6px 10px;font-size:11px;user-select:none';
      var wrap = document.createElement('div');
      wrap.className = 'think-scroll-wrap';
      wrap.id = 'stream-reasoning-wrap';
      var con = document.createElement('div');
      con.className = 'think-content';
      con.id = 'stream-reasoning-content';
      con.style.cssText = 'color:#6b7280;line-height:1.6;white-space:pre-wrap;font-size:11px';
      wrap.appendChild(con);
      var meta = document.createElement('div');
      meta.className = 'think-meta';
      var countEl = document.createElement('span');
      countEl.className = 'think-count';
      countEl.id = 'stream-reasoning-count';
      countEl.textContent = '0 字';
      var expandBtn = document.createElement('button');
      expandBtn.className = 'think-expand-btn';
      expandBtn.textContent = '展开全部';
      expandBtn.style.display = 'none';
      expandBtn.id = 'stream-reasoning-expand';
      expandBtn.onclick = function() {
        var isExpanded = wrap.classList.toggle('expanded');
        expandBtn.textContent = isExpanded ? '收起' : '展开全部';
        if (!isExpanded) wrap.scrollTop = wrap.scrollHeight;
      };
      var copyThinkBtn = document.createElement('button');
      copyThinkBtn.className = 'think-expand-btn';
      copyThinkBtn.textContent = '复制思考';
      copyThinkBtn.id = 'stream-reasoning-copy';
      // 注意：直接捕获 con 元素而非 getElementById —— ASSISTANT 完成时会清掉
      // stream-reasoning-content 的 id，靠 id 查询的话完成后按钮会拿到空内容
      copyThinkBtn.onclick = function() {
        copyText(con.textContent, copyThinkBtn);
      };
      var speakThinkBtn = document.createElement('button');
      speakThinkBtn.className = 'think-expand-btn';
      speakThinkBtn.textContent = '🔊 朗读';
      speakThinkBtn.onclick = function() {
        speakTextAloud(con.textContent, speakThinkBtn);
      };
      meta.appendChild(countEl);
      meta.appendChild(copyThinkBtn);
      meta.appendChild(expandBtn);
      det.appendChild(sum); det.appendChild(wrap); det.appendChild(meta);
      thinkMsg.appendChild(det);
      var typingEl = assistantColumn.querySelector('.typing');
      if (typingEl) assistantColumn.insertBefore(thinkMsg, typingEl);
      else assistantColumn.appendChild(thinkMsg);
      // 思考活跃标记：提示用户思考进行中
      det.classList.add('think-active');
    }
    var rc = document.getElementById('stream-reasoning-content');
    if (rc) rc.textContent += d.data;
    var rw = document.getElementById('stream-reasoning-wrap');
    if (rw) {
      if (!rw.classList.contains('expanded')) rw.scrollTop = rw.scrollHeight;
      var _rcEl = rw.querySelector('.think-content');
      var _cnt = document.getElementById('stream-reasoning-count');
      if (_cnt && _rcEl) _cnt.textContent = _rcEl.textContent.length + ' 字';
      var _ex = document.getElementById('stream-reasoning-expand');
      if (_ex && rw.scrollHeight > rw.clientHeight + 4) _ex.style.display = '';
    }
    // 记录思考接收速率 → 驱动答案打字速度联动
    trackReasoningSpeed(rc);
    scrollToBottom();
    return;
  }

  // 生成内容流式到达（打字机显示，速度随生成节奏动态调节）
  if (d.type === 'content_chunk') {
    removeTyping();
    if (!streamContentId) {
      streamContentBuf = '';
      _streamTyped = 0;
      _streamRenderCounter = 0;
      _streamAborted = false;
      if (_streamTimer) { clearTimeout(_streamTimer); _streamTimer = null; }
      var div = document.createElement('div');
      div.className = 'msg assistant';
      div.id = 'stream-msg';
      var bubble = document.createElement('div');
      bubble.className = 'bubble';
      bubble.id = 'stream-bubble';
      div.appendChild(bubble);
      assistantColumn.appendChild(div);
      scrollToBottom();
      streamContentId = 'stream-msg';
    }
    streamContentBuf += d.data;
    // 注意：播报不随内容流走（那样会把全文都念出来）。语音模式只播服务端
    // 生成的『播报：』一句话总结（spoken 事件），不再逐句喂 TTS。
    // 启动/继续打字机（积压会驱动 tick）
    if (!_streamTimer) _streamTimer = setTimeout(streamTypeTick, 10);
    return;
  }

  // ── 讯飞识别引擎事件 ──
  if (d.type === 'voice_caps') {
    // 服务端握手：讯飞可用 → xfyun，否则回退浏览器引擎
    sttEngine = (d.data && d.data.stt === 'xfyun') ? 'xfyun' : 'browser';
    return;
  }
  if (d.type === 'voice_partial') {
    if (sttEngine === 'xfyun') showInterim(d.data);
    return;
  }
  if (d.type === 'voice_final') {
    if (sttEngine !== 'xfyun') return;
    var _ft = (d.data || '').trim();
    if (xfDiscardFinal) { xfDiscardFinal = false; clearInterim(); return; } // 回声结果丢弃
    if (voiceState === 'off') return;
    if (_ft) { clearInterim(); sendVoiceTranscript(_ft); } // 复用思考线
    return;
  }
  if (d.type === 'voice_error') {
    if (sttEngine !== 'xfyun' || voiceState === 'off') return;
    showToast('讯飞识别出错，已回退浏览器识别: ' + (d.data || ''));
    xfStop();
    sttEngine = 'browser';
    setVoiceState('off');
    startListening(); // 用浏览器引擎继续聆听
    return;
  }

  // 语音播报句到达（服务端从回复末尾剥离的『播报：』一句话总结，先于 ASSISTANT 发送）
  if (d.type === 'spoken') {
    spokenReceived = true;
    feedSpoken(d.data);
    return;
  }

  // 完整助手回复（替换流式内容 / 无流式时打字机）
  if (d.type === 'event' && d.data.event_type === 'ASSISTANT') {
    removeTyping();
    onAssistantDone((d.data && d.data.result) || ''); // 语音线收尾：发 pending / 兜底播报
    var reasoning = d.data.reasoning || '';
    var result = d.data.result || '';

    // 停止流式打字机，补全未打出的剩余内容（终止标志阻止残余 tick）
    _streamAborted = true;
    if (_streamTimer) { clearTimeout(_streamTimer); _streamTimer = null; }
    // 移除思考活跃动画
    var _actDet = document.getElementById('stream-reasoning');
    if (_actDet) _actDet.classList.remove('think-active');

    var streamEl = document.getElementById('stream-msg');
    if (streamEl) {
      var finalBubble = streamEl.querySelector('.bubble');
      if (finalBubble) {
        finalBubble.innerHTML = renderMarkdown(result);
        assistantColumn.scrollTop = assistantColumn.scrollHeight;
      }
      if (!streamEl.querySelector('.copy-btn')) {
        var copyBtn = document.createElement('button');
        copyBtn.className = 'copy-btn visible';
        copyBtn.textContent = '复制';
        copyBtn.onclick = function() {
          navigator.clipboard.writeText(result).then(function() {
            showToast('已复制');
          });
        };
        streamEl.appendChild(copyBtn);
        var speakBtn = document.createElement('button');
        speakBtn.className = 'copy-btn visible';
        speakBtn.textContent = '🔊 朗读';
        speakBtn.onclick = function() { speakTextAloud(result, speakBtn); };
        streamEl.appendChild(speakBtn);
      }
      // 实时回复添加反馈按钮（👍/👎）
      if (!streamEl.querySelector('.feedback-btns')) {
        addFeedbackBtns(streamEl, result, reasoning);
      }
      // 清除 ID，防止下一条消息 getElementById 命中旧元素
      streamEl.removeAttribute('id');
      var _bub = streamEl.querySelector('.bubble');
      if (_bub) _bub.removeAttribute('id');
      // 清除思考区所有相关 id（含子元素），避免下一条消息命中旧元素
      var _rs = document.getElementById('stream-reasoning');
      if (_rs) _rs.removeAttribute('id');
      ['stream-reasoning-msg', 'stream-reasoning-wrap', 'stream-reasoning-content',
       'stream-reasoning-count', 'stream-reasoning-expand',
       'stream-reasoning-copy'].forEach(function(rid) {
        var el = document.getElementById(rid);
        if (el) el.removeAttribute('id');
      });
      streamContentId = null;
      _streamTyped = 0;
      // 流式结束，恢复 smooth 滚动（历史加载等场景仍用）
      assistantColumn.classList.remove('instant-scroll');
      restoreSendBtn();
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

// 回复完成/失败后恢复发送按钮
function restoreSendBtn() {
  sendBtn.disabled = false;
  sendBtn.textContent = '发送';
  input.focus();
}

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
        det.className = 'thinking';
        det.style.cssText = 'margin:2px 0 4px;background:#0d0d14;border:1px solid #1a1a2e;border-radius:8px;overflow:hidden;font-size:11px';
        var sum = document.createElement('summary');
        sum.textContent = '思考过程';
        sum.style.cssText = 'cursor:pointer;color:#6366f1;padding:6px 10px;user-select:none';
        var wrap = document.createElement('div');
        wrap.className = 'think-scroll-wrap';
        var con = document.createElement('div');
        con.className = 'think-content';
        con.textContent = msg.reasoning;
        con.style.cssText = 'color:#6b7280;line-height:1.6;white-space:pre-wrap';
        wrap.appendChild(con);
        var meta = document.createElement('div');
        meta.className = 'think-meta';
        var countEl = document.createElement('span');
        countEl.className = 'think-count';
        countEl.textContent = msg.reasoning.length + ' 字';
        var expandBtn = document.createElement('button');
        expandBtn.className = 'think-expand-btn';
        expandBtn.textContent = '展开全部';
        expandBtn.style.display = 'none';
        expandBtn.onclick = function() {
          var isExpanded = wrap.classList.toggle('expanded');
          expandBtn.textContent = isExpanded ? '收起' : '展开全部';
          if (!isExpanded) wrap.scrollTop = wrap.scrollHeight;
        };
        var copyThinkBtn = document.createElement('button');
        copyThinkBtn.className = 'think-expand-btn';
        copyThinkBtn.textContent = '复制思考';
        copyThinkBtn.onclick = function() {
          copyText(msg.reasoning, copyThinkBtn);
        };
        var speakThinkBtn = document.createElement('button');
        speakThinkBtn.className = 'think-expand-btn';
        speakThinkBtn.textContent = '🔊 朗读';
        speakThinkBtn.onclick = function() {
          speakTextAloud(msg.reasoning, speakThinkBtn);
        };
        meta.appendChild(countEl);
        meta.appendChild(copyThinkBtn);
        meta.appendChild(expandBtn);
        det.appendChild(sum); det.appendChild(wrap); det.appendChild(meta);
        div.appendChild(det);
        // 内容超高时显示展开按钮（延迟到布局完成）
        requestAnimationFrame(function() {
          if (wrap.scrollHeight > wrap.clientHeight + 4) expandBtn.style.display = '';
        });
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
      var speakBtn = document.createElement('button');
      speakBtn.className = 'copy-btn visible';
      speakBtn.textContent = '🔊 朗读';
      speakBtn.onclick = function(){ speakTextAloud(msg.content, speakBtn); };
      div.appendChild(speakBtn);
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
  // 防连点：已禁用（等待回复）时忽略
  if (sendBtn.disabled) return;
  // 连接断开时给出提示，避免静默失败
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    addMessage('system', '⚠️ 连接已断开，请稍后刷新页面重试');
    showToast('连接已断开');
    return;
  }
  input.value = '';
  autoResizeInput();
  addMessage('user', text);
  showTyping();
  // 非阻塞发送：不锁发送按钮，可连续输入排队（队列状态见 #queue-status）
  // 语音模式开着时，文字提问同样走语音播报线（voice:true → 服务端附播报总结）
  ws.send(JSON.stringify({type: 'user_input', text, voice: voiceState !== 'off'}));
}

// textarea 自适应高度
function autoResizeInput() {
  input.style.height = 'auto';
  input.style.height = Math.min(input.scrollHeight, 120) + 'px';
}

input.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.isComposing) {
    if (e.shiftKey) {
      // Shift+Enter：插入换行
      return; // textarea 默认行为即换行
    }
    e.preventDefault();
    send();
  }
});

// ══════════════════════════════════════════════════════════════════
// 语音对话：聆听线 + 思考线 + 播报线（浏览器 Web Speech API）
//  - 聆听线：webkitSpeechRecognition 持续识别，onend 自动重启（补偿
//    Chrome/Safari 静音后自停的已知行为），interim 实时转写
//  - 思考线：复用现有 WS user_input / content_chunk 通道
//    latest-wins：思考中来了新句只保留最新，避免回答过时问题
//  - 播报线：只播「像真人聊天」的一句话总结（服务端 voice 轮次在回复
//    末尾生成『播报：』并单独下发 spoken 事件），不念全文；
//    用户开口即打断（barge-in），说话期间不抢话
// ══════════════════════════════════════════════════════════════════
var voiceState = 'off';            // off | listening | thinking | speaking
var voiceRec = null;               // 当前 SpeechRecognition 实例
var voiceLang = 'zh-CN';
var voiceTtsOn = true;             // 🔊 播报开关
var voiceInFlight = false;         // 语音触发的回复是否在途
var pendingVoice = null;           // latest-wins：在途时收到的新句
var voiceLastFinalIdx = 0;         // 已处理的 final 序号（去重）
var voiceErrStreak = 0;            // 连续无结果错误计数（防静默死循环）
var voiceUserTalking = false;      // 用户正在说话（期间不播报）
var ttsQueue = [];                 // 待播句段
var ttsSpeaking = false;           // 是否有句段正在播
var _ttsAudio = null;              // 当前播报的 <audio> 实例（edge-tts mp3 播放用）
var _ttsBlobUrl = null;            // 当前 audio 的 blob URL（播完/打断时释放）
var spokenReceived = false;        // 本轮是否已收到服务端『播报：』总结
var _cachedVoices = [];
var _userTalkingTimer = null;      // 兜底：Safari 可能不触发 onspeechend，超时强制复位
var _ttsWatchdog = null;           // 兜底：个别浏览器不触发 utterance onend，超时强制续播
// 回声抑制：播报结束后的 2s 内，麦克风识别到的都是 TTS 自己的声音 →
// 跳过这些结果，避免把自己说的话又当作「用户输入」喂回 LLM
var voiceEchoGraceUntil = 0;
var lastSpoken = '';               // 刚播报的内容（剥掉混入转写段首的回声前缀）
var sttEngine = 'browser';         // 'browser' | 'xfyun'（服务端 voice_caps 握手决定）

function setVoiceState(st) {
  voiceState = st;
  var btn = document.getElementById('voice-toggle');
  var stEl = document.getElementById('voice-status');
  if (btn) btn.className = 'voice-btn ' + st;
  if (stEl) {
    var labels = {off:'语音未开启', listening:'聆听中…', thinking:'思考中…', speaking:'播报中…'};
    stEl.textContent = labels[st] || '';
  }
}

// 停止当前播报：停 edge-tts 音频 + 释放 blob URL + 停浏览器 speechSynthesis（双保险）
function stopTtsAudio() {
  if (_ttsAudio) {
    try { _ttsAudio.pause(); _ttsAudio.onended = null; _ttsAudio.onerror = null; } catch(e) {}
    _ttsAudio = null;
  }
  if (_ttsBlobUrl) { try { URL.revokeObjectURL(_ttsBlobUrl); } catch(e) {} _ttsBlobUrl = null; }
  if (window.speechSynthesis) { try { speechSynthesis.cancel(); } catch(e) {} }
}

function showInterim(text) {
  var el = document.getElementById('voice-interim');
  if (el) el.textContent = '🎙️ ' + text;
}
function clearInterim() {
  var el = document.getElementById('voice-interim');
  if (el) el.textContent = '';
}

// ── 聆听线：识别状态机 ──
function getVoiceRec() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  return SR ? new SR() : null;
}

function startRec() {
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return;
  var rec = new SR();
  voiceRec = rec;
  rec.lang = voiceLang;
  rec.continuous = true;
  rec.interimResults = true;
  rec.maxAlternatives = 1;

  rec.onstart = function() {
    voiceLastFinalIdx = 0; // 新实例 results 从 0 开始
  };
  rec.onresult = function(ev) {
    voiceErrStreak = 0; // 有结果到达 → 识别链路正常
    // 回声抑制：正在播报 / 播完后 2s 内，识别到的都是 TTS 自己的声音 → 整体跳过
    // （不显示、不发送），避免把自己说的话又当作「用户输入」喂回 LLM
    if (ttsSpeaking || Date.now() < voiceEchoGraceUntil) {
      voiceLastFinalIdx = ev.results.length;
      clearInterim();
      return;
    }
    var finals = [];
    for (var i = voiceLastFinalIdx; i < ev.results.length; i++) {
      var r = ev.results[i];
      var text = (r[0] && r[0].transcript || '').trim();
      if (!text) continue;
      if (r.isFinal) {
        finals.push(text);
        voiceLastFinalIdx = i + 1;
      } else {
        showInterim(text);
      }
    }
    if (finals.length) {
      clearInterim();
      // final 到达 = 用户这句话说完了 → 复位「用户说话中」，避免 Safari
      // 不触发 onspeechend 导致播报永远被卡住
      if (_userTalkingTimer) { clearTimeout(_userTalkingTimer); _userTalkingTimer = null; }
      voiceUserTalking = false;
      // 本段所有整句都送（之前只送最后一句，一句话里说两件事会丢前半句）
      var text = finals.join('');
      // 播报期间就开始说话时，识别会把回声和用户的话混在同一段 →
      // 若段首正好是刚播过的总结，先剥掉再送
      if (lastSpoken && text.indexOf(lastSpoken) === 0) {
        text = text.slice(lastSpoken.length);
      }
      text = text.replace(/^(嗯+|呃+|啊+|额+)+/, '').trim(); // 去句首语气词
      if (text) sendVoiceTranscript(text);
    }
  };
  rec.onerror = function(ev) {
    var err = ev.error || '';
    if (err === 'not-allowed' || err === 'service-not-allowed') {
      stopVoice(true);
      showToast('麦克风权限被拒绝，请在浏览器设置中允许后重试');
      return;
    }
    voiceErrStreak++;
    if (err === 'network') {
      // Chrome 的识别把音频发往 Google 服务：国内网络不可达时反复报 network，
      // 静默重试会让用户以为「在听但转不出字」。提示并停止，避免死循环。
      if (voiceErrStreak >= 2) {
        stopVoice(true);
        showToast('语音识别网络错误：Chrome 识别依赖 Google 服务，请改用 Safari 或检查网络');
      } else {
        showToast('语音识别网络错误，正在重试…');
      }
      return;
    }
    if (err === 'no-speech') {
      // 麦克风没拾到音：静默重启继续听，多次无果提示一次
      if (voiceErrStreak === 3) showToast('没有听到声音，请检查麦克风是否被静音');
      return; // onend 自动重启
    }
    if (err === 'audio-capture') {
      stopVoice(true);
      showToast('无法获取麦克风音频，请检查系统麦克风权限');
      return;
    }
    // 其余错误（aborted 等）交给 onend 自动重启
  };
  rec.onspeechstart = function() {
    // 回声抑制：播报期间/播完后 2s 内检测到的「说话」是我们自己的声音 →
    // 不打断播报、不当作用户发言（否则 TTS 一开口就把自己打断）
    if (ttsSpeaking || Date.now() < voiceEchoGraceUntil) return;
    // barge-in：用户开口 → 立即打断播报，期间不抢话
    if (voiceTtsOn) stopTtsAudio();
    ttsQueue = [];
    ttsSpeaking = false;
    voiceUserTalking = true;
    // 兜底：Safari 可能不触发 onspeechend → 3s 后强制复位，避免播报永远被卡
    if (_userTalkingTimer) clearTimeout(_userTalkingTimer);
    _userTalkingTimer = setTimeout(function() {
      voiceUserTalking = false;
      drainTts();
    }, 3000);
  };
  rec.onspeechend = function() {
    // 回声段的结束（播报声的 speechend）不处理
    if (ttsSpeaking || Date.now() < voiceEchoGraceUntil) return;
    if (_userTalkingTimer) { clearTimeout(_userTalkingTimer); _userTalkingTimer = null; }
    voiceUserTalking = false;
    drainTts(); // 用户说完 → 若有缓存句段继续播
  };
  rec.onend = function() {
    // 静音后浏览器自动停止识别 → 语音模式仍开则自动重启
    if (voiceRec === rec && voiceState !== 'off') {
      setTimeout(function() {
        if (voiceState !== 'off' && voiceRec === rec) { try { startRec(); } catch(e) {} }
      }, 300);
    }
  };
  try { rec.start(); } catch(e) {
    // 启动失败（上一实例未完全释放等）→ 稍后重试，避免静默死锁
    setTimeout(function() {
      if (voiceState !== 'off' && voiceRec === rec) {
        try { rec.start(); } catch(e2) { /* 交给 onend 链继续重试 */ }
      }
    }, 600);
  }
}

function startListening() {
  // 用户在点击手势内预热 speechSynthesis：规避 Safari 首次 speak 被自动播放策略拦截
  if (window.speechSynthesis) {
    try { speechSynthesis.cancel(); if (speechSynthesis.paused) speechSynthesis.resume(); } catch(e) {}
  }
  if (voiceState !== 'off') return;
  // 讯飞引擎：麦克风采集 + VAD 句尾检测（会话级，天然防回声）
  if (sttEngine === 'xfyun' && navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
    xfStart();
    return;
  }
  if (!getVoiceRec()) {
    showToast('当前浏览器不支持语音识别，请用 Chrome/Safari');
    return;
  }
  setVoiceState('listening');
  startRec();
}

function stopVoice(silent) {
  setVoiceState('off');
  xfStop(); // 讯飞引擎：释放麦克风/音频上下文/会话
  if (voiceRec) {
    try { voiceRec.onend = null; voiceRec.stop(); } catch(e) {}
    voiceRec = null;
  }
  stopTtsAudio();
  if (_userTalkingTimer) { clearTimeout(_userTalkingTimer); _userTalkingTimer = null; }
  if (_ttsWatchdog) { clearTimeout(_ttsWatchdog); _ttsWatchdog = null; }
  ttsQueue = []; ttsSpeaking = false;
  voiceUserTalking = false;
  voiceEchoGraceUntil = 0;
  lastSpoken = '';
  clearInterim();
  if (!silent) showToast('语音已关闭');
}

function toggleVoice() {
  if (voiceState === 'off') startListening();
  else stopVoice(false);
}

// ══════════════════════════════════════════════════════════════════
// 讯飞引擎：麦克风采集 + VAD 句尾检测（会话级，天然防回声）
// 浏览器(8011) → 本地 WS → 讯飞 WS 转写；音频只在用户说话时上传，
// TTS 播报期间暂停采集 → 播报声不会进识别，结构上消除回声
// ══════════════════════════════════════════════════════════════════
var xfCtx = null, xfStream = null, xfScript = null, xfStarting = false;
var xfSessionOpen = false, xfSilenceMs = 0, xfSpeakMs = 0;
var xfDiscardFinal = false, xfDiscardTimer = null;
var xfDecAcc = 0, xfPcm = [];

var XF_BLOCK = 4096;          // ScriptProcessor 块大小（48k 下约 85ms）
var XF_RATE = 16000;          // 讯飞要求 16kHz PCM16
var XF_PRE_ROLL = 9600;       // 预卷保留 600ms：开口瞬间的音频不丢
var XF_FLUSH_AT = 6400;       // 每 ~400ms 发一批
var XF_VAD_TALK_MS = 250;     // 连续说话 250ms 才算开口
var XF_VAD_SILENCE_MS = 900;  // 静音 900ms 算一句结束
var XF_RMS_TALK = 0.02;       // 语音能量阈值

function xfLangParam() {
  if (voiceLang === 'en-US') return 'en_us';
  if (voiceLang === 'zh-TW') return 'zh_tw';
  return 'zh_cn';
}

function xfSendJson(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
}

function xfOpenSession() {
  if (xfSessionOpen || voiceState === 'off') return;
  xfSessionOpen = true;
  xfSilenceMs = 0;
  xfSendJson({type: 'voice_start', lang: xfLangParam()});
  if (xfPcm.length) xfFlushPcm(); // 预卷音频跟随会话头发出
}

function xfCloseSession() {
  if (!xfSessionOpen) return;
  xfSessionOpen = false;
  xfSendJson({type: 'voice_end'});
}

function xfOnTtsStart() {
  // 播报开始：立刻结束采集会话并丢弃其回声结果（播报声不进 LLM）
  xfCloseSession();
  xfDiscardFinal = true;
  clearInterim();
  if (xfDiscardTimer) clearTimeout(xfDiscardTimer);
  xfDiscardTimer = setTimeout(function() { xfDiscardFinal = false; }, 6000);
}
function xfOnTtsEnd() { /* 播报结束：采集自动恢复（xfOnAudio 按 ttsSpeaking 门控） */ }

function xfStart() {
  if (xfStarting || xfStream || xfCtx) return false;
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showToast('当前浏览器不支持麦克风采集，请用 Chrome/Safari');
    return false;
  }
  xfStarting = true;
  navigator.mediaDevices.getUserMedia({audio: {echoCancellation: true, noiseSuppression: true}})
    .then(function(stream) {
      xfStarting = false;
      if (voiceState === 'off') { stream.getTracks().forEach(function(t){t.stop();}); return; }
      xfStream = stream;
      xfCtx = new (window.AudioContext || window.webkitAudioContext)();
      var src = xfCtx.createMediaStreamSource(stream);
      xfScript = xfCtx.createScriptProcessor(XF_BLOCK, 1, 1);
      xfScript.onaudioprocess = xfOnAudio;
      src.connect(xfScript);
      // 零增益输出端：保持回调触发但不把麦克风放出去（防啸叫）
      var mute = xfCtx.createGain();
      mute.gain.value = 0;
      xfScript.connect(mute);
      mute.connect(xfCtx.destination);
      if (xfCtx.state === 'suspended') xfCtx.resume();
      setVoiceState('listening');
    })
    .catch(function() {
      xfStarting = false;
      stopVoice(true);
      showToast('麦克风权限被拒绝，请在浏览器设置中允许后重试');
    });
  return true;
}

function xfStop() {
  if (xfStream) { xfStream.getTracks().forEach(function(t){t.stop();}); xfStream = null; }
  if (xfScript) { try { xfScript.onaudioprocess = null; xfScript.disconnect(); } catch(e) {} xfScript = null; }
  if (xfCtx) { try { xfCtx.close(); } catch(e) {} xfCtx = null; }
  if (xfSessionOpen) xfCloseSession(); // 让讯飞尽快出最终结果（如有则被丢弃标记忽略）
  if (xfDiscardTimer) { clearTimeout(xfDiscardTimer); xfDiscardTimer = null; }
  xfSilenceMs = 0; xfSpeakMs = 0;
  xfDiscardFinal = false; xfDecAcc = 0; xfPcm = [];
}

// 音频块处理：48k→16k 降采样 + PCM16→base64 + VAD 句检测
function xfOnAudio(e) {
  if (voiceState === 'off' || sttEngine !== 'xfyun') return;
  // TTS 播报中 + 播完回声期内：不采集不判定（播报声不进识别）
  if (ttsSpeaking || Date.now() < voiceEchoGraceUntil) return;
  var data = e.inputBuffer.getChannelData(0);
  // 语音能量（隔点采样，够用且省）
  var sum = 0;
  for (var i = 0; i < data.length; i += 4) sum += data[i] * data[i];
  var rms = Math.sqrt(sum / (data.length / 4));
  var talking = rms > XF_RMS_TALK;
  var blockMs = XF_BLOCK / xfCtx.sampleRate * 1000;

  // 降采样入缓冲（会话开 → 发送；会话闭 → 只保留尾部预卷）
  var ratio = xfCtx.sampleRate / XF_RATE;
  for (var j = 0; j < data.length; j++) {
    xfDecAcc += 1 / ratio;
    if (xfDecAcc >= 1) {
      xfDecAcc -= 1;
      var s = Math.max(-1, Math.min(1, data[j]));
      xfPcm.push(s < 0 ? s * 32768 : s * 32767);
    }
  }

  if (xfSessionOpen) {
    if (xfPcm.length >= XF_FLUSH_AT) xfFlushPcm();
    if (talking) {
      xfSilenceMs = 0;
    } else if (xfSilenceMs >= XF_VAD_SILENCE_MS) {
      xfFlushPcm();
      xfCloseSession();              // 一句结束
    } else {
      xfSilenceMs += blockMs;
    }
  } else {
    if (xfPcm.length > XF_PRE_ROLL) xfPcm = xfPcm.slice(xfPcm.length - XF_PRE_ROLL);
    if (talking) {
      xfSpeakMs += blockMs;
      if (xfSpeakMs >= XF_VAD_TALK_MS) xfOpenSession(); // 开口 → 预卷一起送出
    } else {
      xfSpeakMs = 0;
    }
  }
}

function xfFlushPcm() {
  if (!xfPcm.length) return;
  var bytes = new Uint8Array(xfPcm.length * 2);
  for (var i = 0; i < xfPcm.length; i++) {
    var v = xfPcm[i] & 0xffff;
    bytes[i * 2] = v & 0xff;
    bytes[i * 2 + 1] = (v >> 8) & 0xff;
  }
  xfPcm = [];
  var bin = '';
  for (var k = 0; k < bytes.length; k++) bin += String.fromCharCode(bytes[k]);
  xfSendJson({type: 'voice_audio', data: btoa(bin)});
}

// ── 思考线：把转写文本送进 LLM（复用现有 WS 通道）──
function sendVoiceTranscript(text) {
  if (!text) return;
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    showToast('连接已断开，无法发送语音');
    return;
  }
  // 有回复在途（语音或文字）→ latest-wins：只留最新一句，当前回复完成后再发
  if (voiceInFlight || sendBtn.disabled) {
    pendingVoice = text;
    return;
  }
  dispatchVoiceText(text);
}

function dispatchVoiceText(text) {
  voiceInFlight = true;
  spokenReceived = false;
  addMessage('user', '🎙️ ' + text);
  showTyping();
  ws.send(JSON.stringify({type: 'user_input', text, voice: true}));
  setVoiceState('thinking');
}

// 当前回复完成：发 pending 最新句 / 收尾播报 / 回到聆听
function onAssistantDone(result) {
  voiceInFlight = false;
  if (voiceState === 'off') return;
  if (pendingVoice) {
    var p = pendingVoice;
    pendingVoice = null;
    dispatchVoiceText(p);
    return;
  }
  // 没等到服务端总结（本地快答/离线/模型未遵守格式）→ 前端兜底抽取口语化内容
  if (!spokenReceived && result) {
    var fb = conversationalExtract(result);
    if (fb) feedSpoken(fb);
  }
  // 无新句 → 让剩余句段自然播完；播完即回聆听（drainTts 内处理）
  drainTts();
}

// ── 播报线：只播「像真人聊天」的一句话总结，不念全文 ──
// 服务端在语音轮次会要求模型在回复末尾附『播报：』总结并单独下发（spoken 事件）；
// 这里只在两种情况下产出播报内容：收到 spoken 事件、或服务端没给时用兜底抽取。

// 兜底抽取：从完整回复里挑出适合开口说的话
// （去掉代码/列表/标题/表格，去寒暄前缀，最多 2 句、80 字）
function conversationalExtract(raw) {
  if (!raw) return '';
  var s = raw.replace(/```[\\s\\S]*?```/g, ' '); // 代码块整段不念
  var lines = s.split('\\n').map(function(l) { return l.trim(); }).filter(function(l) {
    if (!l) return false;
    if (/^[-*•+\\s]+\\s/.test(l)) return false;   // 列表项不念
    if (/^\\d+[.、)）]\\s/.test(l)) return false;  // 编号项不念
    if (/^#{1,6}\\s/.test(l)) return false;       // 标题不念
    if (/^\\|.*\\|$/.test(l)) return false;       // 表格行不念
    return true;
  });
  var joined = lines.join(' ')
    .replace(/`([^`]*)`/g, '$1')                   // 行内代码
    .replace(/\\[([^\\]]*)\\]\\([^)]*\\)/g, '$1') // 链接 → 纯文字
    .replace(/[#*_>~|]/g, '')
    .replace(/\\s+/g, ' ')
    .replace(/^(好的|好的，|好的。|没问题|没问题，|当然可以|当然可以，|好的没问题|首先|首先，|您好|你好|根据(您的|你的)?(要求|需求|信息)|基于以上)/, '')
    .trim();
  if (!joined) return '';
  var parts = joined.split(/(?<=[。！？!?；;])/);
  var spoken = '';
  for (var i = 0; i < parts.length && i < 2; i++) {
    spoken += parts[i];
    if (spoken.length >= 80) break;
  }
  spoken = spoken.trim();
  if (spoken.length > 80) spoken = spoken.slice(0, 80) + '……';
  return spoken;
}

// 入队一句话总结并尝试播报（latest-wins：已有更新问题在等 → 本轮总结作废）
function feedSpoken(text) {
  if (!voiceTtsOn || voiceState === 'off') return;
  if (pendingVoice) return; // 已有更新的问题在排队 → 上一轮的总结已过时
  var s = (text || '').trim();
  if (!s) return;
  ttsQueue = [s];
  drainTts();
}

function drainTts() {
  if (!voiceTtsOn || voiceState === 'off') return;
  if (voiceUserTalking) return;          // 用户说话中，不抢话
  if (ttsSpeaking || ttsQueue.length === 0) {
    if (!ttsSpeaking) setVoiceState(voiceInFlight ? 'thinking' : 'listening');
    return;
  }
  var text = ttsQueue.shift();
  ttsSpeaking = true;
  lastSpoken = text;
  setVoiceState('speaking');
  playTtsText(text, voiceLang);
}

// ── 手动朗读：原文 / 思考过程的「🔊 朗读」按钮共用 ──
var _aloudBtn = null;                  // 正在「⏹ 停止」状态的朗读按钮（其余保持原文标签）
function plainTextForTts(text) {
  var s = (text || '').replace(/\\r\\n/g, '\\n');
  s = s.replace(/```[\\s\\S]*?```/g, ' ');         // 代码块整体去掉
  s = s.replace(/`([^`]*)`/g, '$1');             // 行内代码 → 原文
  s = s.replace(/!\\[[^\\]]*\\]\\([^)]*\\)/g, ' ');   // 图片
  s = s.replace(/\\[([^\\]]*)\\]\\([^)]*\\)/g, '$1'); // 链接 → 文字
  s = s.replace(/(^|\\n)\\s*#{1,6}\\s*/g, '$1');    // 标题符号
  s = s.replace(/[*_~>]/g, ' ');                 // 粗斜体/删除线/引用符
  s = s.replace(/\\s+/g, ' ');                    // 压缩空白
  return s.trim();
}
function stopAloudPlayback() {
  stopTtsAudio();
  ttsSpeaking = false;
  if (_ttsWatchdog) { clearTimeout(_ttsWatchdog); _ttsWatchdog = null; }
  if (_aloudBtn) { _aloudBtn.textContent = '🔊 朗读'; _aloudBtn = null; }
  if (sttEngine === 'xfyun') xfOnTtsEnd();
}
function resetAloudBtn(btn) {
  if (_aloudBtn === btn) { btn.textContent = '🔊 朗读'; _aloudBtn = null; }
}
// 手动朗读指定文本（按钮点击）：再点同一个按钮 = 停止；自动播报队列让位等手动播完
function speakTextAloud(text, btn) {
  var plain = plainTextForTts(text);
  if (!plain) { showToast('没有可朗读的内容'); return; }
  if (_aloudBtn === btn && ttsSpeaking) { stopAloudPlayback(); return; }
  stopAloudPlayback();     // 打断当前（自动总结或别的朗读）
  ttsQueue = [];           // 清自动队列：手动朗读结束后不追念旧句
  _aloudBtn = btn;
  btn.textContent = '⏹ 停止';
  ttsSpeaking = true;      // 回声抑制/麦克风门控依赖此标志
  if (voiceState !== 'off') setVoiceState('speaking');
  playTtsText(plain, voiceLang, true, function() { resetAloudBtn(btn); });
}

// 主播放：请求后端 edge-tts 合成 mp3 并播放（带缓存，重复内容秒回）
// manual=true：手动朗读（按钮点击），绕过静音/语音关闭的自动播报门控；
// onFinish：播放走到任一终态（播完/出错/打断后由调用方负责复位）时回调
function playTtsText(text, lang, manual, onFinish) {
  if (sttEngine === 'xfyun') xfOnTtsStart(); // 关采集会话并丢弃回声（ttsSpeaking 已由 drainTts 置位）
  var ctrl = new AbortController();
  // 合成超时按文本长度缩放（edge-tts 实测约 100ms/字，留 2 倍余量）：
  // 固定 8s 会误杀长文（朗读原文动辄几百字），中止后回退浏览器 TTS 又会被 Chrome 掐断
  var _fetchTimer = setTimeout(function(){ ctrl.abort(); }, Math.max(8000, text.length * 200));
  fetch('/api/tts', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({text: text, lang: lang}),
    signal: ctrl.signal
  }).then(function(r) {
    if (!r.ok) throw new Error('tts http ' + r.status);
    return r.blob();
  }).then(function(blob) {
    clearTimeout(_fetchTimer);
    // fetch 不随 mute/stop 取消：合成期间被静音/关闭 → 丢弃不播（手动朗读除外）
    if (!manual && (!voiceTtsOn || voiceState === 'off')) {
      ttsSpeaking = false;
      if (onFinish) onFinish();
      return;
    }
    var url = URL.createObjectURL(blob);
    _ttsBlobUrl = url; // 交给 stopTtsAudio 统一释放（打断/静音/关闭时）
    var au = new Audio(url);
    _ttsAudio = au;
    var done = function() {
      URL.revokeObjectURL(url);
      if (_ttsBlobUrl === url) _ttsBlobUrl = null;
      if (_ttsAudio === au) _ttsAudio = null;
      ttsSpeaking = false;
      if (sttEngine === 'xfyun') xfOnTtsEnd();
      voiceEchoGraceUntil = Date.now() + 2000; // 播完留 2s 回声区
      if (_ttsWatchdog) { clearTimeout(_ttsWatchdog); _ttsWatchdog = null; }
      drainTts();
      if (onFinish) onFinish();
    };
    au.onended = done;
    au.onerror = done;
    // 看门狗：Audio 偶发不触发 ended → 20s 后强制复位并续播
    _ttsWatchdog = setTimeout(function() {
      if (ttsSpeaking) {
        ttsSpeaking = false;
        if (sttEngine === 'xfyun') xfOnTtsEnd();
        voiceEchoGraceUntil = Date.now() + 2000;
        stopTtsAudio();
        drainTts();
        if (onFinish) onFinish();
      }
    }, Math.max(20000, text.length * 600)); // 播放看门狗按长度缩放：固定 20s 会掐掉长文后半段
    au.play().catch(function() {
      // 自动播放被浏览器拦截 → 回退浏览器 TTS
      URL.revokeObjectURL(url);
      if (_ttsBlobUrl === url) _ttsBlobUrl = null;
      if (_ttsAudio === au) _ttsAudio = null;
      ttsSpeaking = false;
      if (_ttsWatchdog) { clearTimeout(_ttsWatchdog); _ttsWatchdog = null; }
      speakFallback(text, lang);
      if (onFinish) onFinish();
    });
  }).catch(function() {
    // 后端不可用（edge-tts 未装/断网/超时）→ 回退浏览器 TTS
    clearTimeout(_fetchTimer);
    ttsSpeaking = false;
    if (_ttsWatchdog) { clearTimeout(_ttsWatchdog); _ttsWatchdog = null; }
    speakFallback(text, lang);
    if (onFinish) onFinish();
  });
}

// 回退：edge-tts 不可用时用浏览器 speechSynthesis（原逻辑兜底）
// Chrome 对超过 ~15s 的长文本会自动掐断 → 按句切块逐个排队念，逐块 onend 续播
function speakFallback(text, lang) {
  if (sttEngine === 'xfyun') xfOnTtsStart(); // 主播放失败间隙可能开过新会话 → 一并关闭丢弃
  if (!window.speechSynthesis) { ttsSpeaking = false; voiceEchoGraceUntil = Date.now() + 2000; drainTts(); return; }
  var parts = (text || '').match(/[^。！？!?…\\n]+[。！？!?…\\n]?/g) || [text];
  var idx = 0;
  var v = pickVoice(lang);
  function finish() {
    ttsSpeaking = false;
    if (sttEngine === 'xfyun') xfOnTtsEnd();
    voiceEchoGraceUntil = Date.now() + 2000;
    if (_ttsWatchdog) { clearTimeout(_ttsWatchdog); _ttsWatchdog = null; }
    drainTts();
  }
  function speakNext() {
    if (idx >= parts.length) { finish(); return; }
    var u = new SpeechSynthesisUtterance(parts[idx++]);
    u.lang = lang;
    u.rate = 1.0;
    u.pitch = 1.0;
    if (v) u.voice = v;
    u.onstart = function() { ttsSpeaking = true; setVoiceState('speaking'); };
    u.onend = speakNext;
    u.onerror = speakNext;
    try { speechSynthesis.speak(u); } catch(e) { speakNext(); }
  }
  speakNext();
  // 看门狗：个别浏览器不触发 onend → 超时强制复位（长文按长度缩放）
  _ttsWatchdog = setTimeout(function() {
    if (ttsSpeaking) {
      ttsSpeaking = false;
      if (sttEngine === 'xfyun') xfOnTtsEnd();
      voiceEchoGraceUntil = Date.now() + 2000;
      stopTtsAudio();
      drainTts();
    }
  }, Math.max(20000, text.length * 600));
}

function loadVoices() {
  if (window.speechSynthesis) _cachedVoices = speechSynthesis.getVoices();
}
function pickVoice(lang) {
  if (!_cachedVoices.length) loadVoices();
  var byLang = _cachedVoices.filter(function(v) { return v.lang === lang; });
  if (byLang.length) return byLang[0];
  var prefix = lang.split('-')[0];
  var byPrefix = _cachedVoices.filter(function(v) { return v.lang && v.lang.split('-')[0] === prefix; });
  return byPrefix.length ? byPrefix[0] : null;
}

function toggleVoiceMute() {
  voiceTtsOn = !voiceTtsOn;
  var btn = document.getElementById('voice-mute');
  if (btn) {
    btn.textContent = voiceTtsOn ? '🔊' : '🔇';
    btn.classList.toggle('off', !voiceTtsOn);
  }
  if (!voiceTtsOn) {
    ttsQueue = []; ttsSpeaking = false;
    stopTtsAudio();
    voiceEchoGraceUntil = Date.now() + 2000; // 中断的播报尾音不进识别
  }
  showToast(voiceTtsOn ? '语音播报已开启' : '语音播报已静音');
}

function changeVoiceLang() {
  var sel = document.getElementById('voice-lang');
  voiceLang = sel ? sel.value : 'zh-CN';
  if (voiceRec) { try { voiceRec.lang = voiceLang; } catch(e) {} }
  _cachedVoices = [];
}

// 初始化：不支持语音识别的浏览器禁用麦克风按钮（播报仍可用）
(function initVoice() {
  var btn = document.getElementById('voice-toggle');
  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  // 两种识别引擎都不可用（浏览器 STT + 讯飞麦克风采集）才禁用
  var micOk = !!(SR || (navigator.mediaDevices && navigator.mediaDevices.getUserMedia));
  if (!micOk) {
    if (btn) { btn.disabled = true; btn.title = '浏览器不支持语音识别，请用 Chrome/Safari'; }
    return;
  }
  btn.addEventListener('click', toggleVoice);
  document.getElementById('voice-mute').addEventListener('click', toggleVoiceMute);
  document.getElementById('voice-lang').addEventListener('change', changeVoiceLang);
  if (window.speechSynthesis && 'onvoiceschanged' in speechSynthesis) {
    speechSynthesis.onvoiceschanged = loadVoices;
  }
  loadVoices();
})();

// ----- Helper: smart auto-scroll & copy -----
function addThinking(reasoning, callback) {
  const div = document.createElement('div');
  div.className = 'msg thinking';
  const details = document.createElement('details');
  details.open = true;
  const summary = document.createElement('summary');
  summary.textContent = '思考过程';
  // 滚动视图容器（max 200px，自动吸附底部）
  const scrollWrap = document.createElement('div');
  scrollWrap.className = 'think-scroll-wrap';
  const content = document.createElement('div');
  content.className = 'think-content';
  scrollWrap.appendChild(content);
  // 底部元信息：字数统计 + 展开按钮
  const meta = document.createElement('div');
  meta.className = 'think-meta';
  const countEl = document.createElement('span');
  countEl.className = 'think-count';
  countEl.textContent = '0 字';
  const expandBtn = document.createElement('button');
  expandBtn.className = 'think-expand-btn';
  expandBtn.textContent = '展开全部';
  expandBtn.style.display = 'none';  // 仅在内容超高时显示
  expandBtn.onclick = function() {
    const isExpanded = scrollWrap.classList.toggle('expanded');
    expandBtn.textContent = isExpanded ? '收起' : '展开全部';
    if (!isExpanded) scrollWrap.scrollTop = scrollWrap.scrollHeight;
  };
  var speakThinkBtn = document.createElement('button');
  speakThinkBtn.className = 'think-expand-btn';
  speakThinkBtn.textContent = '🔊 朗读';
  speakThinkBtn.onclick = function() { speakTextAloud(reasoning, speakThinkBtn); };
  meta.appendChild(countEl);
  meta.appendChild(speakThinkBtn);
  meta.appendChild(expandBtn);
  details.appendChild(summary);
  details.appendChild(scrollWrap);
  details.appendChild(meta);
  div.appendChild(details);
  // 思考面板属于 LINK 的回复，固定进右列
  const targetCol = assistantColumn;
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
      // 字数统计
      countEl.textContent = pos + ' 字';
      // 内容超高后自动吸附底部（仅在未展开时）
      if (!scrollWrap.classList.contains('expanded')) {
        scrollWrap.scrollTop = scrollWrap.scrollHeight;
      }
      // 判断是否需要显示展开按钮（内容超出现有高度时）
      if (scrollWrap.scrollHeight > scrollWrap.clientHeight + 4) {
        expandBtn.style.display = '';
      }
      scrollToBottom();
      setTimeout(typeThink, THINK_SPEED);
    } else {
      // 完成：最终字数
      countEl.textContent = reasoning.length + ' 字';
      if (scrollWrap.scrollHeight > scrollWrap.clientHeight + 4) {
        expandBtn.style.display = '';
      }
      if (callback) callback();
    }
  }
  typeThink();
}

function isNearBottom() {
  return assistantColumn.scrollHeight - assistantColumn.scrollTop - assistantColumn.clientHeight < 120;
}
// rAF 节流的滚动到底：同一帧内多次调用只执行一次，避免强制同步布局
var _scrollRaf = false;
function scrollToBottom() {
  if (_scrollRaf) return;
  _scrollRaf = true;
  requestAnimationFrame(function() {
    _scrollRaf = false;
    if (isNearBottom()) assistantColumn.scrollTop = assistantColumn.scrollHeight;
    userColumn.scrollTop = userColumn.scrollHeight;
  });
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
  // 滚动到顶部附近时自动加载更早消息（防抖）
  if (!historyLoading && !historyEnd && assistantColumn.scrollTop <= 40) {
    var loadMore = document.getElementById('load-more');
    if (loadMore) {
      clearTimeout(window._autoLoadTimer);
      window._autoLoadTimer = setTimeout(function() {
        historyPage++;
        loadHistory(historyPage);
      }, 500);
    }
  }
}
assistantColumn.addEventListener('scroll', updateScrollButtons);
setTimeout(updateScrollButtons, 500);

// Scroll Nav: drag + snap + expand/collapse
(function() {
  var nav = document.getElementById('scroll-nav');
  if (!nav) return;
  var toggle = nav.querySelector('.nav-toggle');
  var isDragging = false, wasDragged = false, startX, startY, startLeft, startTop;
  
  // Hover: expand on enter, collapse 1s after leave
  var _collapseTimer = null;
  nav.addEventListener('mouseenter', function() {
    if (_collapseTimer) { clearTimeout(_collapseTimer); _collapseTimer = null; }
    if (!nav.classList.contains('expanded')) {
      nav.classList.remove('collapsed');
      nav.classList.add('expanded');
    }
  });
  nav.addEventListener('mouseleave', function() {
    if (isDragging) return;
    if (_collapseTimer) clearTimeout(_collapseTimer);
    _collapseTimer = setTimeout(function() {
      _collapseTimer = null;
      nav.classList.remove('expanded');
      nav.classList.add('collapsed');
    }, 1000);
  });
  
  // Drag on toggle mousedown
  if (toggle) {
    toggle.addEventListener('mousedown', function(e) {
      isDragging = true; wasDragged = false;
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
    wasDragged = true;
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
// XSS 净化：marked 允许原始 HTML 穿透（新版已移除 sanitize 选项），
// 对渲染结果做白名单过滤，移除 script/iframe/on* 事件/javascript: 链接
function sanitizeHTML(html) {
  try {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    // 移除高危节点
    ['script', 'iframe', 'object', 'embed', 'link', 'meta', 'style', 'form', 'svg'].forEach(function(tag) {
      var els = doc.querySelectorAll(tag);
      for (var i = els.length - 1; i >= 0; i--) els[i].parentNode.removeChild(els[i]);
    });
    // 移除所有元素的事件属性
    var all = doc.querySelectorAll('*');
    for (var i = 0; i < all.length; i++) {
      var attrs = all[i].attributes;
      for (var j = attrs.length - 1; j >= 0; j--) {
        var name = attrs[j].name.toLowerCase();
        var val = attrs[j].value.toLowerCase();
        if (name.indexOf('on') === 0 || val.indexOf('javascript:') === 0) {
          all[i].removeAttribute(attrs[j].name);
        }
      }
    }
    return doc.body.innerHTML;
  } catch(e) { return html; }
}

function renderMarkdown(text) {
  if (!text) return '';
  try { return sanitizeHTML(marked.parse(text)); }
  catch(e) { return '<p>' + text.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</p>'; }
}

// 流式打字中的部分 markdown 渲染：未闭合的语法标记临时转义，避免闪烁
function renderMarkdownPartial(text) {
  if (!text) return '';
  var t = text;
  // 未闭合的代码围栏 ``` → 补一个闭合围栏，保证 marked 不吞内容
  // （优先处理围栏，避免内部单反引号干扰计数）
  var fenceCount = (t.match(/```/g) || []).length;
  var fenceOpen = fenceCount % 2 === 1;
  if (fenceOpen) {
    t += '\\n```';
  } else {
    // 无未闭合围栏时，才处理单个反引号（行内代码）
    var backticks = (t.match(/`/g) || []).length;
    if (backticks % 2 === 1) t = t.replace(/`(?=[^`]*$)/, '～');
  }
  // 未闭合的 **bold** → 保留为字面星号（不触发解析）
  var stars = (t.match(/\\*\\*/g) || []).length;
  if (stars % 2 === 1) t = t.replace(/\\*\\*(?=[^*]*$)/, '∗∗');
  try { return sanitizeHTML(marked.parse(t)); }
  catch(e) { return '<p>' + t.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</p>'; }
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

  // ── 动态打字速度调节 ──
  // 基础间隔 50ms；根据"已打字量 / 总量"自适应：
  //   - 内容少（总时长短）→ 保持基础速度
  //   - 内容多 → 逐步加速（前 30% 用基础速度，之后线性加快），
  //     避免长回复让用户干等
  // 若后续有 reasoning_chunk 仍在返回（思考还没结束），则减速等待。
  var totalTokens = tokens.length;
  var startTime = Date.now();
  var lastTickTime = startTime;

  function calcInterval() {
    var progress = totalTokens > 0 ? idx / totalTokens : 0;
    // 内容越往后越快：前 30% 基础 50ms，后 70% 线性降到 12ms
    var base = 50;
    var min = 12;
    if (progress < 0.3) return base;
    var t = (progress - 0.3) / 0.7;  // 0→1
    return Math.max(min, base - t * (base - min));
  }

  // 渲染节流：全量 marked.parser 保持渲染正确，但每 RENDER_STEP 个 token
  // 才渲染一次（打字机按 token 步进，合并中间步骤），把 O(n²) 开销降为
  // O(n²)/RENDER_STEP。长内容（>200 token）时步长加大，进一步减负。
  var RENDER_STEP = tokens.length > 200 ? 3 : 1;
  var _lastRenderIdx = -1;
  var _rafPending = false;

  function renderCurrent() {
    _rafPending = false;
    try { bubble.innerHTML = marked.parser(tokens.slice(0, idx + 1)); }
    catch(e) { bubble.innerHTML = '<p>' + fullText.replace(/&/g,'&amp;').replace(/</g,'&lt;') + '</p>'; }
    scrollToBottom();
  }

  function type() {
    if (idx < tokens.length) {
      var now = Date.now();
      var elapsed = now - lastTickTime;
      lastTickTime = now;
      // 渲染节流：仅当跨过 RENDER_STEP 边界或到末尾时渲染，并用 rAF 合并
      if (idx >= _lastRenderIdx + RENDER_STEP) {
        _lastRenderIdx = idx;
        if (!_rafPending) {
          _rafPending = true;
          requestAnimationFrame(renderCurrent);
        }
      }
      idx++;
      setTimeout(type, calcInterval());
    } else {
      // 确保最终渲染完整
      if (!_rafPending) { _rafPending = true; requestAnimationFrame(renderCurrent); }
      scrollToBottom();
      if (!div.querySelector('.copy-btn')) {
        var copyBtn = document.createElement('button');
        copyBtn.className = 'copy-btn visible';
        copyBtn.textContent = '复制';
        copyBtn.onclick = function() { copyText(fullText, copyBtn); };
        div.appendChild(copyBtn);
        var speakBtn = document.createElement('button');
        speakBtn.className = 'copy-btn visible';
        speakBtn.textContent = '🔊 朗读';
        speakBtn.onclick = function() { speakTextAloud(fullText, speakBtn); };
        div.appendChild(speakBtn);
      }
      // 打字完成的消息添加反馈按钮
      if (!div.querySelector('.feedback-btns')) {
        addFeedbackBtns(div, fullText, '');
      }
      restoreSendBtn();
    }
  }

  type();
}

// 给消息添加反馈按钮（👍/👎）
function addFeedbackBtns(msgDiv, content, reasoning) {
  var fbDiv = document.createElement('div');
  fbDiv.className = 'feedback-btns';
  var fId = 'fb_' + Date.now().toString(36) + '_' + Math.random().toString(36).substr(2,6);
  var up = document.createElement('button');
  up.className = 'feedback-btn up';
  up.dataset.msgId = fId; up.dataset.rating = 'up'; up.title = '有用';
  up.textContent = '👍';
  up.onclick = function(){ sendFeedback(fId, 'up', content, reasoning || ''); };
  var down = document.createElement('button');
  down.className = 'feedback-btn down';
  down.dataset.msgId = fId; down.dataset.rating = 'down'; down.title = '没用';
  down.textContent = '👎';
  down.onclick = function(){ sendFeedback(fId, 'down', content, reasoning || ''); };
  fbDiv.appendChild(up); fbDiv.appendChild(down);
  msgDiv.appendChild(fbDiv);
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
  // 左右分屏：用户消息进左列，LINK 回复进右列（见 #chat-container 注释）
  const targetCol = (role === 'user') ? userColumn : assistantColumn;
  const typing = targetCol.querySelector('.typing');
  if (typing) targetCol.insertBefore(div, typing);
  else targetCol.appendChild(div);
  scrollToBottom();
}

var typingTimer = null;
var _typingCharTimer = null;  // 逐字符动画定时器（可被 removeTyping 中断）
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
      _typingCharTimer = setTimeout(typeChar, 12);
    } else {
      _typingCharTimer = null;
      typingStep++;
      typingTimer = setTimeout(nextTypingStep, 400);
    }
  }
  typeChar();
}

function removeTyping() {
  if (typingTimer) { clearTimeout(typingTimer); typingTimer = null; }
  if (_typingCharTimer) { clearTimeout(_typingCharTimer); _typingCharTimer = null; }
  const el = assistantColumn.querySelector('.typing');
  if (el) el.remove();
}

// 轻量 toast 提示（#toast 元素已在 HTML 中定义）
var _toastTimer = null;
function showToast(msg) {
  var t = document.getElementById('toast');
  if (!t) return;
  t.textContent = msg;
  t.classList.add('show');
  if (_toastTimer) clearTimeout(_toastTimer);
  _toastTimer = setTimeout(function() { t.classList.remove('show'); }, 1800);
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── 问卷（Onboarding） ──
var _obStep = 0;
var _obTotal = 4;
var _obAns = {};

function openOnboarding() {
  _obStep = 0;
  document.getElementById('ob-modal').classList.add('show');
  obRender();
}
function closeOnboarding() {
  document.getElementById('ob-modal').classList.remove('show');
}
function obRender() {
  document.querySelectorAll('.ob-step').forEach(function(s) {
    s.classList.toggle('active', parseInt(s.dataset.step) === _obStep);
  });
  var prev = document.getElementById('ob-prev');
  var next = document.getElementById('ob-next');
  var sub = document.getElementById('ob-submit');
  prev.style.display = _obStep === 0 ? 'none' : '';
  next.style.display = _obStep === _obTotal - 1 ? 'none' : '';
  sub.style.display = _obStep === _obTotal - 1 ? '' : 'none';
  // 进度条
  var bar = document.getElementById('ob-progress-bar');
  bar.style.width = ((_obStep + 1) / _obTotal * 100) + '%';
  // dots
  var dots = document.getElementById('ob-dots');
  dots.innerHTML = '';
  for (var i = 0; i < _obTotal; i++) {
    var d = document.createElement('span');
    d.className = 'ob-dot' + (i === _obStep ? ' cur' : '');
    dots.appendChild(d);
  }
}
function obNext() {
  if (_obStep < _obTotal - 1) { _obStep++; obRender(); }
}
function obPrev() {
  if (_obStep > 0) { _obStep--; obRender(); }
}
// Chip 选择器（单选式，可取消）
document.addEventListener('click', function(e) {
  if (e.target.classList.contains('ob-chip')) {
    e.target.classList.toggle('sel');
  }
});
// 提交
async function obSubmit() {
  // 收集答案
  _obAns.name = (document.getElementById('ob-name').value || '').trim();
  var selChips = function(id) {
    var out = [];
    document.querySelectorAll('#' + id + ' .ob-chip.sel').forEach(function(c) {
      out.push(c.dataset.v);
    });
    return out;
  };
  // chips 容器(div) + 自定义输入框分别读取：chips 取选中项，input 取文本
  var chipText = function(chipsId, inputId) {
    var chips = selChips(chipsId);
    var inputEl = document.getElementById(inputId);
    if (inputEl && inputEl.value) {
      var v = String(inputEl.value).trim();
      if (v) chips.push(v);
    }
    return chips.join('、');
  };
  _obAns.nickname = chipText('ob-nickname-chips', 'ob-nickname');
  _obAns.job = chipText('ob-job-chips', 'ob-job');
  _obAns.likes = chipText('ob-interest-chips', 'ob-interests');
  _obAns.habits = chipText('ob-habit-chips', 'ob-habits');
  _obAns.dislikes = (document.getElementById('ob-dislikes').value || '').trim();
  _obAns.goals = (document.getElementById('ob-goals').value || '').trim();
  _obAns.contact = (document.getElementById('ob-contact').value || '').trim();
  _obAns.extra = (document.getElementById('ob-extra').value || '').trim();
  var work = document.querySelector('input[name="ob-work"]:checked');
  if (work) _obAns.habits = (_obAns.habits + '、' + work.value).replace(/^、/, '');
  var style = selChips('ob-style-chips');
  if (style.length) _obAns.likes = (_obAns.likes + '、回复风格偏好:' + style.join('、')).replace(/^、/, '');

  var btn = document.getElementById('ob-submit');
  btn.disabled = true; btn.textContent = '保存中...';
  try {
    var r = await fetch('/api/onboarding', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(_obAns)
    });
    var d = await r.json();
    addMessage('system', d.message || '已保存');
    if (d.success) {
      closeOnboarding();
      loadExecMode();
    } else {
      btn.disabled = false; btn.textContent = '✅ 提交并保存';
    }
  } catch(e) {
    addMessage('system', '问卷保存失败: ' + e.message);
    btn.disabled = false; btn.textContent = '✅ 提交并保存';
  }
}
// 检查是否已完成问卷（完成过则导航按钮标注）
async function checkOnboarding() {
  try {
    var r = await fetch('/api/onboarding/status');
    var d = await r.json();
    if (d.completed) {
      var nav = document.querySelector('.header a[onclick="openOnboarding()"]');
      if (nav) nav.textContent = '📝 问卷 ✓';
    }
  } catch(e) {}
}

// Permission Modal
var _pendingPermRequestId = null;
var _pendingPermDir = null;

// Duration selector
document.addEventListener('click', function(e) {
  if (e.target.closest('#perm-duration') && e.target.tagName === 'BUTTON') {
    var parent = document.getElementById('perm-duration');
    parent.querySelectorAll('button').forEach(function(b) { b.classList.remove('active'); });
    e.target.classList.add('active');
  }
});

// 目录授权开关：勾选后授权整个目录
function toggleGrantDir() {
  var cb = document.getElementById('perm-grant-dir-cb');
  var dirLabel = document.getElementById('perm-grant-dir-label');
  if (!cb) return;
  if (cb.checked) {
    document.getElementById('perm-grant-dir').style.display = 'block';
    dirLabel.textContent = '目录: ' + (_pendingPermDir || '');
  } else {
    document.getElementById('perm-grant-dir').style.display = 'none';
  }
}

function confirmPermission() {
  var active = document.querySelector('#perm-duration .active');
  var grantDir = false;
  var cb = document.getElementById('perm-grant-dir-cb');
  if (cb && cb.checked) grantDir = true;
  ws.send(JSON.stringify({
    type: 'permission_response',
    request_id: _pendingPermRequestId,
    approved: true,
    duration: active ? active.dataset.duration : 'once',
    grant_dir: grantDir
  }));
  document.getElementById('permission-modal').style.display = 'none';
  _pendingPermRequestId = null;
  _pendingPermDir = null;
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
  _pendingPermDir = null;
}
</script>

<!-- Onboarding Questionnaire Modal -->
<div id="ob-modal" class="ob-modal">
  <div class="ob-box">
    <div class="ob-progress"><div class="ob-progress-inner" id="ob-progress-bar"></div></div>
    <div class="ob-head">
      <h3>📝 让我更了解你</h3>
      <p>填写这份问卷，LINK 会记住你的偏好和习惯，帮你更好地回答问题、完成任务。所有信息仅保存在本机记忆库。</p>
    </div>
    <div class="ob-body" id="ob-body">
      <div class="ob-step active" data-step="0">
        <div class="ob-q">
          <label>你的名字或昵称？<span class="ob-desc">LINK 之后会用这个称呼你</span></label>
          <input type="text" id="ob-name" placeholder="例如：小明">
        </div>
        <div class="ob-q">
          <label>你希望 LINK 怎么称呼你？</label>
          <div class="ob-chips" id="ob-nickname-chips">
            <button class="ob-chip" data-v="直接叫名字">直接叫名字</button>
            <button class="ob-chip" data-v="哥/姐">哥/姐</button>
            <button class="ob-chip" data-v="老板">老板</button>
            <button class="ob-chip" data-v="亲爱的">亲爱的</button>
          </div>
          <input type="text" id="ob-nickname" placeholder="或自定义称呼" style="margin-top:8px">
        </div>
      </div>
      <div class="ob-step" data-step="1">
        <div class="ob-q">
          <label>你的职业/身份？</label>
          <div class="ob-chips" id="ob-job-chips">
            <button class="ob-chip" data-v="软件工程师">软件工程师</button>
            <button class="ob-chip" data-v="产品经理">产品经理</button>
            <button class="ob-chip" data-v="设计师">设计师</button>
            <button class="ob-chip" data-v="学生">学生</button>
            <button class="ob-chip" data-v="自由职业">自由职业</button>
          </div>
          <input type="text" id="ob-job" placeholder="或其他职业" style="margin-top:8px">
        </div>
        <div class="ob-q">
          <label>你平时的技术/兴趣领域？<span class="ob-desc">选几个你常接触的领域</span></label>
          <div class="ob-chips" id="ob-interest-chips">
            <button class="ob-chip" data-v="编程">编程</button>
            <button class="ob-chip" data-v="AI/人工智能">AI/人工智能</button>
            <button class="ob-chip" data-v="设计">设计</button>
            <button class="ob-chip" data-v="摄影">摄影</button>
            <button class="ob-chip" data-v="阅读">阅读</button>
            <button class="ob-chip" data-v="健身">健身</button>
            <button class="ob-chip" data-v="美食">美食</button>
            <button class="ob-chip" data-v="旅行">旅行</button>
          </div>
          <input type="text" id="ob-interests" placeholder="其他兴趣（用逗号分隔）" style="margin-top:8px">
        </div>
      </div>
      <div class="ob-step" data-step="2">
        <div class="ob-q">
          <label>你的习惯？</label>
          <div class="ob-chips" id="ob-habit-chips">
            <button class="ob-chip" data-v="早起">早起</button>
            <button class="ob-chip" data-v="夜猫子">夜猫子</button>
            <button class="ob-chip" data-v="喜欢喝咖啡">喜欢喝咖啡</button>
            <button class="ob-chip" data-v="喝茶">喝茶</button>
            <button class="ob-chip" data-v="每天锻炼">每天锻炼</button>
            <button class="ob-chip" data-v="午休">午休</button>
          </div>
          <input type="text" id="ob-habits" placeholder="其他习惯" style="margin-top:8px">
        </div>
        <div class="ob-q">
          <label>你不喜欢/讨厌什么？<span class="ob-desc">LINK 会尽量避免这些</span></label>
          <input type="text" id="ob-dislikes" placeholder="例如：打扰我午休、太长的回复">
        </div>
        <div class="ob-q">
          <label>你最近的目标或想做的事？</label>
          <input type="text" id="ob-goals" placeholder="例如：学完 Python、准备马拉松">
        </div>
      </div>
      <div class="ob-step" data-step="3">
        <div class="ob-q">
          <label>你希望 LINK 怎么帮你工作？</label>
          <div class="ob-opt" id="ob-work-opts">
            <label><input type="radio" name="ob-work" value="让我确认每一步"><span>谨慎型：每个操作都先问我确认</span></label>
            <label><input type="radio" name="ob-work" value="自动完成常规任务"><span>高效型：常规任务自动完成，重要操作再确认</span></label>
            <label><input type="radio" name="ob-work" value="全力自动执行"><span>激进型：尽量自动执行所有任务</span></label>
          </div>
        </div>
        <div class="ob-q">
          <label>回复风格偏好？</label>
          <div class="ob-chips" id="ob-style-chips">
            <button class="ob-chip" data-v="简洁直接">简洁直接</button>
            <button class="ob-chip" data-v="详细完整">详细完整</button>
            <button class="ob-chip" data-v="轻松幽默">轻松幽默</button>
            <button class="ob-chip" data-v="专业严谨">专业严谨</button>
          </div>
        </div>
        <div class="ob-q">
          <label>你的联系方式（选填）？<span class="ob-desc">用于需要联系你时的场景</span></label>
          <input type="text" id="ob-contact" placeholder="邮箱 / 手机号 / 微信">
        </div>
        <div class="ob-q">
          <label>其他想告诉 LINK 的？</label>
          <textarea id="ob-extra" placeholder="任何关于你的信息..."></textarea>
        </div>
      </div>
    </div>
    <div class="ob-dots" id="ob-dots"></div>
    <div class="ob-nav">
      <button class="ob-btn" id="ob-prev" onclick="obPrev()">← 上一步</button>
      <button class="ob-btn" id="ob-next" onclick="obNext()">下一步 →</button>
      <button class="ob-btn primary" id="ob-submit" onclick="obSubmit()" style="display:none">✅ 提交并保存</button>
    </div>
  </div>
</div>

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
      <label class="perm-grant-row">
        <input type="checkbox" id="perm-grant-dir-cb" onchange="toggleGrantDir()" style="accent-color:#6366f1;width:16px;height:16px;margin-right:6px">
        授权整个目录（一次性授权目录下所有文件读写）
      </label>
      <div class="value" id="perm-grant-dir" style="display:none;color:#6366f1;word-break:break-all;font-size:12px">
        目录: <span id="perm-grant-dir-label"></span>
      </div>
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
        try:
            from src.tools.permission_request_manager import PermissionRequestManager as PRM
        except ImportError:
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
            # 语音能力宣告：配置了讯飞 → 用讯飞识别；否则回退浏览器内置识别
            await websocket.send_json({
                "type": "voice_caps",
                "data": {"stt": "xfyun" if self._xfyun_config() else "browser"}
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
                                data.get("duration", "once"),
                                grant_dir=bool(data.get("grant_dir", False))
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

                        elif msg_type == "voice_start":
                            # 开启讯飞识别会话。旧的会通过 voice_end 的 None 哨兵
                            # 自然收尾并下发 voice_final —— 不 cancel，否则用户连续
                            # 说话时上一句的结果会被丢掉
                            old = self._xfyun_queues.get(client_id)
                            if old:
                                try:
                                    old[0].put_nowait(None)
                                except Exception:
                                    pass
                            audio_q: asyncio.Queue = asyncio.Queue()
                            task = asyncio.create_task(
                                self._xfyun_run(websocket, audio_q,
                                                data.get("lang", "zh_cn")))
                            self._xfyun_queues[client_id] = (audio_q, task)

                        elif msg_type == "voice_audio":
                            entry = self._xfyun_queues.get(client_id)
                            if entry:
                                try:
                                    audio = base64.b64decode(data.get("data", ""))
                                except Exception:
                                    audio = b""
                                if audio:
                                    try:
                                        entry[0].put_nowait(audio)
                                    except Exception:
                                        pass

                        elif msg_type == "voice_end":
                            entry = self._xfyun_queues.get(client_id)
                            if entry:
                                try:
                                    entry[0].put_nowait(None)
                                except Exception:
                                    pass
                except WebSocketDisconnect:
                    pass
                except Exception as e:
                    print(f"receive_task 异常: {e}")
                finally:
                    PRM.get_instance().cancel_all()

            async def process_task():
                """将用户输入提交到 TaskManager，非阻塞（LLM 调用由 worker_task 串行消费）"""
                try:
                    while True:
                        data = await input_queue.get()
                        text = data.get("text", "")
                        if not text:
                            continue
                        # 语音触发轮次：要求模型附『播报：』总结，前端只播这句（不念全文）
                        voice = bool(data.get("voice", False))
                        self.add_user_input(text, client_id)
                        await self._broadcast_event({
                            "event_type": "USER_INPUT",
                            "message": f"\U0001f4dd 收到用户输入: {text}",
                            "source": f"user_{client_id}"
                        })
                        task = await self.task_manager.submit(text, voice=voice)
                        await self._broadcast_event({
                            "event_type": "TASK_UPDATE",
                            "task_id": task.id, "status": task.status,
                            "position": self.task_manager.pending_count,
                            "message": f"\U0001f4e5 任务已入队 (第{self.task_manager.pending_count}个)"
                        })
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"process_task 异常: {e}")

            async def worker_task():
                """后台工作者：从队列串行取任务，做 LLM 调用并广播结果"""
                prm = PRM.get_instance()
                try:
                    while True:
                        task = await self.task_manager._queue.get()
                        if task.status == "cancelled":
                            continue
                        # 单条任务失败不影响队列后续任务（避免整个工作者退出）
                        try:
                            task.status = "processing"
                            self.task_manager._current = task
                            await self._broadcast_event({
                                "event_type": "TASK_UPDATE", "task_id": task.id,
                                "status": "processing", "message": "⏳ 正在处理..."
                            })
                            def _perm_cb(req):
                                asyncio.run_coroutine_threadsafe(websocket.send_json({
                                    "type": "permission_request", "request_id": req.id,
                                    "resource": req.resource, "mode": req.mode,
                                    "resource_type": req.resource_type.value,
                                    "suggest_dir": getattr(req, "suggest_dir", None),
                                }), loop)
                            prm.register_callback(_perm_cb)
                            _stream_content_buf = ['']
                            def _stream_cb(ctype, content):
                                if ctype == "reasoning" and content.strip():
                                    asyncio.run_coroutine_threadsafe(
                                        websocket.send_json({"type":"reasoning_chunk","data":content}), loop)
                                elif ctype == "content" and content:
                                    _stream_content_buf[0] += content
                                    asyncio.run_coroutine_threadsafe(
                                        websocket.send_json({"type":"content_chunk","data":content}), loop)
                            from functools import partial
                            # CPU 密集/阻塞任务放到线程池；voice=语音轮次，要模型附播报总结
                            _task_fn = partial(self._process_input_direct, task.text,
                                               stream_callback=_stream_cb, voice=task.voice)
                            try:
                                brain_resp = await asyncio.get_event_loop().run_in_executor(None, _task_fn)
                            finally:
                                # 无论成功失败都要注销回调，否则回调会泄漏到下一个任务
                                prm.unregister_callback(_perm_cb)
                            if brain_resp and brain_resp.get("result"):
                                task.result = brain_resp["result"]
                                task.reasoning = brain_resp.get("reasoning", "")
                                task.status = "done"
                                # 语音播报句先到（前端可先开口），随后 ASSISTANT 更新文字
                                if brain_resp.get("spoken"):
                                    await websocket.send_json({
                                        "type": "spoken",
                                        "data": brain_resp["spoken"]
                                    })
                                await self._broadcast_event({
                                    "event_type": "ASSISTANT", "result": brain_resp["result"],
                                    "reasoning": brain_resp.get("reasoning", ""),
                                    "source": "link_brain", "timestamp": time.time()
                                })
                            else:
                                task.status = "error"
                        except asyncio.CancelledError:
                            raise
                        except Exception as e:
                            task.status = "error"
                            print(f"worker_task 单条任务处理异常: {e}")
                            try:
                                await websocket.send_json({
                                    "type": "event",
                                    "data": {"event_type": "ERROR",
                                             "message": f"处理消息时出错: {e}",
                                             "timestamp": time.time()}
                                })
                            except Exception:
                                pass
                        finally:
                            self.task_manager._current = None
                            await self._broadcast_event({
                                "event_type": "TASK_UPDATE", "task_id": task.id,
                                "status": task.status,
                                "message": "✅ 任务完成" if task.status == "done" else "❌ 任务失败"
                            })
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    print(f"worker_task 异常: {e}")

            # 并行运行三个任务
            try:
                await asyncio.gather(receive_task(), process_task(), worker_task())
            except Exception as e:
                print(f"WebSocket 处理器异常: {e}")
            finally:
                self.websocket_clients = [c for c in self.websocket_clients if c["id"] != client_id]
                # 清理讯飞识别会话
                entry = self._xfyun_queues.pop(client_id, None)
                if entry:
                    try:
                        entry[1].cancel()
                    except Exception:
                        pass
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

        # ── 任务执行模式 + 任务监控 ──

        @self.app.get("/api/execution-mode")
        async def get_execution_mode():
            if not self.brain_link:
                return {"mode": "manual", "auto_steps_limit": 3}
            return self.brain_link.get_execution_mode()

        @self.app.post("/api/execution-mode")
        async def post_execution_mode(request_data: dict):
            mode = request_data.get("mode", "manual")
            if not self.brain_link:
                return {"success": False, "message": "LINK 未就绪"}
            ok = self.brain_link.set_execution_mode(mode)
            return {"success": ok, "mode": mode,
                    "message": "已切换为自动执行" if ok and mode == "auto" else
                               "已切换为手动执行" if ok else "无效模式"}

        @self.app.get("/api/tasks")
        async def get_tasks():
            if not self.brain_link:
                return {"tasks": []}
            return {"tasks": self.brain_link.get_task_status_summary()}

        # ── 用户问卷（构建个人记忆库） ──

        @self.app.post("/api/onboarding")
        async def post_onboarding(data: dict):
            """提交问卷答案 → 写入用户记忆库"""
            if not self.brain_link:
                return {"success": False, "message": "大脑引擎未就绪"}
            result = self.brain_link.import_onboarding(data or {})
            saved = result.get("saved", 0)
            return {
                "success": result.get("success", False),
                "saved": saved,
                "message": f"✅ 已保存 {saved} 条关于你的信息，LINK 已记住你的偏好和习惯" if saved
                           else "未保存任何信息（答案为空？）",
            }

        @self.app.get("/api/onboarding/status")
        async def get_onboarding_status():
            """检查是否已完成问卷（是否有 onboarding 标签的记忆）"""
            if not self.brain_link or not self.brain_link.memory_engine:
                return {"completed": False}
            try:
                all_mem = self.brain_link.memory_engine.store.get_all_memories()
                has = any(
                    "onboarding" in (m.metadata.get("tags") or [])
                    for m in all_mem
                )
                return {"completed": has}
            except Exception:
                return {"completed": False}

        # ── 完全初始化（清空记忆与设置） ──

        @self.app.post("/api/reset")
        async def post_reset():
            """完全初始化 LINK：清空记忆、重置设置、清空提醒和授权。"""
            result = await self._full_reset()
            return result

        @self.app.get("/api/reset/progress")
        async def get_reset_progress():
            """查询初始化进度（前端进度条轮询）"""
            p = getattr(self, "_reset_progress", None)
            if not p:
                return {"percent": 0, "step": "未开始", "done": False, "error": None}
            return p

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
            try:
                from src.tools.permission_settings import PermissionSettings
            except ImportError:
                from tools.permission_settings import PermissionSettings
            ps = PermissionSettings()
            return ps.list_settings()

        @self.app.post("/api/permission-settings")
        async def save_permission_settings(data: dict):
            try:
                from src.tools.permission_settings import PermissionSettings
            except ImportError:
                from tools.permission_settings import PermissionSettings
            ps = PermissionSettings()
            return ps.update_settings(data)

        # ── 文字转语音：edge-tts 合成 mp3 ──
        @self.app.post("/api/tts")
        def api_tts(data: dict):
            text = (data.get("text") or "").strip()
            lang = data.get("lang") or "zh-CN"
            # 设置页试听时用 voice/rate 显式覆盖该语言的默认音色/语速
            voice = data.get("voice") or None
            rate = data.get("rate") or None
            if not text:
                return JSONResponse({"error": "empty text"}, status_code=400)
            t0 = time.time()
            try:
                mp3 = synthesize_tts(text, lang, voice=voice, rate=rate)
                print(f"[tts] OK {lang} {len(text)}字 {time.time()-t0:.2f}s")
                return Response(content=mp3, media_type="audio/mpeg")
            except Exception as e:
                print(f"[tts] 合成失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=503)

        # ── 音色设置：GET 当前值+候选音色，POST 保存（data/settings/tts.json） ──
        @self.app.get("/api/tts-settings")
        def api_tts_settings_get():
            return {"settings": load_tts_settings(), "candidates": _TTS_VOICE_CANDIDATES}

        @self.app.post("/api/tts-settings")
        def api_tts_settings_post(data: dict):
            try:
                saved = save_tts_settings(data)
                return {"success": True, "message": "音色设置已保存", "settings": saved}
            except Exception as e:
                print(f"保存音色设置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)

        # ── 讯飞语音识别密钥：GET 脱敏状态，POST 保存/清空（data/settings/xfyun.json） ──
        # 运行链路 _xfyun_config() 每次实时读文件 → 保存即生效，无需重启；环境变量优先级更高
        @self.app.get("/api/xf-settings")
        def api_xf_settings_get():
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "settings", "xfyun.json")
            cfg = {}
            try:
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        cfg = json.load(f) or {}
            except Exception:
                cfg = {}
            def _mask(v):
                v = str(v or "")
                if not v:
                    return ""
                if len(v) <= 8:
                    return v[:2] + "***"
                return v[:3] + "*" * 6 + v[-2:]

            env_list = []
            for key, env in (("app_id", "XFYUN_APP_ID"),
                             ("api_key", "XFYUN_API_KEY"),
                             ("api_secret", "XFYUN_API_SECRET")):
                if os.getenv(env):
                    env_list.append(env)
            return {
                "configured": bool(cfg.get("app_id") and cfg.get("api_key") and cfg.get("api_secret")),
                "env_set": env_list,
                "masked": {"app_id": _mask(cfg.get("app_id")),
                           "api_key": _mask(cfg.get("api_key")),
                           "api_secret": _mask(cfg.get("api_secret"))},
            }

        @self.app.post("/api/xf-settings")
        def api_xf_settings_post(data: dict):
            p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "data", "settings", "xfyun.json")
            cfg = {}
            try:
                if os.path.exists(p):
                    with open(p, encoding="utf-8") as f:
                        cfg = json.load(f) or {}
            except Exception:
                cfg = {}
            if data.get("clear"):
                cfg = {}
            else:
                for k in ("app_id", "api_key", "api_secret"):
                    v = str(data.get(k) or "").strip()
                    if v:
                        cfg[k] = v
            try:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"保存讯飞配置失败: {e}")
                return JSONResponse({"error": str(e)}, status_code=500)
            env_list = [e for e in ("XFYUN_APP_ID", "XFYUN_API_KEY", "XFYUN_API_SECRET")
                        if os.getenv(e)]
            note = f"（检测到环境变量 {', '.join(env_list)} 仍优先生效）" if env_list else "，立即生效"
            return {"success": True, "message": f"讯飞密钥已保存{note}"}

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
            # 负面反馈 → 触发反思学习（从错误中改进）
            learned = False
            if rating == "down":
                learned = self.brain_link.learn_from_feedback(
                    content, reasoning or "")
            return {"success": True, "learned": learned}
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
            if hasattr(be, "get_token_stats"):
                try:
                    result["token_stats"] = be.get_token_stats()
                except Exception:
                    result["token_stats"] = {}
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

    async def _full_reset(self) -> dict:
        """完全初始化：清空记忆、重置设置/授权/提醒、清空知识库与归档。

        分阶段执行并更新 self._reset_progress（供前端进度条轮询）。

        返回统计信息。
        """
        import os as _os

        report = {}

        # 进度定义：阶段名 → (说明, 权重)
        self._reset_progress = {"percent": 0, "step": "准备中", "done": False,
                                "error": None}
        steps = [
            ("memory", "清空记忆库", 30),
            ("archive", "清空记忆归档", 10),
            ("provider", "重置模型设置", 15),
            ("perm_settings", "重置授权规则", 10),
            ("perm", "清空外部授权", 15),
            ("reminder", "清空提醒", 10),
            ("knowledge", "清空知识库", 10),
        ]
        done_weight = 0
        max_weight = sum(w for _, _, w in steps)

        def _report(percent, label):
            self._reset_progress = {"percent": percent, "step": label,
                                    "done": False, "error": None}

        # 1. 清空记忆库（json 记忆 + 嵌入 + 图谱）
        mem_cleared = 0
        _report(int(done_weight / max_weight * 100), "清空记忆库...")
        await asyncio.sleep(0.05)
        try:
            if self.brain_link and self.brain_link.memory_engine:
                store = self.brain_link.memory_engine.store
                mem_cleared = store.get_stats().get("total_memories", 0)
                store.reset_memory()
                self.brain_link._user_profile = ""
                self.brain_link._history_summary = ""
                self.brain_link._conversation_history = []
                self.brain_link._project_context = ""
                self.brain_link._project_scanned = False
        except Exception as e:
            report["memory_error"] = str(e)
        report["memories"] = mem_cleared
        done_weight += 30

        # 2. 清空记忆归档目录
        _report(int(done_weight / max_weight * 100), "清空记忆归档...")
        await asyncio.sleep(0.05)
        try:
            archives = _os.path.join("data", "memory", "json", "archives")
            if _os.path.isdir(archives):
                for f in _os.listdir(archives):
                    _os.remove(_os.path.join(archives, f))
        except Exception as e:
            report["archive_error"] = str(e)
        done_weight += 10

        # 3. 重置模型提供者设置为默认（删除文件 → 下次加载走默认，含清空 API key）
        _report(int(done_weight / max_weight * 100), "重置模型设置...")
        await asyncio.sleep(0.05)
        try:
            provider_file = _os.path.join("data", "settings", "provider.json")
            if _os.path.exists(provider_file):
                _os.remove(provider_file)
        except Exception as e:
            report["provider_error"] = str(e)
        done_weight += 15

        # 4. 重置授权默认规则
        _report(int(done_weight / max_weight * 100), "重置授权规则...")
        await asyncio.sleep(0.05)
        try:
            from src.tools.permission_settings import PermissionSettings
            ps = PermissionSettings()
            ps.update_settings({
                "file_read": "ask",
                "file_write": "ask",
                "command_exec": "ask",
            })
        except Exception as e:
            report["perm_settings_error"] = str(e)
        done_weight += 10

        # 5. 清空外部文件授权
        _report(int(done_weight / max_weight * 100), "清空外部授权...")
        await asyncio.sleep(0.05)
        try:
            try:
                from src.tools.file_permissions import (
                    get_permission_manager, reset_permission_manager,
                )
            except ImportError:
                from tools.file_permissions import (
                    get_permission_manager, reset_permission_manager,
                )
            reset_permission_manager()  # 丢弃内存中的旧授权
            perm_file = _os.path.join("data", "permissions.json")
            if _os.path.exists(perm_file):
                _os.remove(perm_file)
        except Exception as e:
            report["perm_error"] = str(e)
        done_weight += 15

        # 6. 清空提醒数据库与通知日志
        _report(int(done_weight / max_weight * 100), "清空提醒...")
        await asyncio.sleep(0.05)
        try:
            for f in ["data/reminders/reminders.db",
                      "data/reminders/notifications.log"]:
                if _os.path.exists(f):
                    _os.remove(f)
        except Exception as e:
            report["reminder_error"] = str(e)
        done_weight += 10

        # 7. 清空项目知识库
        _report(int(done_weight / max_weight * 100), "清空知识库...")
        await asyncio.sleep(0.05)
        try:
            kb = _os.path.join("data", "knowledge", "knowledge_base.json")
            if _os.path.exists(kb):
                _os.remove(kb)
        except Exception as e:
            report["knowledge_error"] = str(e)
        done_weight += 10

        _report(100, "初始化完成")
        import logging as _lg
        _lg.getLogger("link").warning(f"LINK 已完全初始化: {report}")
        return {
            "success": True,
            "message": f"✅ LINK 已完全初始化，清除 {mem_cleared} 条记忆，设置已重置",
            "cleared": report,
        }

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
    
    def _broadcast_reminder(self, reminder_data: Dict[str, Any]):
        """广播提醒到所有 WebSocket 客户端（由事件循环线程调用）"""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            asyncio.run_coroutine_threadsafe(
                self._broadcast_event(reminder_data), loop
            )
        except Exception:
            pass

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

    # ══════════════════════════════════════════════════════════════
    # 讯飞语音识别（iat v2）：浏览器采集音频 → 本服务转发讯飞 → 文本回前端
    # 未配置 data/settings/xfyun.json 时自动回退浏览器内置识别
    # ══════════════════════════════════════════════════════════════
    XFYUN_URL = "wss://iat-api.xfyun.cn/v2/iat"
    XFYUN_HOST = "iat-api.xfyun.cn"
    XFYUN_PATH = "/v2/iat"

    def _xfyun_config(self) -> Optional[Dict[str, str]]:
        """读取讯飞配置（data/settings/xfyun.json，可被环境变量覆盖）；缺任一字段返回 None"""
        cfg = {}
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "data", "settings", "xfyun.json")
        try:
            if os.path.exists(p):
                with open(p, encoding="utf-8") as f:
                    cfg = json.load(f) or {}
        except Exception as e:
            print(f"读取讯飞配置失败: {e}")
        for env, key in (("XFYUN_APP_ID", "app_id"),
                         ("XFYUN_API_KEY", "api_key"),
                         ("XFYUN_API_SECRET", "api_secret")):
            v = os.getenv(env)
            if v:
                cfg[key] = v
        if cfg.get("app_id") and cfg.get("api_key") and cfg.get("api_secret"):
            return cfg
        return None

    @staticmethod
    def _xfyun_auth_header(api_key: str, api_secret: str) -> Dict[str, str]:
        """讯飞 v2 鉴权：HMAC-SHA256 签名 Authorization 头"""
        date = datetime.now(datetime.timezone.utc).strftime('%a, %d %b %Y %H:%M:%S GMT')
        string_to_sign = (f"host: {WebActiveLINK.XFYUN_HOST}\n"
                          f"date: {date}\n"
                          f"GET {WebActiveLINK.XFYUN_PATH} HTTP/1.1")
        sig = base64.b64encode(
            hmac.new(api_secret.encode("utf-8"), string_to_sign.encode("utf-8"),
                     hashlib.sha256).digest()).decode("utf-8")
        auth = (f'api_key="{api_key}", algorithm="hmac-sha256", '
                f'headers="host date request-line", signature="{sig}"')
        return {"Host": WebActiveLINK.XFYUN_HOST, "Date": date, "Authorization": auth}

    async def _xfyun_run(self, websocket: WebSocket, audio_q: asyncio.Queue,
                         lang: str) -> None:
        """讯飞识别会话：消费音频队列 → 转发 iat → 回传 partial / final / error"""
        cfg = self._xfyun_config()
        if not cfg:
            await websocket.send_json({
                "type": "voice_error",
                "data": "讯飞未配置：请填写 data/settings/xfyun.json 的 app_id/api_key/api_secret"
            })
            return
        # 语言映射：zh_cn / en_us（zh_tw 暂用 mandarin 口音，输出简体）
        business = {"language": "zh_cn", "domain": "iat", "accent": "mandarin",
                    "dwa": "wpgs", "ptt": 0, "vad_eos": 1500}
        if lang == "en_us":
            business = {"language": "en_us", "domain": "iat",
                        "dwa": "wpgs", "ptt": 0, "vad_eos": 1500}
        import websockets as _ws
        try:
            async with _ws.connect(
                self.XFYUN_URL,
                additional_headers=self._xfyun_auth_header(
                    cfg["api_key"], cfg["api_secret"]),
                max_size=None
            ) as xf:
                await xf.send(json.dumps({
                    "common": {"app_id": cfg["app_id"]},
                    "business": business,
                    "data": {"status": 0, "format": "audio/L16;rate=16000",
                             "encoding": "raw", "seq": 0}
                }))
                segs: List[str] = []
                done = asyncio.Event()

                async def send_loop():
                    while not done.is_set():
                        try:
                            chunk = await asyncio.wait_for(audio_q.get(), timeout=0.5)
                        except asyncio.TimeoutError:
                            continue
                        if chunk is None:  # 结束哨兵 → 通知讯飞本段结束
                            try:
                                await xf.send(json.dumps({"data": {"status": 2}}))
                            except Exception:
                                pass
                            return
                        await xf.send(chunk)

                async def recv_loop():
                    async for msg in xf:
                        if isinstance(msg, bytes):
                            continue
                        try:
                            d = json.loads(msg)
                        except Exception:
                            continue
                        if d.get("code", 0) != 0:
                            raise RuntimeError(d.get("message") or f"讯飞错误码 {d.get('code')}")
                        rst = (d.get("data") or {}).get("result")
                        if rst is None:
                            if (d.get("data") or {}).get("status") == 2:
                                done.set()
                            continue
                        if isinstance(rst, str):  # 部分返回 base64，防御性解码
                            try:
                                rst = json.loads(base64.b64decode(rst))
                            except Exception:
                                continue
                        # wpgs 逐句拼接：rpl 替换第 rg[0] 段之后追加，apd 直接追加
                        pgs = rst.get("pgs", "rpl")
                        rg = rst.get("rg") or [0, 0]
                        words = "".join(
                            cw.get("w", "") for s in rst.get("ws", [])
                            for cw in (s.get("cw") or []))
                        if pgs == "rpl" and rg:
                            segs = segs[: rg[0]]
                        segs.append(words)
                        segs = segs[-200:]
                        text = "".join(segs).strip()
                        if text:
                            await websocket.send_json({"type": "voice_partial", "data": text})
                        if (d.get("data") or {}).get("status") == 2:
                            done.set()

                try:
                    await asyncio.wait_for(
                        asyncio.gather(send_loop(), recv_loop()), timeout=120)
                except asyncio.TimeoutError:
                    done.set()
            text = "".join(segs).strip()
            if text:
                await websocket.send_json({"type": "voice_final", "data": text})
        except Exception as e:
            print(f"讯飞识别会话异常: {e}")
            try:
                await websocket.send_json({"type": "voice_error",
                                           "data": f"讯飞识别失败: {e}"})
            except Exception:
                pass

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
    
    def _process_input_direct(self, text: str, stream_callback: callable = None,
                              voice: bool = False) -> dict:
        """处理用户输入，返回 {result, reasoning, spoken}"""
        if not self.brain_link:
            return {"result": "⚠️ 大脑引擎未就绪", "reasoning": ""}
        try:
            start = time.time()
            result = self.brain_link.process_input(text, stream_callback=stream_callback,
                                                   voice=voice)
            reasoning = getattr(self.brain_link, '_last_reasoning', '')
            elapsed = time.time() - start
            import logging
            logging.getLogger("link").info(f"LLM 响应完成 ({elapsed:.1f}s)")
            # 语音轮次：剥离回复末尾的『播报：』一句话总结（前端只播这句，不念全文）
            spoken = None
            if voice and result:
                import re as _re
                _matches = list(_re.finditer(r'\n?\s*播报[:：]\s*([^\n]+)', result))
                if _matches:
                    _m = _matches[-1]
                    spoken = _m.group(1).strip()
                    result = (result[:_m.start()] + result[_m.end():]).strip()
            return {"result": result, "reasoning": reasoning, "spoken": spoken}
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
        html += `<td><a onclick="showMemDetail('${escapeHtml(mem.id).replace(/'/g, "\\\\'")}')" style="cursor:pointer;color:#1a73e8;font-size:12px">详情</a></td></tr>`;
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
        listHtml += `<td><button class="restore-btn" onclick="restoreArchive('${escapeHtml(a.archive_id).replace(/'/g, "\\\\'")}')" style="padding:4px 12px;background:#34a853;color:#fff;border:none;border-radius:4px;cursor:pointer;font-size:12px">恢复</button></td></tr>`;
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
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#f0f2f5;color:#333;display:flex;height:100vh}
.sidebar{width:200px;background:#fff;border-right:1px solid #e0e0e0;padding:20px 0;flex-shrink:0;display:flex;flex-direction:column}
.sidebar h1{font-size:18px;padding:0 20px 20px;color:#1a1a2e;border-bottom:1px solid #eee;margin-bottom:8px}
.nav-item{padding:12px 20px;cursor:pointer;font-size:14px;color:#555;display:flex;align-items:center;gap:8px;transition:all .15s;border:none;background:none;width:100%;text-align:left}
.nav-item:hover{background:#f5f5f5;color:#1a73e8}
.nav-item.active{background:#e8f0fe;color:#1a73e8;font-weight:500;border-right:3px solid #1a73e8}
.content{flex:1;min-width:0;padding:24px 32px;overflow-y:auto;max-width:700px}
.tab{display:none}
.tab.active{display:block}
.card{background:#fff;border-radius:12px;padding:20px;margin-bottom:16px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
.card h2{font-size:15px;margin-bottom:12px;color:#1a73e8}
.field{margin-bottom:14px}
.field label{display:block;font-size:13px;color:#555;margin-bottom:4px;font-weight:500}
.field .value-display{background:#f5f5f5;padding:10px 12px;border-radius:8px;font-size:13px;color:#333;word-break:break-all}
.field input,.field select{width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;transition:border-color .2s}
.field input:focus,.field select:focus{border-color:#1a73e8}
.radio-group{display:flex;flex-wrap:wrap;gap:12px 24px;margin-bottom:4px}
.radio-group label{font-size:14px;cursor:pointer;display:flex;align-items:center;gap:4px;color:#333;padding:8px 12px;border:2px solid #e0e0e0;border-radius:8px;transition:all .2s;white-space:nowrap;max-width:100%}
.radio-group label:has(input:checked){border-color:#1a73e8;background:#e8f0fe}
.btn{padding:10px 20px;border:none;border-radius:8px;cursor:pointer;font-size:13px;font-weight:500;transition:all .2s}
.btn-primary{background:#1a73e8;color:#fff}
.btn-primary:hover{background:#1557b0}
.btn-primary:disabled{background:#ccc;cursor:not-allowed}
.btn-secondary{background:#e8eaed;color:#333}
.btn-secondary:hover{background:#d2d5d9}
.action-bar{display:flex;gap:10px;margin-top:16px;align-items:center}
.status{display:none;padding:10px 14px;border-radius:8px;margin-bottom:12px;font-size:13px}
.status.success{display:block;background:#e8f5e9;color:#2e7d32;border:1px solid #c8e6c9}
.status.error{display:block;background:#fce8e8;color:#d93025;border:1px solid #f5c6cb}
.hidden{display:none}
.model-info{font-size:12px;color:#888;margin-top:6px}
.status-preview{margin-top:8px;font-size:13px;color:#555;padding:10px 14px;background:#f9f9f9;border-radius:8px;border:1px solid #eee;overflow-wrap:anywhere}
.status-preview strong{color:#1a73e8}
/* ≤600px：侧栏转为顶部横向导航，内容区不再被 200px 侧栏压扁 */
@media (max-width:600px){
body{flex-direction:column}
.sidebar{width:auto;flex-direction:row;align-items:center;gap:4px;overflow-x:auto;padding:8px 12px;border-right:none;border-bottom:1px solid #e0e0e0;flex-shrink:1}
.sidebar h1{font-size:15px;padding:0 10px 0 0;margin:0;border-bottom:none;white-space:nowrap}
.nav-item{width:auto;padding:8px 12px;white-space:nowrap;border-radius:8px}
.nav-item.active{border-right:none;background:#e8f0fe}
.sidebar>div{display:none}
.sidebar a[href="/"]{padding:8px 12px;border-top:none!important;white-space:nowrap}
.content{max-width:none;padding:16px;min-width:0}
}
</style>
</head>
<body>

<div class="sidebar">
  <h1>&#x2699;&#xFE0F; LINK 设置</h1>
  <button class="nav-item active" data-tab="api" onclick="switchTab('api')">&#x1F310; API 配置</button>
  <button class="nav-item" data-tab="perm" onclick="switchTab('perm')">&#x1F512; 授权规则</button>
  <button class="nav-item" data-tab="voice" onclick="switchTab('voice')">&#x1F3A4; 音色</button>
  <button class="nav-item" data-tab="xf" onclick="switchTab('xf')">&#x1F399;&#xFE0F; 语音识别</button>
  <button class="nav-item" data-tab="init" onclick="switchTab('init')" style="color:#d93025">&#x1F5D1;&#xFE0F; 初始化</button>
  <div style="flex:1"></div>
  <a href="/" style="padding:12px 20px;color:#888;text-decoration:none;font-size:13px;border-top:1px solid #eee">&#x2190; 返回聊天</a>
</div>

<div class="content">
<div id="status" class="status"></div>

<div id="tab-api" class="tab active">
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
        <option value="custom">自定义</option>
      </select>
    </div>
    <div class="field">
      <label>API 地址</label>
      <input id="api-base" placeholder="https://api.deepseek.com">
      <div id="api-base-preview" class="status-preview"></div>
    </div>
    <div class="field">
      <label>API Key</label>
      <input id="api-key" type="password" placeholder="sk-...">
      <div id="api-key-preview" class="status-preview"></div>
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
  <div class="action-bar">
    <button class="btn btn-primary" onclick="saveApiSettings()">保存 API 设置</button>
    <button class="btn btn-secondary" onclick="testConnection()">测试连接</button>
  </div>
</div>

<div id="tab-perm" class="tab">
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
  <div class="action-bar">
    <button class="btn btn-primary" onclick="savePermSettings()">保存授权规则</button>
  </div>
</div>

<div id="tab-voice" class="tab">
  <div class="card">
    <h2>&#x1F3A4; 语音播报音色</h2>
    <p style="font-size:13px;color:#666;line-height:1.7;margin-bottom:12px">
      聊天播报（🔊）用的朗读音色与语速，保存后立即生效，无需重启。<br>
      语速为百分比：<code>-10%</code> 放慢、<code>+10%</code> 加快，留空用微软默认。
    </p>
    <div id="tts-voice-fields"></div>
    <div class="model-info">音色通过 edge-tts（微软神经语音）在服务器端合成；未安装或合成失败时自动回退浏览器内置朗读。</div>
  </div>
  <div class="action-bar">
    <button class="btn btn-primary" onclick="saveTtsSettings()">保存音色设置</button>
  </div>
</div>

<div id="tab-xf" class="tab">
  <div class="card">
    <h2>&#x1F399;&#xFE0F; 语音识别（讯飞）</h2>
    <p style="font-size:13px;color:#666;line-height:1.7;margin-bottom:12px">
      填写讯飞开放平台「<strong>语音听写（iat）</strong>」的密钥后，语音对话识别自动改走<strong>讯飞</strong>
      （中文准确度更高、不依赖 Google 服务）；三项留空则回退<strong>浏览器内置识别</strong>。
      保存后立即生效，无需重启。
    </p>
    <div class="field">
      <label>讯飞 APPID</label>
      <input id="xf-app-id" type="text" autocomplete="off">
    </div>
    <div class="field">
      <label>讯飞 APIKey</label>
      <input id="xf-api-key" type="password" autocomplete="new-password">
    </div>
    <div class="field">
      <label>讯飞 APISecret</label>
      <input id="xf-api-secret" type="password" autocomplete="new-password">
    </div>
    <div id="xf-engine-preview" class="status-preview" style="margin-top:4px"></div>
    <div class="model-info" style="margin-top:10px;line-height:1.8">
      &#x1F511; 密钥只保存在 <code>data/settings/xfyun.json</code>（不入库）；也可用环境变量
      <code>XFYUN_APP_ID / XFYUN_API_KEY / XFYUN_API_SECRET</code> 覆盖（优先级更高，此时页面不可改）。
      <br>&#x1F4A1; 字段留空 = 保持原值不变；想清空密钥回退浏览器识别，点下方「清除并回退浏览器识别」。
    </div>
  </div>
  <div class="action-bar">
    <button class="btn btn-primary" onclick="saveXfSettings()">保存讯飞密钥</button>
    <button class="btn btn-secondary" onclick="clearXfSettings()">清除并回退浏览器识别</button>
  </div>
</div>

<div id="tab-init" class="tab">
  <div class="card" style="border:1px solid #f5c6cb;background:#fffafa">
    <h2 style="color:#d93025">&#x1F5D1;&#xFE0F; 完全初始化 LINK</h2>
    <p style="font-size:13px;color:#666;line-height:1.7;margin-bottom:8px">
      将 LINK 恢复为出厂初始状态，<strong style="color:#d93025">所有记忆与设置都会被清除</strong>，不可恢复。
    </p>
    <div style="background:#f5f5f5;border-radius:8px;padding:12px 14px;font-size:13px;color:#444;line-height:1.8;margin-bottom:16px">
      <div style="font-weight:600;color:#d93025;margin-bottom:6px">&#x26A0;&#xFE0F; 以下数据将被清除：</div>
      <div>&#x1F5C2;&#xFE0F; 全部记忆（对话历史、用户画像、问卷信息、项目知识）</div>
      <div>&#x1F4BE; 记忆归档文件</div>
      <div>&#x2699;&#xFE0F; 模型设置（在线/离线模式、API 地址、密钥、模型）</div>
      <div>&#x1F512; 授权规则（文件读取/写入/命令执行默认权限）</div>
      <div>&#x1F513; 所有外部文件/目录授权</div>
      <div>&#x23F0; 所有提醒（提醒数据库与通知日志）</div>
      <div>&#x1F4D6; 项目知识库</div>
    </div>
    <div class="action-bar">
      <button class="btn btn-primary" id="btn-reset" onclick="confirmReset()" style="background:#d93025">&#x1F5D1;&#xFE0F; 初始化 LINK</button>
    </div>
  </div>
</div>
</div>

<!-- 初始化确认弹窗 -->
<div id="reset-modal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,.5);align-items:center;justify-content:center;z-index:1000">
  <div style="background:#fff;border-radius:12px;padding:24px;width:min(480px,92vw);box-shadow:0 8px 40px rgba(0,0,0,.3)">
    <div style="font-size:16px;font-weight:600;color:#d93025;margin-bottom:12px">&#x26A0;&#xFE0F; 确认完全初始化？</div>
    <div style="font-size:13px;color:#555;line-height:1.8;margin-bottom:8px">此操作将永久清除以下内容，<strong style="color:#d93025">无法恢复</strong>：</div>
    <div style="background:#fce8e8;border:1px solid #f5c6cb;border-radius:8px;padding:12px 14px;font-size:13px;color:#444;line-height:1.9;margin-bottom:16px">
      <div>&#x2022; 全部记忆：对话历史、用户画像、问卷信息、项目知识</div>
      <div>&#x2022; 记忆归档文件</div>
      <div>&#x2022; 模型设置：在线/离线模式、API 地址、密钥、模型</div>
      <div>&#x2022; 授权规则与所有外部文件/目录授权</div>
      <div>&#x2022; 所有提醒与通知日志</div>
      <div>&#x2022; 项目知识库</div>
    </div>
    <!-- 确认短语输入 -->
    <div style="font-size:13px;color:#555;margin-bottom:6px">请输入 <strong style="color:#d93025">"确认初始化"</strong> 以启用按钮：</div>
    <input id="reset-confirm-input" type="text" placeholder="输入：确认初始化" oninput="checkResetConfirm()"
      style="width:100%;padding:10px 12px;border:1px solid #ddd;border-radius:8px;font-size:14px;outline:none;box-sizing:border-box;margin-bottom:16px">
    <!-- 进度条（初始化时显示） -->
    <div id="reset-progress-wrap" style="display:none;margin-bottom:16px">
      <div style="font-size:13px;color:#555;margin-bottom:6px"><span id="reset-progress-label">初始化中...</span> <span id="reset-progress-pct" style="color:#d93025;font-weight:600">0%</span></div>
      <div style="background:#eee;border-radius:6px;height:10px;overflow:hidden">
        <div id="reset-progress-bar" style="height:100%;width:0;background:linear-gradient(90deg,#d93025,#ea4335);transition:width .4s ease"></div>
      </div>
    </div>
    <div style="display:flex;gap:10px;justify-content:flex-end">
      <button class="btn btn-secondary" onclick="closeResetModal()">取消</button>
      <button class="btn btn-primary" id="btn-reset-confirm" onclick="doReset()" style="background:#d93025" disabled>确认初始化</button>
    </div>
  </div>
</div>

<script>
function showStatus(msg, type) {
  var el = document.getElementById("status");
  el.textContent = msg; el.className = "status " + (type || "success");
  setTimeout(function(){ el.className = "status"; }, 4000);
}
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(function(t){ t.classList.remove("active"); });
  document.querySelectorAll(".nav-item").forEach(function(n){ n.classList.remove("active"); });
  document.getElementById("tab-"+name).classList.add("active");
  document.querySelector(\'[data-tab="\'+name+\'"]\').classList.add("active");
}
function toggleMode() {
  var el = document.querySelector("input[name=mode]:checked");
  if (!el) return;
  var m = el.value;
  document.getElementById("online-settings").classList.toggle("hidden", m !== "online");
  document.getElementById("offline-settings").classList.toggle("hidden", m !== "offline");
}
async function loadModels() {
  var sel = document.getElementById("offline-model");
  sel.innerHTML = \'<option value="">加载中...</option>\';
  try {
    var r = await fetch("/api/models"); var d = await r.json();
    if (d.models && d.models.length > 0) {
      var em = ["bge-m3","nomic-embed-text","all-MiniLM"];
      sel.innerHTML = d.models.map(function(m){
        for(var i=0;i<em.length;i++){if(m.indexOf(em[i])===0) return \'<option value="\'+m+\'">\'+m+\' (仅嵌入)</option>\';}
        return \'<option value="\'+m+\'">\'+m+\'</option>\';
      }).join("");
    } else { sel.innerHTML = \'<option value="">未发现本地模型</option>\'; }
  } catch(e) { sel.innerHTML = \'<option value="">加载失败</option>\'; }
}
async function loadSettings() {
  try {
    var r = await fetch("/api/settings"); var s = await r.json();
    var radio = document.querySelector("input[name=mode][value=\\""+s.mode+"\\"]");
    if (radio) radio.checked = true;
    if (s.provider) document.getElementById("provider").value = s.provider;
    if (s.api_base) {
      document.getElementById("api-base").value = s.api_base;
      document.getElementById("api-base-preview").innerHTML = \'<strong>当前:</strong> \'+s.api_base;
    }
    if (s.api_key_display) {
      document.getElementById("api-key").placeholder = s.api_key_display;
      document.getElementById("api-key-preview").innerHTML = \'<strong>当前:</strong> \'+s.api_key_display+\' <span style="color:#999">(已保存)</span>\';
    }
    if (s.model) document.getElementById("model-name").value = s.model;
    if (s.temperature) document.getElementById("temperature").value = s.temperature;
    toggleMode();
    if (s.offline_model) {
      var sel = document.getElementById("offline-model");
      for(var i=0;i<sel.options.length;i++){if(sel.options[i].value===s.offline_model){sel.options[i].selected=true;break;}}
    }
  } catch(e) { showStatus("加载失败: "+e.message, "error"); }
}
async function saveApiSettings() {
  var btn = document.querySelector("#tab-api .btn-primary");
  btn.disabled = true; btn.textContent = "保存中...";
  var data = {
    mode: (document.querySelector("input[name=mode]:checked")||{}).value||"offline",
    provider: document.getElementById("provider").value,
    api_base: document.getElementById("api-base").value,
    api_key: document.getElementById("api-key").value,
    model: document.getElementById("model-name").value,
    offline_model: document.getElementById("offline-model").value,
    temperature: parseFloat(document.getElementById("temperature").value)||0.7,
  };
  try {
    var r = await fetch("/api/settings",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(data)});
    var d = await r.json();
    showStatus(d.message||"已保存", d.success?"success":"error");
    await loadSettings();
  } catch(e) { showStatus("保存失败: "+e.message, "error"); }
  btn.disabled = false; btn.textContent = "保存 API 设置";
}
async function savePermSettings() {
  var btn = document.querySelector("#tab-perm .btn-primary");
  btn.disabled = true; btn.textContent = "保存中...";
  try {
    var r = await fetch("/api/permission-settings",{method:"POST",headers:{"Content-Type":"application/json"},
      body:JSON.stringify({file_read:document.getElementById("perm-file-read").value,file_write:document.getElementById("perm-file-write").value,command_exec:document.getElementById("perm-command-exec").value})});
    await r.json();
    showStatus("授权规则已保存","success");
  } catch(e) { showStatus("保存失败: "+e.message, "error"); }
  btn.disabled = false; btn.textContent = "保存授权规则";
}
async function loadPermSettings() {
  try {
    var r = await fetch("/api/permission-settings"); var ps = await r.json();
    if (ps.file_read) document.getElementById("perm-file-read").value = ps.file_read;
    if (ps.file_write) document.getElementById("perm-file-write").value = ps.file_write;
    if (ps.command_exec) document.getElementById("perm-command-exec").value = ps.command_exec;
  } catch(e) {}
}
async function testConnection() {
  var modeEl = document.querySelector("input[name=mode]:checked");
  if (!modeEl) return;
  if (modeEl.value === "offline") {
    try { var r=await fetch("/api/models");var d=await r.json();showStatus(d.models&&d.models.length?"Ollama OK, "+d.models.length+" 个模型":"Ollama 正常","success");}catch(e){showStatus("连接失败","error");}
    return;
  }
  try { var r=await fetch("/api/settings/test",{method:"POST"});var d=await r.json();showStatus(d.message||"测试完成",d.success?"success":"error");}catch(e){showStatus("测试失败","error");}
}
// ── 完全初始化 ──
var _RESET_PHRASE = '确认初始化';
function confirmReset() {
  document.getElementById('reset-modal').style.display = 'flex';
  document.getElementById('reset-confirm-input').value = '';
  checkResetConfirm();
  // 重置进度条显示
  document.getElementById('reset-progress-wrap').style.display = 'none';
  document.getElementById('btn-reset-confirm').style.display = '';
}
function closeResetModal() {
  document.getElementById('reset-modal').style.display = 'none';
  document.getElementById('reset-confirm-input').value = '';
}
function checkResetConfirm() {
  // 输入完全匹配指定句子才启用确认按钮
  var v = document.getElementById('reset-confirm-input').value.trim();
  var btn = document.getElementById('btn-reset-confirm');
  btn.disabled = v !== _RESET_PHRASE;
}
async function doReset() {
  var btn = document.getElementById('btn-reset-confirm');
  btn.disabled = true; btn.textContent = '初始化中...';
  // 显示进度条
  var pw = document.getElementById('reset-progress-wrap');
  pw.style.display = 'block';
  btn.style.display = 'none';
  // 启动进度轮询
  var pollTimer = setInterval(async function() {
    try {
      var pr = await fetch('/api/reset/progress');
      var pd = await pr.json();
      if (pd && typeof pd.percent === 'number') {
        document.getElementById('reset-progress-bar').style.width = pd.percent + '%';
        document.getElementById('reset-progress-pct').textContent = pd.percent + '%';
        document.getElementById('reset-progress-label').textContent = pd.step || '初始化中...';
      }
    } catch(e) {}
  }, 300);
  try {
    var r = await fetch('/api/reset', {method: 'POST'});
    var d = await r.json();
    clearInterval(pollTimer);
    if (d.success) {
      // 进度条满
      document.getElementById('reset-progress-bar').style.width = '100%';
      document.getElementById('reset-progress-pct').textContent = '100%';
      document.getElementById('reset-progress-label').textContent = '初始化完成';
      showStatus(d.message, 'success');
      setTimeout(function(){ location.href = '/settings'; }, 1500);
    } else {
      pw.style.display = 'none';
      btn.style.display = '';
      showStatus(d.message || '初始化失败', 'error');
      btn.disabled = false; btn.textContent = '确认初始化';
    }
  } catch(e) {
    clearInterval(pollTimer);
    pw.style.display = 'none';
    btn.style.display = '';
    showStatus('初始化失败: ' + e.message, 'error');
    btn.disabled = false; btn.textContent = '确认初始化';
  }
}
function updateBaseUrl() {
  var p=document.getElementById("provider").value;
  var urls={deepseek:"https://api.deepseek.com",openai:"https://api.openai.com"};
  if(p!=="custom"){
    document.getElementById("api-base").value=urls[p]||"";
    document.getElementById("api-base-preview").innerHTML=\'<strong>默认:</strong> \'+(urls[p]||"");
  }
  var models={deepseek:"deepseek-chat",openai:"gpt-4o"};
  if(p!=="custom") document.getElementById("model-name").value=models[p]||"";
}
// ── 音色设置：候选由 GET /api/tts-settings 下发，试听走 /api/tts ──
var _ttsLangs = ["zh-CN","zh-TW","en-US"];
var _ttsLangNames = {"zh-CN":"中文","zh-TW":"繁體","en-US":"English"};
var _ttsSampleText = {
  "zh-CN":"好的，明天下午三点有个团队会议，我会提前十五分钟提醒你。",
  "zh-TW":"好的，明天下午三點有個團隊會議，我會提前十五分鐘提醒你。",
  "en-US":"All right. There is a team meeting at three tomorrow afternoon, and I will remind you fifteen minutes before."
};
async function loadTtsSettings() {
  try {
    var r = await fetch(\'/api/tts-settings\');
    var d = await r.json();
    var s = d.settings || {};
    var wrap = document.getElementById(\'tts-voice-fields\');
    wrap.innerHTML = \'\';
    _ttsLangs.forEach(function(lang) {
      var row = document.createElement(\'div\');
      row.className = \'field\';
      var opts = ((d.candidates || {})[lang] || []).map(function(c) {
        var sel = (s.voices || {})[lang] === c[0] ? \' selected\' : \'\';
        return \'<option value="\' + c[0] + \'"\' + sel + \'>\' + c[1] + \'</option>\';
      }).join(\'\');
      row.innerHTML =
        \'<label>\' + _ttsLangNames[lang] + \' · 音色</label>\' +
        \'<div style="display:flex;gap:8px;align-items:center">\' +
          \'<select id="tts-voice-\' + lang + \'">\' + opts + \'</select>\' +
          \'<input id="tts-rate-\' + lang + \'" style="width:90px;flex-shrink:0" placeholder="语速 %" value="\' + ((s.rates || {})[lang] || \'\') + \'">\' +
          \'<button class="btn btn-secondary" style="flex-shrink:0" onclick="playTtsSample(\\\'\' + lang + \'\\\')">试听</button>\' +
        \'</div>\';
      wrap.appendChild(row);
    });
  } catch(e) {
    showStatus(\'加载音色设置失败: \' + e.message, \'error\');
  }
}
function playTtsSample(lang) {
  var voice = document.getElementById(\'tts-voice-\' + lang).value;
  var rate = document.getElementById(\'tts-rate-\' + lang).value.trim();
  var au = document.getElementById(\'tts-preview-audio\');
  if (!au) { au = document.createElement(\'audio\'); au.id = \'tts-preview-audio\'; document.body.appendChild(au); }
  fetch(\'/api/tts\', {
    method: \'POST\',
    headers: {\'Content-Type\': \'application/json\'},
    body: JSON.stringify({text: _ttsSampleText[lang] || _ttsSampleText["zh-CN"], lang: lang, voice: voice, rate: rate || undefined})
  }).then(function(r) {
    if (!r.ok) { return r.json().then(function(e) { throw new Error(e.error || \'合成失败\'); }); }
    return r.blob();
  }).then(function(b) {
    au.src = URL.createObjectURL(b);
    var p = au.play();
    if (p && p.catch) p.catch(function() { showStatus(\'浏览器拦截了自动播放\', \'error\'); });
  }).catch(function(e) {
    showStatus(\'试听失败: \' + e.message, \'error\');
  });
}
async function saveTtsSettings() {
  var btn = document.querySelector(\'#tab-voice .btn-primary\');
  btn.disabled = true; btn.textContent = \'保存中...\';
  var voices = {}, rates = {};
  _ttsLangs.forEach(function(lang) {
    voices[lang] = document.getElementById(\'tts-voice-\' + lang).value;
    rates[lang] = document.getElementById(\'tts-rate-\' + lang).value.trim();
  });
  try {
    var r = await fetch(\'/api/tts-settings\', {
      method: \'POST\',
      headers: {\'Content-Type\': \'application/json\'},
      body: JSON.stringify({voices: voices, rates: rates})
    });
    var d = await r.json();
    showStatus(d.message || (d.success ? \'已保存\' : \'保存失败\'), d.success ? \'success\' : \'error\');
    if (d.success) loadTtsSettings();  // 服务端可能回退坏值，回读同步
  } catch(e) {
    showStatus(\'保存失败: \' + e.message, \'error\');
  }
  btn.disabled = false; btn.textContent = \'保存音色设置\';
}

// ── 讯飞语音识别配置：密钥存 data/settings/xfyun.json（不入库），环境变量可覆盖 ──
async function loadXfSettings() {
  var r, d;
  try { r = await fetch(\'/api/xf-settings\'); d = await r.json(); } catch(e) { return; }
  var ids = [\'xf-app-id\', \'xf-api-key\', \'xf-api-secret\'];
  var pv = document.getElementById(\'xf-engine-preview\');
  if (d.env_set && d.env_set.length) {  // 环境变量优先生效 → 锁定表单
    for (var i = 0; i < ids.length; i++) {
      var el = document.getElementById(ids[i]);
      el.value = \'\'; el.disabled = true;
    }
    pv.textContent = \'引擎：讯飞（环境变量 \' + d.env_set.join(\', \') + \' 配置中，页面不可修改）\';
    return;
  }
  for (var i = 0; i < ids.length; i++) {
    var el = document.getElementById(ids[i]);
    el.disabled = false;
    var key = ids[i].slice(3).replace(/-/g, \'_\');
    var m = (d.masked && d.masked[key]) || \'\';
    el.value = \'\';
    el.placeholder = m ? \'已配置：\' + m + \'（留空保持不变）\' : \'未配置\';
  }
  pv.textContent = d.configured
    ? \'引擎：讯飞已启用（三项留空直接保存 = 保持当前密钥不变）\'
    : \'引擎：浏览器内置识别（未配置讯飞，填写下方密钥并保存后自动切换）\';
}
async function saveXfSettings() {
  var data = {
    app_id: document.getElementById(\'xf-app-id\').value.trim(),
    api_key: document.getElementById(\'xf-api-key\').value.trim(),
    api_secret: document.getElementById(\'xf-api-secret\').value.trim()
  };
  if (!data.app_id && !data.api_key && !data.api_secret) {
    showStatus(\'请至少填写一项密钥\', \'error\'); return;
  }
  var btn = document.querySelector(\'#tab-xf .btn-primary\'); btn.disabled = true;
  try {
    var r = await fetch(\'/api/xf-settings\', {method: \'POST\', headers: {\'Content-Type\': \'application/json\'}, body: JSON.stringify(data)});
    var d = await r.json();
    showStatus(d.message || (d.success ? \'已保存\' : \'保存失败\'), d.success ? \'success\' : \'error\');
    if (d.success) loadXfSettings();  // 回读刷新状态与占位符
  } catch(e) { showStatus(\'保存失败: \' + e.message, \'error\'); }
  btn.disabled = false;
}
async function clearXfSettings() {
  var btn = document.querySelector(\'#tab-xf .btn-secondary\'); btn.disabled = true;
  try {
    var r = await fetch(\'/api/xf-settings\', {method: \'POST\', headers: {\'Content-Type\': \'application/json\'}, body: JSON.stringify({clear: true})});
    var d = await r.json();
    showStatus(d.message || (d.success ? \'已清除\' : \'清除失败\'), d.success ? \'success\' : \'error\');
    if (d.success) loadXfSettings();
  } catch(e) { showStatus(\'清除失败: \' + e.message, \'error\'); }
  btn.disabled = false;
}
loadModels(); loadSettings(); loadPermSettings(); loadTtsSettings(); loadXfSettings();
document.getElementById("api-base").addEventListener("input",function(){
  this.value&&(document.getElementById("api-base-preview").innerHTML=\'<strong>待保存:</strong> \'+this.value);
});
document.getElementById("api-key").addEventListener("input",function(){
  if(this.value) document.getElementById("api-key-preview").innerHTML=\'<strong>待保存:</strong> 新密钥 (\'+this.value.length+\' 字符)\';
  else document.getElementById("api-key-preview").innerHTML=\'\';
});
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