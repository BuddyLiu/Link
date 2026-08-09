"""
文件操作权限管理器
控制外部文件/目录的访问授权，分临时和持久权限。

授权规则：
- 授权单个文件 → 按授权模式（read/write/read_write）控制
- 授权目录 → 该目录下所有文件和子目录自动获得读写权限（继承机制）
- 项目目录内 → 默认拥有全部权限
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, Optional
from utils.logger import logger

# 授权时长映射（秒）
DURATION_MAP = {
    "once": 0,
    "1h": 3600,
    "2h": 7200,
    "4h": 14400,
    "8h": 28800,
    "12h": 43200,
    "24h": 86400,
    "permanent": -1,  # 永不过期
}


# 全局单例
_permission_manager: Optional['FilePermissionManager'] = None


def get_permission_manager() -> 'FilePermissionManager':
    global _permission_manager
    if _permission_manager is None:
        _permission_manager = FilePermissionManager()
    return _permission_manager


def reset_permission_manager():
    """重置权限管理器（测试用）"""
    global _permission_manager
    _permission_manager = None


class FilePermissionManager:
    """文件权限管理器

    维护一个白名单，记录允许访问的项目外路径。
    权限分两类：
    - temporary: 临时权限，仅当前会话有效
    - permanent: 持久权限，写入磁盘，重启后保留
    """

    def __init__(self, persist_path: str = "./data/permissions.json",
                 workspace_root: str = None, source_root: str = None):
        # 工作目录（默认 ~/LINK-Workspace）：文件操作的自由落点
        # 源码目录（默认进程 cwd）：只读保留、写入需授权
        from config.paths import resolve_workspace, resolve_source_root
        self._workspace_root = str(Path(workspace_root or resolve_workspace()).resolve())
        self._source_root = str(Path(source_root or resolve_source_root()).resolve())
        # 兼容旧属性名（外部仍调用 project_root()）
        self._project_root = self._workspace_root
        # whitelist: { abs_path: {"mode": ..., "type": ..., "expires_at": Optional[float]} }
        self._whitelist: Dict[str, dict] = {}
        self._persist_path = str(Path(persist_path).resolve())
        self._check_count = 0
        self._load()
        self._cleanup_expired()

    def project_root(self) -> str:
        """获取工作目录（文件操作的项目根）"""
        return self._workspace_root

    def workspace_root(self) -> str:
        """获取工作目录"""
        return self._workspace_root

    def source_root(self) -> str:
        """获取源码目录"""
        return self._source_root

    def is_path_allowed(self, path: str, mode: str = "read") -> tuple:
        """
        检查路径是否有指定模式的访问权限。

        规则：
        - 工作目录内 → 默认允许读写（严格边界匹配，避免 /proj_evil 误判）
        - 源码目录内 → 只读放行；写入需白名单授权
        - 白名单中的路径 → 按授权模式检查
        - 授权**目录**的**子路径** → 自动继承读写权限（mode 无关）
          例如：授权 /data 目录 → /data/sub/file.txt 可读也可写
        - 授权单个**文件** → 仅该文件自身获得权限，不向子路径传递

        Args:
            path: 要检查的路径
            mode: "read" / "write"

        Returns:
            (allowed: bool, reason: str)
        """
        abs_path = str(Path(path).resolve())

        # 惰性过期清理（每 50 次检查触发一次）
        self._check_count += 1
        if self._check_count % 50 == 0:
            self._cleanup_expired()

        # 1. 精确匹配（授权路径放行，含源码目录已授权写入）
        entry = self._whitelist.get(abs_path)
        exact_ok = False
        if entry and not self._is_expired(entry):
            if self._mode_allows(entry["mode"], mode):
                exact_ok = True

        # 2. 父目录授权继承：只有授权条目是"目录"时才继承
        #    （按路径长度降序，优先最近的父目录）
        #    目录授权授予全读写，比单文件授权更宽松，故优先级更高
        for whitelisted_path in sorted(self._whitelist.keys(), reverse=True,
                                       key=len):
            w_entry = self._whitelist[whitelisted_path]
            if self._is_expired(w_entry):
                continue
            if abs_path == whitelisted_path:
                continue
            # 子路径匹配：授权目录下的所有文件/子目录自动继承读写
            if abs_path.startswith(whitelisted_path + os.sep):
                if self._is_dir_grant(whitelisted_path, w_entry):
                    return True, f"（通过父目录 {whitelisted_path} 授权，子路径自动继承读写权限）"
                # 父路径是单文件授权：不向子路径传递，继续找更远的父目录

        if exact_ok:
            return True, ""
        if entry and not self._is_expired(entry):
            return False, f"路径已在白名单中，但仅有 {entry['mode']} 权限，需要 {mode} 权限"

        # 3. 工作目录内 → 默认允许（严格边界匹配）
        if self._is_under_project(abs_path):
            return True, ""

        # 4. 源码目录内 → 只读放行，写入拒绝（白名单已检查，未授权）
        if self._is_under_source(abs_path):
            if mode == "read":
                return True, ""
            return False, self._build_deny_message(abs_path, mode)

        return False, self._build_deny_message(abs_path, mode)

    def _is_under_project(self, abs_path: str) -> bool:
        """严格判断路径是否在工作目录内（边界匹配，防 /proj_evil 误判）"""
        root = self._workspace_root.rstrip(os.sep) + os.sep
        return abs_path == self._workspace_root or abs_path.startswith(root)

    def _is_under_source(self, abs_path: str) -> bool:
        """严格判断路径是否在源码目录内（边界匹配）"""
        root = self._source_root.rstrip(os.sep) + os.sep
        return abs_path == self._source_root or abs_path.startswith(root)

    def _is_dir_grant(self, whitelisted_path: str, entry: dict) -> bool:
        """判断授权条目是否为目录授权（是目录时才允许子路径继承）"""
        if entry.get("is_dir"):
            return True
        # 兼容旧数据：路径是目录则视为目录授权
        try:
            return Path(whitelisted_path).is_dir()
        except Exception:
            return False

    def _build_deny_message(self, path: str, mode: str) -> str:
        """构建友好的拒绝访问提示"""
        parent = os.path.dirname(path)
        # 源码目录内的写入 → 专用提示（源码默认只读）
        if self._is_under_source(path):
            return (
                f"源码目录默认只读，不允许写入:\n  {path}\n\n"
                f"如需允许写入源码，可以告诉我：\n"
                f'  "授权写入源码 {path}"\n'
                f'  "授权目录 {parent} 的读写权限"   ← 授权后该目录下文件可读写\n\n'
                f"也可以直接让我弹窗授权。\n"
                f"💡 普通文件请保存到默认工作目录 {self._workspace_root}"
            )
        return (
            f"不允许访问项目目录之外的路径:\n  {path}\n\n"
            f"如需授权，可以告诉我：\n"
            f'  "授权读取 {path}"\n'
            f'  "授权写入 {path}"\n'
            f'  "授权目录 {parent} 的读取权限"   ← 授权父目录后，其下所有文件自动获得读写权限\n'
            f'  "永久授权 {path} 的读写权限"\n\n'
            f"也可以直接让我弹窗授权：\n"
            f'  "授权打开 {parent}"'
        )

    def needs_grant(self, path: str, mode: str = "read") -> tuple:
        """检查路径是否已获授权；未授权时返回推荐的授权目标。

        Returns:
            (needs_grant: bool, target: str, target_is_dir: bool)
            其中 target 为建议授权的目录（若路径不存在则用父目录）
        """
        abs_path = str(Path(path).resolve())
        allowed, _ = self.is_path_allowed(abs_path, mode)
        if allowed:
            return False, "", False
        # 路径不存在 → 建议授权父目录（便于后续创建文件）
        if not os.path.exists(abs_path):
            target = os.path.dirname(abs_path)
            return True, target, True
        return True, abs_path, os.path.isdir(abs_path)

    def grant_dir(self, path: str, mode: str = "read_write",
                  perm_type: str = "permanent", duration: str = None) -> dict:
        """授权一个目录（及以下所有文件），权限模式为读写。

        Args:
            path: 目录路径（若路径不存在，按其父目录处理）
            mode: "read" / "write" / "read_write"（默认读写）
            perm_type: "temporary" / "permanent"
            duration: "once" / "1h" / ... / "permanent"
        """
        abs_path = str(Path(path).resolve())
        # 目录不存在时授权其父目录（保证能创建文件）
        if not os.path.isdir(abs_path):
            parent = os.path.dirname(abs_path)
            # 若父目录在项目内，则无需授权
            if self._is_under_project(parent):
                return {"success": True, "path": abs_path,
                        "message": f"{abs_path} 在项目目录内，无需授权"}
            abs_path = parent
        return self.authorize(abs_path, mode=mode, perm_type=perm_type,
                              duration=duration, as_dir=True)

    def _mode_allows(self, granted: str, required: str) -> bool:
        """检查授权模式是否满足需求"""
        if granted == "read_write":
            return True
        if granted == "read" and required == "read":
            return True
        if granted == "write" and required == "write":
            return True
        return False

    def _is_expired(self, entry: dict) -> bool:
        """检查权限条目是否已过期"""
        expires_at = entry.get("expires_at")
        if expires_at is not None and expires_at > 0:
            if time.time() > expires_at:
                return True
        return False

    def _cleanup_expired(self):
        """清理已过期的权限条目"""
        expired = [p for p, e in self._whitelist.items() if self._is_expired(e)]
        for p in expired:
            del self._whitelist[p]
            logger.info(f"过期权限已清理: {p}")
        if expired:
            self._save()

    def authorize(self, path: str, mode: str = "read",
                  perm_type: str = "temporary",
                  duration: str = None,
                  as_dir: bool = False) -> dict:
        """
        授权访问外部路径。

        如果授权的是一个目录，则该目录下的所有文件和子目录都将自动继承
        读写权限（即使授权的是 read，子文件也能读写）。

        Args:
            path: 要授权的路径（文件或目录）
            mode: "read" / "write" / "read_write"
                注意：目录授权时，子文件始终获得读写权限
            perm_type: "temporary" / "permanent"
            as_dir: 显式声明授权目标是目录（路径尚不存在时也能正确标记，
                    使后续子路径自动继承权限）

        Returns:
            授权结果 dict
        """
        abs_path = str(Path(path).resolve())

        # 如果路径在项目目录内，不需要授权
        if self._is_under_project(abs_path):
            return {"success": False, "message": f"{abs_path} 已在项目目录内，无需授权"}

        # 判断授权对象是目录还是文件（目录授权时子路径自动继承）
        is_dir = as_dir or os.path.isdir(abs_path) or abs_path.endswith(os.sep)

        # 计算过期时间
        expires_at = None
        if duration and duration in DURATION_MAP:
            secs = DURATION_MAP[duration]
            if secs > 0:
                expires_at = time.time() + secs
            elif secs == -1:
                expires_at = None  # permanent: 永不过期

        entry = {"mode": mode, "type": perm_type, "is_dir": is_dir}
        if expires_at is not None:
            entry["expires_at"] = expires_at
        self._whitelist[abs_path] = entry

        duration_label = f" ({duration})" if duration else ""
        kind = "目录" if is_dir else "文件"
        logger.info(f"文件授权: {abs_path} ({kind}, {mode}, {perm_type}{duration_label})")

        if perm_type == "permanent":
            self._save()

        return {
            "success": True,
            "path": abs_path,
            "mode": mode,
            "type": perm_type,
            "message": f"已{'永久' if perm_type == 'permanent' else '临时'}授权 {mode} {abs_path}",
        }

    def revoke(self, path: str) -> bool:
        """撤销授权"""
        abs_path = str(Path(path).resolve())
        if abs_path in self._whitelist:
            del self._whitelist[abs_path]
            self._save()
            logger.info(f"撤销文件授权: {abs_path}")
            return True
        return False

    def list_permissions(self) -> list:
        """列出所有访问权限（工作目录 + 源码目录 + 白名单授权）"""
        result = []
        for path, entry in sorted(self._whitelist.items()):
            result.append({
                "path": path,
                "mode": entry["mode"],
                "type": entry["type"],
                "is_dir": bool(entry.get("is_dir")),
                "under_project": self._is_under_project(path),
            })
        # 工作目录（文件操作的项目根，读写自由）
        result.insert(0, {
            "path": self._workspace_root,
            "mode": "read_write",
            "type": "permanent",
            "is_dir": True,
            "under_project": True,
        })
        # 源码目录（只读，写入需授权）
        result.insert(0, {
            "path": self._source_root,
            "mode": "read",
            "type": "permanent",
            "is_dir": True,
            "under_project": False,
            "read_only": True,
        })
        return result

    def clear_temporary(self):
        """清空所有临时权限"""
        to_delete = [p for p, e in self._whitelist.items() if e.get("type") == "temporary"]
        for p in to_delete:
            del self._whitelist[p]
        logger.info(f"已清空 {len(to_delete)} 条临时文件授权")

    # ── 持久化 ──

    def _persist_file(self) -> str:
        return self._persist_path

    def _save(self):
        path = self._persist_file()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            # 只保存持久权限
            perm_data = {p: e for p, e in self._whitelist.items() if e.get("type") == "permanent"}
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(perm_data, f, indent=2, ensure_ascii=False)
        except IOError as e:
            logger.error(f"保存权限失败: {e}")

    def _load(self):
        path = self._persist_file()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for p, e in data.items():
                    self._whitelist[p] = e
                logger.debug(f"已加载 {len(data)} 条持久文件权限")
            except (json.JSONDecodeError, IOError) as e:
                logger.error(f"加载权限失败: {e}")


# ── 模块别名注册（消除双模块单例分裂） ──
# 项目内同时存在 `tools.file_permissions` 与 `src.tools.file_permissions`
# 两种导入路径，Python 会把同一物理文件当作两个模块加载，导致权限管理器的
# 单例被分裂（工具检查用 A 实例、授权写入 B 实例）。
# 这里采用"先到先得"：本模块先被加载时，把另一名字也指向同一模块对象。
_THIS_NAME = __name__
_OTHER_NAME = ("src.tools.file_permissions" if _THIS_NAME == "tools.file_permissions"
               else "tools.file_permissions")
if _OTHER_NAME not in sys.modules:
    sys.modules[_OTHER_NAME] = sys.modules[_THIS_NAME]
