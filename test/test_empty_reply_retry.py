#!/usr/bin/env python3
"""
回归测试：DeepSeek Reasoner 思考过程耗尽 max_tokens 预算导致回复为空时，
chat_with_tools 应重试一次，返回非空回复（而非触发上层"我已经收到你的消息"兜底）。

场景模拟：
1. 适配器第一次调用返回空 text + 长 reasoning（真实：思考把预算吃光，content 被截断）
2. chat_with_tools 检测到"纯文本回复但 text 为空 + 有思考" → 追加约束提示重试
3. 适配器第二次调用返回正常 text
4. 断言最终返回的 text 非空，且第二次调用确实发生（max_tokens 提升到 8192）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from core.model_engine.brain_engine import BrainEngine
from core.model_engine.model_adapter import ModelResponse


class _MockAdapter:
    """模拟适配器：首次调用返回空文本+长思考，之后返回正常文本。"""

    def __init__(self, first_empty=True):
        self.calls = []
        self._first_empty = first_empty
        self.model_name = "deepseek-reasoner"

    def initialize(self) -> bool:
        return True

    def set_logger(self, logger):
        self.logger = logger

    def _mk(self, text, reasoning="", finish="stop"):
        return ModelResponse(
            text=text,
            model=self.model_name,
            tokens_used=100,
            finish_reason=finish,
            metadata={"reasoning": reasoning},
        )

    def chat_completion(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
        self.calls.append({"max_tokens": max_tokens, "tools": kwargs.get("tools"),
                           "n_messages": len(messages)})
        if self._first_empty and len(self.calls) == 1:
            # 第一次：思考吃光预算，回复为空
            resp = self._mk("", reasoning="x" * 5000, finish="length")
        else:
            resp = self._mk("✅ 重试后的正常回复内容。")
        # 模拟真实适配器触发全局 token 统计回调（返回 100 token）
        cb = getattr(self, "on_token_usage", None)
        if cb:
            try:
                cb(100)
            except Exception:
                pass
        return resp


def _make_engine(adapter) -> BrainEngine:
    engine = BrainEngine.__new__(BrainEngine)
    engine.config = {"default_max_tokens": 4096, "default_temperature": 0.7}
    engine.model_adapter = adapter
    engine.logger = None
    engine._last_tool_sigs = []
    engine._loop_count = 0
    engine._json_fail_counts = {}
    engine.token_usage = {"total": 0, "calls": 0}
    # 挂接全局 token 统计回调（与 _initialize_components 的行为一致）
    adapter.on_token_usage = engine._accum_token
    return engine


def test_empty_reply_retry_returns_text():
    """思考耗尽预算 → 空回复 → 重试 → 返回非空文本"""
    adapter = _MockAdapter(first_empty=True)
    engine = _make_engine(adapter)

    result = engine.chat_with_tools(
        [{"role": "user", "content": "算金星引力辅助"}],
        tools=[],
        max_rounds=3,
    )

    # 触发重试：第二次调用 max_tokens 应为 8192（提升），且关闭了 tools
    assert len(adapter.calls) == 2, f"应重试一次，实际调用 {len(adapter.calls)} 次"
    assert adapter.calls[1]["max_tokens"] == 8192, "重试应提升 max_tokens 到 8192"
    assert adapter.calls[1]["tools"] is None, "重试应关闭 tools 专注纯文本"
    # 最终返回非空文本
    assert result.get("text"), f"重试后仍返回空文本: {result}"
    assert "重试后的正常回复" in result["text"]
    # 思考过程应保留
    assert result.get("reasoning"), "思考过程不应丢失"


def test_non_empty_reply_no_retry():
    """正常非空回复 → 不触发重试"""
    adapter = _MockAdapter(first_empty=False)
    engine = _make_engine(adapter)

    result = engine.chat_with_tools(
        [{"role": "user", "content": "你好"}],
        tools=[],
        max_rounds=3,
    )

    assert len(adapter.calls) == 1, "非空回复不应重试"
    assert result.get("text"), "非空回复不应为空"


def test_empty_without_reasoning_no_retry():
    """回复为空但无思考过程（如流式未拿到 content）→ 不重试，返回空（保持原行为）"""
    adapter = _MockAdapter(first_empty=True)
    adapter._mk = lambda *a, **k: None  # 破坏辅助方法，改用直接覆盖
    # 直接构造：第一次返回空 text 且无 reasoning
    class _A(_MockAdapter):
        def chat_completion(self, messages, temperature=0.7, max_tokens=4096, **kwargs):
            self.calls.append({"max_tokens": max_tokens})
            return ModelResponse(text="", model="m", tokens_used=0, finish_reason="stop",
                                 metadata={})
    adapter = _A(first_empty=True)
    engine = _make_engine(adapter)

    result = engine.chat_with_tools(
        [{"role": "user", "content": "hi"}],
        tools=[],
        max_rounds=3,
    )

    assert len(adapter.calls) == 1, "无思考过程的空回复不应重试"
    assert result.get("text") == ""


def test_token_usage_accumulated():
    """LLM 调用应通过适配器回调累积 token 统计"""
    adapter = _MockAdapter(first_empty=False)
    engine = _make_engine(adapter)

    # 两次调用，每次触发回调累加 100 token
    engine.chat_with_tools(
        [{"role": "user", "content": "你好"}], tools=[], max_rounds=3)
    engine.chat_with_tools(
        [{"role": "user", "content": "再问"}], tools=[], max_rounds=3)

    stats = engine.get_token_stats()
    assert stats["total"] == 200, f"token 应累计 200，实际 {stats['total']}"
    assert stats["calls"] == 2, f"调用数应 2，实际 {stats['calls']}"
    assert stats["total_wan"] == 0.02, f"万级换算错误: {stats['total_wan']}"
    assert stats["avg"] == 100.0, f"平均错误: {stats['avg']}"


def test_token_usage_zero_when_no_calls():
    """未调用 LLM 时 token 统计为 0"""
    adapter = _MockAdapter(first_empty=False)
    engine = _make_engine(adapter)
    stats = engine.get_token_stats()
    assert stats["total"] == 0
    assert stats["calls"] == 0
    assert stats["total_wan"] == 0.0


if __name__ == "__main__":
    test_empty_reply_retry_returns_text()
    test_non_empty_reply_no_retry()
    test_empty_without_reasoning_no_retry()
    test_token_usage_accumulated()
    test_token_usage_zero_when_no_calls()
    print("✅ test_empty_reply_retry 全部通过")
