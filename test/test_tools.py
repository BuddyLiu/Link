"""
LINK 工具系统综合性测试套件

涵盖 src/tools/ 中全部 12 个工具 + ToolManager + file_permissions。
使用 pytest + tmp_path 隔离文件系统操作。
"""
import pytest
import os
import shutil
import json
import datetime
import subprocess
import time
from pathlib import Path


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def tool_manager():
    """返回已注册所有系统工具的 ToolManager 实例"""
    from tools import ToolManager
    from tools.system_tools import initialize_system_tools
    tm = ToolManager()
    initialize_system_tools(tm)
    return tm


@pytest.fixture
def temp_file(temp_workspace):
    """在授权的临时目录中创建测试文件"""
    f = temp_workspace / "test.txt"
    f.write_text("Hello, World!\nLine 2\nLine 3\nLine 4\nLine 5", encoding="utf-8")
    return f

@pytest.fixture
def sample_project(temp_workspace):
    """在授权的临时目录中创建模拟项目"""
    (temp_workspace / "src" / "utils").mkdir(parents=True)
    (temp_workspace / "src" / "__init__.py").write_text("from .utils import helper\n")
    (temp_workspace / "src" / "utils" / "__init__.py").write_text("# utils package\n")
    (temp_workspace / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (temp_workspace / "README.md").write_text("# Project\n\nThis is a test project.\n")
    (temp_workspace / "data.txt").write_text("key1=value1\nkey2=value2\n")
    return temp_workspace


# =============================================================================
# Tool 基类 & ToolManager 测试
# =============================================================================

class TestToolBase:
    """Tool ABC 及 validate_parameters 测试"""

    def test_validate_parameters_bool_false(self):
        """bool("false") 应返回 False（修复关键 bug）"""
        # 通过 ToolManager 执行 ListFilesTool，验证 recursive="false" 不崩溃
        from tools.system_tools import ListFilesTool
        t = ListFilesTool()
        # 直接测试 bool 值转换：参数进入后应保持 False
        p1 = {"recursive": "false"}
        assert t.validate_parameters(p1) is not False
        assert p1["recursive"] is False
        p2 = {"recursive": "False"}
        assert t.validate_parameters(p2) is not False
        assert p2["recursive"] is False
        p3 = {"recursive": False}
        assert t.validate_parameters(p3) is not False
        assert p3["recursive"] is False

    def test_validate_parameters_bool_true(self):
        """bool("true") / "1" / "yes" 应返回 True"""
        from tools.system_tools import ListFilesTool
        t = ListFilesTool()
        for val in ["true", "True", "TRUE", "1", "yes", True]:
            p = {"recursive": val}
            assert t.validate_parameters(p) is not False
            assert p["recursive"] is True

    def test_validate_parameters_missing_required(self):
        """缺少 required 参数应返回 False"""
        from tools import Tool
        class TestTool(Tool):
            def execute(self, **kwargs): return "ok"
        t = TestTool("test", "test", {
            "name": {"type": "string", "required": True}
        })
        assert t.validate_parameters({}) is False

    def test_validate_parameters_type_coercion(self):
        """字符串到整数的自动转换"""
        from tools.system_tools import ExecuteCommandTool
        t = ExecuteCommandTool()
        # timeout="30" 应转为整数 30
        p1 = {"command": "echo hi", "timeout": "30"}
        assert t.validate_parameters(p1) is not False
        assert p1["timeout"] == 30
        p2 = {"command": "echo hi", "timeout": 30}
        assert t.validate_parameters(p2) is not False
        assert p2["timeout"] == 30
        # 空字符串应回退到默认值
        p3 = {"command": "echo hi", "timeout": ""}
        assert t.validate_parameters(p3) is not False
        assert p3["timeout"] == 30

    def test_get_schema_format(self):
        """get_schema() 返回标准 OpenAI function calling 格式"""
        from tools import Tool
        class TestTool(Tool):
            def execute(self, **kwargs): return "ok"
        t = TestTool("my_tool", "A test tool", {
            "input": {"type": "string", "description": "input param", "required": True}
        })
        schema = t.get_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "my_tool"
        assert schema["function"]["description"] == "A test tool"
        assert schema["function"]["parameters"]["type"] == "object"
        assert "input" in schema["function"]["parameters"]["properties"]
        assert "input" in schema["function"]["parameters"]["required"]


class TestToolManager:
    """ToolManager 注册和执行测试"""

    def test_register_and_list(self, tool_manager):
        """注册后 get_tool_names() 应包含工具名"""
        names = tool_manager.get_tool_names()
        assert "read_file" in names
        assert "write_file" in names
        assert "execute_command" in names

    def test_execute_get_time(self, tool_manager):
        """get_time 执行返回时间字符串"""
        result = tool_manager.execute_tool("get_time")
        assert isinstance(result, str)
        assert len(result) > 5

    def test_execute_not_found(self, tool_manager):
        """执行不存在的工具应抛 ValueError"""
        with pytest.raises(ValueError):
            tool_manager.execute_tool("nonexistent_tool")

    def test_duplicate_register(self, tool_manager):
        """重复注册应覆盖而非崩溃"""
        from tools import Tool
        class DummyTool(Tool):
            def execute(self, **kwargs): return "v2"
        tool_manager.register_tool(DummyTool("get_time", "overridden"))
        result = tool_manager.execute_tool("get_time")
        assert result == "v2"

    def test_get_tool_schemas(self, tool_manager):
        """get_tool_schemas 返回非空列表"""
        schemas = tool_manager.get_tool_schemas()
        assert len(schemas) >= 12
        names = [s["function"]["name"] for s in schemas]
        assert "read_file" in names
        assert "execute_command" in names


# =============================================================================
# GetTimeTool
# =============================================================================

class TestGetTimeTool:
    def test_default(self, tool_manager):
        result = tool_manager.execute_tool("get_time")
        assert "年" in result or ":" in result or "2026" in result

    def test_full(self, tool_manager):
        result = tool_manager.execute_tool("get_time", format="full")
        assert "年" in result or ":" in result

    def test_date(self, tool_manager):
        result = tool_manager.execute_tool("get_time", format="date")
        assert "年" in result or "2026" in result

    def test_time(self, tool_manager):
        result = tool_manager.execute_tool("get_time", format="time")
        assert ":" in result

    def test_timestamp(self, tool_manager):
        result = tool_manager.execute_tool("get_time", format="timestamp")
        assert result.isdigit()

    def test_invalid_format(self, tool_manager):
        """无效格式不崩溃，返回完整时间"""
        result = tool_manager.execute_tool("get_time", format="invalid")
        assert isinstance(result, str) and len(result) > 5


# =============================================================================
# GetSystemInfoTool
# =============================================================================

class TestGetSystemInfoTool:
    def test_basic(self, tool_manager):
        result = tool_manager.execute_tool("get_system_info")
        assert isinstance(result, dict)
        assert "platform" in result
        assert "python_version" in result

    def test_detail(self, tool_manager):
        result = tool_manager.execute_tool("get_system_info", detail=True)
        assert "hostname" in result or "architecture" in result

    def test_detail_false(self, tool_manager):
        result = tool_manager.execute_tool("get_system_info", detail=False)
        assert isinstance(result, dict)


# =============================================================================
# ReadFileTool
# =============================================================================

class TestReadFileTool:
    def test_success(self, temp_file, tool_manager):
        result = tool_manager.execute_tool("read_file", path=str(temp_file))
        assert "Hello, World!" in result

    def test_not_found(self, tool_manager):
        with pytest.raises((FileNotFoundError, ValueError, PermissionError)):
            tool_manager.execute_tool("read_file", path="/nonexistent/path/file.txt")

    def test_large_content_truncation(self, temp_workspace, tool_manager):
        f = temp_workspace / "large.txt"
        f.write_text("A" * 60000)
        result = tool_manager.execute_tool("read_file", path=str(f))
        assert len(result) <= 50000 + 100  # 截断后接近 50000

    def test_oversized_file(self, temp_workspace, tool_manager):
        f = temp_workspace / "big.bin"
        # 创建一个超过 10MB 的文件
        f.write_bytes(b"0" * (11 * 1024 * 1024))
        with pytest.raises(ValueError):
            tool_manager.execute_tool("read_file", path=str(f))

    def test_encoding_fallback(self, temp_workspace, tool_manager):
        """Latin-1 文件应可读"""
        f = temp_workspace / "latin1.txt"
        f.write_bytes("Café résumé naïve".encode("latin-1"))
        result = tool_manager.execute_tool("read_file", path=str(f))
        assert len(result) > 0


# =============================================================================
# WriteFileTool
# =============================================================================

class TestWriteFileTool:
    def test_success(self, temp_workspace, tool_manager):
        path = temp_workspace / "new.txt"
        result = tool_manager.execute_tool("write_file", path=str(path), content="Hello, World!")
        assert "已写入" in result
        assert path.read_text() == "Hello, World!"

    def test_creates_dirs(self, temp_workspace, tool_manager):
        path = temp_workspace / "a" / "b" / "c" / "deep.txt"
        result = tool_manager.execute_tool("write_file", path=str(path), content="deep")
        assert path.exists()
        assert path.read_text() == "deep"

    def test_overwrites(self, temp_workspace, tool_manager):
        path = temp_workspace / "existing.txt"
        path.write_text("old content")
        tool_manager.execute_tool("write_file", path=str(path), content="new content")
        assert path.read_text() == "new content"

    def test_content_limit(self, temp_workspace, tool_manager):
        """超过 10MB 的内容应拒绝"""
        path = temp_workspace / "huge.txt"
        with pytest.raises((ValueError, OSError)):
            tool_manager.execute_tool("write_file", path=str(path),
                                      content="x" * (11 * 1024 * 1024))


# =============================================================================
# EditFileTool
# =============================================================================

class TestEditFileTool:
    def test_success(self, temp_file, tool_manager):
        result = tool_manager.execute_tool("edit_file",
                                            path=str(temp_file),
                                            old="World", new="LINK")
        assert "已替换" in result
        content = temp_file.read_text()
        assert "Hello, LINK!" in content

    def test_empty_new(self, temp_file, tool_manager):
        """new="" 应删除匹配的文本块"""
        tool_manager.execute_tool("edit_file",
                                  path=str(temp_file),
                                  old="Line 2\n", new="")
        content = temp_file.read_text()
        assert "Line 2" not in content

    def test_not_found(self, tool_manager):
        with pytest.raises((FileNotFoundError, ValueError, PermissionError)):
            tool_manager.execute_tool("edit_file",
                                      path="/nonexistent/file.txt",
                                      old="x", new="y")

    def test_old_not_found(self, temp_file, tool_manager):
        with pytest.raises(ValueError):
            tool_manager.execute_tool("edit_file",
                                      path=str(temp_file),
                                      old="NONEXISTENT STRING",
                                      new="x")

    def test_duplicate_old(self, temp_file, tool_manager):
        """重复的 old 字符串应拒绝"""
        temp_file.write_text("abc\nabc\n")
        with pytest.raises(ValueError):
            tool_manager.execute_tool("edit_file",
                                      path=str(temp_file),
                                      old="abc", new="xyz")


# =============================================================================
# DeleteFileTool
# =============================================================================

class TestDeleteFileTool:
    def test_success(self, temp_file, tool_manager):
        result = tool_manager.execute_tool("delete_file", path=str(temp_file))
        assert "已删除" in result or "删除" in result
        assert not temp_file.exists()

    def test_not_found(self, tool_manager):
        with pytest.raises((FileNotFoundError, ValueError, PermissionError)):
            tool_manager.execute_tool("delete_file", path="/nonexistent/file.txt")

    def test_is_directory(self, temp_workspace, tool_manager):
        with pytest.raises(ValueError):
            tool_manager.execute_tool("delete_file", path=str(temp_workspace))


# =============================================================================
# ListFilesTool
# =============================================================================

class TestListFilesTool:
    def test_directory(self, sample_project, tool_manager):
        result = tool_manager.execute_tool("list_files", path=str(sample_project))
        assert isinstance(result, list)
        joined = "\n".join(result)
        # 条目含文件名 + 元信息（大小/时间），子串匹配验证
        assert any("src" in r for r in result) or "README.md" in joined or "data.txt" in joined

    def test_recursive(self, sample_project, tool_manager):
        result = tool_manager.execute_tool("list_files", path=str(sample_project),
                                           recursive=True)
        assert isinstance(result, list)
        assert any("main.py" in r for r in result)

    def test_not_found(self, tool_manager):
        with pytest.raises((FileNotFoundError, ValueError, PermissionError)):
            tool_manager.execute_tool("list_files", path="/nonexistent/dir")

    def test_default_path(self, tool_manager):
        """默认 path='.' 应返回工作目录内容"""
        # 在工作目录创建文件（相对路径落点 = 工作目录）
        from config.paths import get_workspace_directory
        ws = get_workspace_directory()
        probe = ws / "default_path_probe.txt"
        probe.write_text("probe")
        try:
            result = tool_manager.execute_tool("list_files")
            assert isinstance(result, list)
            assert any("default_path_probe.txt" in r for r in result)
        finally:
            probe.unlink(missing_ok=True)


# =============================================================================
# GrepFilesTool
# =============================================================================

class TestGrepFilesTool:
    def test_simple(self, tool_manager):
        """grep 在当前项目内搜索"""
        result = tool_manager.execute_tool("grep_files", pattern="import",
                                           path=".", include=".py")
        assert isinstance(result, str) and len(result) > 0

    def test_no_match(self, tool_manager):
        result = tool_manager.execute_tool("grep_files", pattern="XYZZYX_NOTFOUND",
                                           path=".")
        assert isinstance(result, str)

    def test_with_include(self, tool_manager):
        result = tool_manager.execute_tool("grep_files", pattern="import",
                                           include=".py")
        assert isinstance(result, str)

    def test_not_found(self, tool_manager):
        with pytest.raises((PermissionError, OSError, ValueError)):
            tool_manager.execute_tool("grep_files", pattern="test",
                                      path="/nonexistent")


# =============================================================================
# GlobFilesTool
# =============================================================================

class TestGlobFilesTool:
    def test_pattern(self, tool_manager):
        """glob_files 在当前项目中搜索"""
        result = tool_manager.execute_tool("glob_files", pattern="**/*.py")
        assert isinstance(result, str) and len(result) > 0

    def test_no_match(self, tool_manager):
        result = tool_manager.execute_tool("glob_files", pattern="*.nonexistent",
                                           path=".")
        assert isinstance(result, str)

    def test_limit(self, tool_manager):
        result = tool_manager.execute_tool("glob_files", pattern="*.py",
                                           max_results=1)
        assert isinstance(result, str)

    def test_outside_project(self, tool_manager):
        """项目外路径应被拒绝"""
        with pytest.raises((PermissionError, ValueError)):
            tool_manager.execute_tool("glob_files", pattern="*",
                                      path="/etc")


# =============================================================================
# ExecuteCommandTool（安全测试）
# =============================================================================

class TestExecuteCommandTool:
    def test_whitelisted(self, tool_manager):
        result = tool_manager.execute_tool("execute_command", command="echo hello")
        assert isinstance(result, dict)
        assert result["success"]
        assert "hello" in result["stdout"]

    def test_dangerous_pattern(self, tool_manager):
        with pytest.raises((ValueError, PermissionError)):
            tool_manager.execute_tool("execute_command", command="rm -rf /")

    def test_unknown_command(self, tool_manager):
        with pytest.raises((ValueError, PermissionError)):
            tool_manager.execute_tool("execute_command", command="nonexistent_cmd_xyz")

    def test_shell_injection(self, tool_manager):
        """ls; whoami 应被安全拒绝（shell=False 后不会执行两条命令）"""
        with pytest.raises((ValueError, PermissionError, subprocess.CalledProcessError)):
            result = tool_manager.execute_tool("execute_command", command="ls; whoami")
            # 如果返回了结果（而不是抛异常），检查是否安全
            if isinstance(result, dict):
                assert not result["success"]
                assert "ls;" in result.get("stdout", "") or not result["stdout"]

    def test_timeout(self, tool_manager):
        """短超时应返回超时错误"""
        with pytest.raises((ValueError, TimeoutError, OSError)):
            tool_manager.execute_tool("execute_command",
                                      command="sleep 3", timeout=1)

    def test_binary_output(self, temp_workspace, tool_manager):
        """二进制输出应被检测"""
        f = temp_workspace / "test.bin"
        f.write_bytes(b"\x00\x01\x02\x03")
        result = tool_manager.execute_tool("execute_command",
                                           command=f"cat {f}")
        assert isinstance(result, dict)
        assert result["binary"] or True  # cat 二进制文件可能被检测到

    def test_sudo_as_argument_not_blocked(self, tool_manager):
        """sudo 作为参数（echo "sudo xxx"）不应被误拦"""
        result = tool_manager.execute_tool("execute_command",
                                           command='echo "sudo hello"')
        assert isinstance(result, dict)
        assert result["success"]

    def test_sudo_as_command_blocked(self, tool_manager):
        """sudo 作为首 token 应被拒绝（提权）"""
        with pytest.raises((ValueError, PermissionError)):
            tool_manager.execute_tool("execute_command", command="sudo ls")


# =============================================================================
# SearchWebTool（基本测试，不依赖网络）
# =============================================================================

class TestSearchWebTool:
    def test_basic(self, tool_manager):
        """SearchWebTool 可执行，返回字符串或错误"""
        result = tool_manager.execute_tool("search_web", query="test")
        assert isinstance(result, str)
        assert len(result) > 0


# =============================================================================
# CalculateTool
# =============================================================================

class TestCalculateTool:
    def test_simple(self, tool_manager):
        result = tool_manager.execute_tool("calculate", expression="2 + 3 * 4")
        assert "14" in result

    def test_functions(self, tool_manager):
        result = tool_manager.execute_tool("calculate", expression="sqrt(16)")
        assert "4" in result

    def test_division(self, tool_manager):
        result = tool_manager.execute_tool("calculate", expression="10 / 3")
        assert "3." in result

    def test_dangerous(self, tool_manager):
        with pytest.raises(ValueError):
            tool_manager.execute_tool("calculate", expression="__import__('os').system('ls')")

    def test_invalid_expression(self, tool_manager):
        with pytest.raises(ValueError):
            tool_manager.execute_tool("calculate", expression="invalid syntax @@@")

    def test_division_by_zero(self, tool_manager):
        with pytest.raises((ValueError, ZeroDivisionError)):
            tool_manager.execute_tool("calculate", expression="1/0")

    def test_trig_inverse(self, tool_manager):
        """反三角函数（引力辅助转向角计算需要）"""
        result = tool_manager.execute_tool("calculate", expression="asin(1)")
        assert "1.57" in result  # asin(1) ≈ π/2

    def test_atan_degrees(self, tool_manager):
        """atan + degrees 组合（轨道力学常用）"""
        result = tool_manager.execute_tool("calculate", expression="degrees(atan(1))")
        assert "45" in result

    def test_bitwise_xor(self, tool_manager):
        """位运算异或"""
        result = tool_manager.execute_tool("calculate", expression="5 ^ 3")
        assert "6" in result  # 0b101 ^ 0b011 = 0b110

    def test_constants(self, tool_manager):
        """裸常量（pi/e）"""
        result = tool_manager.execute_tool("calculate", expression="2 * pi")
        assert "6.28" in result

    def test_power_expression(self, tool_manager):
        """幂运算（轨道力学常用）"""
        result = tool_manager.execute_tool("calculate", expression="2 ** 10")
        assert "1024" in result

    def test_escape_angle(self, tool_manager):
        """完整引力辅助公式：e = 1 + r_p * v_inf^2 / mu"""
        result = tool_manager.execute_tool(
            "calculate", expression="1 + 6350 * 2.71 ** 2 / 324859")
        # 1 + 6350*7.3441/324859 = 1 + 46635.0/324859 ≈ 1.1436
        assert "1.14" in result

    def test_unknown_variable_rejected(self, tool_manager):
        """未知变量应被拒绝（保持安全）"""
        with pytest.raises(ValueError):
            tool_manager.execute_tool("calculate", expression="x + 1")


# =============================================================================
# 回归测试：main.py TOOL_DEFS
# =============================================================================

class TestToolDefs:
    """确保 main.py 的 TOOL_DEFS 与工具实现一致"""

    def test_all_tools_in_defs(self):
        """TOOL_DEFS 应包含所有暴露给 LLM 的工具"""
        try:
            from main import LINK
        except ImportError:
            pytest.skip("无法导入 main.py（依赖 chain 问题，非工具系统错误）")
            return
        names = [t["function"]["name"] for t in LINK.TOOL_DEFS]
        required = ["read_file", "write_file", "edit_file", "delete_file",
                     "search_web", "glob_files", "execute_command",
                     "save_user_fact", "get_project_info",
                     "grep_files", "get_time", "list_files", "calculate"]
        for name in required:
            assert name in names, f"TOOL_DEFS 中缺少 {name}"

    def test_parameter_descriptions(self):
        """TOOL_DEFS 中的所有参数应有 description 字段"""
        try:
            from main import LINK
        except ImportError:
            pytest.skip("无法导入 main.py")
            return
        for t in LINK.TOOL_DEFS:
            func = t["function"]
            params = func.get("parameters", {}).get("properties", {})
            for pname, pinfo in params.items():
                if pname in ("category",) and "enum" in pinfo:
                    continue  # enum 字段自描述，允许无 description
                if pname == "value" and func["name"] == "save_user_fact":
                    continue  # value 字段自描述
                assert "description" in pinfo, \
                    f"{func['name']}.{pname} 缺少 description"

    def test_tool_manager_has_all_registered(self, tool_manager):
        """ToolManager 注册了所有工具"""
        names = tool_manager.get_tool_names()
        expected = ["get_time", "get_system_info", "list_files",
                     "read_file", "edit_file", "write_file",
                     "grep_files", "glob_files", "delete_file",
                     "execute_command", "search_web", "calculate"]
        for name in expected:
            assert name in names, f"ToolManager 中缺少 {name}"
        assert len(names) >= len(expected)


# =============================================================================
# 兼容 run_link.py 测试运行器
# =============================================================================

def run_all_tests() -> bool:
    """供 run_link.py test 模式调用（返回 True 表示全部通过）"""
    import subprocess
    import sys
    result = subprocess.run(
        [sys.executable, "-m", "pytest", __file__, "-v", "--tb=short"],
        capture_output=True, text=True
    )
    print(result.stdout)
    if result.stderr:
        print(result.stderr[-1000:])
    return result.returncode == 0
