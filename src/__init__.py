"""
JARVIS智能体基座
一个模块化、可扩展的智能体系统
"""

__version__ = "1.0.0"
__author__ = "JARVIS Team"
__license__ = "MIT"

# 导出常用组件（main.py 在项目根目录而非 src/ 下，不从包内导入）
from .config.settings import settings
from .utils.logger import logger
from .tools import tool_manager


__all__ = [
    "settings",
    "logger",
    "tool_manager",
]