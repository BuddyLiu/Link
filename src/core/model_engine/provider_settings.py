"""
Provider 设置管理 — 在线/离线模型切换配置
"""

import json
import os
from pathlib import Path
from typing import Optional

_SETTINGS_PATH = Path("data/settings/provider.json")

DEFAULT_SETTINGS = {
    "mode": "offline",
    "provider": "deepseek",
    "api_base": "https://api.deepseek.com",
    "api_key": "",
    "model": "deepseek-chat",
    "offline_model": "qwen2.5:1.5b",
    "temperature": 0.7,
    "max_tokens": 4096,
}


def load_settings() -> dict:
    """加载 provider 设置"""
    if _SETTINGS_PATH.exists():
        try:
            data = json.loads(_SETTINGS_PATH.read_text(encoding="utf-8"))
            # 合并默认值（补全新字段）
            result = DEFAULT_SETTINGS.copy()
            result.update(data)
            return result
        except (json.JSONDecodeError, IOError):
            pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings: dict) -> dict:
    """保存 provider 设置"""
    current = load_settings()
    current.update(settings)
    # 不保存空 api_key（如果传了空字符串也不覆盖已有值）
    if not settings.get("api_key") and current.get("api_key"):
        pass  # 保留旧值
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 写盘时脱敏 key
    serializable = current.copy()
    if serializable.get("api_key"):
        serializable["api_key"] = serializable["api_key"]
    _SETTINGS_PATH.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return current


def get_brain_config() -> dict:
    """根据设置生成 BrainEngine 配置"""
    s = load_settings()
    if s["mode"] == "online":
        return {
            "model_provider": s.get("provider", "openai"),
            "model_name": s.get("model", "deepseek-chat"),
            "base_url": s.get("api_base", "https://api.deepseek.com"),
            "api_key": s.get("api_key", ""),
            "timeout": 60,
            "default_temperature": s.get("temperature", 0.7),
            "default_max_tokens": s.get("max_tokens", 4096),
            "enable_intent_analysis": True,
            "enable_task_planning": True,
            "enable_response_generation": True,
            "response_style": "professional",
            "log_interactions": True,
        }
    else:
        return {
            "model_provider": "ollama",
            "model_name": s.get("offline_model", "qwen2.5:1.5b"),
            "base_url": "http://localhost:11434",
            "timeout": 60,
            "default_temperature": s.get("temperature", 0.7),
            "default_max_tokens": s.get("max_tokens", 4096),
            "enable_intent_analysis": True,
            "enable_task_planning": True,
            "enable_response_generation": True,
            "response_style": "professional",
            "log_interactions": True,
        }


def mask_api_key(key: str) -> str:
    """脱敏显示 API Key"""
    if not key or len(key) < 8:
        return ""
    return key[:4] + "*" * (len(key) - 8) + key[-4:]


def get_ollama_models() -> list:
    """从 Ollama 获取可用模型列表"""
    import urllib.request
    import json
    try:
        req = urllib.request.Request(
            "http://localhost:11434/api/tags",
            method="GET",
            headers={"Accept": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=5)
        data = json.loads(resp.read().decode())
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []
