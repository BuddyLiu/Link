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
from tools import Tool, SystemTool, tool_manager
from utils.logger import logger
from tools.file_permissions import get_permission_manager


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
    """执行系统命令工具（多层安全检查+白名单）"""

    # ── 安全命令白名单（前缀匹配，如 ls -la 匹配 ls） ──
    SAFE_COMMANDS = {
        # 读文件/信息
        "ls", "cat", "head", "tail", "echo", "pwd", "which",
        "date", "cal", "uptime", "whoami", "id", "uname",
        "hostname", "env", "printenv",
        # Python / 环境
        "python --version", "python3 --version",
        "pip list", "pip3 list", "pip freeze",
        # Git 只读
        "git status", "git log", "git diff", "git branch",
        "git show", "git blame",
        # 文件系统只读
        "tree", "du", "df", "file", "stat",
        "wc", "sort", "cut", "grep",
        # 杂项安全
        "clear", "history", "type",
        # 网络只读
        "curl", "ping", "dig", "nslookup", "traceroute",
    }

    # ── 危险模式（子串匹配，任何出现即拒绝） ──
    DANGEROUS_PATTERNS = [
        # 系统破坏
        "rm -rf /", "rm -rf /*", "rm -rf ~",
        "dd if=", "mkfs", "mkswap", "fdisk", "parted", "format",
        # 提权
        "chmod 777 /", "chmod -R 777", "chown -R",
        "sudo", "su ",
        # Fork 炸弹 / shell-shock
        ":(){ :|:& };:", "() { :; };",
        # 设备操作
        "> /dev/", "> /dev/sd", "> /dev/nvme",
        "pv", "cryptsetup", "luks",
        # 系统断电
        "shutdown", "reboot", "halt", "poweroff",
        "init 0", "init 6", "systemctl poweroff",
        # 重定向管道到 shell
        "| bash", "| sh", "| zsh", "| /bin/sh",
        "> /etc/", "> /boot/", "> /sys/",
    ]

    def __init__(self):
        parameters = {
            "command": {
                "type": "string",
                "description": "要执行的命令（仅限安全命令：ls/cat/pwd/git 等）",
                "required": True
            },
            "timeout": {
                "type": "integer",
                "description": "命令超时时间（秒，上限60）",
                "required": False,
                "default": 30
            }
        }
        super().__init__("execute_command", "执行系统命令（安全受限，仅白名单内命令）", parameters)
        self._project_root = str(Path.cwd())

    def _classify_command(self, command: str) -> str:
        """将命令分类: 'safe' / 'dangerous' / 'unknown'"""
        cmd = command.strip().lstrip()
        cmd_lower = cmd.lower()

        # 1. 危险模式优先（子串匹配）
        for pattern in self.DANGEROUS_PATTERNS:
            if pattern in cmd_lower:
                logger.warning(f"命令被危险模式拦截: {pattern} in {cmd[:100]}")
                return "dangerous"

        # 2. 白名单前缀匹配
        first_token = cmd_lower.split()[0] if cmd_lower else ""

        # 尝试完整命令前缀匹配（如 "git status"）
        for prefix in self.SAFE_COMMANDS:
            if cmd_lower.startswith(prefix):
                return "safe"

        # 退而求其次：仅匹配第一个 token（如 "ls" 匹配 "ls -la /tmp"）
        safe_tokens = {p.split()[0] for p in self.SAFE_COMMANDS}
        if first_token in safe_tokens:
            return "safe"

        return "unknown"

    def execute(self, **kwargs) -> Dict[str, Any]:
        command = kwargs["command"]
        timeout = min(kwargs.get("timeout", 30), 60)  # 上限 60s

        # ── Layer 1：命令分类 ──
        classification = self._classify_command(command)
        if classification == "dangerous":
            raise ValueError(
                f"❌ 命令被安全系统拒绝（检测到危险模式）\n"
                f"命令: {command[:200]}"
            )
        if classification == "unknown":
            raise PermissionError(
                f"⚠️ 命令不在安全白名单中，已自动拒绝\n"
                f"命令: {command[:200]}\n"
                f"安全命令示例: {', '.join(sorted(self.SAFE_COMMANDS)[:10])} ..."
            )

        # ── Layer 2：工作目录限制 ──
        workdir = self._project_root

        # ── Layer 3：执行 ──
        logger.warning(f"执行命令: {command} (分类={classification}, timeout={timeout}s)")

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=workdir,
            )

            stdout = result.stdout or ""
            stderr = result.stderr or ""

            # 输出截断
            MAX_OUT = 100_000
            MAX_ERR = 50_000
            truncated = False
            if len(stdout) > MAX_OUT:
                stdout = stdout[:MAX_OUT] + f"\n... (输出截断, 共 {len(result.stdout)} 字符)"
                truncated = True
            if len(stderr) > MAX_ERR:
                stderr = stderr[:MAX_ERR] + f"\n... (错误截断, 共 {len(result.stderr)} 字符)"
                truncated = True

            # 二进制检测
            is_binary = False
            if stdout:
                try:
                    stdout.encode('utf-8')
                except (UnicodeEncodeError, UnicodeDecodeError):
                    is_binary = True
                    stdout = f"[二进制输出, {len(result.stdout)} 字节]"
            if stderr:
                try:
                    stderr.encode('utf-8')
                except (UnicodeEncodeError, UnicodeDecodeError):
                    stderr = f"[二进制错误输出, {len(result.stderr)} 字节]"

            return {
                "returncode": result.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "success": result.returncode == 0,
                "classification": classification,
                "truncated": truncated,
                "binary": is_binary,
            }

        except subprocess.TimeoutExpired:
            raise ValueError(f"⏱ 命令执行超时 (超过{timeout}秒): {command[:100]}")
        except PermissionError:
            raise
        except ValueError:
            raise
        except Exception as e:
            logger.error(f"执行命令失败: {str(e)}")
            raise ValueError(f"执行命令失败: {str(e)}")


