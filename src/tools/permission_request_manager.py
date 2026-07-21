"""
权限请求/响应阻塞管理器

当工具执行遇到 PermissionError 时，创建 PermissionRequest 并阻塞线程，
等用户通过前端弹窗响应后再继续执行。
"""
import threading
import uuid
import time
import logging
from typing import Optional, Callable, List, Dict
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("link.permission_request")


class ResourceType(Enum):
    FILE = "file"
    COMMAND = "command"


@dataclass
class PermissionRequest:
    """权限请求，对应前端一个弹窗"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resource: str = ""  # 文件路径或命令字符串
    mode: str = "read"  # read / write / execute
    resource_type: ResourceType = ResourceType.FILE
    created_at: float = field(default_factory=time.time)
    _event: threading.Event = field(default_factory=threading.Event)
    _response: Optional[dict] = None


class PermissionRequestManager:
    """权限请求管理器（单例）"""

    _instance: Optional['PermissionRequestManager'] = None
    _lock: threading.Lock = threading.Lock()

    def __init__(self):
        self._requests: Dict[str, PermissionRequest] = {}
        self._callbacks: List[Callable[[PermissionRequest], None]] = []
        self._req_lock = threading.Lock()
        self._logger = logging.getLogger("link.perm_req_mgr")

    @classmethod
    def get_instance(cls) -> 'PermissionRequestManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """仅用于测试"""
        with cls._lock:
            cls._instance = None

    def register_callback(self, cb: Callable[[PermissionRequest], None]):
        """注册回调（创建请求时触发，用于通知前端弹窗）"""
        with self._req_lock:
            self._callbacks.append(cb)

    def unregister_callback(self, cb: Callable[[PermissionRequest], None]):
        """取消注册回调"""
        with self._req_lock:
            try:
                self._callbacks.remove(cb)
            except ValueError:
                pass

    def create_request(self, resource: str, mode: str,
                       resource_type: ResourceType) -> PermissionRequest:
        """创建权限请求，通知所有回调，返回 request"""
        req = PermissionRequest(resource=resource, mode=mode,
                                resource_type=resource_type)
        with self._req_lock:
            self._requests[req.id] = req
            cbs = list(self._callbacks)
        for cb in cbs:
            try:
                cb(req)
            except Exception as e:
                self._logger.error(f"权限回调异常: {e}")
        return req

    def wait_for_response(self, req_id: str, timeout: float = 300) -> dict:
        """阻塞等待用户响应（最多 timeout 秒），超时返回拒绝"""
        req = self._requests.get(req_id)
        if not req:
            return {"approved": False, "reason": "request_not_found"}
        ok = req._event.wait(timeout=timeout)
        if not ok:
            self._logger.warning(f"权限请求超时: {req_id}")
            with self._req_lock:
                self._requests.pop(req_id, None)
            return {"approved": False, "reason": "timeout"}
        with self._req_lock:
            resp = req._response or {"approved": False, "reason": "no_response"}
            self._requests.pop(req_id, None)
        return resp

    def respond(self, req_id: str, approved: bool, duration: str = "once"):
        """用户响应：设置结果并唤醒等待线程"""
        req = self._requests.get(req_id)
        if not req:
            self._logger.warning(f"权限请求 {req_id} 已不存在")
            return
        req._response = {"approved": approved, "duration": duration}
        req._event.set()
        self._logger.info(f"权限响应: {req_id} approved={approved} duration={duration}")

    def cancel_all(self):
        """拒绝所有待处理请求（如断开连接时）"""
        with self._req_lock:
            reqs = list(self._requests.values())
            self._requests.clear()
        for req in reqs:
            req._response = {"approved": False, "reason": "disconnected"}
            req._event.set()

    @property
    def pending_count(self) -> int:
        return len(self._requests)

    def list_pending(self) -> list:
        return [
            {"id": rid, "resource": req.resource, "mode": req.mode,
             "resource_type": req.resource_type.value, "created_at": req.created_at}
            for rid, req in self._requests.items()
        ]
