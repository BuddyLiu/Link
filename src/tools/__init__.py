"""
LINK工具模块
提供工具注册、管理和执行功能
"""

from typing import Dict, List, Any, Optional, Callable, Type, Union
from abc import ABC, abstractmethod
import json
import sys

# ── 模块名别名注册（消除双模块单例分裂） ──
# 项目内同时存在 `tools` 与 `src.tools` 两种导入路径，Python 会把同一物理
# 包当作两个模块加载，各自持有独立单例（tool_manager / 权限管理器被分裂）。
# 无论哪个名字先被 import，另一个名字都会被重定向到同一个模块对象。
_canonical_tools = sys.modules.get("src.tools") or sys.modules.get("tools")
if _canonical_tools is None or _canonical_tools is sys.modules.get(__name__):
    # 当前模块（tools 或 src.tools）成为 canonical
    pass
# 注册另一个名字指向当前模块
if sys.modules.get("src.tools") is not sys.modules.get(__name__):
    sys.modules["src.tools"] = sys.modules[__name__]
if sys.modules.get("tools") is not sys.modules.get(__name__):
    sys.modules["tools"] = sys.modules[__name__]

# 修复导入路径问题
from config.settings import settings
from utils.logger import logger, LoggerMixin


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
    
    def validate_parameters(self, params: Dict) -> Any:
        """验证参数并原地修改 params（纠正类型），成功返回修改后的 dict，失败返回 False

        注意: 接收 dict 引用而非 **kwargs，确保类型转换能传回调用方。
        """
        for param_name, param_info in self.parameters.items():
            if param_info.get("required", False) and param_name not in params:
                self._logger.error(f"Missing required parameter: {param_name}")
                return False

            # 类型检查和转换（原地修改 params）
            if param_name in params and "type" in param_info:
                expected_type = param_info["type"]
                value = params[param_name]

                try:
                    if expected_type == "string":
                        if not isinstance(value, str):
                            params[param_name] = str(value)
                    elif expected_type == "integer":
                        if value == "" or value is None:
                            if "default" in param_info:
                                params[param_name] = param_info["default"]
                            else:
                                raise ValueError("空值且无默认值")
                        else:
                            params[param_name] = int(value)
                    elif expected_type == "number":
                        params[param_name] = float(value)
                    elif expected_type == "boolean":
                        if isinstance(value, str):
                            params[param_name] = value.lower() in ("true", "1", "yes")
                        else:
                            params[param_name] = bool(value)
                except (ValueError, TypeError) as e:
                    self._logger.error(f"Invalid type for parameter {param_name}: {e}")
                    return False

        return params
    
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

        # 验证参数（返回转换后的 kwargs，如 int/boolean 类型纠正）
        validated = tool.validate_parameters(kwargs)
        if validated is False:
            raise ValueError(f"Invalid parameters for tool: {tool_name}")

        self.logger.info(f"Executing tool: {tool_name} with args: {validated}")

        try:
            result = tool.execute(**validated)
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