"""
记忆存储模块
提供基于Chroma向量数据库的记忆存储和检索功能
"""

import os
import json
import uuid
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

from .memory_entry import MemoryEntry, MemoryType
from .embedding_service import EmbeddingService, ChromaEmbeddingFunction
from ..utils.logger import logger


class MemoryStore:
    """记忆存储类
    
    基于Chroma向量数据库实现记忆的存储、检索和管理功能。
    """
    
    def __init__(self, 
                 chroma_persist_directory: str = "./data/memory/chroma",
                 embedding_service: Optional[EmbeddingService] = None,
                 similarity_threshold: float = 0.7,
                 max_memories_per_query: int = 5):
        """
        初始化记忆存储
        
        Args:
            chroma_persist_directory: Chroma数据库持久化目录
            embedding_service: 嵌入服务实例
            similarity_threshold: 相似度阈值，低于此值的记忆将被过滤
            max_memories_per_query: 每次查询返回的最大记忆数量
        """
        self.chroma_persist_directory = chroma_persist_directory
        self.similarity_threshold = similarity_threshold
        self.max_memories_per_query = max_memories_per_query
        
        # 设置日志
        self.logger = logger.getChild("memory_store")
        
        # 创建嵌入服务
        if embedding_service is None:
            self.embedding_service = EmbeddingService()
        else:
            self.embedding_service = embedding_service
        
        # 初始化Chroma客户端
        self.chroma_client = None
        self.collection = None
        self._initialize_chroma()
        
        self.logger.info(f"记忆存储初始化完成，数据库路径: {chroma_persist_directory}")
    
    def _initialize_chroma(self):
        """初始化Chroma向量数据库"""
        try:
            if not CHROMA_AVAILABLE:
                raise ImportError("chromadb 未安装")
            
            # 确保目录存在
            os.makedirs(self.chroma_persist_directory, exist_ok=True)
            
            # 创建Chroma客户端
            self.chroma_client = chromadb.PersistentClient(
                path=self.chroma_persist_directory,
                settings=ChromaSettings(
                    anonymized_telemetry=False,  # 禁用遥测
                    allow_reset=True
                )
            )
            
            # 创建或获取记忆集合
            collection_name = "link_memories"
            
            try:
                self.collection = self.chroma_client.get_collection(collection_name)
                self.logger.info(f"找到现有记忆集合: {collection_name}")
            except Exception:
                # 创建新的集合
                self.collection = self.chroma_client.create_collection(
                    name=collection_name,
                    embedding_function=ChromaEmbeddingFunction(self.embedding_service),
                    metadata={"description": "LINK智能体记忆存储"}
                )
                self.logger.info(f"创建新的记忆集合: {collection_name}")
            
            # 测试连接
            test_count = self.collection.count()
            self.logger.info(f"记忆集合包含 {test_count} 条记录")
            
        except Exception as e:
            self.logger.error(f"初始化Chroma数据库失败: {str(e)}")
            self.collection = None
            raise
    
    def add_memory(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """
        添加记忆
        
        Args:
            content: 记忆内容
            metadata: 记忆元数据
            
        Returns:
            记忆ID
        """
        if not content or not content.strip():
            raise ValueError("记忆内容不能为空")
        
        try:
            # 生成唯一ID
            memory_id = str(uuid.uuid4())
            
            # 处理元数据
            metadata = metadata or {}
            metadata["id"] = memory_id
            metadata["created_at"] = datetime.now().isoformat()
            
            # 如果未指定类型，默认为对话
            if "type" not in metadata:
                metadata["type"] = "conversation"
            
            # 创建记忆条目
            memory_entry = MemoryEntry(
                id=memory_id,
                content=content,
                metadata=metadata,
                memory_type=MemoryType(metadata.get("type", "conversation")),
                importance=metadata.get("importance", 0.5)
            )
            
            # 生成嵌入
            embedding = self.embedding_service.embed(content)
            memory_entry.embedding = embedding
            
            # 存储到Chroma
            self.collection.add(
                ids=[memory_id],
                embeddings=[embedding],
                documents=[content],
                metadatas=[metadata]
            )
            
            self.logger.info(f"添加记忆成功，ID: {memory_id}, 类型: {metadata['type']}")
            return memory_id
            
        except Exception as e:
            self.logger.error(f"添加记忆失败: {str(e)}")
            raise
    
    def search_memories(self, query: str, n_results: int = None) -> List[Tuple[MemoryEntry, float]]:
        """
        搜索相关记忆
        
        Args:
            query: 查询文本
            n_results: 返回结果数量，默认使用配置值
            
        Returns:
            记忆条目和相似度得分的列表
        """
        if not query or not query.strip():
            return []
        
        if n_results is None:
            n_results = self.max_memories_per_query
        
        try:
            # 搜索相似记忆
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results,
                include=["documents", "metadatas", "distances"]
            )
            
            # 处理结果
            memories = []
            
            if results["ids"] and results["ids"][0]:
                for i, memory_id in enumerate(results["ids"][0]):
                    # 计算相似度（Chroma返回的是距离，需要转换为相似度）
                    distance = results["distances"][0][i]
                    similarity = 1.0 / (1.0 + distance)  # 将距离转换为相似度
                    
                    # 过滤低于阈值的记忆
                    if similarity < self.similarity_threshold:
                        continue
                    
                    # 获取记忆数据
                    content = results["documents"][0][i]
                    metadata = results["metadatas"][0][i]
                    
                    # 创建记忆条目
                    memory_entry = MemoryEntry.from_dict({
                        "id": memory_id,
                        "content": content,
                        "metadata": metadata,
                        "memory_type": metadata.get("type", "conversation")
                    })
                    
                    memories.append((memory_entry, similarity))
            
            # 按相似度排序
            memories.sort(key=lambda x: x[1], reverse=True)
            
            self.logger.info(f"搜索记忆完成，查询: '{query[:30]}...'，找到 {len(memories)} 条相关记忆")
            return memories
            
        except Exception as e:
            self.logger.error(f"搜索记忆失败: {str(e)}")
            return []
    
    def get_memory(self, memory_id: str) -> Optional[MemoryEntry]:
        """
        根据ID获取记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            记忆条目，如果不存在则返回None
        """
        try:
            results = self.collection.get(
                ids=[memory_id],
                include=["documents", "metadatas"]
            )
            
            if not results["ids"]:
                return None
            
            content = results["documents"][0]
            metadata = results["metadatas"][0]
            
            return MemoryEntry.from_dict({
                "id": memory_id,
                "content": content,
                "metadata": metadata,
                "memory_type": metadata.get("type", "conversation")
            })
            
        except Exception as e:
            self.logger.error(f"获取记忆失败: {str(e)}")
            return None
    
    def delete_memory(self, memory_id: str) -> bool:
        """
        删除记忆
        
        Args:
            memory_id: 记忆ID
            
        Returns:
            是否删除成功
        """
        try:
            self.collection.delete(ids=[memory_id])
            self.logger.info(f"删除记忆成功，ID: {memory_id}")
            return True
        except Exception as e:
            self.logger.error(f"删除记忆失败: {str(e)}")
            return False
    
    def update_memory(self, memory_id: str, new_content: str = None, 
                     new_metadata: Dict = None) -> bool:
        """
        更新记忆
        
        Args:
            memory_id: 记忆ID
            new_content: 新的记忆内容
            new_metadata: 新的元数据
            
        Returns:
            是否更新成功
        """
        try:
            # 获取现有记忆
            existing = self.get_memory(memory_id)
            if not existing:
                return False
            
            # 更新内容
            if new_content is not None:
                existing.content = new_content
                # 重新计算嵌入
                new_embedding = self.embedding_service.embed(new_content)
                existing.embedding = new_embedding
            else:
                new_content = existing.content
            
            # 更新元数据
            if new_metadata is not None:
                existing.metadata.update(new_metadata)
            existing.metadata["updated_at"] = datetime.now().isoformat()
            
            # 更新Chroma中的记录
            self.collection.update(
                ids=[memory_id],
                embeddings=[existing.embedding] if existing.embedding else None,
                documents=[new_content],
                metadatas=[existing.metadata]
            )
            
            self.logger.info(f"更新记忆成功，ID: {memory_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"更新记忆失败: {str(e)}")
            return False
    
    def get_all_memories(self, limit: int = 1000) -> List[MemoryEntry]:
        """
        获取所有记忆（按时间倒序）
        
        Args:
            limit: 限制返回数量
            
        Returns:
            记忆条目列表
        """
        try:
            results = self.collection.get(
                limit=limit,
                include=["documents", "metadatas"]
            )
            
            memories = []
            for i, memory_id in enumerate(results["ids"]):
                memory_entry = MemoryEntry.from_dict({
                    "id": memory_id,
                    "content": results["documents"][i],
                    "metadata": results["metadatas"][i],
                    "memory_type": results["metadatas"][i].get("type", "conversation")
                })
                memories.append(memory_entry)
            
            # 按创建时间排序（最新的在前）
            memories.sort(key=lambda x: x.metadata.get("created_at", ""), reverse=True)
            
            return memories
            
        except Exception as e:
            self.logger.error(f"获取所有记忆失败: {str(e)}")
            return []
    
    def cleanup_old_memories(self, days_threshold: int = 365) -> int:
        """
        清理旧记忆
        
        Args:
            days_threshold: 天数阈值，超过此天数的记忆将被清理
            
        Returns:
            清理的记忆数量
        """
        try:
            all_memories = self.get_all_memories()
            threshold_date = datetime.now() - timedelta(days=days_threshold)
            
            memories_to_delete = []
            for memory in all_memories:
                created_at_str = memory.metadata.get("created_at")
                if not created_at_str:
                    continue
                
                try:
                    created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    if created_at < threshold_date:
                        memories_to_delete.append(memory.id)
                except ValueError:
                    continue
            
            # 删除旧记忆
            if memories_to_delete:
                self.collection.delete(ids=memories_to_delete)
                self.logger.info(f"清理 {len(memories_to_delete)} 条旧记忆（超过 {days_threshold} 天）")
                return len(memories_to_delete)
            
            return 0
            
        except Exception as e:
            self.logger.error(f"清理旧记忆失败: {str(e)}")
            return 0
    
    def export_memories(self, filepath: str) -> bool:
        """
        导出记忆数据到JSON文件
        
        Args:
            filepath: 导出文件路径
            
        Returns:
            是否导出成功
        """
        try:
            memories = self.get_all_memories()
            data = [memory.to_dict() for memory in memories]
            
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            self.logger.info(f"导出 {len(data)} 条记忆到 {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"导出记忆失败: {str(e)}")
            return False
    
    def import_memories(self, filepath: str) -> bool:
        """
        从JSON文件导入记忆数据
        
        Args:
            filepath: 导入文件路径
            
        Returns:
            是否导入成功
        """
        try:
            if not os.path.exists(filepath):
                self.logger.error(f"导入文件不存在: {filepath}")
                return False
            
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            imported_count = 0
            for item in data:
                try:
                    # 检查是否已存在
                    memory_id = item.get("id")
                    if memory_id and self.get_memory(memory_id):
                        continue
                    
                    # 添加记忆
                    content = item.get("content", "")
                    metadata = item.get("metadata", {})
                    
                    if content:
                        self.add_memory(content, metadata)
                        imported_count += 1
                        
                except Exception as e:
                    self.logger.warning(f"导入单条记忆失败: {str(e)}")
                    continue
            
            self.logger.info(f"从 {filepath} 导入 {imported_count} 条记忆")
            return imported_count > 0
            
        except Exception as e:
            self.logger.error(f"导入记忆失败: {str(e)}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取记忆统计信息
        
        Returns:
            统计信息字典
        """
        try:
            all_memories = self.get_all_memories()
            
            # 按类型统计
            type_counts = {}
            for memory in all_memories:
                memory_type = memory.memory_type.value
                type_counts[memory_type] = type_counts.get(memory_type, 0) + 1
            
            # 计算平均重要性
            total_importance = sum(m.importance for m in all_memories)
            avg_importance = total_importance / len(all_memories) if all_memories else 0
            
            return {
                "total_memories": len(all_memories),
                "type_counts": type_counts,
                "average_importance": round(avg_importance, 3),
                "database_path": self.chroma_persist_directory,
                "similarity_threshold": self.similarity_threshold
            }
            
        except Exception as e:
            self.logger.error(f"获取统计信息失败: {str(e)}")
            return {"error": str(e)}
    
    def reset_memory(self) -> bool:
        """
        重置所有记忆（清空数据库）
        
        Returns:
            是否重置成功
        """
        try:
            self.collection.delete(where={})  # 删除所有记录
            self.logger.warning("已重置所有记忆")
            return True
        except Exception as e:
            self.logger.error(f"重置记忆失败: {str(e)}")
            return False


def test_memory_store():
    """测试记忆存储功能"""
    print("🧪 测试记忆存储模块...")
    
    try:
        # 创建测试目录
        test_dir = "./data/test_memory"
        os.makedirs(test_dir, exist_ok=True)
        
        # 创建记忆存储实例
        store = MemoryStore(
            chroma_persist_directory=test_dir,
            similarity_threshold=0.5,
            max_memories_per_query=3
        )
        
        print("✅ 记忆存储初始化成功")
        
        # 测试添加记忆
        memory_id1 = store.add_memory(
            content="我喜欢喝咖啡，不喜欢喝茶",
            metadata={"type": "preference", "user": "test_user", "importance": 0.8}
        )
        print(f"✅ 添加记忆1成功，ID: {memory_id1}")
        
        memory_id2 = store.add_memory(
            content="明天下午3点有会议",
            metadata={"type": "event", "importance": 0.9}
        )
        print(f"✅ 添加记忆2成功，ID: {memory_id2}")
        
        # 测试搜索记忆
        results = store.search_memories("咖啡", n_results=2)
        print(f"✅ 搜索'咖啡'找到 {len(results)} 条相关记忆")
        for memory, similarity in results:
            print(f"  - 相似度: {similarity:.3f}, 内容: {memory.content[:50]}...")
        
        # 测试获取记忆
        memory = store.get_memory(memory_id1)
        if memory:
            print(f"✅ 获取记忆成功，内容: {memory.content[:50]}...")
        
        # 测试更新记忆
        store.update_memory(memory_id1, new_content="我特别喜欢喝拿铁咖啡")
        updated = store.get_memory(memory_id1)
        print(f"✅ 更新记忆成功，新内容: {updated.content}")
        
        # 测试统计信息
        stats = store.get_stats()
        print(f"✅ 统计信息: {stats}")
        
        # 测试清理功能（这里不会真正清理，只是演示）
        cleaned = store.cleanup_old_memories(days_threshold=1)
        print(f"✅ 清理测试完成，清理了 {cleaned} 条旧记忆")
        
        # 测试导出导入
        export_file = "./data/test_export.json"
        if store.export_memories(export_file):
            print(f"✅ 导出记忆成功: {export_file}")
        
        # 测试重置
        store.reset_memory()
        stats_after = store.get_stats()
        print(f"✅ 重置记忆成功，剩余记忆: {stats_after.get('total_memories', 0)}")
        
        print("🎉 记忆存储测试完成")
        return True
        
    except Exception as e:
        print(f"❌ 记忆存储测试失败: {str(e)}")
        return False


if __name__ == "__main__":
    test_memory_store()


__all__ = [
    'MemoryStore',
    'test_memory_store',
]