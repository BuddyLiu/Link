"""
JARVIS大脑引擎模块

提供统一的模型接口，支持多种模型提供商（OpenAI、Anthropic、本地Ollama等）。
基于Order.txt中3.1基座核心模块要求实现意图理解、任务规划、回复生成功能。
"""

from .model_adapter import ModelAdapter, ModelResponse
from .ollama_adapter import OllamaAdapter, create_ollama_adapter
from .openai_adapter import OpenAIAdapter, create_openai_adapter
from .model_factory import ModelFactory, create_model_adapter
from .brain_engine import BrainEngine, create_brain_engine

__all__ = [
    "ModelAdapter",
    "ModelResponse",
    "OllamaAdapter",
    "OpenAIAdapter",
    "ModelFactory",
    "BrainEngine",
    "create_ollama_adapter",
    "create_openai_adapter",
    "create_model_adapter",
    "create_brain_engine",
]