class EditFileTool(SystemTool):
    """编辑文件工具——用字符串匹配替换内容（类似 Claude Code Edit）"""

    def __init__(self):
        parameters = {
            "path": {"type": "string", "description": "文件路径", "required": True},
            "old": {
                "type": "string",
                "description": "要被替换的原内容（必须唯一存在于文件中）",
                "required": True,
            },
            "new": {
                "type": "string",
                "description": "替换后的内容",
                "required": False,
                "default": "",
            },
        }
        super().__init__("edit_file", "编辑文件：用字符串匹配替换内容", parameters)

    def _safe_path(self, path: str, mode: str = "write") -> Path:
        p = Path(path).resolve()
        allowed, reason = get_permission_manager().is_path_allowed(str(p), mode)
        if not allowed:
            raise PermissionError(reason)
        return p

    def execute(self, **kwargs) -> str:
        path = self._safe_path(kwargs["path"])
        old = kwargs["old"]
        new = kwargs.get("new", "")

        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        if not path.is_file():
            raise ValueError(f"不是文件: {path}")

        content = path.read_text(encoding="utf-8")
        if old not in content:
            raise ValueError(
                f"文件中未找到指定内容:\n  {old[:80]}...\n"
                f"请先用 read_file 读取文件，确认内容后再编辑"
            )

        count = content.count(old)
        if count > 1:
            raise ValueError(f"内容重复出现 {count} 次，请提供更多上下文，使 old 参数唯一匹配")

        new_content = content.replace(old, new, 1)
        path.write_text(new_content, encoding="utf-8")

        logger.info(f"编辑文件 {path}: 替换 {len(old)} 字符 → {len(new)} 字符")
        return f"已替换文件 {path.name} 中的内容"


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


class GlobFilesTool(SystemTool):
    """搜索文件路径工具——按模式匹配文件名"""

    def __init__(self):
        parameters = {
            "pattern": {"type": "string", "description": "文件模式，如 '**/*.py', 'src/**/*.ts'", "required": True},
            "path": {"type": "string", "description": "搜索根目录（默认当前目录）", "required": False, "default": "."},
            "max_results": {"type": "integer", "description": "最大结果数", "required": False, "default": 30},
        }
        super().__init__("glob_files", "按模式匹配文件名，如 **/*.py", parameters)

    def execute(self, **kwargs) -> str:
        import glob
        pattern = kwargs["pattern"]
        root = kwargs.get("path", ".")
        max_results = int(kwargs.get("max_results", 30))

        search_path = Path(root).resolve()
        allowed = Path(os.getcwd()).resolve()
        try:
            search_path.relative_to(allowed)
        except ValueError:
            raise PermissionError(f"不允许访问项目目录外: {search_path}")

        full_pattern = str(search_path / pattern)
        matches = sorted(glob.glob(full_pattern, recursive=True))[:max_results]

        if not matches:
            return f"未匹配到文件: {pattern}"

        lines = [f"找到 {len(matches)} 个文件:" if len(matches) < max_results
                 else f"找到 {len(matches)} 个文件（仅显示前 {max_results} 条）:"]
        for m in matches:
            p = Path(m)
            try:
                rel = p.relative_to(allowed)
            except ValueError:
                rel = m
            if p.is_dir():
                lines.append(f"  📁 {rel}/")
            else:
                size = p.stat().st_size
                size_str = f"{size}B" if size < 1024 else f"{size//1024}KB"
                lines.append(f"  📄 {rel} ({size_str})")
        return "\n".join(lines)


