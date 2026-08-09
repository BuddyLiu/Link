"""
默认工作目录回归测试

覆盖：
1. 相对路径写入落到工作目录（源码目录不污染）
2. 源码目录只读（读允许、写需授权、授权后成功）
3. 绝对外部路径行为不变（需授权）
4. execute_command 在工作目录执行
5. 工作目录自动创建
6. list_permissions 显示工作目录 + 源码只读
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))) + "/src")

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def main():
    import tempfile as tf
    import shutil

    ws_tmp = Path(tf.mkdtemp(prefix="link_ws_test_"))
    # 用环境变量指定工作目录（隔离，不碰真实家目录）
    os.environ["LINK_WORKSPACE"] = str(ws_tmp)

    from config.paths import get_workspace_directory, resolve_workspace
    from tools.file_permissions import reset_permission_manager
    from tools.system_tools import initialize_system_tools
    from tools import ToolManager

    # 清理持久化白名单，避免上一次测试的授权残留干扰（测试用独立文件）
    import json as _json
    _perm_file = Path("data/permissions.json")
    _perm_bak = None
    if _perm_file.exists():
        _perm_bak = _perm_file.read_text(encoding="utf-8")
        _perm_file.write_text("{}", encoding="utf-8")
    reset_permission_manager()

    src_root = Path.cwd().resolve()  # 源码目录 = 测试进程 cwd

    # ── 1. 相对路径落到工作目录 ──
    print("\n[1] 相对路径落到工作目录")
    tm = ToolManager()
    initialize_system_tools(tm)
    tm.execute_tool("write_file", path="ws_probe.txt", content="hello ws")
    ws_file = ws_tmp / "ws_probe.txt"
    src_file = src_root / "ws_probe.txt"
    check("工作目录存在文件", ws_file.exists())
    check("源码目录无此文件", not src_file.exists())
    check("内容正确", ws_file.read_text() == "hello ws")
    # 相对读
    r = tm.execute_tool("read_file", path="ws_probe.txt")
    check("相对读命中工作目录", "hello ws" in r)
    # 清理
    ws_file.unlink(missing_ok=True)

    # ── 2. 源码目录只读 ──
    print("\n[2] 源码目录只读")
    src_probe = src_root / "src_probe_tmp.txt"
    # 读源码允许（用现存源码文件）
    ok_read = True
    try:
        tm.execute_tool("read_file", path=str(src_root / "main.py"))
    except PermissionError:
        ok_read = False
    check("读源码文件允许", ok_read)
    # 写源码拒绝
    denied = False
    try:
        tm.execute_tool("write_file", path=str(src_probe), content="x")
    except PermissionError:
        denied = True
    check("写源码文件被拒", denied)
    check("源码文件未创建", not src_probe.exists())
    # 授权后写成功
    if not src_probe.exists():
        pm = __import__("tools.file_permissions", fromlist=["get_permission_manager"]).get_permission_manager()
        pm.authorize(str(src_probe), "read_write", "permanent")
        try:
            tm.execute_tool("write_file", path=str(src_probe), content="ok")
            check("授权后写源码成功", src_probe.read_text() == "ok")
        except PermissionError as e:
            check("授权后写源码成功", False, str(e)[:60])
        src_probe.unlink(missing_ok=True)

    # ── 3. 绝对外部路径需授权 ──
    print("\n[3] 绝对外部路径")
    ext_dir = Path(tf.mkdtemp(prefix="link_ext_test_"))
    ext_file = ext_dir / "f.txt"
    denied_ext = False
    try:
        tm.execute_tool("write_file", path=str(ext_file), content="x")
    except PermissionError:
        denied_ext = True
    check("外部绝对路径未授权被拒", denied_ext)

    # ── 4. execute_command 工作目录 ──
    print("\n[4] execute_command 工作目录")
    r = tm.execute_tool("execute_command", command="pwd")
    check("pwd 输出为工作目录", str(ws_tmp.resolve()) in r.get("stdout", ""))

    # ── 5. 工作目录自动创建 ──
    print("\n[5] 工作目录自动创建")
    auto_ws = Path(tf.mkdtemp(prefix="link_auto_")) / "auto"
    os.environ["LINK_WORKSPACE"] = str(auto_ws)
    resolved = resolve_workspace()
    check("自动创建工作目录", resolved.exists())

    # ── 6. list_permissions 显示工作目录 + 源码只读 ──
    print("\n[6] list_permissions")
    from tools.file_permissions import FilePermissionManager
    pm2 = FilePermissionManager(workspace_root=str(ws_tmp),
                                source_root=str(src_root),
                                persist_path=str(ws_tmp / "perm.json"))
    perms = pm2.list_permissions()
    has_ws = any(p.get("path") == str(Path(ws_tmp).resolve())
                 and p.get("under_project") for p in perms)
    has_src = any(p.get("path") == str(Path(src_root).resolve())
                  and p.get("read_only") for p in perms)
    check("显示工作目录(读写)", has_ws)
    check("显示源码目录(只读)", has_src)

    shutil.rmtree(ws_tmp, ignore_errors=True)
    shutil.rmtree(ext_dir, ignore_errors=True)

    # 恢复持久化白名单
    if _perm_bak is not None:
        _perm_file.write_text(_perm_bak, encoding="utf-8")
    else:
        _perm_file.unlink(missing_ok=True)
    reset_permission_manager()

    print(f"\n{'='*40}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
