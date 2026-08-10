"""
Provider 设置管理 — 在线/离线模型切换配置
"""

import json
import os
from pathlib import Path
from typing import Optional

_SETTINGS_PATH = Path("data/settings/provider.json")

DEFAULT_SETTINGS = {
    "mode": "online",
    "provider": "deepseek",
    "api_base": "https://api.deepseek.com",  # 不含 /v1，代码会自动添加
    "api_key": "",
    "model": "deepseek-chat",
    "offline_model": "qwen2.5:1.5b",
    "temperature": 0.7,
    "max_tokens": 8192,  # DeepSeek Reasoner 思考+回复共享该预算，4096 易被长思考耗尽
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
    # 如果传入了新的 api_key 则更新，否则保留旧值
    new_key = settings.get("api_key", "")
    if new_key:
        current["api_key"] = new_key
    # 其他字段直接更新
    for k in ["mode", "provider", "api_base", "model", "offline_model", "temperature"]:
        if k in settings:
            current[k] = settings[k]
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    # 写盘
    serializable = current.copy()
    _SETTINGS_PATH.write_text(
        json.dumps(serializable, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return current


def get_brain_config() -> dict:
    """根据设置生成 BrainEngine 配置"""
    s = load_settings()
    if s["mode"] == "online":
        provider = s.get("provider", "openai")
        if provider == "deepseek":
            provider = "openai"
        # DeepSeek 使用 OpenAI 兼容 API，需 /v1 路径
        api_base = s.get("api_base", "https://api.deepseek.com").rstrip("/")
        if not api_base.endswith("/v1"):
            api_base += "/v1"
        return {
            "model_provider": provider,
            "model_name": s.get("model", "deepseek-chat"),
            "api_base": api_base,
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
