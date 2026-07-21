"""pytest 配置 — 自动将 src/ 加入 import 路径"""
import sys
import os
import pytest

# 将项目根目录和 src/ 加入 sys.path
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_src = os.path.join(_project_root, "src")
for p in [_project_root, _src]:
    if p not in sys.path:
        sys.path.insert(0, p)


@pytest.fixture
def temp_workspace(tmp_path):
    """返回一个已在 file_permissions 中授权的临时工作目录"""
    from tools.file_permissions import get_permission_manager
    pm = get_permission_manager()
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True)
    # 授权临时目录的所有访问
    pm.authorize(str(ws), "read_write", "temporary")
    return ws
