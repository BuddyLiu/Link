"""
记忆条目数据结构定义
定义记忆的存储格式和类型
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Any, Optional
from enum import Enum


class MemoryType(Enum):
    """记忆类型枚举"""
    CONVERSATION = "conversation"  # 对话记忆
    FACT = "fact"                  # 事实记忆
    PREFERENCE = "preference"      # 用户偏好
    EVENT = "event"                # 事件记忆
    TODO = "todo"                  # 待办事项
    NOTE = "note"                  # 笔记
    FEEDBACK = "feedback"          # 用户反馈（👍/👎评分）
    INSIGHT = "insight"            # 分析洞察


@dataclass
class MemoryEntry:
    """记忆条目数据结构
    
    Attributes:
        id: 唯一标识符 (UUID)
        content: 记忆内容
        embedding: 向量嵌入
        summary: 记忆摘要
        metadata: 元数据字典
        created_at: 创建时间
        updated_at: 更新时间
        importance: 重要性评分 (0-1)
        memory_type: 记忆类型
    """
    
    id: str
    content: str
    embedding: Optional[List[float]] = None
    summary: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    importance: float = 0.5
    memory_type: MemoryType = MemoryType.CONVERSATION
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "content": self.content,
            "summary": self.summary,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "importance": self.importance,
            "memory_type": self.memory_type.value,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'MemoryEntry':
        """从字典创建实例"""
        # 处理时间字段
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.now()
        
        updated_at = data.get("updated_at")
        if isinstance(updated_at, str):
            updated_at = datetime.fromisoformat(updated_at)
        elif updated_at is None:
            updated_at = datetime.now()
        
        # 处理记忆类型
        memory_type_str = data.get("memory_type", "conversation")
        memory_type = MemoryType(memory_type_str)
        
        return cls(
            id=data.get("id", ""),
            content=data.get("content", ""),
            summary=data.get("summary", ""),
            metadata=data.get("metadata", {}),
            created_at=created_at,
            updated_at=updated_at,
            importance=data.get("importance", 0.5),
            memory_type=memory_type,
        )
    
    def update_content(self, new_content: str, new_summary: Optional[str] = None):
        """更新内容"""
        self.content = new_content
        self.updated_at = datetime.now()
        if new_summary is not None:
            self.summary = new_summary
    
    def add_metadata(self, key: str, value: Any):
        """添加元数据"""
        self.metadata[key] = value
        self.updated_at = datetime.now()
    
    def remove_metadata(self, key: str):
        """移除元数据"""
        if key in self.metadata:
            del self.metadata[key]
            self.updated_at = datetime.now()
    
    def get_age_days(self) -> float:
        """获取记忆天数（从创建到现在）"""
        return (datetime.now() - self.created_at).total_seconds() / (24 * 3600)
    
    def is_old(self, days_threshold: int = 365) -> bool:
        """判断是否过时"""
        return self.get_age_days() > days_threshold
    
    def should_forget(self, importance_threshold: float = 0.3) -> bool:
        """判断是否应该遗忘（重要性低于阈值且较旧）"""
        if self.importance < importance_threshold:
            age_days = self.get_age_days()
            # 重要性越低，遗忘时间越短
            forget_threshold = 30 * (1 + importance_threshold - self.importance)  # 30-60天
            return age_days > forget_threshold
        return False


@dataclass
class ConversationMemory:
    """对话记忆（专门处理对话的结构）"""
    
    user_input: str
    assistant_response: str
    timestamp: datetime = field(default_factory=datetime.now)
    conversation_id: Optional[str] = None
    user_id: str = "default"
    emotion_tone: Optional[str] = None  # 情感语调：positive, negative, neutral
    topics: List[str] = field(default_factory=list)
    
    def to_memory_entry(self) -> MemoryEntry:
        """转换为通用记忆条目"""
        content = f"用户: {self.user_input}\n助手: {self.assistant_response}"
        summary = f"对话: {self.user_input[:50]}..." if len(self.user_input) > 50 else self.user_input
        
        metadata = {
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "emotion_tone": self.emotion_tone,
            "topics": self.topics,
            "timestamp": self.timestamp.isoformat(),
            "type": "conversation"
        }
        
        return MemoryEntry(
            id=f"conv_{self.timestamp.timestamp()}",
            content=content,
            summary=summary,
            metadata=metadata,
            created_at=self.timestamp,
            memory_type=MemoryType.CONVERSATION,
            importance=0.6  # 对话记忆中等重要性
        )


@dataclass
class PreferenceMemory:
    """用户偏好记忆"""
    
    preference: str  # 偏好描述，如"不喜欢喝咖啡"
    user_id: str = "default"
    category: Optional[str] = None  # 类别：food, entertainment, work, etc.
    strength: float = 0.8  # 偏好强度 (0-1)
    created_at: datetime = field(default_factory=datetime.now)
    source: Optional[str] = None  # 来源：explicit（显式）, inferred（推断）
    
    def to_memory_entry(self) -> MemoryEntry:
        """转换为通用记忆条目"""
        metadata = {
            "user_id": self.user_id,
            "category": self.category,
            "strength": self.strength,
            "source": self.source,
            "created_at": self.created_at.isoformat(),
            "type": "preference"
        }
        
        return MemoryEntry(
            id=f"pref_{hash(self.preference) & 0xffffffff}",
            content=self.preference,
            summary=f"用户偏好: {self.preference[:50]}...",
            metadata=metadata,
            created_at=self.created_at,
            memory_type=MemoryType.PREFERENCE,
            importance=0.8  # 用户偏好较高重要性
        )


def create_conversation_memory(user_input: str, assistant_response: str, **kwargs) -> MemoryEntry:
    """创建对话记忆条目"""
    conv_memory = ConversationMemory(
        user_input=user_input,
        assistant_response=assistant_response,
        **kwargs
    )
    return conv_memory.to_memory_entry()


def create_preference_memory(preference: str, user_id: str = "default", **kwargs) -> MemoryEntry:
    """创建偏好记忆条目"""
    pref_memory = PreferenceMemory(
        preference=preference,
        user_id=user_id,
        **kwargs
    )
    return pref_memory.to_memory_entry()


def create_fact_memory(fact: str, importance: float = 0.5, tags: List[str] = None) -> MemoryEntry:
    """创建事实记忆条目"""
    metadata = {
        "tags": tags or [],
        "type": "fact"
    }
    
    return MemoryEntry(
        id=f"fact_{hash(fact) & 0xffffffff}",
        content=fact,
        summary=f"事实: {fact[:50]}..." if len(fact) > 50 else fact,
        metadata=metadata,
        importance=importance,
        memory_type=MemoryType.FACT
    )


__all__ = [
    'MemoryEntry',
    'MemoryType',
    'ConversationMemory',
    'PreferenceMemory',
    'create_conversation_memory',
    'create_preference_memory',
    'create_fact_memory',
]