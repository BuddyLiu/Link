"""
图记忆索引 — 记忆关系的图结构 + 扩散激活引擎

基于图中节点之间的边实现"锚点→扩散→激活"的记忆检索。
配合 SimpleMemoryStore 使用：向量搜索找到锚点 → 图扩散激活邻居 → 返回综合结果。
"""

import json
import os
import time
from typing import List, Dict, Any, Optional, Tuple


class GraphIndex:
    """图记忆索引

    以邻接表形式存储记忆实体之间的关系边，
    并提供扩散激活（Spreading Activation）检索能力。
    """

    def __init__(self, persist_directory: str = "./data/memory/json"):
        """
        初始化图索引

        Args:
            persist_directory: 持久化目录（与 SimpleMemoryStore 共用）
        """
        self.persist_directory = persist_directory
        # 邻接表: source_id → [Edge, ...]
        self._edges: Dict[str, List[dict]] = {}
        self._load()

    # ─── 边的基础操作 ─────────────────────────────────

    def add_edge(self, source_id: str, target_id: str,
                 relation: str = "相关", weight: float = 0.5):
        """
        在两条记忆之间添加双向边（无向图）。

        Args:
            source_id: 源记忆 ID
            target_id: 目标记忆 ID
            relation: 关系类型（"语义相似", "相同会话", "共同激活", "时间相邻"）
            weight: 连接强度 0.0-1.0
        """
        if source_id == target_id:
            return
        if self._has_edge(source_id, target_id):
            return  # 已存在，不重复添加

        edge = {
            "target": target_id,
            "relation": relation,
            "weight": min(1.0, max(0.0, weight)),
            "created_at": time.time(),
            "last_activated": 0.0,
            "co_count": 0,
        }
        reverse = {
            "target": source_id,
            "relation": relation,
            "weight": min(1.0, max(0.0, weight)),
            "created_at": time.time(),
            "last_activated": 0.0,
            "co_count": 0,
        }

        self._edges.setdefault(source_id, []).append(edge)
        self._edges.setdefault(target_id, []).append(reverse)

        # 写盘持久化
        self._save()

    def reset(self):
        """清空所有边"""
        self._edges = {}
        self._save()

    def remove_node(self, node_id: str):
        """删除一个节点及其所有边"""
        self._edges.pop(node_id, None)
        for src, edges in list(self._edges.items()):
            self._edges[src] = [e for e in edges if e["target"] != node_id]
            if not self._edges[src]:
                del self._edges[src]

    def _has_edge(self, src: str, tgt: str) -> bool:
        """检查两个节点之间是否已有边"""
        for e in self._edges.get(src, []):
            if e["target"] == tgt:
                return True
        return False

    def get_neighbors(self, node_id: str) -> List[dict]:
        """获取节点邻居列表"""
        return self._edges.get(node_id, [])

    def get_edge_count(self) -> int:
        """获取总边数（双向边算一条）"""
        # 每条边存了双向，所以 /2
        total = sum(len(edges) for edges in self._edges.values())
        return total // 2

    # ─── 扩散激活 ─────────────────────────────────────

    def activate(self, seeds: List[Tuple[str, float]],
                 max_depth: int = 2,
                 activation_threshold: float = 0.2,
                 decay: float = 0.7) -> List[Tuple[str, float]]:
        """
        从种子节点开始扩散激活。

        Args:
            seeds: 种子节点列表，每项为 (node_id, 初始激活值)
            max_depth: 扩散最大深度
            activation_threshold: 激活值低于此阈值停止传播
            decay: 每跳衰减系数（0.0=不扩散, 1.0=不减）

        Returns:
            所有被激活节点列表，按激活值降序，每项为 (node_id, activation)
        """
        activated: Dict[str, float] = {}
        # BFS 队列: (node_id, current_activation, depth)
        queue: List[Tuple[str, float, int]] = []

        # 初始化种子
        for node_id, score in seeds:
            if score >= activation_threshold:
                # 如果多个种子激活同一个节点，取最大值
                existing = activated.get(node_id, 0.0)
                activated[node_id] = max(existing, score)
                queue.append((node_id, score, 0))

        # BFS 扩散
        while queue:
            node_id, score, depth = queue.pop(0)

            if depth >= max_depth:
                continue

            for edge in self.get_neighbors(node_id):
                neighbor = edge["target"]
                # 激活值 = 当前值 × 边权重 × 衰减系数
                propagated = score * edge["weight"] * decay

                if propagated >= activation_threshold:
                    existing = activated.get(neighbor, 0.0)
                    if propagated > existing:
                        activated[neighbor] = propagated
                        queue.append((neighbor, propagated, depth + 1))

        # 按激活值降序排列
        return sorted(activated.items(), key=lambda x: x[1], reverse=True)

    # ─── 共同激活强化 ──────────────────────────────────

    def record_co_activation(self, node_ids: List[str]):
        """
        记录一批节点同时被激活。增加它们之间的边权重。

        当某条路径被频繁共同激活，权重会逐渐增加（类似 Hebbian 学习）。
        """
        if len(node_ids) < 2:
            return

        changed = False
        for i in range(len(node_ids)):
            for j in range(i + 1, len(node_ids)):
                src, tgt = node_ids[i], node_ids[j]
                found = False
                for e in self._edges.get(src, []):
                    if e["target"] == tgt:
                        # 现有边加强
                        e["co_count"] = e.get("co_count", 0) + 1
                        e["weight"] = min(0.9, e["weight"] + 0.1)
                        e["last_activated"] = time.time()
                        # 同步反向边
                        for re in self._edges.get(tgt, []):
                            if re["target"] == src:
                                re["co_count"] = e["co_count"]
                                re["weight"] = e["weight"]
                                re["last_activated"] = e["last_activated"]
                        found = True
                        changed = True
                        break
                if not found:
                    # 建一条弱边
                    self.add_edge(src, tgt, "共同激活", 0.15)
                    changed = True

        if changed:
            self._save()

    # ─── 持久化 ────────────────────────────────────────

    def _edge_path(self) -> str:
        return os.path.join(self.persist_directory, "graph_edges.json")

    def _save(self):
        """保存边数据到磁盘"""
        path = self._edge_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self._edges, f, indent=2, ensure_ascii=False)
        except IOError as e:
            print(f"⚠️ 图索引保存失败: {e}")

    def _load(self):
        """从磁盘加载边数据"""
        path = self._edge_path()
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    self._edges = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._edges = {}

    def get_stats(self) -> dict:
        """获取图索引统计"""
        node_count = len(self._edges)
        edge_count = self.get_edge_count()

        # 统计关系类型分布
        relation_counts = {}
        for edges in self._edges.values():
            for e in edges:
                r = e.get("relation", "未知")
                relation_counts[r] = relation_counts.get(r, 0) + 1

        return {
            "nodes": node_count,
            "edges": edge_count,
            "relation_counts": {k: v // 2 for k, v in relation_counts.items()},
        }


def test_graph_index():
    """测试图索引"""
    import tempfile
    import shutil

    test_dir = tempfile.mkdtemp(prefix="jarvis_graph_test_")
    try:
        g = GraphIndex(persist_directory=test_dir)
        print("✅ GraphIndex 初始化成功")

        # 建边
        g.add_edge("mem_001", "mem_002", "语义相似", 0.85)
        g.add_edge("mem_001", "mem_003", "相同会话", 0.9)
        g.add_edge("mem_002", "mem_004", "时间相邻", 0.4)
        g.add_edge("mem_003", "mem_005", "相关", 0.6)
        print(f"✅ 添加 4 条边（实际存 8 条定向），总数: {g.get_edge_count()}")

        # 激活扩散
        seeds = [("mem_001", 0.85)]
        results = g.activate(seeds, max_depth=2, activation_threshold=0.2)
        print(f"✅ 扩散激活结果 ({len(results)} 个节点):")
        for nid, act in results:
            print(f"   {nid}: {act:.3f}")

        # 共同激活
        g.record_co_activation(["mem_001", "mem_005"])
        after = g.get_edge_count()
        print(f"✅ 共同激活后总边数: {after}")

        # 持久化
        g2 = GraphIndex(persist_directory=test_dir)
        print(f"✅ 持久化验证: {g2.get_edge_count()} 条边，{len(g2._edges)} 个节点")

        print("🎉 图索引测试通过")
        return True
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


if __name__ == "__main__":
    test_graph_index()
