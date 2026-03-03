"""
模型工厂

根据配置创建合适的模型适配器实例。
"""

from typing import Dict, Any, Optional, Type

from .model_adapter import ModelAdapter
from .ollama_adapter import OllamaAdapter, create_ollama_adapter
from .openai_adapter import OpenAIAdapter, create_openai_adapter

# 尝试导入Anthropic适配器，如果不可用则设置为None
try:
    from .anthropic_adapter import AnthropicAdapter, create_anthropic_adapter
    ANTHROPIC_AVAILABLE = True
except ImportError:
    AnthropicAdapter = None
    create_anthropic_adapter = None
    ANTHROPIC_AVAILABLE = False


class ModelFactory:
    """模型工厂类"""
    
    # 注册的适配器类型
    ADAPTER_REGISTRY = {
        "ollama": (OllamaAdapter, create_ollama_adapter),
        "openai": (OpenAIAdapter, create_openai_adapter),
    }
    
    # 只有在Anthropic可用时才注册
    if ANTHROPIC_AVAILABLE:
        ADAPTER_REGISTRY["anthropic"] = (AnthropicAdapter, create_anthropic_adapter)
    
    @classmethod
    def register_adapter(cls, 
                         adapter_type: str, 
                         adapter_class: Type[ModelAdapter],
                         factory_func=None):
        """
        注册新的适配器类型
        
        Args:
            adapter_type: 适配器类型标识
            adapter_class: 适配器类
            factory_func: 工厂函数（可选）
        """
        cls.ADAPTER_REGISTRY[adapter_type] = (adapter_class, factory_func)
    
    @classmethod
    def get_supported_types(cls) -> list:
        """
        获取支持的适配器类型
        
        Returns:
            支持的类型列表
        """
        return list(cls.ADAPTER_REGISTRY.keys())
    
    @classmethod
    def create_adapter(cls, config: Dict[str, Any]) -> ModelAdapter:
        """
        根据配置创建模型适配器
        
        Args:
            config: 配置参数，必须包含：
                - model_provider: 模型提供商类型（ollama, openai, anthropic）
                - model_name: 模型名称
                
        Returns:
            创建的模型适配器实例
            
        Raises:
            ValueError: 当配置无效或适配器类型不支持时
        """
        if not config:
            raise ValueError("配置参数不能为空")
        
        # 提取配置
        model_provider = config.get("model_provider", "ollama")
        model_name = config.get("model_name")
        
        if not model_name:
            raise ValueError("配置中必须包含model_name参数")
        
        # 检查适配器类型是否支持
        if model_provider not in cls.ADAPTER_REGISTRY:
            supported = cls.get_supported_types()
            raise ValueError(
                f"不支持的模型提供商: {model_provider}。"
                f"支持的提供商: {supported}"
            )
        
        # 获取适配器类和工厂函数
        adapter_class, factory_func = cls.ADAPTER_REGISTRY[model_provider]
        
        # 使用工厂函数或直接创建实例
        if factory_func:
            adapter = factory_func(config)
        else:
            adapter = adapter_class(config)
        
        return adapter
    
    @classmethod
    def detect_best_adapter(cls, 
                           available_resources: Dict[str, Any] = None,
                           preferences: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        检测最佳适配器配置
        
        Args:
            available_resources: 可用资源信息（如是否有Ollama服务、API密钥等）
            preferences: 用户偏好（如偏好本地模型、成本敏感等）
            
        Returns:
            推荐的适配器配置
        """
        if available_resources is None:
            available_resources = {}
        if preferences is None:
            preferences = {}
        
        # 默认配置
        default_config = {
            "model_provider": "ollama",
            "model_name": "deepseek-r1:7b",
            "base_url": "http://localhost:11434",
            "timeout": 30,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
        
        # 检查Ollama服务是否可用
        ollama_available = False
        try:
            import requests
            response = requests.get("http://localhost:11434/api/tags", timeout=3)
            ollama_available = response.status_code == 200
        except:
            ollama_available = False
        
        # 检查OpenAI API密钥
        openai_available = bool(available_resources.get("openai_api_key"))
        
        # 检查Anthropic API密钥
        anthropic_available = bool(available_resources.get("anthropic_api_key"))
        
        # 根据可用性和偏好选择适配器
        if preferences.get("prefer_local") and ollama_available:
            # 偏好本地模型且Ollama可用
            config = default_config.copy()
            config["model_provider"] = "ollama"
            config["model_name"] = preferences.get("preferred_model", "deepseek-r1:7b")
            
        elif preferences.get("prefer_cloud") and openai_available:
            # 偏好云端模型且OpenAI可用
            config = {
                "model_provider": "openai",
                "model_name": preferences.get("preferred_model", "gpt-3.5-turbo"),
                "api_key": available_resources.get("openai_api_key"),
                "temperature": 0.7,
                "max_tokens": 1024,
            }
            
        elif preferences.get("prefer_cloud") and anthropic_available:
            # 偏好云端模型且Anthropic可用
            config = {
                "model_provider": "anthropic",
                "model_name": preferences.get("preferred_model", "claude-3-haiku-20240307"),
                "api_key": available_resources.get("anthropic_api_key"),
                "temperature": 0.7,
                "max_tokens": 1024,
            }
            
        elif ollama_available:
            # Ollama可用
            config = default_config.copy()
            
        elif openai_available:
            # OpenAI可用
            config = {
                "model_provider": "openai",
                "model_name": "gpt-3.5-turbo",
                "api_key": available_resources.get("openai_api_key"),
                "temperature": 0.7,
                "max_tokens": 1024,
            }
            
        elif anthropic_available:
            # Anthropic可用
            config = {
                "model_provider": "anthropic",
                "model_name": "claude-3-haiku-20240307",
                "api_key": available_resources.get("anthropic_api_key"),
                "temperature": 0.7,
                "max_tokens": 1024,
            }
            
        else:
            # 没有任何可用，使用默认但需要手动配置
            config = default_config.copy()
            config["needs_configuration"] = True
            config["warning"] = "没有检测到可用的模型服务，需要手动配置"
        
        return config


# 便捷函数
def create_model_adapter(config: Dict[str, Any] = None) -> ModelAdapter:
    """
    创建模型适配器的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        模型适配器实例
    """
    if config is None:
        # 尝试自动检测最佳配置
        factory = ModelFactory()
        config = factory.detect_best_adapter()
    
    return ModelFactory.create_adapter(config)