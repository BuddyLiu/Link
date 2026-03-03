"""
JARVIS日志模块
提供统一、可配置的日志记录功能
"""

import os
import sys
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional
from pathlib import Path

# 修复导入路径问题
try:
    from config.settings import settings
except ImportError:
    from ..config.settings import settings


class ColorFormatter(logging.Formatter):
    """彩色日志格式化器"""
    
    COLORS = {
        'DEBUG': '\033[36m',      # 青色
        'INFO': '\033[32m',       # 绿色
        'WARNING': '\033[33m',    # 黄色
        'ERROR': '\033[31m',      # 红色
        'CRITICAL': '\033[1;31m', # 红色加粗
        'RESET': '\033[0m'        # 重置颜色
    }
    
    def format(self, record):
        """格式化日志记录，添加颜色"""
        log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
        record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
        return super().format(record)


def setup_logger(
    name: str = "jarvis",
    log_level: Optional[str] = None,
    log_file: Optional[str] = None,
    console_output: bool = True
) -> logging.Logger:
    """
    设置和配置日志记录器
    
    Args:
        name: 日志记录器名称
        log_level: 日志级别（DEBUG, INFO, WARNING, ERROR, CRITICAL）
        log_file: 日志文件路径，如果为None则不记录到文件
        console_output: 是否输出到控制台
        
    Returns:
        logging.Logger: 配置好的日志记录器
    """
    # 从设置获取日志级别
    if log_level is None:
        log_level = settings.system.log_level
    
    # 创建日志记录器
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    
    # 避免重复添加处理器
    if logger.handlers:
        return logger
    
    # 创建格式化器
    console_formatter = ColorFormatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    file_formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # 控制台处理器
    if console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)
    
    # 文件处理器
    if log_file:
        # 确保日志目录存在
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 使用旋转文件处理器，每个文件最大10MB，保留5个备份
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        file_handler.setLevel(getattr(logging, log_level.upper(), logging.INFO))
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    # 禁用传播，避免重复记录
    logger.propagate = False
    
    return logger


def get_default_log_file() -> str:
    """
    获取默认日志文件路径
    
    Returns:
        str: 默认日志文件路径
    """
    # 创建日志目录
    log_dir = Path(settings.system.data_directory) / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    # 按日期命名日志文件
    date_str = datetime.now().strftime("%Y-%m-%d")
    return str(log_dir / f"jarvis_{date_str}.log")


class LoggerMixin:
    """日志混入类，为其他类提供日志功能"""
    
    def __init__(self):
        self._logger = None
    
    @property
    def logger(self) -> logging.Logger:
        """获取日志记录器"""
        if self._logger is None:
            # 使用类名作为日志记录器名称
            class_name = self.__class__.__name__
            log_file = get_default_log_file() if settings.system.debug_mode else None
            
            self._logger = setup_logger(
                name=f"jarvis.{class_name}",
                log_file=log_file,
                console_output=settings.system.debug_mode
            )
        
        return self._logger


# 全局日志记录器
def get_global_logger() -> logging.Logger:
    """
    获取全局日志记录器
    
    Returns:
        logging.Logger: 全局日志记录器
    """
    log_file = get_default_log_file() if settings.system.debug_mode else None
    
    return setup_logger(
        name="jarvis",
        log_file=log_file,
        console_output=True
    )


# 创建全局日志记录器实例
logger = get_global_logger()


def log_function_call(func):
    """
    函数调用日志装饰器
    
    Args:
        func: 要装饰的函数
        
    Returns:
        function: 装饰后的函数
    """
    def wrapper(*args, **kwargs):
        func_name = func.__name__
        logger.debug(f"Calling function: {func_name} with args={args}, kwargs={kwargs}")
        
        try:
            result = func(*args, **kwargs)
            logger.debug(f"Function {func_name} completed successfully")
            return result
        except Exception as e:
            logger.error(f"Function {func_name} failed with error: {str(e)}", exc_info=True)
            raise
    
    return wrapper


def log_exception(logger: logging.Logger):
    """
    异常日志装饰器
    
    Args:
        logger: 日志记录器
        
    Returns:
        function: 异常处理装饰器
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                logger.exception(f"Exception in {func.__name__}: {str(e)}")
                raise
        
        return wrapper
    
    return decorator


# 导出常用函数
__all__ = [
    'logger',
    'setup_logger',
    'get_global_logger',
    'get_default_log_file',
    'LoggerMixin',
    'log_function_call',
    'log_exception',
]