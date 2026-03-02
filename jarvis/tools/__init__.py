"""
JARVIS工具模块
提供工具注册、管理和执行功能
"""

from typing import Dict, List, Any, Optional, Callable, Type, Union
from abc import ABC, abstractmethod
import json

# 修复导入路径问题
try:
    from config.settings import settings
    from utils.logger import logger, LoggerMixin
except ImportError:
    from ..config.settings import settings
    from ..utils.logger import logger, LoggerMixin


class Tool(ABC):
    """工具基类"""
    
    def __init__(self, name: str, description: str, parameters: Optional[Dict] = None):
        self.name = name
        self.description = description
        self.parameters = parameters or {}
        self._logger = logger.getChild(f"tool.{name}")
    
    @abstractmethod
    def execute(self, **kwargs) -> Any:
        """执行工具"""
        pass
    
    def validate_parameters(self, **kwargs) -> bool:
        """验证参数"""
        for param_name, param_info in self.parameters.items():
            if param_info.get("required", False) and param_name not in kwargs:
                self._logger.error(f"Missing required parameter: {param_name}")
                return False
            
            # 类型检查
            if param_name in kwargs and "type" in param_info:
                expected_type = param_info["type"]
                value = kwargs[param_name]
                
                try:
                    if expected_type == "string":
                        if not isinstance(value, str):
                            kwargs[param_name] = str(value)
                    elif expected_type == "integer":
                        kwargs[param_name] = int(value)
                    elif expected_type == "number":
                        kwargs[param_name] = float(value)
                    elif expected_type == "boolean":
                        kwargs[param_name] = bool(value)
                except (ValueError, TypeError) as e:
                    self._logger.error(f"Invalid type for parameter {param_name}: {e}")
                    return False
        
        return True
    
    def get_schema(self) -> Dict:
        """获取工具schema（OpenAI格式）"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": [
                        param_name for param_name, param_info in self.parameters.items()
                        if param_info.get("required", False)
                    ],
                },
            }
        }


class ToolManager(LoggerMixin):
    """工具管理器"""
    
    def __init__(self):
        super().__init__()
        self._tools: Dict[str, Tool] = {}
        self._tool_schemas: Dict[str, Dict] = {}
    
    def register_tool(self, tool: Tool) -> None:
        """注册工具"""
        if tool.name in self._tools:
            self.logger.warning(f"Tool '{tool.name}' already registered, overwriting")
        
        self._tools[tool.name] = tool
        self._tool_schemas[tool.name] = tool.get_schema()
        self.logger.info(f"Registered tool: {tool.name}")
    
    def register_function(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: Optional[Dict] = None
    ) -> None:
        """注册函数作为工具"""
        
        class FunctionTool(Tool):
            def execute(self, **kwargs):
                return func(**kwargs)
        
        tool = FunctionTool(name, description, parameters)
        self.register_tool(tool)
    
    def execute_tool(self, tool_name: str, **kwargs) -> Any:
        """执行工具"""
        if tool_name not in self._tools:
            self.logger.error(f"Tool not found: {tool_name}")
            raise ValueError(f"Tool not found: {tool_name}")
        
        tool = self._tools[tool_name]
        
        # 验证参数
        if not tool.validate_parameters(**kwargs):
            raise ValueError(f"Invalid parameters for tool: {tool_name}")
        
        self.logger.info(f"Executing tool: {tool_name} with args: {kwargs}")
        
        try:
            result = tool.execute(**kwargs)
            self.logger.info(f"Tool {tool_name} executed successfully")
            return result
        except Exception as e:
            self.logger.error(f"Tool {tool_name} execution failed: {str(e)}", exc_info=True)
            raise
    
    def get_tool_schemas(self) -> List[Dict]:
        """获取所有工具的schema"""
        return list(self._tool_schemas.values())
    
    def get_tool_names(self) -> List[str]:
        """获取所有工具名称"""
        return list(self._tools.keys())
    
    def get_tool(self, tool_name: str) -> Optional[Tool]:
        """获取工具实例"""
        return self._tools.get(tool_name)
    
    def clear_tools(self) -> None:
        """清空所有工具"""
        self._tools.clear()
        self._tool_schemas.clear()
        self.logger.info("Cleared all tools")


# 创建全局工具管理器实例
tool_manager = ToolManager()


class SystemTool(Tool):
    """系统工具基类"""
    
    def __init__(self, name: str, description: str, parameters: Optional[Dict] = None):
        super().__init__(name, description, parameters)
        self._logger = logger.getChild(f"system_tool.{name}")


# 导出常用类和函数
__all__ = [
    'Tool',
    'ToolManager',
    'SystemTool',
    'tool_manager',
]