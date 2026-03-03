"""
JARVIS智能体基座
一个模块化、可扩展的智能体系统
"""

__version__ = "1.0.0"
__author__ = "JARVIS Team"
__license__ = "MIT"

# 导出常用组件
from .config.settings import settings
from .utils.logger import logger
from .tools import tool_manager
from .main import JARVIS, main


__all__ = [
    "settings",
    "logger",
    "tool_manager",
    "JARVIS",
    "main",
]