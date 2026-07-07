"""
轻量级记忆存储模块
基于JSON文件持久化 + numpy向量相似度搜索，不依赖ChromaDB
兼容Python 3.14+
"""

import json
import os
import uuid
import time
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from .memory_entry import MemoryEntry, MemoryType
from .embedding_service import EmbeddingService
from ..utils.logger import logger


class SimpleMemoryStore:
    """轻量级记忆存储类
    使用JSON文件持久化 + numpy向量相似度搜索
    无需ChromaDB，兼容Python 3.14+
    """

    def __init__(self,
                 persist_directory: str = "./data/memory/json",
                 embedding_service: Optional[EmbeddingService] = None,
                 similarity_threshold: float = 0.7,
                 max_memories_per_query: int = 5):
        """
        初始化记忆存储

        Args:
            persist_directory: JSON持久化目录
            embedding_service: 嵌入服务实例
            similarity_threshold: 相似度阈值
            max_memories_per_query: 每次查询最大记忆数量
        """
        self.persist_directory = persist_directory
        self.similarity_threshold = similarity_threshold
        self.max_memories_per_query = max_memories_per_query

        # 设置日志
        self.logger = logger.getChild("simple_memory")

        # 创建嵌入服务（默认使用 Ollama + bge-m3）
        if embedding_service is None:
            self.embedding_service = EmbeddingService(
                model_name="bge-m3",
                backend="ollama",
                ollama_base_url="http://localhost:11434"
            )
        else:
            self.embedding_service = embedding_service

        # 内存中的记忆索引
        self._memories: List[Dict[str, Any]] = []
        self._embeddings: Optional[np.ndarray] = None

        # 初始化 - 从磁盘加载
        self._initialize()

    def _initialize(self):
        """初始化存储"""
        os.makedirs(self.persist_directory, exist_ok=True)
        self._load_from_disk()

        # 检查嵌入服务是否就绪
        if self.embedding_service.is_ready():
            # 模型就绪后检查旧嵌入是否需要重建
            # (如果之前的嵌入是用随机fallback生成的，与真实模型不兼容)
            if self._embeddings_need_rebuild():
                self.logger.info("检测到嵌入模型更新，重建向量索引...")
                self._rebuild_embeddings()
        else:
            self.logger.warning("嵌入服务未就绪，记忆搜索功能可能受限")

        self.logger.info(f"SimpleMemoryStore初始化完成，已加载 {len(self._memories)} 条记忆")

    def _embeddings_need_rebuild(self) -> bool:
        """检查是否需要重建嵌入索引"""
        if not self._memories:
            return False
        if self._embeddings is None:
            return True
        # 嵌入模型就绪但旧的嵌入是随机生成的：维度不匹配
        if self._embeddings.shape[1] != self.embedding_service.dimension:
            self.logger.info(f"嵌入维度不匹配 (旧: {self._embeddings.shape[1]}, 新: {self.embedding_service.dimension})")
            return True
        # 嵌入数量与记忆数量不一致
        if len(self._embeddings) != len(self._memories):
            return True
        # 检查第一组嵌入是否像随机哈希生成的（高方差）
        # 真实嵌入通常接近单位范数，随机哈希方差大
        try:
            if len(self._embeddings) > 0:
                norms = np.linalg.norm(self._embeddings, axis=1)
                # 随机哈希产生的嵌入通常范数在 ~sqrt(384) ≈ 19.6 附近
                # 真实嵌入通常范数更小且更一致
                if np.mean(norms) > 10.0:
                    self.logger.info("检测到旧嵌入为随机fallback，重建索引")
                    return True
        except Exception:
            pass
        return False

    def _memory_file_path(self) -> str:
        """获取记忆数据文件路径"""
        return os.path.join(self.persist_directory, "memories.json")

    def _embeddings_file_path(self) -> str:
        """获取嵌入向量文件路径"""
        return os.path.join(self.persist_directory, "embeddings.npy")

    def _load_from_disk(self):
        """从磁盘加载记忆和嵌入向量"""
        mem_file = self._memory_file_path()
        emb_file = self._embeddings_file_path()

        # 加载记忆数据
        if os.path.exists(mem_file):
            try:
                with open(mem_file, 'r', encoding='utf-8') as f:
                    self._memories = json.load(f)
                self.logger.debug(f"从磁盘加载 {len(self._memories)} 条记忆")
            except (json.JSONDecodeError, IOError) as e:
                self.logger.error(f"加载记忆文件失败: {e}")
                self._memories = []
        else:
            self._memories = []

        # 加载嵌入向量
        if os.path.exists(emb_file):
            try:
                self._embeddings = np.load(emb_file)
                self.logger.debug(f"加载嵌入向量: {self._embeddings.shape}")
            except (IOError, ValueError) as e:
                self.logger.error(f"加载嵌入向量失败: {e}")
                self._embeddings = None
        else:
            self._embeddings = None

        # 如果不一致，重新计算
        if self._embeddings is not None and len(self._embeddings) != len(self._memories):
            self.logger.warning("记忆数与嵌入向量数不匹配，重建嵌入索引")
            self._rebuild_embeddings()

    def _save_to_disk(self):
        """保存记忆和嵌入向量到磁盘"""
        mem_file = self._memory_file_path()
        emb_file = self._embeddings_file_path()

        # 确保目录存在
        os.makedirs(self.persist_directory, exist_ok=True)

        # 保存记忆数据
        try:
            with open(mem_file, 'w', encoding='utf-8') as f:
                json.dump(self._memories, f, indent=2, ensure_ascii=False)
        except IOError as e:
            self.logger.error(f"保存记忆文件失败: {e}")

        # 保存嵌入向量
        if self._embeddings is not None:
            try:
                np.save(emb_file, self._embeddings)
            except IOError as e:
                self.logger.error(f"保存嵌入向量失败: {e}")

    def _rebuild_embeddings(self):
        """重建所有记忆的嵌入向量"""
        if not self._memories:
            self._embeddings = None
            return

        if not self.embedding_service.is_ready():
            self.logger.error("无法重建嵌入：嵌入服务未就绪")
            self._embeddings = None
            return

        try:
            texts = [m.get("content", "") for m in self._memories]
            embeddings = self.embedding_service.embed_batch(texts)
            self._embeddings = np.array(embeddings, dtype=np.float32)
            self._save_to_disk()
            self.logger.info(f"重建完成: {len(texts)} 条嵌入")
        except Exception as e:
            self.logger.error(f"重建嵌入失败: {e}")
            self._embeddings = None

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

        # 生成唯一ID
        memory_id = str(uuid.uuid4())

        # 处理元数据
        metadata = metadata or {}
        metadata["id"] = memory_id
        metadata["created_at"] = datetime.now().isoformat()

        # 如果未指定类型，默认为对话
        if "type" not in metadata:
            metadata["type"] = "conversation"

        # 更新时间字段
        metadata["updated_at"] = metadata["created_at"]

        # 创建记忆记录（importance 同时存顶层和 metadata 内，便于搜索和显示）
        imp = metadata.get("importance", 0.5)
        memory_record = {
            "id": memory_id,
            "content": content,
            "metadata": metadata,
            "memory_type": metadata.get("type", "conversation"),
            "importance": imp,
        }

        # 计算嵌入向量
        embedding = None
        try:
            if self.embedding_service.is_ready():
                embedding = self.embedding_service.embed(content)
            else:
                self.logger.warning("嵌入服务未就绪，跳过向量化")
        except Exception as e:
            self.logger.error(f"计算嵌入向量失败: {e}")

        # 添加到内存索引
        self._memories.append(memory_record)
        if embedding is not None:
            if self._embeddings is not None:
                self._embeddings = np.vstack([self._embeddings, np.array(embedding, dtype=np.float32)])
            else:
                self._embeddings = np.array([embedding], dtype=np.float32)

        # 持久化到磁盘
        self._save_to_disk()

        self.logger.info(f"添加记忆成功，ID: {memory_id}, 类型: {metadata.get('type', 'unknown')}")
        return memory_id

    def search_memories(self, query: str, n_results: int = None) -> List[Tuple[Any, float]]:
        """
        搜索相关记忆

        Args:
            query: 查询文本
            n_results: 返回结果数量

        Returns:
            (MemoryEntry, similarity) 列表
        """
        if not query or not query.strip():
            return []

        if n_results is None:
            n_results = self.max_memories_per_query

        if not self._memories:
            return []

        # 先用关键词搜索召回（对短查询/专有名词高效）
        keyword_results = {}
        query_lower = query.lower()
        query_tokens = set(query_lower.split())

        # 对中文查询，提取所有长度 >= 2 的连续字符片段
        chinese_ngrams = set()
        for c in query_lower:
            if '一' <= c <= '鿿' or '　' <= c <= '〿' or '＀' <= c <= '￯':
                chinese_ngrams.add(c)
        # 生成连续 2-4 字片段
        query_chars = [c for c in query_lower if '一' <= c <= '鿿']
        chinese_bigrams = set()
        for i in range(len(query_chars) - 1):
            chinese_bigrams.add(''.join(query_chars[i:i+2]))
            if i < len(query_chars) - 2:
                chinese_bigrams.add(''.join(query_chars[i:i+3]))

        for i, memory_record in enumerate(self._memories):
            content = memory_record.get("content", "").lower()
            metadata = memory_record.get("metadata", {})
            metadata_str = json.dumps(metadata, ensure_ascii=False).lower()

            keyword_score = 0.0
            # 精确子串匹配（含中文）
            if query_lower in content:
                keyword_score = 0.85
            elif query_lower in metadata_str:
                keyword_score = 0.5
            # 英文分词匹配
            if keyword_score < 0.5 and len(query_tokens) <= 3:
                matched = sum(1 for token in query_tokens if len(token) > 1 and token in content)
                if matched > 0:
                    keyword_score = 0.5 + (matched / len(query_tokens)) * 0.3
            # 中文二元组匹配（适用于"叫什么名字"匹配"我叫张三"）
            if keyword_score < 0.5 and len(chinese_bigrams) > 0:
                matched_bigrams = sum(1 for bg in chinese_bigrams if bg in content)
                if matched_bigrams > 0:
                    ratio = matched_bigrams / len(chinese_bigrams)
                    keyword_score = max(keyword_score, 0.3 + ratio * 0.4)

            if keyword_score >= min(0.5, self.similarity_threshold):
                keyword_results[i] = keyword_score

        # 再用向量搜索（对语义相似高效）
        vector_results = []
        if self.embedding_service.is_ready() and self._embeddings is not None:
            try:
                query_embedding = self.embedding_service.embed(query)
                query_vec = np.array(query_embedding, dtype=np.float32)

                norms = np.linalg.norm(self._embeddings, axis=1)
                query_norm = np.linalg.norm(query_vec)

                if query_norm > 0 and np.all(norms > 0):
                    similarities = np.dot(self._embeddings, query_vec) / (norms * query_norm)
                    indices = np.argsort(similarities)[::-1]

                    for idx in indices:
                        sim = float(similarities[idx])
                        if sim >= self.similarity_threshold:
                            vector_results.append((idx, sim))
            except Exception as e:
                self.logger.debug(f"向量搜索失败: {e}")

        # 合并结果（关键词优先，向量补充，降低向量假阳性）
        seen_indices = set()
        merged = []

        # 先加关键词结果（高精确度）
        for idx, score in sorted(keyword_results.items(), key=lambda x: x[1], reverse=True):
            if idx not in seen_indices:
                seen_indices.add(idx)
                merged.append((idx, score))

        # 再加向量结果（补充未覆盖的，但要求更高相似度以降低假阳性）
        keyword_found = bool(keyword_results)
        for idx, sim in vector_results:
            if idx not in seen_indices:
                # 已有关键词命中时，向量补充需更高阈值
                effective_min_sim = 0.75 if keyword_found else self.similarity_threshold
                if sim >= effective_min_sim:
                    seen_indices.add(idx)
                    merged.append((idx, sim))

        # 转换为 MemoryEntry
        results = []
        for idx, score in merged[:n_results]:
            memory_record = self._memories[idx]
            memory_entry = MemoryEntry.from_dict(memory_record)
            results.append((memory_entry, score))

        self.logger.info(f"混合搜索完成，查询: '{query[:30]}...'，找到 {len(results)} 条记忆")
        return results

    def get_memory(self, memory_id: str) -> Optional[Any]:
        """根据ID获取记忆"""
        for memory_record in self._memories:
            if memory_record.get("id") == memory_id:
                return MemoryEntry.from_dict(memory_record)
        return None

    def delete_memory(self, memory_id: str) -> bool:
        """删除记忆"""
        for i, memory_record in enumerate(self._memories):
            if memory_record.get("id") == memory_id:
                self._memories.pop(i)
                if self._embeddings is not None:
                    self._embeddings = np.delete(self._embeddings, i, axis=0)
                self._save_to_disk()
                self.logger.info(f"删除记忆成功，ID: {memory_id}")
                return True
        return False

    def update_memory(self, memory_id: str, new_content: str = None,
                      new_metadata: Dict = None) -> bool:
        """更新记忆"""
        for i, memory_record in enumerate(self._memories):
            if memory_record.get("id") == memory_id:
                if new_content is not None:
                    memory_record["content"] = new_content
                    # 重新计算嵌入
                    try:
                        if self.embedding_service.is_ready():
                            new_embedding = self.embedding_service.embed(new_content)
                            if self._embeddings is not None:
                                self._embeddings[i] = np.array(new_embedding, dtype=np.float32)
                    except Exception as e:
                        self.logger.error(f"更新嵌入失败: {e}")

                if new_metadata is not None:
                    memory_record["metadata"].update(new_metadata)

                memory_record["metadata"]["updated_at"] = datetime.now().isoformat()
                self._save_to_disk()
                self.logger.info(f"更新记忆成功，ID: {memory_id}")
                return True
        return False

    def get_all_memories(self, limit: int = 1000) -> List[Any]:
        """获取所有记忆（按时间倒序）"""
        memories = [MemoryEntry.from_dict(m) for m in self._memories]
        memories.sort(key=lambda x: x.metadata.get("created_at", ""), reverse=True)
        return memories[:limit]

    def cleanup_old_memories(self, days_threshold: int = 365) -> int:
        """清理旧记忆"""
        threshold_date = datetime.now() - timedelta(days=days_threshold)
        before_count = len(self._memories)

        self._memories = [
            m for m in self._memories
            if not self._is_older_than(m, threshold_date)
        ]

        cleaned = before_count - len(self._memories)
        if cleaned > 0:
            self._rebuild_embeddings()
            self._save_to_disk()

        self.logger.info(f"清理 {cleaned} 条旧记忆（超过 {days_threshold} 天）")
        return cleaned

    def _is_older_than(self, memory_record: Dict, threshold_date: datetime) -> bool:
        """检查记忆是否早于阈值"""
        created_at_str = memory_record.get("metadata", {}).get("created_at")
        if not created_at_str:
            return False
        try:
            created_at = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            return created_at < threshold_date
        except (ValueError, AttributeError):
            return False

    def export_memories(self, filepath: str) -> bool:
        """导出记忆到JSON"""
        try:
            data = []
            for m in self._memories:
                entry = MemoryEntry.from_dict(m)
                data.append(entry.to_dict())

            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            self.logger.info(f"导出 {len(data)} 条记忆到 {filepath}")
            return True
        except Exception as e:
            self.logger.error(f"导出失败: {e}")
            return False

    def import_memories(self, filepath: str) -> bool:
        """从JSON导入记忆"""
        if not os.path.exists(filepath):
            self.logger.error(f"导入文件不存在: {filepath}")
            return False

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)

            imported = 0
            for item in data:
                content = item.get("content", "")
                metadata = item.get("metadata", {})
                if content:
                    # 去重检查
                    existing_ids = {m.get("id") for m in self._memories}
                    if metadata.get("id") not in existing_ids:
                        self._memories.append({
                            "id": metadata.get("id", str(uuid.uuid4())),
                            "content": content,
                            "metadata": metadata,
                        })
                        imported += 1

            if imported > 0:
                self._rebuild_embeddings()
                self._save_to_disk()

            self.logger.info(f"从 {filepath} 导入 {imported} 条记忆")
            return imported > 0
        except Exception as e:
            self.logger.error(f"导入失败: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """获取记忆统计信息"""
        type_counts = {}
        for m in self._memories:
            mem_type = m.get("metadata", {}).get("type", "unknown")
            type_counts[mem_type] = type_counts.get(mem_type, 0) + 1

        return {
            "total_memories": len(self._memories),
            "type_counts": type_counts,
            "database_path": self.persist_directory,
            "similarity_threshold": self.similarity_threshold,
            "embeddings_loaded": self._embeddings is not None,
        }

    def reset_memory(self) -> bool:
        """重置所有记忆"""
        self._memories = []
        self._embeddings = None
        self._save_to_disk()
        self.logger.warning("已重置所有记忆")
        return True

    def is_available(self) -> bool:
        """检查存储是否可用"""
        return True  # 轻量级实现始终可用


def test_simple_memory_store():
    """测试简单记忆存储"""
    print("🧪 测试 SimpleMemoryStore...")

    import tempfile
    import shutil

    test_dir = tempfile.mkdtemp(prefix="jarvis_memory_test_")

    try:
        store = SimpleMemoryStore(
            persist_directory=test_dir,
            similarity_threshold=0.1,  # 低阈值便于测试
            max_memories_per_query=5
        )
        print("✅ SimpleMemoryStore 初始化成功")

        # 测试添加记忆
        mid1 = store.add_memory("我喜欢喝咖啡，不喜欢喝茶",
                                {"type": "preference", "user": "test_user", "importance": 0.8})
        print(f"✅ 添加记忆1成功: {mid1[:8]}...")

        mid2 = store.add_memory("明天下午3点有会议",
                                {"type": "event", "importance": 0.9})
        print(f"✅ 添加记忆2成功: {mid2[:8]}...")

        # 测试搜索
        results = store.search_memories("咖啡", n_results=5)
        print(f"✅ 搜索'咖啡'找到 {len(results)} 条记忆")
        for mem, sim in results:
            print(f"   sim={sim:.3f}: {mem.content[:40]}")

        # 测试获取
        mem = store.get_memory(mid1)
        print(f"✅ 获取记忆: {mem.content[:30] if mem else 'NOT FOUND'}")

        # 测试更新
        store.update_memory(mid1, new_content="我特别喜欢喝拿铁咖啡")
        updated = store.get_memory(mid1)
        print(f"✅ 更新后: {updated.content}")

        # 测试统计
        stats = store.get_stats()
        print(f"✅ 统计: {stats}")

        # 测试导出导入
        export_path = os.path.join(test_dir, "export.json")
        store.export_memories(export_path)
        print(f"✅ 导出到 {export_path}")

        # 测试重置
        store.reset_memory()
        stats2 = store.get_stats()
        print(f"✅ 重置后记忆数: {stats2['total_memories']}")

        # 测试持久化（新建一个实例读取）
        import time
        store1 = SimpleMemoryStore(persist_directory=test_dir)
        store1.add_memory("持久化测试", {"type": "test"})

        store2 = SimpleMemoryStore(persist_directory=test_dir)
        print(f"✅ 持久化测试: 新实例读取到 {store2.get_stats()['total_memories']} 条记忆")

        print("🎉 所有测试通过!")
        return True

    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    test_simple_memory_store()
