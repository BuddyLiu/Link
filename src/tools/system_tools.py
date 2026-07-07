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
    from .file_permissions import get_permission_manager
except ImportError:
    from . import Tool, SystemTool, tool_manager
    from ..utils.logger import logger
    from ..tools.file_permissions import get_permission_manager


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

        # 权限检查
        p = Path(path).resolve()
        allowed, reason = get_permission_manager().is_path_allowed(str(p), "read")
        if not allowed:
            raise PermissionError(reason)

        try:
            path_obj = p
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

        # 权限检查
        p = Path(path).resolve()
        allowed, reason = get_permission_manager().is_path_allowed(str(p), "read")
        if not allowed:
            raise PermissionError(reason)

        try:
            path_obj = p
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


class EditFileTool(SystemTool):
    """编辑文件工具——替换/插入/删除文件的指定行"""

    def __init__(self):
        parameters = {
            "path": {"type": "string", "description": "文件路径", "required": True},
            "operation": {
                "type": "string",
                "description": "操作类型: replace(替换行), insert(插入行), delete(删除行)",
                "enum": ["replace", "insert", "delete"],
                "required": True,
            },
            "line": {"type": "integer", "description": "行号（从1开始）", "required": True},
            "content": {
                "type": "string",
                "description": "新内容（replace/insert 时需要）。insert 时插入到此行之前",
                "required": False,
                "default": "",
            },
            "count": {
                "type": "integer",
                "description": "从 line 开始替换/删除的行数，默认 1",
                "required": False,
                "default": 1,
            },
        }
        super().__init__("edit_file", "编辑文件指定行（替换/插入/删除）", parameters)

    def _safe_path(self, path: str, mode: str = "write") -> Path:
        """检查路径访问权限"""
        p = Path(path).resolve()
        allowed, reason = get_permission_manager().is_path_allowed(str(p), mode)
        if not allowed:
            raise PermissionError(reason)
        return p

    def execute(self, **kwargs) -> str:
        path = self._safe_path(kwargs["path"])
        operation = kwargs["operation"]
        line = int(kwargs["line"])
        content = kwargs.get("content", "")
        count = int(kwargs.get("count", 1))

        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"不是文件: {path}")
        if line < 1:
            raise ValueError("行号必须 >= 1")

        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        total = len(lines)

        if operation == "replace":
            if line > total:
                raise ValueError(f"行号 {line} 超出文件范围（共 {total} 行）")
            end = min(line + count - 1, total)
            old_text = "".join(lines[line - 1:end])
            lines[line - 1:end] = [(content if content else "") + "\n"]
            if not content.endswith("\n"):
                lines[line - 1] = lines[line - 1].rstrip("\n") + "\n"
            new_text = lines[line - 1]
            logger.info(f"编辑文件 {path}: 替换第 {line}-{end} 行")
            result = f"已替换第 {line} 行（原: {old_text[:60].strip()}）"

        elif operation == "insert":
            if line > total + 1:
                raise ValueError(f"行号 {line} 超出范围（共 {total} 行，可插入到第 {total+1} 行）")
            insert_text = (content if content else "") + "\n"
            if not content.endswith("\n"):
                insert_text = content + "\n"
            lines.insert(line - 1, insert_text)
            logger.info(f"编辑文件 {path}: 在第 {line} 行前插入")
            result = f"已在第 {line} 行前插入"

        elif operation == "delete":
            if line > total:
                raise ValueError(f"行号 {line} 超出文件范围（共 {total} 行）")
            end = min(line + count - 1, total)
            deleted = "".join(lines[line - 1:end])
            del lines[line - 1:end]
            logger.info(f"编辑文件 {path}: 删除第 {line}-{end} 行")
            result = f"已删除第 {line}-{end} 行（共 {count} 行）"

        else:
            raise ValueError(f"不支持的操作: {operation}")

        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        return result


class WriteFileTool(SystemTool):
    """写入文件工具——创建新文件或覆盖已有文件"""

    def __init__(self):
        parameters = {
            "path": {"type": "string", "description": "文件路径", "required": True},
            "content": {"type": "string", "description": "文件内容", "required": True},
        }
        super().__init__("write_file", "创建或覆盖写入文件", parameters)

    def _safe_path(self, path: str, mode: str = "write") -> Path:
        p = Path(path).resolve()
        allowed, reason = get_permission_manager().is_path_allowed(str(p), mode)
        if not allowed:
            raise PermissionError(reason)
        return p

    def execute(self, **kwargs) -> str:
        path = self._safe_path(kwargs["path"])
        content = kwargs["content"]

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)

        logger.info(f"写入文件 {path} ({len(content)} 字符)")
        return f"已写入 {path} ({len(content)} 字符)"


class GrepFilesTool(SystemTool):
    """搜索文件内容工具——在项目中搜索文本"""

    def __init__(self):
        parameters = {
            "pattern": {"type": "string", "description": "搜索关键词", "required": True},
            "path": {"type": "string", "description": "搜索路径（默认当前目录）", "required": False, "default": "."},
            "include": {"type": "string", "description": "文件后缀过滤，如 '.py,.txt'", "required": False, "default": ""},
            "max_results": {"type": "integer", "description": "最大结果数", "required": False, "default": 20},
        }
        super().__init__("grep_files", "在文件中搜索文本", parameters)

    def _safe_path(self, path: str, mode: str = "read") -> Path:
        p = Path(path).resolve()
        allowed, reason = get_permission_manager().is_path_allowed(str(p), mode)
        if not allowed:
            raise PermissionError(reason)
        return p

    def execute(self, **kwargs) -> str:
        pattern = kwargs["pattern"]
        search_path = self._safe_path(kwargs.get("path", "."))
        include = kwargs.get("include", "")
        max_results = int(kwargs.get("max_results", 20))

        if not search_path.exists():
            raise FileNotFoundError(f"路径不存在: {search_path}")

        allowed_exts = [e.strip().lower() for e in include.split(",") if e.strip()] if include else None

        results = []
        try:
            for fpath in search_path.rglob("*"):
                if not fpath.is_file():
                    continue
                if allowed_exts and fpath.suffix.lower() not in allowed_exts:
                    continue
                # 跳过隐藏目录和二进制文件
                if any(p.startswith(".") for p in fpath.relative_to(search_path).parts):
                    continue
                try:
                    if fpath.stat().st_size > 1024 * 1024:  # 跳过 >1MB 的文件
                        continue
                    with open(fpath, 'r', encoding='utf-8', errors='ignore') as f:
                        for ln, line in enumerate(f, 1):
                            if pattern.lower() in line.lower():
                                preview = line.strip()[:120]
                                rel = fpath.relative_to(Path(os.getcwd()))
                                results.append(f"{rel}:{ln}: {preview}")
                                if len(results) >= max_results:
                                    raise StopIteration
                                break  # 每个文件只匹配一次，显示第一处
                except (IOError, UnicodeDecodeError):
                    continue
        except StopIteration:
            pass

        if not results:
            return f"在 {search_path} 中未找到 '{pattern}'"

        output = "\n".join(results)
        if len(results) >= max_results:
            output += f"\n...（仅显示前 {max_results} 条）"
        return output


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
        EditFileTool(),
        WriteFileTool(),
        GrepFilesTool(),
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
    'EditFileTool',
    'WriteFileTool',
    'GrepFilesTool',
    'ExecuteCommandTool',
    'SearchWebTool',
    'CalculateTool',
]