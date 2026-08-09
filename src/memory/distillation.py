"""
记忆蒸馏模块

将低价值的原始记忆（对话、碎片偏好）蒸馏为高价值的结构化记忆：
1. 对话摘要：批量对话 → 摘要（含关键事实抽取）
2. 偏好聚合：分散偏好 → 去重合并的用户画像条目
3. 长期压缩：清理过期/低价值记忆，防止记忆库膨胀

不依赖 LLM 时自动降级为规则摘要（关键词 + 长度截断）。
"""

from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import re


class MemoryDistiller:
    """记忆蒸馏器"""

    def __init__(self, memory_engine=None, logger=None):
        self.memory_engine = memory_engine
        self.logger = logger

    # ── 对话摘要蒸馏 ──

    def distill_conversations(self, max_items: int = 50,
                              min_age_days: int = 1,
                              keep_recent: int = 20,
                              summary_prompt: str = None) -> int:
        """将旧的对话记忆蒸馏为摘要。

        策略：
          - 选取超过 min_age_days 天、且不属于最近 keep_recent 条的 conversation 记忆
          - 按时间分批，用 LLM 生成摘要（无 LLM 时用规则摘要）
          - 删除原始对话，保存为一条 INSIGHT 类型摘要记忆

        Args:
            max_items: 每次最多蒸馏多少条
            min_age_days: 只蒸馏超过该天数的对话
            keep_recent: 始终保留最近的 N 条对话（避免删掉近期内容）

        Returns:
            int: 蒸馏生成的摘要条数
        """
        if not self.memory_engine or not self.memory_engine.store:
            return 0
        try:
            store = self.memory_engine.store
            all_mem = store.get_all_memories(limit=2000) or []
            cutoff = datetime.now() - timedelta(days=min_age_days)

            conversations = []
            for m in all_mem:
                if m.metadata.get("type") != "conversation":
                    continue
                ts = m.metadata.get("timestamp", "")
                try:
                    t = datetime.fromisoformat(ts)
                except Exception:
                    t = datetime.now()
                conversations.append((t, m))

            # 按时间倒序：最近的排前面
            conversations.sort(key=lambda x: x[0], reverse=True)
            # 保留最近 keep_recent 条，其余且超龄的才进入候选
            candidates = []
            for idx, (t, m) in enumerate(conversations):
                if idx < keep_recent:
                    continue
                if t < cutoff:
                    candidates.append(m)
            if not candidates:
                return 0

            # 取最旧的 max_items 条（时间正序）
            candidates.sort(key=lambda m: m.metadata.get("timestamp", ""))
            conversations = candidates[:max_items]

            # 拼成文本块供摘要
            raw_text = "\n".join(
                f"[{m.metadata.get('timestamp', '')[:16]}] {m.content[:300]}"
                for m in conversations
            )

            summary = self._generate_summary(raw_text, summary_prompt)
            if not summary:
                return 0

            # 保存摘要记忆
            metadata = {
                "type": "insight",
                "distilled_from": len(conversations),
                "source": "conversation_distill",
                "timestamp": datetime.now().isoformat(),
            }
            store.add_memory(f"对话摘要: {summary}", metadata)

            # 删除原始对话
            for m in conversations:
                try:
                    store.delete_memory(m.id)
                except Exception:
                    pass

            if self.logger:
                self.logger.info(
                    f"记忆蒸馏: {len(conversations)} 条对话 → 1 条摘要")
            return 1
        except Exception as e:
            if self.logger:
                self.logger.error(f"对话蒸馏失败: {e}")
            return 0

    # ── 偏好聚合 ──

    def aggregate_preferences(self) -> int:
        """聚合分散的用户偏好记忆。

        策略：
          - 找出所有 preference/fact 中含"喜欢/偏好/爱好/不爱"等词的内容
          - 去重（相似内容合并），按重要度排序
          - 生成聚合后的偏好画像条目，删除重复的碎片

        Returns:
            int: 合并减少的记忆条数
        """
        if not self.memory_engine or not self.memory_engine.store:
            return 0
        try:
            store = self.memory_engine.store
            all_mem = store.get_all_memories(limit=2000) or []

            pref_entries = []
            for m in all_mem:
                t = str(m.metadata.get("type", ""))
                content = str(m.content or "")
                is_pref = t == "preference" or (
                    t == "fact" and any(k in content for k in
                                        ("偏好", "喜欢", "爱好", "不爱", "讨厌", "热衷于")))
                if is_pref:
                    pref_entries.append(m)

            if len(pref_entries) <= 1:
                return 0

            # 去重：按内容前20字分组
            groups: Dict[str, List] = {}
            for m in pref_entries:
                key = re.sub(r'\s+', '', m.content)[:20]
                groups.setdefault(key, []).append(m)

            # 统计保留数 = 分组数，删除其余
            kept = 0
            removed = 0
            for key, group in groups.items():
                group.sort(key=lambda m: m.metadata.get("importance", 0), reverse=True)
                for extra in group[1:]:
                    try:
                        store.delete_memory(extra.id)
                        removed += 1
                    except Exception:
                        pass
                kept += 1

            if removed and self.logger:
                self.logger.info(f"偏好聚合: 去重 {removed} 条冗余偏好")
            return removed
        except Exception as e:
            if self.logger:
                self.logger.error(f"偏好聚合失败: {e}")
            return 0

    # ── 长期压缩 ──

    def compress_old_memories(self, max_age_days: int = 180) -> int:
        """清理超过 max_age_days 的低价值记忆。

        保留：fact / preference / insight 类型（高价值）
        清理：旧 conversation / 低重要度 feedback

        Returns:
            int: 清理条数
        """
        if not self.memory_engine or not self.memory_engine.store:
            return 0
        try:
            store = self.memory_engine.store
            all_mem = store.get_all_memories(limit=2000) or []
            cutoff = datetime.now() - timedelta(days=max_age_days)

            keep_types = {"fact", "preference", "insight"}
            cleaned = 0
            for m in all_mem:
                t = str(m.metadata.get("type", ""))
                if t in keep_types:
                    continue
                ts = m.metadata.get("timestamp", "")
                try:
                    age = datetime.now() - datetime.fromisoformat(ts)
                except Exception:
                    continue
                if age.days >= max_age_days:
                    try:
                        store.delete_memory(m.id)
                        cleaned += 1
                    except Exception:
                        pass

            if cleaned and self.logger:
                self.logger.info(f"长期压缩: 清理 {cleaned} 条过期记忆")
            return cleaned
        except Exception as e:
            if self.logger:
                self.logger.error(f"长期压缩失败: {e}")
            return 0

    # ── 内部工具 ──

    def _generate_summary(self, raw_text: str, summary_prompt: str = None) -> str:
        """生成摘要（优先 LLM，失败回退规则摘要）"""
        if self.memory_engine and getattr(self, "_brain", None):
            try:
                prompt = summary_prompt or (
                    "把以下对话内容总结为一段简洁的中文摘要（100字内），"
                    "重点保留：用户的重要信息、待办事项、关键事件。\n\n"
                    f"{raw_text[:3000]}"
                )
                result = self._brain.simple_query(
                    prompt,
                    system_prompt="你是记忆整理助手，只输出摘要，不要解释。",
                )
                out = (result or "").strip()
                if out and len(out) > 10 and "查询失败" not in out:
                    return out[:500]
            except Exception:
                pass
        return self._rule_summary(raw_text)

    def _rule_summary(self, raw_text: str) -> str:
        """规则摘要：提取关键行（含用户/待办/事件关键词）"""
        lines = raw_text.split("\n")
        important = []
        keywords = ("用户", "待办", "提醒", "计划", "安排", "需要", "记住",
                    "偏好", "喜欢", "不喜欢", "生日", "会议", "聚会")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            if any(k in line for k in keywords):
                important.append(line[:120])
        if not important:
            # 取前 3 行
            important = [l.strip()[:120] for l in lines if l.strip()][:3]
        return "；".join(important[:8])[:500]

    def set_brain(self, brain):
        """注入大脑引擎（用于 LLM 摘要）"""
        self._brain = brain


def create_memory_distiller(memory_engine=None, brain=None, logger=None):
    """创建记忆蒸馏器"""
    distiller = MemoryDistiller(memory_engine=memory_engine, logger=logger)
    if brain is not None:
        distiller.set_brain(brain)
    return distiller
