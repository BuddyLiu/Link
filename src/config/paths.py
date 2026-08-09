"""
路径解析辅助模块 — 唯一的工作目录/源码目录定义来源。

LINK 有三个"项目根"概念（权限边界、命令执行目录、知识扫描根），
此模块统一提供路径解析，实现 DRY：
- 工作目录（默认 ~/LINK-Workspace）：文件操作（读写创建）的默认落点
- 源码目录：LINK 进程启动时的 cwd，只读保留、写入需授权
- 数据存储（data/）：保持相对 cwd（源码目录），不受工作目录影响

配置优先级：LINK_WORKSPACE 环境变量 > settings.system.workspace_directory > 默认值
"""

import os
import sys
from pathlib import Path
from typing import Union

DEFAULT_WORKSPACE = "~/LINK-Workspace"


def get_workspace_directory() -> Path:
    """获取工作目录（未展开 ~，未 resolve），不创建"""
    raw = os.getenv("LINK_WORKSPACE") or os.getenv("SYSTEM_WORKSPACE_DIRECTORY")
    if not raw:
        try:
            from config.settings import settings  # 惰性导入避免循环依赖
            raw = settings.system.workspace_directory
        except Exception:
            raw = ""
    if not raw:
        raw = DEFAULT_WORKSPACE
    return Path(raw).expanduser()


def resolve_workspace() -> Path:
    """解析工作目录为绝对路径；目录不存在时自动创建（幂等）"""
    p = get_workspace_directory().resolve()
    try:
        p.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return p


def get_source_directory() -> Path:
    """源码目录 = LINK 进程启动时的 cwd（数据存储与项目扫描基准）"""
    return Path(os.getcwd()).resolve()


def resolve_source_root() -> Path:
    """源码根目录（绝对路径）"""
    return get_source_directory()


def resolve_tool_path(path: Union[str, Path]) -> Path:
    """将工具传入的路径解析为绝对路径：
    - 相对路径 → 解析到工作目录（默认落点）
    - 绝对路径 → 原样保留（权限边界另行检查）
    """
    p = Path(path)
    if p.is_absolute():
        return p.resolve()
    return (get_workspace_directory() / p).resolve()


# ── 模块别名注册（消除双模块单例分裂） ──
# 与 src/tools/file_permissions.py 同注释：保证 config.paths 与 src.config.paths 指向同一模块。
_THIS_NAME = __name__
_OTHER_NAME = ("src.config.paths" if _THIS_NAME == "config.paths"
               else "config.paths")
if _OTHER_NAME not in sys.modules:
    sys.modules[_OTHER_NAME] = sys.modules[_THIS_NAME]
