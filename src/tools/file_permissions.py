"""
文件操作权限管理器
控制外部文件/目录的访问授权，分临时和持久权限。
"""

import json
import os
from pathlib import Path
from typing import Dict, Optional
from ..utils.logger import logger


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

    def __init__(self, persist_path: str = "./data/permissions.json"):
        self._project_root = str(Path(os.getcwd()).resolve())
        # whitelist: { abs_path: {"mode": "read"/"write"/"read_write", "type": "temporary"/"permanent"} }
        self._whitelist: Dict[str, dict] = {}
        self._persist_path = str(Path(persist_path).resolve())
        self._load()

    def project_root(self) -> str:
        """获取项目根目录"""
        return self._project_root

    def is_path_allowed(self, path: str, mode: str = "read") -> tuple:
        """
        检查路径是否有指定模式的访问权限。

        Args:
            path: 要检查的路径
            mode: "read" / "write"

        Returns:
            (allowed: bool, reason: str)
        """
        abs_path = str(Path(path).resolve())

        # 1. 项目目录内 → 默认允许
        if abs_path.startswith(self._project_root):
            return True, ""

        # 2. 白名单检查
        # 精确匹配
        entry = self._whitelist.get(abs_path)
        if entry:
            if self._mode_allows(entry["mode"], mode):
                return True, ""
            else:
                return False, f"路径已在白名单中，但仅有 {entry['mode']} 权限，需要 {mode} 权限"

        # 3. 父目录白名单检查（如果 /a/b 在白名单中，/a/b/c/d.txt 也应该允许）
        for whitelisted_path in sorted(self._whitelist.keys(), reverse=True):
            if abs_path.startswith(whitelisted_path + os.sep) or abs_path == whitelisted_path:
                entry = self._whitelist[whitelisted_path]
                if self._mode_allows(entry["mode"], mode):
                    return True, f"（通过父目录 {whitelisted_path} 授权）"
                break

        return False, self._build_deny_message(abs_path, mode)

    def _build_deny_message(self, path: str, mode: str) -> str:
        """构建友好的拒绝访问提示"""
        return (
            f"不允许访问项目目录之外的路径:\n  {path}\n\n"
            f"如需授权，可以告诉我：\n"
            f'  "授权读取 {path}"\n'
            f'  "授权写入 {path}"\n'
            f'  "永久授权 {path} 的读写权限"'
        )

    def _mode_allows(self, granted: str, required: str) -> bool:
        """检查授权模式是否满足需求"""
        if granted == "read_write":
            return True
        if granted == "read" and required == "read":
            return True
        if granted == "write" and required == "write":
            return True
        return False

    def authorize(self, path: str, mode: str = "read",
                  perm_type: str = "temporary") -> dict:
        """
        授权访问外部路径。

        Args:
            path: 要授权的路径（文件或目录）
            mode: "read" / "write" / "read_write"
            perm_type: "temporary" / "permanent"

        Returns:
            授权结果 dict
        """
        abs_path = str(Path(path).resolve())

        # 如果路径在项目目录内，不需要授权
        if abs_path.startswith(self._project_root):
            return {"success": False, "message": f"{abs_path} 已在项目目录内，无需授权"}

        self._whitelist[abs_path] = {"mode": mode, "type": perm_type}
        logger.info(f"文件授权: {abs_path} ({mode}, {perm_type})")

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
        """列出所有外部授权"""
        result = []
        for path, entry in sorted(self._whitelist.items()):
            result.append({
                "path": path,
                "mode": entry["mode"],
                "type": entry["type"],
                "under_project": path.startswith(self._project_root),
            })
        # 也显示项目根目录
        result.insert(0, {
            "path": self._project_root,
            "mode": "read_write",
            "type": "permanent",
            "under_project": True,
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
