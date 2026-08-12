#!/usr/bin/env python3
"""
Skill 加载器单元测试

覆盖：
1. frontmatter 解析（name/description/trigger/core 多行块）
2. 按意图匹配 skill
3. 渐进披露注入（core 精简指令）
4. 无匹配时返回空
5. 完整文档保留（body 含完整内容）
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import importlib.util


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "skill_loader", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "src/core/skills/skill_loader.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["skill_loader"] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_skill_dir(tmpdir):
    """构造一个测试 skill 目录"""
    d = Path(tmpdir)
    skill_file = d / "test-skill.skill.md"
    skill_file.write_text(
        "---\n"
        "name: test-skill\n"
        "description: 测试技能\n"
        "trigger: 读取, 文件, 计算\n"
        "core: |\n"
        "  读取文件 → read_file\n"
        "  计算 → calculate\n"
        "---\n"
        "# 完整文档\n"
        "这里是完整内容\n",
        encoding="utf-8",
    )
    return str(d)


def test_load_and_parse():
    """frontmatter 解析正确（含 core 多行块）"""
    sl = _load_module().SkillLoader(_make_skill_dir(tempfile.mkdtemp()))
    skills = sl.load()
    assert len(skills) == 1, f"应加载 1 个 skill，实际 {len(skills)}"
    s = skills[0]
    assert s.name == "test-skill"
    assert "测试技能" in s.description
    assert "读取" in s.triggers
    assert "读取文件 → read_file" in s.core
    assert "完整内容" in s.body  # 完整文档保留


def test_match_by_trigger():
    """按触发关键词匹配"""
    sl = _load_module().SkillLoader(_make_skill_dir(tempfile.mkdtemp()))
    sl.load()
    assert [s.name for s in sl.match("帮我读取文件")] == ["test-skill"]
    assert [s.name for s in sl.match("计算一下 2+2")] == ["test-skill"]
    assert sl.match("你好") == []  # 无匹配


def test_build_context_injection():
    """build_system_context 注入精简指令（渐进披露）"""
    sl = _load_module().SkillLoader(_make_skill_dir(tempfile.mkdtemp()))
    sl.load()
    ctx = sl.build_system_context("读取文件")
    assert "test-skill" in ctx
    assert "读取文件 → read_file" in ctx
    # 渐进披露：注入的是 core 而非完整文档
    assert "完整内容" not in ctx
    # 无匹配返回空
    assert sl.build_system_context("随便聊聊") == ""


def test_no_skills_dir():
    """目录不存在时安全返回空"""
    sl = _load_module().SkillLoader("/nonexistent/skills")
    assert sl.load() == []
    assert sl.build_system_context("任何输入") == ""


if __name__ == "__main__":
    test_load_and_parse()
    test_match_by_trigger()
    test_build_context_injection()
    test_no_skills_dir()
    print("✅ test_skill_loader 全部通过")
