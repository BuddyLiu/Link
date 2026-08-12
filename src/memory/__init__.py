"""
LINK记忆模块
提供长期记忆存储、检索和管理功能

注意：使用SimpleMemoryStore替代ChromaDB的MemoryStore，
因为chromadb不兼容Python 3.14+。
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

__version__ = "1.1.0"
__author__ = "LINK Team"

# 使用轻量级实现替代chromadb (chromadb不兼容Python 3.14+)
from .simple_memory_store import SimpleMemoryStore as MemoryStore
from .embedding_service import EmbeddingService
from .memory_entry import MemoryEntry, MemoryType
from .graph_index import GraphIndex


@dataclass
class SearchResult:
    """记忆搜索结果"""
    memory: MemoryEntry
    similarity: float


class MemoryManager:
    """记忆管理器（高级接口）"""

    def __init__(self, memory_store: MemoryStore):
        self.store = memory_store
        self.logger = None  # 将在初始化时设置

    def search_memories(self, query: str, n_results: int = 5) -> List[SearchResult]:
        """搜索相关记忆"""
        raw_results = self.store.search_memories(query, n_results)
        return [SearchResult(memory=mem, similarity=sim) for mem, sim in raw_results]

    def add_conversation_memory(self, user_input: str, assistant_response: str,
                               metadata: Optional[Dict] = None) -> str:
        """添加对话记忆"""
        content = f"用户: {user_input}\n助手: {assistant_response}"
        metadata = metadata or {}
        metadata.update({
            "type": MemoryType.CONVERSATION.value,
            "timestamp": datetime.now().isoformat()
        })
        return self.store.add_memory(content, metadata)

    def add_fact_memory(self, fact: str, importance: float = 0.5,
                       tags: List[str] = None) -> str:
        """添加事实记忆（含去重：同类事实更新替代，避免重复存储）

        用户信息类事实（姓名/职业/偏好/联系方式等）可能被多个来源重复保存
        （正则提取/LLM提取/save_user_fact）。这里归一化类别 + 相似度比对，
        同类已有记录则更新替代旧记录，而非新增重复。
        """
        metadata = {
            "type": MemoryType.FACT.value,
            "importance": importance,
            "tags": tags or [],
            "timestamp": datetime.now().isoformat()
        }
        # 去重：仅对用户信息类事实（含 用户/我的/姓名/职业/偏好/手机号 等标识）
        if self._is_user_fact(fact):
            try:
                dup_id = self._find_duplicate_fact(fact)
                if dup_id:
                    # 更新现有记录（保留原 id），替代旧值
                    self.store.update_memory(dup_id, new_content=fact, new_metadata=metadata)
                    return dup_id
            except Exception as e:
                if self.logger:
                    self.logger.debug(f"事实去重跳过: {e}")
        return self.store.add_memory(fact, metadata)

    @staticmethod
    def _is_user_fact(fact: str) -> bool:
        """判断是否为用户信息类事实（需要去重）"""
        user_markers = ("用户", "我的", "我叫", "姓名", "职业", "偏好", "爱好",
                        "手机号", "邮箱", "生日", "地址", "年龄", "技能", "喜欢", "不爱")
        return any(m in fact for m in user_markers)

    def _find_duplicate_fact(self, fact: str) -> Optional[str]:
        """在历史 fact 中找同类别、内容相似的事实，返回其 id（无则 None）"""
        import re
        # 归一化类别：提取事实的类别键
        cat_key = self._extract_fact_category(fact)
        if not cat_key:
            return None
        try:
            all_mem = self.store.get_all_memories(limit=2000) or []
        except Exception:
            return None
        for m in all_mem:
            if m.metadata.get("type") != MemoryType.FACT.value:
                continue
            content = m.content or ""
            if content == fact:  # 完全相同
                return m.id
            # 同类别且核心值相似（内容格式可能不同：'用户叫陈晨' vs '姓名：陈晨'）
            if self._fact_similar(fact, content):
                return m.id
        return None

    @staticmethod
    def _extract_fact_category(fact: str) -> Optional[str]:
        """提取事实的类别键（姓名/职业/偏好/联系方式等）"""
        import re
        for marker in ("姓名", "职业", "偏好", "爱好", "手机号", "邮箱", "生日", "地址"):
            if marker in fact:
                return marker
        # 用户叫X / 我的名字叫X → 姓名类
        if re.search(r'用户叫|名字叫|我的名字', fact):
            return "姓名"
        # 喜欢X / 不爱X → 偏好类
        if any(k in fact for k in ("喜欢", "不爱", "讨厌", "擅长")):
            return "偏好"
        return None

    @staticmethod
    def _fact_similar(a: str, b: str) -> bool:
        """判断两条同类别事实是否指向同一信息（提取核心值比较）"""
        import re
        # 提取第一个匹配的值（如 陈晨 / 前端工程师）
        def extract_val(s):
            # 去掉类别前缀和标点
            s = re.sub(r'^(用户|我的|我)(?:叫|名字叫|职业是|是|手机号|偏好|爱好|邮箱|生日|地址|年龄)?[:：\s]*', '', s)
            s = re.sub(r'^(姓名|职业|偏好|爱好|手机号|邮箱|生日|地址)[:：\s]*', '', s)
            s = re.sub(r'^叫', '', s)
            s = s.strip().strip('，。,.！!？?')
            return s
        va, vb = extract_val(a), extract_val(b)
        if not va or not vb:
            return False
        # 核心值相同或互为子串（如 "陈晨" vs "陈晨，是一名前端工程师"）
        return va in vb or vb in va or va == vb

    def add_preference_memory(self, preference: str, user_id: str = "default") -> str:
        """添加用户偏好记忆"""
        metadata = {
            "type": MemoryType.PREFERENCE.value,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        return self.store.add_memory(preference, metadata)

    def get_user_preferences(self, user_id: str = "default") -> List[MemoryEntry]:
        """获取用户偏好"""
        memories = self.store.get_all_memories()
        return [m for m in memories
                if m.metadata.get("type") == MemoryType.PREFERENCE.value
                and m.metadata.get("user_id") == user_id]

    def cleanup_old_memories(self, days_threshold: int = 365) -> int:
        """清理旧记忆"""
        return self.store.cleanup_old_memories(days_threshold)

    def export_memories(self, filepath: str) -> bool:
        """导出记忆数据"""
        return self.store.export_memories(filepath)

    def import_memories(self, filepath: str) -> bool:
        """导入记忆数据"""
        return self.store.import_memories(filepath)


def create_memory_manager(config=None) -> MemoryManager:
    """创建记忆管理器实例"""
    # 允许直接传入配置对象或字典
    # 默认使用 Ollama + bge-m3
    if config is None:
        persist_dir = "./data/memory/json"
        embed_model = "bge-m3"
        sim_threshold = 0.7
        max_memories = 5
        embed_backend = "ollama"
    elif hasattr(config, 'memory'):
        persist_dir = config.memory.chroma_persist_directory
        embed_model = getattr(config.memory, 'embedding_model', "bge-m3")
        sim_threshold = config.memory.similarity_threshold
        max_memories = config.memory.max_memories_per_query
        embed_backend = getattr(config.memory, 'embedding_provider', "ollama")
    elif isinstance(config, dict):
        persist_dir = config.get("persist_directory", "./data/memory/json")
        embed_model = config.get("embedding_model", "bge-m3")
        sim_threshold = config.get("similarity_threshold", 0.7)
        max_memories = config.get("max_memories_per_query", 5)
        embed_backend = config.get("embedding_provider", "ollama")
    else:
        persist_dir = "./data/memory/json"
        embed_model = "bge-m3"
        sim_threshold = 0.7
        max_memories = 5
        embed_backend = "ollama"

    # 创建嵌入服务
    if embed_backend == "ollama":
        embedding_service = EmbeddingService(
            model_name=embed_model,
            backend="ollama",
            ollama_base_url="http://localhost:11434"
        )
    else:
        embedding_service = EmbeddingService(
            model_name=embed_model,
            backend="sentence_transformers"
        )

    # 创建记忆存储 (使用轻量级实现)
    memory_store = MemoryStore(
        persist_directory=persist_dir,
        embedding_service=embedding_service,
        similarity_threshold=sim_threshold,
        max_memories_per_query=max_memories
    )

    # 创建记忆管理器
    manager = MemoryManager(memory_store)
    return manager


# 导出常用类和函数
__all__ = [
    'MemoryStore',
    'MemoryEntry',
    'MemoryType',
    'EmbeddingService',
    'MemoryManager',
    'SearchResult',
    'GraphIndex',
    'create_memory_manager',
]
