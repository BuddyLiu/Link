"""
OpenAI模型适配器

用于连接OpenAI API服务。
"""

import os
import json
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from .model_adapter import ModelAdapter, ModelResponse


class OpenAIAdapter(ModelAdapter):
    """OpenAI模型适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化OpenAI适配器
        
        Args:
            config: 配置参数，包括：
                - model_name: 模型名称（如"gpt-3.5-turbo"）
                - api_key: OpenAI API密钥（可选，从环境变量读取）
                - api_base: OpenAI API基础URL（可选）
                - timeout: 请求超时时间（秒）
        """
        super().__init__(config)
        
        self.api_key = config.get("api_key") or os.getenv("OPENAI_API_KEY")
        self.api_base = config.get("api_base", "https://api.openai.com/v1")
        self.timeout = config.get("timeout", 30)
        self.headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
    
    def initialize(self) -> bool:
        """
        初始化OpenAI适配器，检查API密钥和连接
        
        Returns:
            是否初始化成功
        """
        self._log("info", f"初始化OpenAI适配器，模型: {self.model_name}")
        
        if not self.api_key:
            self._log("error", "未提供OpenAI API密钥，请在配置中设置api_key或设置OPENAI_API_KEY环境变量")
            return False
        
        # 简化检查：不实际调用API，只检查配置
        self._initialized = True
        self._log("info", "OpenAI适配器初始化成功（API密钥存在）")
        return True
    
    def chat_completion(self,
                        messages: List[Dict[str, str]],
                        temperature: float = 0.7,
                        max_tokens: int = 1024,
                        stream_callback: callable = None,
                        **kwargs) -> ModelResponse:
        """
        使用OpenAI API进行聊天完成（支持流式回调）。

        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大生成token数
            stream_callback: 流式回调，接收 (chunk_type, text)
                            chunk_type: "reasoning" / "content"
            **kwargs: 其他参数

        Returns:
            模型响应
        """
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError("OpenAI适配器未正确初始化")

        self._log("debug", f"发送聊天请求到OpenAI，模型: {self.model_name}")

        # 准备请求数据
        request_data = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if kwargs.get("tools"):
            request_data["tools"] = kwargs["tools"]
            request_data["tool_choice"] = kwargs.get("tool_choice", "auto")
        if kwargs.get("top_p"):
            request_data["top_p"] = kwargs["top_p"]
        if kwargs.get("frequency_penalty"):
            request_data["frequency_penalty"] = kwargs["frequency_penalty"]
        if kwargs.get("presence_penalty"):
            request_data["presence_penalty"] = kwargs["presence_penalty"]

        try:
            start_time = time.time()
            import openai

            client = openai.OpenAI(
                api_key=self.api_key,
                base_url=self.api_base,
                timeout=self.timeout
            )

            use_stream = stream_callback is not None

            if use_stream:
                request_data["stream"] = True
                request_data["stream_options"] = {"include_usage": True}
                response = client.chat.completions.create(**request_data)

                reasoning_buf = ""
                content_buf = ""
                tool_calls_buf = {}
                finish_reason = "stop"

                for chunk in response:
                    delta = chunk.choices[0].delta if chunk.choices else None
                    if not delta:
                        continue

                    if hasattr(delta, 'reasoning_content') and delta.reasoning_content:
                        reasoning_buf += delta.reasoning_content
                        stream_callback("reasoning", delta.reasoning_content)

                    if delta.content:
                        content_buf += delta.content
                        stream_callback("content", delta.content)

                    if hasattr(delta, 'tool_calls') and delta.tool_calls:
                        for tc in delta.tool_calls:
                            idx = tc.index
                            if idx not in tool_calls_buf:
                                tool_calls_buf[idx] = {
                                    "id": tc.id or "",
                                    "type": "function",
                                    "function": {"name": tc.function.name or "", "arguments": tc.function.arguments or ""}
                                }
                            else:
                                if tc.function and tc.function.name:
                                    tool_calls_buf[idx]["function"]["name"] += tc.function.name
                                if tc.function and tc.function.arguments:
                                    tool_calls_buf[idx]["function"]["arguments"] += tc.function.arguments

                    if chunk.choices and chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason

                reasoning = reasoning_buf
                response_text = content_buf
                tool_calls = list(tool_calls_buf.values()) if tool_calls_buf else []
                total_tokens = chunk.usage.total_tokens if hasattr(chunk, 'usage') and chunk.usage else 0

            else:
                request_data["stream"] = False
                response = client.chat.completions.create(**request_data)
                choice = response.choices[0]
                response_text = choice.message.content or ""
                tool_calls = []
                if hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:
                    for tc in choice.message.tool_calls:
                        tool_calls.append({
                            "id": tc.id, "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                        })
                reasoning = ""
                if hasattr(choice.message, 'reasoning_content') and choice.message.reasoning_content:
                    reasoning = choice.message.reasoning_content
                finish_reason = choice.finish_reason or "stop"
                total_tokens = response.usage.total_tokens if response.usage else 0

            extra_meta = {}
            if reasoning:
                extra_meta["reasoning"] = reasoning
            if tool_calls:
                extra_meta["tool_calls"] = tool_calls
            result = ModelResponse(
                text=response_text,
                model=self.model_name,
                tokens_used=total_tokens,
                finish_reason=finish_reason,
                metadata={"response_time": time.time() - start_time, **extra_meta}
            )

            self._log("debug", f"OpenAI响应完成，使用{result.tokens_used}个token，耗时{result.metadata['response_time']:.2f}秒")
            return result

        except ImportError:
            error_msg = "未安装openai库，请运行: pip install openai"
            self._log("error", error_msg)
            raise ImportError(error_msg)
        except Exception as e:
            error_msg = f"OpenAI请求失败: {str(e)}"
            self._log("error", error_msg)
            raise RuntimeError(error_msg)
    
    def health_check(self) -> Dict[str, Any]:
        """
        OpenAI健康检查
        
        Returns:
            健康状态信息
        """
        try:
            if not self.api_key:
                return {
                    "status": "unhealthy",
                    "model": self.model_name,
                    "error": "未配置API密钥",
                    "timestamp": datetime.now().isoformat()
                }
            
            # 尝试发送一个简单的测试请求
            test_messages = [{"role": "user", "content": "Hello"}]
            
            start_time = time.time()
            response = self.chat_completion(
                messages=test_messages,
                temperature=0.1,
                max_tokens=10
            )
            response_time = time.time() - start_time
            
            return {
                "status": "healthy",
                "model": self.model_name,
                "response_time": f"{response_time:.2f}s",
                "test_response_length": len(response.text),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.model_name,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }


# 便捷函数
def create_openai_adapter(config: Dict[str, Any] = None) -> OpenAIAdapter:
    """
    创建OpenAI适配器的便捷函数
    
    Args:
        config: 配置参数，至少包含model_name和api_key
        
    Returns:
        OpenAI适配器实例
    """
    if config is None:
        config = {}
    
    # 设置默认值
    default_config = {
        "model_name": "gpt-3.5-turbo",
        "api_base": "https://api.openai.com/v1",
        "timeout": 30
    }
    
    # 合并配置
    merged_config = {**default_config, **config}
    
    # 尝试从环境变量获取API密钥
    if not merged_config.get("api_key") and "OPENAI_API_KEY" in os.environ:
        merged_config["api_key"] = os.environ["OPENAI_API_KEY"]
    
    return OpenAIAdapter(merged_config)