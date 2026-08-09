"""
自动授权默认规则

持久化存储用户设置的默认授权规则，在工具遇到 PermissionError 时
先检查是否有匹配的自动规则，有则自动授权不弹窗。
"""
import json
import os
import sys
import logging
from typing import Optional

logger = logging.getLogger("link.permission_settings")

_DEFAULT_SETTINGS = {
    "file_read": "ask",
    "file_write": "ask",
    "command_exec": "ask",
    "custom_rules": [],
}

_SETTINGS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "settings", "permission_defaults.json"
)


class PermissionSettings:
    """自动授权默认规则管理"""

    def __init__(self):
        self._settings = dict(_DEFAULT_SETTINGS)
        self._load()

    def _load(self):
        try:
            if os.path.exists(_SETTINGS_PATH):
                with open(_SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._settings.update(data)
        except Exception as e:
            logger.warning(f"加载权限设置失败: {e}")

    def _save(self):
        try:
            os.makedirs(os.path.dirname(_SETTINGS_PATH), exist_ok=True)
            with open(_SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self._settings, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"保存权限设置失败: {e}")

    def get_auto_auth_duration(self, resource_type: str, mode: str) -> Optional[str]:
        """根据资源类型和模式获取自动授权时长，返回 None 表示需要弹窗询问"""
        key = f"{resource_type}_{mode}"
        val = self._settings.get(key)
        if val is None:
            val = self._settings.get(key.replace("file_write", "file_read"))
        if val == "ask":
            return None
        return val

    def list_settings(self) -> dict:
        return dict(self._settings)

    def update_settings(self, new_settings: dict) -> dict:
        self._settings.update(new_settings)
        self._save()
        return self.list_settings()


# ── 模块别名注册（消除双模块单例分裂） ──
_THIS_NAME = __name__
_OTHER_NAME = ("src.tools.permission_settings" if _THIS_NAME == "tools.permission_settings"
               else "tools.permission_settings")
if _OTHER_NAME not in sys.modules:
    sys.modules[_OTHER_NAME] = sys.modules[_THIS_NAME]
