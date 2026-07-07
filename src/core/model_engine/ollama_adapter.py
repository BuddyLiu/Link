"""
Ollama本地模型适配器

用于连接本地Ollama服务，支持deepseek-r1:7b等本地模型。
"""

import json
import requests
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

from .model_adapter import ModelAdapter, ModelResponse


class OllamaAdapter(ModelAdapter):
    """Ollama本地模型适配器"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化Ollama适配器
        
        Args:
            config: 配置参数，包括：
                - model_name: 模型名称（如"deepseek-r1:7b"）
                - base_url: Ollama API基础URL（默认http://localhost:11434）
                - timeout: 请求超时时间（秒）
        """
        super().__init__(config)
        
        self.base_url = config.get("base_url", "http://localhost:11434")
        self.timeout = config.get("timeout", 30)
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        
        # 确保模型名称正确
        if not self.model_name or self.model_name == "unknown":
            self.model_name = config.get("model", "deepseek-r1:7b")
    
    def initialize(self) -> bool:
        """
        初始化Ollama适配器，检查连接和模型可用性
        
        Returns:
            是否初始化成功
        """
        self._log("info", f"初始化Ollama适配器，模型: {self.model_name}")
        
        try:
            # 检查Ollama服务是否运行
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code != 200:
                self._log("error", f"Ollama服务不可用，状态码: {response.status_code}")
                return False
            
            models_data = response.json()
            available_models = models_data.get("models", [])
            
            # 检查模型是否可用
            model_available = False
            for model in available_models:
                if model.get("name") == self.model_name or model.get("model") == self.model_name:
                    model_available = True
                    self._log("info", f"找到模型: {model.get('name')}")
                    break
            
            if not model_available:
                self._log("warning", f"模型 {self.model_name} 未在Ollama中找到")
                self._log("info", f"可用模型: {[m.get('name') for m in available_models]}")
                # 仍然尝试使用，因为模型名称可能有变体
            
            self._initialized = True
            self._log("info", "Ollama适配器初始化成功")
            return True
            
        except requests.exceptions.ConnectionError:
            self._log("error", f"无法连接到Ollama服务，请确保Ollama正在运行 ({self.base_url})")
            return False
        except Exception as e:
            self._log("error", f"Ollama适配器初始化失败: {str(e)}")
            return False
    
    def chat_completion(self,
                        messages: List[Dict[str, str]],
                        temperature: float = 0.7,
                        max_tokens: int = 1024,
                        **kwargs) -> ModelResponse:
        """
        使用Ollama API进行聊天完成
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            模型响应
        """
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError("Ollama适配器未正确初始化")
        
        self._log("debug", f"发送聊天请求到Ollama，模型: {self.model_name}")
        
        # 准备请求数据
        request_data = {
            "model": self.model_name,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
            },
            "stream": False
        }
        
        # 添加其他选项
        if kwargs.get("top_p"):
            request_data["options"]["top_p"] = kwargs["top_p"]
        if kwargs.get("top_k"):
            request_data["options"]["top_k"] = kwargs["top_k"]
        if kwargs.get("repeat_penalty"):
            request_data["options"]["repeat_penalty"] = kwargs["repeat_penalty"]
        
        try:
            start_time = time.time()
            
            # 发送请求
            response = requests.post(
                f"{self.base_url}/api/chat",
                headers=self.headers,
                json=request_data,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                # 如果模型不支持 chat 接口，自动回退到 generate 接口
                if response.status_code == 400 and "does not support chat" in response.text:
                    self._log("warning", f"模型 {self.model_name} 不支持 chat 接口，自动回退到 generate 接口")
                    # 将 messages 转为 prompt 格式
                    prompt_parts = []
                    for msg in messages:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        if role == "system":
                            prompt_parts.append(f"System: {content}")
                        elif role == "user":
                            prompt_parts.append(f"User: {content}")
                        elif role == "assistant":
                            prompt_parts.append(f"Assistant: {content}")
                    prompt_parts.append("Assistant: ")
                    prompt = "\n".join(prompt_parts)
                    return self.generate_completion(prompt, temperature, max_tokens, **kwargs)

                error_msg = f"Ollama API错误: {response.status_code} - {response.text}"
                self._log("error", error_msg)
                raise RuntimeError(error_msg)

            response_data = response.json()
            
            # 解析响应
            model_response = response_data.get("message", {})
            response_text = model_response.get("content", "")
            
            # 提取token使用信息
            eval_count = response_data.get("eval_count", 0)
            prompt_eval_count = response_data.get("prompt_eval_count", 0)
            total_tokens = eval_count + prompt_eval_count
            
            # 构建响应对象
            result = ModelResponse(
                text=response_text,
                model=self.model_name,
                tokens_used=total_tokens,
                finish_reason=response_data.get("done_reason", "stop"),
                metadata={
                    "response_time": time.time() - start_time,
                    "eval_count": eval_count,
                    "prompt_eval_count": prompt_eval_count,
                    "total_duration": response_data.get("total_duration", 0),
                    "load_duration": response_data.get("load_duration", 0),
                    "raw_response": response_data
                }
            )
            
            self._log("debug", f"Ollama响应完成，使用{total_tokens}个token，耗时{result.metadata['response_time']:.2f}秒")
            return result
            
        except requests.exceptions.Timeout:
            error_msg = f"Ollama请求超时 ({self.timeout}秒)"
            self._log("error", error_msg)
            raise TimeoutError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"Ollama请求失败: {str(e)}"
            self._log("error", error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"处理Ollama响应时出错: {str(e)}"
            self._log("error", error_msg)
            raise
    
    def generate_completion(self,
                           prompt: str,
                           temperature: float = 0.7,
                           max_tokens: int = 1024,
                           **kwargs) -> ModelResponse:
        """
        使用Ollama生成API（非聊天模式）
        
        Args:
            prompt: 提示词
            temperature: 温度参数
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            模型响应
        """
        if not self._initialized:
            if not self.initialize():
                raise RuntimeError("Ollama适配器未正确初始化")
        
        self._log("debug", f"发送生成请求到Ollama，模型: {self.model_name}")
        
        # 准备请求数据
        request_data = {
            "model": self.model_name,
            "prompt": prompt,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
                "num_ctx": 8192,
                "num_ctx": 8192,
            },
            "stream": False
        }
        
        # 添加其他选项
        if kwargs.get("top_p"):
            request_data["options"]["top_p"] = kwargs["top_p"]
        
        try:
            start_time = time.time()
            
            # 发送请求
            response = requests.post(
                f"{self.base_url}/api/generate",
                headers=self.headers,
                json=request_data,
                timeout=self.timeout
            )
            
            if response.status_code != 200:
                error_msg = f"Ollama生成API错误: {response.status_code} - {response.text}"
                self._log("error", error_msg)
                raise RuntimeError(error_msg)
            
            response_data = response.json()
            response_text = response_data.get("response", "")
            
            # 提取token使用信息
            eval_count = response_data.get("eval_count", 0)
            prompt_eval_count = response_data.get("prompt_eval_count", 0)
            total_tokens = eval_count + prompt_eval_count
            
            # 构建响应对象
            result = ModelResponse(
                text=response_text,
                model=self.model_name,
                tokens_used=total_tokens,
                finish_reason=response_data.get("done_reason", "stop"),
                metadata={
                    "response_time": time.time() - start_time,
                    "eval_count": eval_count,
                    "prompt_eval_count": prompt_eval_count,
                    "total_duration": response_data.get("total_duration", 0),
                    "load_duration": response_data.get("load_duration", 0),
                    "raw_response": response_data
                }
            )
            
            self._log("debug", f"Ollama生成完成，使用{total_tokens}个token，耗时{result.metadata['response_time']:.2f}秒")
            return result
            
        except requests.exceptions.Timeout:
            error_msg = f"Ollama生成请求超时 ({self.timeout}秒)"
            self._log("error", error_msg)
            raise TimeoutError(error_msg)
        except requests.exceptions.RequestException as e:
            error_msg = f"Ollama生成请求失败: {str(e)}"
            self._log("error", error_msg)
            raise RuntimeError(error_msg)
        except Exception as e:
            error_msg = f"处理Ollama生成响应时出错: {str(e)}"
            self._log("error", error_msg)
            raise
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        获取Ollama模型详细信息
        
        Returns:
            模型信息
        """
        base_info = super().get_model_info()
        
        try:
            # 尝试获取模型详情
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                models_data = response.json()
                for model in models_data.get("models", []):
                    if model.get("name") == self.model_name or model.get("model") == self.model_name:
                        base_info.update({
                            "ollama_model_info": {
                                "size": model.get("size"),
                                "digest": model.get("digest"),
                                "modified_at": model.get("modified_at"),
                                "details": model.get("details", {})
                            }
                        })
                        break
        except Exception as e:
            self._log("debug", f"无法获取模型详情: {str(e)}")
        
        return base_info
    
    def health_check(self) -> Dict[str, Any]:
        """
        Ollama健康检查
        
        Returns:
            健康状态信息
        """
        try:
            # 检查服务是否运行
            start_time = time.time()
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            response_time = time.time() - start_time
            
            if response.status_code == 200:
                # 检查模型是否可用
                models_data = response.json()
                model_available = False
                for model in models_data.get("models", []):
                    if model.get("name") == self.model_name or model.get("model") == self.model_name:
                        model_available = True
                        break
                
                if model_available:
                    return {
                        "status": "healthy",
                        "model": self.model_name,
                        "response_time": f"{response_time:.2f}s",
                        "ollama_status": "running",
                        "model_available": True,
                        "timestamp": datetime.now().isoformat()
                    }
                else:
                    return {
                        "status": "degraded",
                        "model": self.model_name,
                        "response_time": f"{response_time:.2f}s",
                        "ollama_status": "running",
                        "model_available": False,
                        "warning": f"模型 {self.model_name} 未找到",
                        "timestamp": datetime.now().isoformat()
                    }
            else:
                return {
                    "status": "unhealthy",
                    "model": self.model_name,
                    "response_time": f"{response_time:.2f}s",
                    "ollama_status": f"error_{response.status_code}",
                    "error": f"API返回状态码 {response.status_code}",
                    "timestamp": datetime.now().isoformat()
                }
                
        except requests.exceptions.ConnectionError:
            return {
                "status": "unhealthy",
                "model": self.model_name,
                "ollama_status": "not_running",
                "error": "无法连接到Ollama服务，请确保Ollama正在运行",
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
def create_ollama_adapter(config: Dict[str, Any] = None) -> OllamaAdapter:
    """
    创建Ollama适配器的便捷函数
    
    Args:
        config: 配置参数，至少包含model_name
        
    Returns:
        Ollama适配器实例
    """
    if config is None:
        config = {}
    
    # 设置默认值
    default_config = {
        "model_name": "deepseek-r1:7b",
        "base_url": "http://localhost:11434",
        "timeout": 30
    }
    
    # 合并配置
    merged_config = {**default_config, **config}
    
    return OllamaAdapter(merged_config)