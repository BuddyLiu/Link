"""
权限请求/响应阻塞管理器

当工具执行遇到 PermissionError 时，创建 PermissionRequest 并阻塞线程，
等用户通过前端弹窗响应后再继续执行。
"""
import threading
import uuid
import time
import logging
import sys
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
    suggest_dir: Optional[str] = None  # 建议授权的目录（用于目录授权弹窗）
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
        # 文件请求：自动计算建议授权的目录（用于前端目录授权弹窗）
        if resource_type == ResourceType.FILE and resource:
            req.suggest_dir = self._suggest_dir(resource)
        with self._req_lock:
            self._requests[req.id] = req
            cbs = list(self._callbacks)
        for cb in cbs:
            try:
                cb(req)
            except Exception as e:
                self._logger.error(f"权限回调异常: {e}")
        return req

    @staticmethod
    def _suggest_dir(resource: str) -> Optional[str]:
        """为文件路径建议授权目录：资源是目录→自身；否则→父目录"""
        import os
        try:
            res = os.path.abspath(resource)
            if os.path.isdir(res):
                return res
            parent = os.path.dirname(res)
            return parent or None
        except Exception:
            return None

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
        # 授权目录：将资源替换为建议授权的目录（用户勾选"授权整个目录"时）
        if resp.get("approved") and resp.get("grant_dir"):
            resp["grant_dir"] = True
            resp["grant_resource"] = req.suggest_dir or req.resource
        return resp

    def respond(self, req_id: str, approved: bool, duration: str = "once",
                grant_dir: bool = False):
        """用户响应：设置结果并唤醒等待线程

        Args:
            req_id: 请求ID
            approved: 是否批准
            duration: 授权时长（"once" 等）
            grant_dir: 是否改为授权请求资源的父目录（目录授权）
        """
        req = self._requests.get(req_id)
        if not req:
            self._logger.warning(f"权限请求 {req_id} 已不存在")
            return
        req._response = {"approved": approved, "duration": duration,
                         "grant_dir": grant_dir}
        req._event.set()
        self._logger.info(f"权限响应: {req_id} approved={approved} "
                          f"duration={duration} grant_dir={grant_dir}")

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
             "resource_type": req.resource_type.value,
             "suggest_dir": req.suggest_dir, "created_at": req.created_at}
            for rid, req in self._requests.items()
        ]


# ── 模块别名注册（消除双模块单例分裂） ──
# 见 file_permissions.py 同注释：保证 tools.* 与 src.tools.* 指向同一模块。
_THIS_NAME = __name__
_OTHER_NAME = ("src.tools.permission_request_manager" if _THIS_NAME == "tools.permission_request_manager"
               else "tools.permission_request_manager")
if _OTHER_NAME not in sys.modules:
    sys.modules[_OTHER_NAME] = sys.modules[_THIS_NAME]
