"""
JARVIS记忆模块
提供长期记忆存储、检索和管理功能
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, field

__version__ = "1.0.0"
__author__ = "JARVIS Team"

# 导出主要类和函数
from .memory_store import MemoryStore
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
        return self.store.search_memories(query, n_results)
    
    def add_conversation_memory(self, user_input: str, assistant_response: str, 
                               metadata: Optional[Dict] = None) -> str:
        """添加对话记忆"""
        content = f"用户: {user_input}\n助手: {assistant_response}"
        metadata = metadata or {}
        metadata.update({
            "type": MemoryType.CONVERSATION,
            "timestamp": datetime.now().isoformat()
        })
        return self.store.add_memory(content, metadata)
    
    def add_fact_memory(self, fact: str, importance: float = 0.5, 
                       tags: List[str] = None) -> str:
        """添加事实记忆"""
        metadata = {
            "type": MemoryType.FACT,
            "importance": importance,
            "tags": tags or [],
            "timestamp": datetime.now().isoformat()
        }
        return self.store.add_memory(fact, metadata)
    
    def add_preference_memory(self, preference: str, user_id: str = "default") -> str:
        """添加用户偏好记忆"""
        metadata = {
            "type": MemoryType.PREFERENCE,
            "user_id": user_id,
            "timestamp": datetime.now().isoformat()
        }
        return self.store.add_memory(preference, metadata)
    
    def get_user_preferences(self, user_id: str = "default") -> List[MemoryEntry]:
        """获取用户偏好"""
        memories = self.store.get_all_memories()
        return [m for m in memories 
                if m.metadata.get("type") == MemoryType.PREFERENCE 
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


def create_memory_manager(config) -> MemoryManager:
    """创建记忆管理器实例"""
    from .memory_store import MemoryStore
    from .embedding_service import EmbeddingService
    
    # 创建嵌入服务
    embedding_service = EmbeddingService(
        model_name=config.memory.embedding_model
    )
    
    # 创建记忆存储
    memory_store = MemoryStore(
        chroma_persist_directory=config.memory.chroma_persist_directory,
        embedding_service=embedding_service,
        similarity_threshold=config.memory.similarity_threshold,
        max_memories_per_query=config.memory.max_memories_per_query
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