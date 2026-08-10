#!/usr/bin/env python3
"""
回归测试：DeepSeek Reasoner 思考过程耗尽 max_tokens 预算导致回复缺失时，
chat_with_tools 应自动重试，返回完整回复。

覆盖场景：
1. content 为空 + 长思考 → 触发重试 → 返回非空文本
2. content 非空但 finish_reason=length（被截断）→ 触发重试 → 返回完整文本
3. 正常非空回复（finish_reason=stop）→ 不重试
4. 空回复但无思考过程 → 不重试（保持原行为）
5. 重试全部失败 → 返回已获取内容（优于空兜底）
6. token 统计正确累积
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.model_engine.brain_engine import BrainEngine
from core.model_engine.model_adapter import ModelResponse


class _SeqAdapter:
    """按预设序列返回响应的模拟适配器。每次调用触发 token 回调。"""

    def __init__(self, *responses):
        # responses: 每项为 dict {text, reasoning, finish}
        self._queue = list(responses)
        self.calls = []
        self.model_name = "deepseek-reasoner"
        self.on_token_usage = None

    def initialize(self) -> bool:
        return True

    def set_logger(self, logger):
        self.logger = logger

    def chat_completion(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
        self.calls.append({"max_tokens": max_tokens, "tools": kwargs.get("tools"),
                           "n_messages": len(messages)})
        cfg = self._queue.pop(0) if self._queue else {"text": "默认回复", "finish": "stop"}
        resp = ModelResponse(
            text=cfg.get("text", ""),
            model=self.model_name,
            tokens_used=100,
            finish_reason=cfg.get("finish", "stop"),
            metadata={"reasoning": cfg.get("reasoning", "")},
        )
        cb = getattr(self, "on_token_usage", None)
        if cb:
            try:
                cb(100)
            except Exception:
                pass
        return resp


def _make_engine(adapter) -> BrainEngine:
    engine = BrainEngine.__new__(BrainEngine)
    engine.config = {"default_max_tokens": 8192, "default_temperature": 0.7}
    engine.model_adapter = adapter
    engine.logger = None
    engine._last_tool_sigs = []
    engine._loop_count = 0
    engine._json_fail_counts = {}
    engine.token_usage = {"total": 0, "calls": 0}
    adapter.on_token_usage = engine._accum_token
    return engine


def test_empty_reply_retry_returns_text():
    """思考耗尽预算 → 空回复 → 重试 → 返回非空文本"""
    adapter = _SeqAdapter(
        {"text": "", "reasoning": "x" * 5000, "finish": "length"},
        {"text": "✅ 重试后的正常回复内容。", "finish": "stop"},
    )
    engine = _make_engine(adapter)

    result = engine.chat_with_tools(
        [{"role": "user", "content": "算金星引力辅助"}], tools=[], max_rounds=3)

    assert len(adapter.calls) == 2, f"应重试一次，实际 {len(adapter.calls)} 次"
    assert adapter.calls[1]["max_tokens"] == 8192, "重试应提升 max_tokens 到 8192"
    assert adapter.calls[1]["tools"] is None, "重试应关闭 tools"
    assert result.get("text"), f"重试后仍空: {result}"
    assert "重试后的正常回复" in result["text"]
    assert result.get("reasoning"), "思考过程不应丢失"


def test_truncated_reply_triggers_retry():
    """content 非空但被 length 截断 → 也应触发重试"""
    adapter = _SeqAdapter(
        {"text": "三个 lambda 捕获的是*", "reasoning": "y" * 9000, "finish": "length"},
        {"text": "三个 lambda 捕获的是同一个 i，最终 [4, 4, 4]。", "finish": "stop"},
    )
    engine = _make_engine(adapter)

    result = engine.chat_with_tools(
        [{"role": "user", "content": "讲解闭包"}], tools=[], max_rounds=3)

    assert len(adapter.calls) == 2, f"被截断应触发重试，实际 {len(adapter.calls)} 次"
    assert result.get("text"), "重试后应返回完整文本"
    assert "最终 [4, 4, 4]" in result["text"]
    assert result.get("reasoning"), "思考过程应保留"


def test_non_empty_reply_no_retry():
    """正常非空回复（stop）→ 不重试"""
    adapter = _SeqAdapter({"text": "正常回复", "finish": "stop"})
    engine = _make_engine(adapter)

    result = engine.chat_with_tools([{"role": "user", "content": "你好"}],
                                    tools=[], max_rounds=3)

    assert len(adapter.calls) == 1, "非空回复不应重试"
    assert result["text"] == "正常回复"


def test_empty_without_reasoning_no_retry():
    """回复为空但无思考 → 不重试（保持原行为）"""
    adapter = _SeqAdapter({"text": "", "finish": "stop"})
    engine = _make_engine(adapter)

    result = engine.chat_with_tools([{"role": "user", "content": "hi"}],
                                    tools=[], max_rounds=3)

    assert len(adapter.calls) == 1, "无思考的空回复不应重试"
    assert result["text"] == ""


def test_all_retries_fail_returns_partial():
    """重试多次仍失败 → 返回已获取内容（优于空兜底）"""
    adapter = _SeqAdapter(
        {"text": "", "reasoning": "a" * 5000, "finish": "length"},  # 主调用空
        {"text": "部分内容", "finish": "length"},                   # 重试1被截断
        {"text": "更多部分", "finish": "length"},                   # 重试2被截断
    )
    engine = _make_engine(adapter)

    result = engine.chat_with_tools([{"role": "user", "content": "q"}],
                                    tools=[], max_rounds=3)

    # 主调用 + 2 次重试 = 3 次调用
    assert len(adapter.calls) == 3
    # 最后一次获取到"更多部分"（即使截断也返回，优于空兜底）
    assert result["text"] == "更多部分"


def test_token_usage_accumulated():
    """LLM 调用应通过适配器回调累积 token 统计"""
    adapter = _SeqAdapter({"text": "正常回复", "finish": "stop"})
    engine = _make_engine(adapter)

    engine.chat_with_tools([{"role": "user", "content": "你好"}], tools=[], max_rounds=3)
    engine.chat_with_tools([{"role": "user", "content": "再问"}], tools=[], max_rounds=3)

    stats = engine.get_token_stats()
    assert stats["total"] == 200, f"token 应累计 200，实际 {stats['total']}"
    assert stats["calls"] == 2
    assert stats["total_wan"] == 0.02
    assert stats["avg"] == 100.0


def test_token_usage_zero_when_no_calls():
    """未调用 LLM 时 token 统计为 0"""
    adapter = _SeqAdapter({"text": "x", "finish": "stop"})
    engine = _make_engine(adapter)
    stats = engine.get_token_stats()
    assert stats["total"] == 0
    assert stats["calls"] == 0


if __name__ == "__main__":
    test_empty_reply_retry_returns_text()
    test_truncated_reply_triggers_retry()
    test_non_empty_reply_no_retry()
    test_empty_without_reasoning_no_retry()
    test_all_retries_fail_returns_partial()
    test_token_usage_accumulated()
    test_token_usage_zero_when_no_calls()
    print("✅ test_empty_reply_retry 全部通过")
