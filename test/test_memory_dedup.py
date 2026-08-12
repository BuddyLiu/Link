#!/usr/bin/env python3
"""
记忆去重单元测试

覆盖：
1. 不同来源同类别事实只存一条（正则/LLM/save_user_fact 三种格式）
2. 相同内容不重复
3. 不同类别互不干扰
4. 非用户信息不触发去重（保持原行为）
5. 更新替代旧记录（保留 id）
"""

import os
import sys
import tempfile
import importlib.util
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))


def _make_manager():
    """构造 MemoryManager（用临时目录 + 简单 store）"""
    from src.memory import MemoryManager
    from src.memory.simple_memory_store import SimpleMemoryStore
    tmp = Path(tempfile.mkdtemp())
    store = SimpleMemoryStore(persist_directory=str(tmp / "mem"))
    manager = MemoryManager(store)
    return manager, tmp


def test_duplicate_same_category_dedup():
    """不同来源的同类事实只存一条（姓名类三种格式）"""
    manager, _ = _make_manager()
    # 正则格式
    id1 = manager.add_fact_memory("用户叫陈晨", importance=0.85)
    # LLM 格式
    id2 = manager.add_fact_memory("姓名：陈晨", importance=0.85)
    # save_user_fact 格式
    id3 = manager.add_fact_memory("用户姓名: 陈晨", importance=0.85)

    all_mem = manager.store.get_all_memories(limit=100)
    facts = [m for m in all_mem if m.metadata.get("type") == "fact"]
    # 应只有 1 条（去重后）
    assert len(facts) == 1, f"同类事实应去重为1条，实际 {len(facts)}: {[m.content for m in facts]}"
    # 保留第一个 id（更新替代）
    assert id1 == id2 == id3, "重复保存应返回原 id"


def test_exact_duplicate_dedup():
    """完全相同内容不重复"""
    manager, _ = _make_manager()
    id1 = manager.add_fact_memory("用户职业: 软件工程师")
    id2 = manager.add_fact_memory("用户职业: 软件工程师")

    all_mem = manager.store.get_all_memories(limit=100)
    facts = [m for m in all_mem if m.metadata.get("type") == "fact"]
    assert len(facts) == 1, f"相同内容应只存1条，实际 {len(facts)}"
    assert id1 == id2


def test_different_categories_keep():
    """不同类别的事实互不干扰"""
    manager, _ = _make_manager()
    manager.add_fact_memory("用户姓名: 李雷")
    manager.add_fact_memory("用户职业: 设计师")
    manager.add_fact_memory("用户偏好: 游泳")

    all_mem = manager.store.get_all_memories(limit=100)
    facts = [m for m in all_mem if m.metadata.get("type") == "fact"]
    assert len(facts) == 3, f"不同类别应保留3条，实际 {len(facts)}"


def test_similar_content_dedup():
    """同类别核心值相似（'陈晨' vs '陈晨，是一名前端工程师'）去重"""
    manager, _ = _make_manager()
    id1 = manager.add_fact_memory("姓名：陈晨")
    id2 = manager.add_fact_memory("用户叫陈晨，是一名前端工程师")

    all_mem = manager.store.get_all_memories(limit=100)
    facts = [m for m in all_mem if m.metadata.get("type") == "fact"]
    assert len(facts) == 1, f"相似内容应去重，实际 {len(facts)}: {[m.content for m in facts]}"
    assert id1 == id2


def test_non_user_fact_no_dedup():
    """非用户信息事实不触发去重（保持原行为）"""
    manager, _ = _make_manager()
    id1 = manager.add_fact_memory("项目使用 FastAPI 框架", tags=["project_knowledge"])
    id2 = manager.add_fact_memory("项目使用 FastAPI 框架", tags=["project_knowledge"])

    all_mem = manager.store.get_all_memories(limit=100)
    facts = [m for m in all_mem if m.metadata.get("type") == "fact"]
    # 非用户信息：不去重（即使内容相同），因为不含用户标识
    assert len(facts) == 2, f"非用户信息不应去重，实际 {len(facts)}"


if __name__ == "__main__":
    test_duplicate_same_category_dedup()
    test_exact_duplicate_dedup()
    test_different_categories_keep()
    test_similar_content_dedup()
    test_non_user_fact_no_dedup()
    print("✅ test_memory_dedup 全部通过")
