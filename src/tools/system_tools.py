"""
JARVIS系统工具模块
提供基础的系统工具功能
"""

import os
import sys
import json
import platform
import subprocess
import datetime
from typing import Dict, Any, Optional
from pathlib import Path

# 修复导入路径问题
try:
    from . import Tool, SystemTool, tool_manager
    from utils.logger import logger
except ImportError:
    from . import Tool, SystemTool, tool_manager
    from ..utils.logger import logger


class GetTimeTool(SystemTool):
    """获取当前时间工具"""
    
    def __init__(self):
        parameters = {
            "format": {
                "type": "string",
                "description": "时间格式: 'full'(完整时间), 'date'(仅日期), 'time'(仅时间), 'timestamp'(时间戳)",
                "required": False,
                "default": "full"
            }
        }
        super().__init__("get_time", "获取当前日期和时间", parameters)
    
    def execute(self, **kwargs) -> str:
        format_type = kwargs.get("format", "full")
        now = datetime.datetime.now()
        
        if format_type == "full":
            return now.strftime("%Y年%m月%d日 %H:%M:%S")
        elif format_type == "date":
            return now.strftime("%Y年%m月%d日")
        elif format_type == "time":
            return now.strftime("%H:%M:%S")
        elif format_type == "timestamp":
            return str(int(now.timestamp()))
        else:
            return now.strftime("%Y-%m-%d %H:%M:%S")


