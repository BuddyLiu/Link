"""
JARVIS记忆模块
提供长期记忆存储、检索和管理功能

注意：使用SimpleMemoryStore替代ChromaDB的MemoryStore，
因为chromadb不兼容Python 3.14+。
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

__version__ = "1.1.0"
__author__ = "JARVIS Team"

# 使用轻量级实现替代chromadb (chromadb不兼容Python 3.14+)
from .simple_memory_store import SimpleMemoryStore as MemoryStore
from .embedding_service import EmbeddingService
from .memory_entry import MemoryEntry, MemoryType


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
        """添加事实记忆"""
        metadata = {
            "type": MemoryType.FACT.value,
            "importance": importance,
            "tags": tags or [],
            "timestamp": datetime.now().isoformat()
        }
        return self.store.add_memory(fact, metadata)

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
    if config is None:
        persist_dir = "./data/memory/json"
        embed_model = "all-MiniLM-L6-v2"
        sim_threshold = 0.7
        max_memories = 5
    elif hasattr(config, 'memory'):
        persist_dir = config.memory.chroma_persist_directory
        embed_model = config.memory.embedding_model
        sim_threshold = config.memory.similarity_threshold
        max_memories = config.memory.max_memories_per_query
    elif isinstance(config, dict):
        persist_dir = config.get("persist_directory", "./data/memory/json")
        embed_model = config.get("embedding_model", "all-MiniLM-L6-v2")
        sim_threshold = config.get("similarity_threshold", 0.7)
        max_memories = config.get("max_memories_per_query", 5)
    else:
        persist_dir = "./data/memory/json"
        embed_model = "all-MiniLM-L6-v2"
        sim_threshold = 0.7
        max_memories = 5

    # 创建嵌入服务
    embedding_service = EmbeddingService(model_name=embed_model)

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
    'create_memory_manager',
]
