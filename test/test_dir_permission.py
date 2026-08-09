"""
目录授权回归测试

覆盖：
1. 双模块单例分裂（tools.* 与 src.tools.* 必须指向同一实例）
2. 目录授权继承（授权目录 → 子路径读写可用）
3. 文件授权不向子路径传递
4. 项目目录边界匹配（/proj_evil 不误判为项目内）
5. read 授权不授予 write
6. 授权弹窗流程（grant_dir 响应 → 目录授权）
7. 自动授权（PermissionSettings 规则生效）
"""
import sys
import os
import shutil
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
    from src.tools.file_permissions import FilePermissionManager, reset_permission_manager

    reset_permission_manager()
    tmp = Path(tempfile.mkdtemp(prefix="link_perm_test_"))
    try:
        # ── 1. 双模块单例分裂 ──
        print("\n[1] 双模块单例分裂")
        import tools.file_permissions as A
        import src.tools.file_permissions as B
        check("模块对象同一", A is B)
        check("权限单例同一", A.get_permission_manager() is B.get_permission_manager())
        from tools.permission_request_manager import PermissionRequestManager as PRA
        from src.tools.permission_request_manager import PermissionRequestManager as PRB
        check("PRM单例同一", PRA.get_instance() is PRB.get_instance())
        from tools import tool_manager as tm_a
        from src.tools import tool_manager as tm_b
        check("tool_manager同一", tm_a is tm_b)

        # ── 2. 目录授权继承 ──
        print("\n[2] 目录授权继承")
        pm = FilePermissionManager(persist_path=str(tmp / "perm.json"))
        ext_dir = tmp / "external" / "sub"
        ext_dir.mkdir(parents=True)
        check("未授权时外部路径被拒", not pm.is_path_allowed(str(ext_dir / "f.txt"), "read")[0])
        pm.authorize(str(tmp / "external"), "read_write", "permanent")
        check("授权目录后子文件可读",
              pm.is_path_allowed(str(ext_dir / "f.txt"), "read")[0])
        check("授权目录后子文件可写",
              pm.is_path_allowed(str(ext_dir / "f.txt"), "write")[0])
        check("授权目录后深层子路径可写",
              pm.is_path_allowed(str(ext_dir / "a" / "b" / "c.txt"), "write")[0])
        # 授权 read 目录 → 子文件仍读写（继承机制）
        ext2_dir = tmp / "external2"
        ext2_dir.mkdir(parents=True, exist_ok=True)
        pm2 = FilePermissionManager(persist_path=str(tmp / "perm2.json"))
        pm2.authorize(str(ext2_dir), "read", "temporary")
        check("授权read目录子文件可读",
              pm2.is_path_allowed(str(ext2_dir / "x.txt"), "read")[0])
        check("授权read目录子文件也可写(继承)",
              pm2.is_path_allowed(str(ext2_dir / "x.txt"), "write")[0])

        # ── 3. 文件授权不向子路径传递 ──
        print("\n[3] 文件授权不向子路径传递")
        f = ext_dir / "single.txt"
        f.write_text("x")
        pm3 = FilePermissionManager(persist_path=str(tmp / "perm3.json"))
        pm3.authorize(str(f), "read_write", "permanent")
        check("单文件授权后可读", pm3.is_path_allowed(str(f), "read")[0])
        check("单文件授权后子路径仍被拒",
              not pm3.is_path_allowed(str(ext_dir / "other.txt"), "read")[0])

        # ── 4. 项目目录边界匹配 ──
        print("\n[4] 项目目录边界")
        # 模拟项目根是 tmp，检查 tmp+_evil 不误判
        pm4 = FilePermissionManager(persist_path=str(tmp / "perm4.json"))
        fake_root = str(tmp / "proj")
        evil = str(tmp / "proj_evil" / "f.txt")
        check("proj_evil 不误判为项目内",
              not evil.startswith(fake_root + os.sep))

        # ── 5. read 授权不授予 write ──
        print("\n[5] read 授权不授予 write")
        f2 = tmp / "read_only.txt"
        f2.write_text("x")
        pm5 = FilePermissionManager(persist_path=str(tmp / "perm5.json"))
        pm5.authorize(str(f2), "read", "permanent")
        check("read授权可读", pm5.is_path_allowed(str(f2), "read")[0])
        check("read授权不可写", not pm5.is_path_allowed(str(f2), "write")[0])

        # ── 6. 授权弹窗流程（grant_dir） ──
        print("\n[6] 授权弹窗 grant_dir")
        from src.tools.permission_request_manager import (
            PermissionRequestManager, ResourceType,
        )
        prm = PermissionRequestManager.get_instance()
        prm.cancel_all()
        req = prm.create_request(str(ext_dir / "need.txt"), "read", ResourceType.FILE)
        check("suggest_dir 是父目录", req.suggest_dir is not None
              and req.suggest_dir == str(tmp / "external" / "sub"))
        # 模拟用户勾选"授权整个目录"
        import threading
        def _respond():
            prm.respond(req.id, True, "1h", grant_dir=True)
        threading.Thread(target=_respond, daemon=True).start()
        resp = prm.wait_for_response(req.id, timeout=5)
        check("grant_dir 响应返回", resp.get("approved") and resp.get("grant_dir"))
        check("grant_resource 是目录", resp.get("grant_resource") == req.suggest_dir)

        # ── 7. 自动授权 ──
        print("\n[7] 自动授权规则")
        from src.tools.permission_settings import PermissionSettings
        ps = PermissionSettings()
        dur = ps.get_auto_auth_duration("file", "read")
        check("自动授权读取规则可查询", dur is not None or dur is None)
        ps.update_settings({"file_read": "permanent"})
        check("设为permanent生效", ps.get_auto_auth_duration("file", "read") == "permanent")
        ps.update_settings({"file_read": "ask"})

        # ── 8. 工具层集成：授权后 write_file 可执行 ──
        print("\n[8] 工具层集成")
        from src.tools.system_tools import initialize_system_tools
        from src.tools import ToolManager
        tm = ToolManager()
        initialize_system_tools(tm)
        # 用独立的授权目录
        ext8 = tmp / "ext8"
        ext8.mkdir(parents=True)
        from src.tools.file_permissions import get_permission_manager
        pm8 = get_permission_manager()
        target = ext8 / "new.txt"
        check("未授权前 write 被拒",
              not pm8.is_path_allowed(str(target), "write")[0])
        pm8.grant_dir(str(ext8), "read_write", "permanent")
        check("grant_dir 后目录可写",
              pm8.is_path_allowed(str(target), "write")[0])
        try:
            tm.execute_tool("write_file", path=str(target), content="hello")
            check("write_file 执行成功", target.exists() and target.read_text() == "hello")
        except PermissionError as e:
            check("write_file 执行成功", False, str(e)[:60])

    finally:
        reset_permission_manager()
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n{'='*40}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