class GetSystemInfoTool(SystemTool):
    """获取系统信息工具"""
    
    def __init__(self):
        parameters = {
            "detail": {
                "type": "boolean",
                "description": "是否显示详细信息",
                "required": False,
                "default": False
            }
        }
        super().__init__("get_system_info", "获取系统信息", parameters)
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        detail = kwargs.get("detail", False)
        
        info = {
            "platform": platform.system(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
        }
        
        if detail:
            info.update({
                "hostname": platform.node(),
                "processor": platform.processor(),
                "python_build": platform.python_build(),
                "python_compiler": platform.python_compiler(),
            })
            
            # 获取内存信息（仅限某些系统）
            try:
                if platform.system() == "Darwin":  # macOS
                    import psutil
                    info["memory_total"] = psutil.virtual_memory().total
                    info["memory_available"] = psutil.virtual_memory().available
                    info["cpu_count"] = psutil.cpu_count()
            except ImportError:
                pass
        
        return info


class ListFilesTool(SystemTool):
    """列出文件工具"""
    
    def __init__(self):
        parameters = {
            "path": {
                "type": "string",
                "description": "要列出的目录路径",
                "required": False,
                "default": "."
            },
            "recursive": {
                "type": "boolean",
                "description": "是否递归列出",
                "required": False,
                "default": False
            }
        }
        super().__init__("list_files", "列出目录中的文件", parameters)
    
    def execute(self, **kwargs) -> list:
        path = kwargs.get("path", ".")
        recursive = kwargs.get("recursive", False)
        
        try:
            path_obj = Path(path).resolve()
            if not path_obj.exists():
                raise FileNotFoundError(f"目录不存在: {path}")
            
            if not path_obj.is_dir():
                raise ValueError(f"路径不是目录: {path}")
            
            files = []
            if recursive:
                for file_path in path_obj.rglob("*"):
                    files.append(str(file_path.relative_to(path_obj)))
            else:
                for item in path_obj.iterdir():
                    files.append(item.name)
            
            return files[:100]  # 限制返回数量
            
        except Exception as e:
            logger.error(f"列出文件失败: {str(e)}")
            raise


class ReadFileTool(SystemTool):
    """读取文件工具"""
    
    def __init__(self):
        parameters = {
            "path": {
                "type": "string",
                "description": "要读取的文件路径",
                "required": True
            },
            "encoding": {
                "type": "string",
                "description": "文件编码",
                "required": False,
                "default": "utf-8"
            }
        }
        super().__init__("read_file", "读取文件内容", parameters)
    
    def execute(self, **kwargs) -> str:
        path = kwargs["path"]
        encoding = kwargs.get("encoding", "utf-8")
        
        try:
            path_obj = Path(path).resolve()
            if not path_obj.exists():
                raise FileNotFoundError(f"文件不存在: {path}")
            
            if not path_obj.is_file():
                raise ValueError(f"路径不是文件: {path}")
            
            # 检查文件大小（限制读取大文件）
            file_size = path_obj.stat().st_size
            if file_size > 10 * 1024 * 1024:  # 10MB限制
                raise ValueError(f"文件太大 ({file_size} bytes)，超过10MB限制")
            
            with open(path_obj, 'r', encoding=encoding) as f:
                content = f.read()
            
            # 限制返回内容长度
            max_length = 50000
            if len(content) > max_length:
                content = content[:max_length] + f"\n\n...(已截断，文件总长度: {len(content)} 字符)"
            
            return content
            
        except UnicodeDecodeError:
            # 尝试其他编码
            try:
                with open(path_obj, 'r', encoding='latin-1') as f:
                    content = f.read()
                return content[:50000]
            except Exception as e:
                logger.error(f"读取文件失败: {str(e)}")
                raise ValueError(f"无法读取文件，可能是二进制文件或不支持的编码: {str(e)}")
        except Exception as e:
            logger.error(f"读取文件失败: {str(e)}")
            raise


class ExecuteCommandTool(SystemTool):
    """执行命令工具"""
    
    def __init__(self):
        parameters = {
            "command": {
                "type": "string",
                "description": "要执行的命令",
                "required": True
            },
            "timeout": {
                "type": "integer",
                "description": "命令超时时间（秒）",
                "required": False,
                "default": 30
            }
        }
        super().__init__("execute_command", "执行系统命令", parameters)
    
    def execute(self, **kwargs) -> Dict[str, Any]:
        command = kwargs["command"]
        timeout = kwargs.get("timeout", 30)
        
        # 安全检查：禁止某些危险命令
        dangerous_patterns = [
            "rm -rf /", "rm -rf /*", "dd if=", "mkfs", "fdisk",
            "chmod 777 /", ":(){ :|:& };:",  # fork炸弹
        ]
        
        for pattern in dangerous_patterns:
            if pattern in command.lower():
                raise ValueError(f"命令包含危险操作: {pattern}")
        
        logger.warning(f"执行系统命令: {command}")
        
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            return {
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "success": result.returncode == 0
            }
            
        except subprocess.TimeoutExpired:
            raise ValueError(f"命令执行超时 (超过{timeout}秒)")
        except Exception as e:
            logger.error(f"执行命令失败: {str(e)}")
            raise ValueError(f"执行命令失败: {str(e)}")


class SearchWebTool(SystemTool):
    """搜索网络工具（基础版本）"""
    
    def __init__(self):
        parameters = {
            "query": {
                "type": "string",
                "description": "搜索关键词",
                "required": True
            },
            "max_results": {
                "type": "integer",
                "description": "最大结果数量",
                "required": False,
                "default": 5
            }
        }
        super().__init__("search_web", "搜索网络信息", parameters)
    
    def execute(self, **kwargs) -> str:
        query = kwargs["query"]
        max_results = kwargs.get("max_results", 5)
        
        # 第一阶段：返回模拟结果
        # 第二阶段将集成真实搜索API
        
        logger.info(f"搜索网络: {query}")
        
        # 模拟搜索结果
        mock_results = [
            f"关于 '{query}' 的搜索结果1: 这是模拟的结果，真实搜索功能将在后续版本中实现。",
            f"关于 '{query}' 的搜索结果2: JARVIS第一阶段主要关注本地功能。",
            f"关于 '{query}' 的搜索结果3: 第二阶段将添加天气、新闻等API集成。",
            f"关于 '{query}' 的搜索结果4: 当前版本支持基础系统工具和简单对话。",
            f"关于 '{query}' 的搜索结果5: 请期待后续版本的功能增强。",
        ]
        
        results = mock_results[:max_results]
        return "\n\n".join(results)


class CalculateTool(SystemTool):
    """计算工具"""
    
    def __init__(self):
        parameters = {
            "expression": {
                "type": "string",
                "description": "数学表达式，如 '2 + 3 * 4'",
                "required": True
            }
        }
        super().__init__("calculate", "执行数学计算", parameters)
    
    def execute(self, **kwargs) -> str:
        expression = kwargs["expression"]
        
        # 安全检查：过滤危险操作
        dangerous_operations = [
            "__import__", "exec(", "eval(", "compile(", "open(",
            "import ", "from ", "sys.", "os.", "subprocess."
        ]
        
        for op in dangerous_operations:
            if op in expression.lower():
                raise ValueError(f"表达式包含危险操作: {op}")
        
        try:
            # 使用安全的eval
            import ast
            import operator
            import math
            
            # 定义安全的操作符
            safe_operators = {
                ast.Add: operator.add,
                ast.Sub: operator.sub,
                ast.Mult: operator.mul,
                ast.Div: operator.truediv,
                ast.Pow: operator.pow,
                ast.FloorDiv: operator.floordiv,
                ast.Mod: operator.mod,
                ast.USub: operator.neg,
            }
            
            # 定义安全的函数
            safe_functions = {
                'abs': abs,
                'round': round,
                'max': max,
                'min': min,
                'sum': sum,
                'len': len,
                'sqrt': math.sqrt,
                'sin': math.sin,
                'cos': math.cos,
                'tan': math.tan,
                'log': math.log,
                'log10': math.log10,
                'exp': math.exp,
                'pi': math.pi,
                'e': math.e,
            }
            
            def eval_expr(node):
                if isinstance(node, ast.Num):
                    return node.n
                elif isinstance(node, ast.Constant):
                    return node.value
                elif isinstance(node, ast.BinOp):
                    left_val = eval_expr(node.left)
                    right_val = eval_expr(node.right)
                    operator_func = safe_operators.get(type(node.op))
                    if operator_func:
                        return operator_func(left_val, right_val)
                    else:
                        raise ValueError(f"不支持的运算符: {node.op}")
                elif isinstance(node, ast.UnaryOp):
                    operand_val = eval_expr(node.operand)
                    operator_func = safe_operators.get(type(node.op))
                    if operator_func:
                        return operator_func(operand_val)
                    else:
                        raise ValueError(f"不支持的运算符: {node.op}")
                elif isinstance(node, ast.Call):
                    if not isinstance(node.func, ast.Name):
                        raise ValueError("只支持简单函数调用")
                    func_name = node.func.id
                    func = safe_functions.get(func_name)
                    if not func:
                        raise ValueError(f"不支持的函数: {func_name}")
                    args = [eval_expr(arg) for arg in node.args]
                    return func(*args)
                else:
                    raise ValueError(f"不支持的表达式类型: {type(node)}")
            
            # 解析和计算表达式
            tree = ast.parse(expression, mode='eval')
            result = eval_expr(tree.body)
            
            return f"{expression} = {result}"
            
        except Exception as e:
            logger.error(f"计算失败: {str(e)}")
            raise ValueError(f"计算失败: {str(e)}")


def initialize_system_tools(tool_manager_instance = None):
    """
    初始化所有系统工具
    
    Args:
        tool_manager_instance: 工具管理器实例，如果为None则使用全局实例
    """
    if tool_manager_instance is None:
        tool_manager_instance = tool_manager
    
    logger.info("开始初始化系统工具...")
    
    # 注册所有系统工具
    tools = [
        GetTimeTool(),
        GetSystemInfoTool(),
        ListFilesTool(),
        ReadFileTool(),
        ExecuteCommandTool(),
        SearchWebTool(),
        CalculateTool(),
    ]
    
    for tool in tools:
        tool_manager_instance.register_tool(tool)
    
    logger.info(f"已注册 {len(tools)} 个系统工具")


def get_tool_help() -> str:
    """获取工具帮助信息"""
    tool_names = tool_manager.get_tool_names()
    
    help_text = "可用系统工具：\n\n"
    for tool_name in tool_names:
        tool = tool_manager.get_tool(tool_name)
        if tool:
            help_text += f"  {tool.name}: {tool.description}\n"
    
    help_text += "\n使用示例：\n"
    help_text += "  - 获取时间: get_time\n"
    help_text += "  - 获取系统信息: get_system_info\n"
    help_text += "  - 列出文件: list_files path='.'\n"
    help_text += "  - 读取文件: read_file path='example.txt'\n"
    help_text += "  - 执行命令: execute_command command='ls -la'\n"
    help_text += "  - 搜索网络: search_web query='AI技术'\n"
    help_text += "  - 数学计算: calculate expression='2 + 3 * 4'\n"
    
    return help_text


# 导出函数和类
__all__ = [
    'initialize_system_tools',
    'get_tool_help',
    'GetTimeTool',
    'GetSystemInfoTool',
    'ListFilesTool',
    'ReadFileTool',
    'ExecuteCommandTool',
    'SearchWebTool',
    'CalculateTool',
]