class DeleteFileTool(SystemTool):
    """删除文件工具"""

    def __init__(self):
        parameters = {
            "path": {"type": "string", "description": "要删除的文件路径", "required": True},
        }
        super().__init__("delete_file", "删除文件", parameters)

    def _safe_path(self, path: str, mode: str = "write") -> Path:
        p = Path(path).resolve()
        allowed, reason = get_permission_manager().is_path_allowed(str(p), mode)
        if not allowed:
            raise PermissionError(reason)
        return p

    def execute(self, **kwargs) -> str:
        import os
        path = kwargs["path"]
        p = self._safe_path(path)
        if not p.exists():
            raise FileNotFoundError(f"文件不存在: {p}")
        if not p.is_file():
            raise ValueError(f"不是文件: {p}")
        os.remove(p)
        logger.info(f"删除文件 {p}")
        return f"已删除 {p.name}"


class SearchWebTool(SystemTool):
    """搜索网络工具 — 多后端搜索"""

    def __init__(self):
        parameters = {
            "query": {"type": "string", "description": "搜索关键词", "required": True},
            "max_results": {"type": "integer", "description": "最大结果数量", "required": False, "default": 5},
            "source": {"type": "string", "description": "搜索源: bing / web", "required": False, "default": "web"},
        }
        super().__init__("search_web", "搜索网络信息", parameters)

    def execute(self, **kwargs) -> str:
        import urllib.request, urllib.parse, re, time
        query = kwargs["query"]
        max_results = int(kwargs.get("max_results", 5))
        source = kwargs.get("source", "web")

        logger.info(f"搜索网络: {query}")

        # 统一结果提取
        def clean_html(html_text: str) -> str:
            return re.sub(r'<[^>]+>', '', html_text).strip()

        def extract_results(html, pattern, url_group, title_group, snippet_group=None):
            results = []
            seen = set()
            for m in re.finditer(pattern, html, re.DOTALL):
                url = m.group(url_group)
                title = clean_html(m.group(title_group))
                snippet = clean_html(m.group(snippet_group))[:180] if snippet_group else ""
                if url not in seen and title and len(title) > 2:
                    skip_domains = ["bing.com", "microsoft.com", "live.com"]
                    if not any(d in url for d in skip_domains):
                        seen.add(url)
                        results.append({"url": url, "title": title, "snippet": snippet})
            return results

        backends = []

        if source in ("web", "bing"):
            backends.append(("Bing", "https://www.bing.com/search?q=", [
                r'<h2><a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a></h2>.*?<p>(.*?)</p>',
            ]))

        results = []
        used_source = ""
        for name, base_url, patterns in backends:
            try:
                url = base_url + urllib.parse.quote(query)
                req = urllib.request.Request(url,
                    headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
                    timeout=15)
                resp = urllib.request.urlopen(req, timeout=15)
                html = resp.read().decode("utf-8", errors="ignore")

                for pattern in patterns:
                    extracted = extract_results(html, pattern, 1, 2, 3)
                    if extracted:
                        results = extracted
                        used_source = name
                        break
                if results:
                    break
            except Exception as e:
                logger.debug(f"{name} 搜索失败: {e}")
                continue

        # 兜底
        if not results:
            try:
                url = "https://www.bing.com/search?q=" + urllib.parse.quote(query)
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, timeout=10)
                html = resp.read().decode("utf-8", errors="ignore")
                for m in re.finditer(r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>', html):
                    url = m.group(1)
                    title = clean_html(m.group(2))
                    if title and len(title) > 5 and not any(d in url for d in ["bing.com", "microsoft.com"]):
                        results.append({"url": url, "title": title, "snippet": ""})
                        if len(results) >= max_results:
                            break
                if results:
                    used_source = "Bing"
            except Exception as e:
                logger.debug(f"兜底搜索失败: {e}")

        if not results:
            return f"搜索 '{query}' 未找到结果"

        # 格式化输出
        lines = [f"搜索结果 ({len(results[:max_results])} 条) 来源: {used_source}\n"]
        for i, r in enumerate(results[:max_results], 1):
            lines.append(f"{i}. {r['title']}")
            lines.append(f"   {r['url']}")
            if r['snippet']:
                lines.append(f"   {r['snippet']}")
            lines.append("")

        return "\n".join(lines).strip()


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
        GlobFilesTool(),
        DeleteFileTool(),
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
    'GlobFilesTool',
    'DeleteFileTool',
    'ExecuteCommandTool',
    'SearchWebTool',
    'CalculateTool',
]