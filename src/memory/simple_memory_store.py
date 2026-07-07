"""
轻量级记忆存储模块
基于JSON文件持久化 + numpy向量相似度搜索，不依赖ChromaDB
兼容Python 3.14+
"""

import json
import os
import uuid
import time
import io
import re
import base64
import hashlib
import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta

from .memory_entry import MemoryEntry, MemoryType
from .embedding_service import EmbeddingService
from .graph_index import GraphIndex
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

        # 图记忆索引（记忆关联关系）
        self.graph_index = GraphIndex(persist_directory=persist_directory)

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

        # ─── 图记忆：为新增记忆建立关联边 ───
        if self.graph_index and embedding is not None and len(self._memories) > 1:
            self._build_graph_edges(memory_id, content)

        self.logger.info(f"添加记忆成功，ID: {memory_id}, 类型: {metadata.get('type', 'unknown')}")
        return memory_id

    def _build_graph_edges(self, memory_id: str, content: str):
        """为新记忆自动建立三种关联边"""
        try:
            # 1. 时间相邻边 → 上一条添加的记忆
            if len(self._memories) >= 2:
                prev_id = self._memories[-2]["id"]
                if prev_id != memory_id:
                    self.graph_index.add_edge(memory_id, prev_id, "时间相邻", 0.4)

            # 2. 语义相似边 → embedding 最相似的前 3 条
            new_emb = self._embeddings[-1]
            old_embs = self._embeddings[:-1]
            old_norms = np.linalg.norm(old_embs, axis=1)
            new_norm = np.linalg.norm(new_emb)
            if new_norm > 0 and np.any(old_norms > 0):
                sims = np.dot(old_embs, new_emb) / (old_norms * new_norm + 1e-8)
                top_k = min(3, len(sims))
                top_indices = np.argsort(sims)[-top_k:][::-1]
                for idx in top_indices:
                    sim_score = float(sims[idx])
                    if sim_score > 0.75:
                        target_id = self._memories[idx]["id"]
                        if target_id != memory_id:
                            self.graph_index.add_edge(memory_id, target_id,
                                                      "语义相似", round(sim_score, 2))

            # 3. 相同会话边 → 同一轮提取的 fact 之间已在 ProcessInput 中由调用方建立
            # （通过 add_edge 独立调用，见 _extract_facts_from_conversation）

        except Exception as e:
            self.logger.info(f"建图边异常（不影响记忆存储）: {e}")

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

        # ─── 图索引扩散激活 ───
        # 取向量/关键词搜索中 top-3 作为种子，沿图扩散到关联记忆
        graph_added = []
        if self.graph_index and merged:
            seed_ids = [(self._memories[idx]["id"], score) for idx, score in merged[:3]]
            graph_results = self.graph_index.activate(
                seed_ids, max_depth=2, activation_threshold=0.2, decay=0.7
            )
            if graph_results:
                existing_ids = {self._memories[idx]["id"] for idx, _ in merged}
                for node_id, activation in graph_results:
                    if node_id not in existing_ids:
                        # 在 _memories 中查找该 ID
                        for idx, mem in enumerate(self._memories):
                            if mem.get("id") == node_id:
                                # 图结果按激活值 × 0.7 折算，不压过直接搜索命中
                                graph_added.append((idx, round(activation * 0.7, 3)))
                                existing_ids.add(node_id)
                                break
                if graph_added:
                    merged.extend(graph_added)
                    # 重新排序（关键词/向量分高在前，图扩散在后）
                    merged.sort(key=lambda x: x[1], reverse=True)

        # 记录共同激活（强化被同时检索到的记忆之间的边）
        if self.graph_index and merged:
            top_co_ids = [self._memories[idx]["id"] for idx, _ in merged[:n_results]]
            self.graph_index.record_co_activation(top_co_ids)

        # 转换为 MemoryEntry
        results = []
        for idx, score in merged[:n_results]:
            memory_record = self._memories[idx]
            memory_entry = MemoryEntry.from_dict(memory_record)
            results.append((memory_entry, score))

        graph_info = f"，图扩散 +{len(graph_added)}" if graph_added else ""
        self.logger.info(f"混合搜索完成，查询: '{query[:30]}'，找到 {len(results)} 条记忆{graph_info}")
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
                # 同步删除图索引中的节点
                if self.graph_index:
                    self.graph_index.remove_node(memory_id)
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

        stats = {
            "total_memories": len(self._memories),
            "type_counts": type_counts,
            "database_path": self.persist_directory,
            "similarity_threshold": self.similarity_threshold,
            "embeddings_loaded": self._embeddings is not None,
        }

        # 图索引统计
        if self.graph_index:
            stats["graph"] = self.graph_index.get_stats()

        return stats

    def reset_memory(self) -> bool:
        """重置所有记忆"""
        self._memories = []
        self._embeddings = None
        if self.graph_index:
            self.graph_index.reset()
        self._save_to_disk()
        self.logger.warning("已重置所有记忆")
        return True

    # ─── 记忆归档（打包/恢复/防篡改） ─────────────────────────

    def _archive_dir(self) -> str:
        """归档文件存储目录"""
        d = os.path.join(self.persist_directory, "archives")
        os.makedirs(d, exist_ok=True)
        return d

    def create_archive(self, label: str = "") -> dict:
        """
        将当前所有记忆打包归档（含校验和，检测篡改）。

        Args:
            label: 可选标签，如 "before_python_test"

        Returns:
            归档信息 dict
        """
        import hashlib
        import base64

        # 序列化记忆数据
        memories_data = []
        for m in self._memories:
            memories_data.append({
                "id": m.get("id"),
                "content": m.get("content"),
                "metadata": m.get("metadata"),
                "memory_type": m.get("memory_type", "conversation"),
                "importance": m.get("importance", 0.5),
            })

        # 序列化 embedding（numpy → base64）
        embeddings_b64 = ""
        if self._embeddings is not None:
            buf = io.BytesIO()
            np.save(buf, self._embeddings)
            embeddings_b64 = base64.b64encode(buf.getvalue()).decode()

        # 图边数据
        graph_data = {}
        if self.graph_index:
            graph_data = self.graph_index._edges

        # 构建数据包
        data_payload = {
            "memories": memories_data,
            "embeddings": embeddings_b64,
            "graph_edges": graph_data,
        }

        # 计算校验和（SHA-256）— 用于防篡改检测
        payload_str = json.dumps(data_payload, ensure_ascii=False, sort_keys=True)
        checksum = hashlib.sha256(payload_str.encode()).hexdigest()

        timestamp = datetime.now()
        ts_str = timestamp.strftime("%Y%m%d_%H%M%S")
        safe_label = re.sub(r'[^a-zA-Z0-9_\-一-鿿]', '_', label)[:40] if label else ""
        archive_id = f"archive_{ts_str}{'_' + safe_label if safe_label else ''}"

        archive = {
            "archive_id": archive_id,
            "created_at": timestamp.isoformat(),
            "label": label or "",
            "memory_count": len(memories_data),
            "checksum": checksum,
            "checksum_algorithm": "sha256",
            "jarvis_version": "3.0",
            "data": data_payload,
        }

        # 写盘
        filepath = os.path.join(self._archive_dir(), f"{archive_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(archive, f, indent=2, ensure_ascii=False)

        self.logger.info(f"记忆归档创建成功: {archive_id} ({len(memories_data)} 条记忆)")
        return {
            "archive_id": archive_id,
            "created_at": archive["created_at"],
            "label": label,
            "memory_count": len(memories_data),
            "checksum": checksum,
            "filepath": filepath,
        }

    def list_archives(self) -> list:
        """
        列出所有可用归档。

        Returns:
            归档信息列表，每项含 archive_id, created_at, label, memory_count, checksum, verified
        """
        import hashlib

        archive_dir = self._archive_dir()
        if not os.path.exists(archive_dir):
            return []

        archives = []
        for fname in sorted(os.listdir(archive_dir), reverse=True):
            if not fname.startswith("archive_") or not fname.endswith(".json"):
                continue
            fpath = os.path.join(archive_dir, fname)
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    archive = json.load(f)

                # 校验检查
                stored_checksum = archive.get("checksum", "")
                data_payload = archive.get("data", {})
                payload_str = json.dumps(data_payload, ensure_ascii=False, sort_keys=True)
                computed = hashlib.sha256(payload_str.encode()).hexdigest()
                verified = computed == stored_checksum

                archives.append({
                    "archive_id": archive.get("archive_id", fname.replace(".json", "")),
                    "created_at": archive.get("created_at", ""),
                    "label": archive.get("label", ""),
                    "memory_count": archive.get("memory_count", 0),
                    "checksum": stored_checksum[:16] + "...",
                    "verified": verified,
                    "filepath": fpath,
                })
            except (json.JSONDecodeError, KeyError, IOError) as e:
                archives.append({
                    "archive_id": fname.replace(".json", ""),
                    "created_at": "",
                    "label": f"⚠️ 读取失败: {e}",
                    "memory_count": 0,
                    "checksum": "",
                    "verified": False,
                    "filepath": fpath,
                })

        return archives

    def restore_archive(self, archive_id: str) -> dict:
        """
        从归档恢复记忆。

        Args:
            archive_id: 归档 ID

        Returns:
            恢复结果 dict

        Raises:
            ValueError: 归档不存在或校验失败
        """
        import hashlib
        import base64

        # 查找归档文件
        archive_dir = self._archive_dir()
        fpath = os.path.join(archive_dir, f"{archive_id}.json")
        if not os.path.exists(fpath):
            # 尝试模糊匹配
            for fname in os.listdir(archive_dir):
                if archive_id in fname and fname.endswith(".json"):
                    fpath = os.path.join(archive_dir, fname)
                    break
            else:
                raise ValueError(f"归档 '{archive_id}' 不存在")

        with open(fpath, 'r', encoding='utf-8') as f:
            archive = json.load(f)

        # 校验完整性
        stored_checksum = archive.get("checksum", "")
        data_payload = archive.get("data", {})
        if not data_payload:
            raise ValueError("归档数据损坏：缺少 data 字段")

        payload_str = json.dumps(data_payload, ensure_ascii=False, sort_keys=True)
        computed = hashlib.sha256(payload_str.encode()).hexdigest()
        if computed != stored_checksum:
            raise ValueError(
                f"归档校验失败！文件可能已被篡改。\n"
                f"  期望: {stored_checksum[:16]}...\n"
                f"  实际: {computed[:16]}..."
            )

        # 恢复记忆数据
        old_count = len(self._memories)
        self._memories = data_payload.get("memories", [])

        # 恢复 embedding
        emb_b64 = data_payload.get("embeddings", "")
        if emb_b64:
            buf = io.BytesIO(base64.b64decode(emb_b64))
            self._embeddings = np.load(buf)
        else:
            self._embeddings = None

        # 恢复图边
        graph_data = data_payload.get("graph_edges", {})
        if self.graph_index:
            self.graph_index._edges = graph_data
            self.graph_index._save()

        # 写盘
        self._save_to_disk()

        new_count = len(self._memories)
        self.logger.info(f"记忆归档恢复完成: {archive_id} ({old_count} → {new_count} 条)")
        return {
            "archive_id": archive_id,
            "previous_count": old_count,
            "restored_count": new_count,
            "verified": True,
        }

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
