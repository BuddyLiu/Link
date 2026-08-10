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
            return self._mk("", reasoning="x" * 5000, finish="length")
        return self._mk("✅ 重试后的正常回复内容。")


def _make_engine(adapter) -> BrainEngine:
    engine = BrainEngine.__new__(BrainEngine)
    engine.config = {"default_max_tokens": 4096, "default_temperature": 0.7}
    engine.model_adapter = adapter
    engine.logger = None
    engine._last_tool_sigs = []
    engine._loop_count = 0
    engine._json_fail_counts = {}
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


if __name__ == "__main__":
    test_empty_reply_retry_returns_text()
    test_non_empty_reply_no_retry()
    test_empty_without_reasoning_no_retry()
    print("✅ test_empty_reply_retry 全部通过")
