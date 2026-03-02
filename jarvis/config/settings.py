"""
JARVIS配置文件管理模块
负责管理环境变量、系统配置和模型参数
"""

import os
from typing import Dict, Any, Optional
from pydantic import Field
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# 加载.env文件
load_dotenv()

class ModelSettings(BaseSettings):
    """模型相关配置"""
    model_name: str = Field(default="gpt-3.5-turbo", description="使用的模型名称")
    model_provider: str = Field(default="openai", description="模型提供商：openai, anthropic, local")
    temperature: float = Field(default=0.7, description="模型温度参数")
    max_tokens: int = Field(default=1024, description="最大生成token数")
    
    # 本地模型配置
    local_model_path: Optional[str] = Field(default=None, description="本地模型路径")
    local_model_quantization: Optional[str] = Field(default=None, description="量化格式：4bit, 8bit, fp16")
    
    # API配置
    api_key: Optional[str] = Field(default=None, description="API密钥")
    api_base: Optional[str] = Field(default=None, description="API基础URL")
    
    class Config:
        env_prefix = "MODEL_"

class MemorySettings(BaseSettings):
    """记忆存储配置"""
    vector_store_type: str = Field(default="chroma", description="向量存储类型：chroma, faiss")
    chroma_persist_directory: str = Field(default="./data/chroma", description="Chroma持久化目录")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", description="嵌入模型名称")
    similarity_threshold: float = Field(default=0.7, description="相似度阈值")
    
    class Config:
        env_prefix = "MEMORY_"

class ToolSettings(BaseSettings):
    """工具配置"""
    enabled_tools: list = Field(default=["get_time", "get_weather", "search_files"], description="启用的工具列表")
    mcp_server_enabled: bool = Field(default=False, description="是否启用MCP服务器")
    mcp_server_port: int = Field(default=8000, description="MCP服务器端口")
    
    class Config:
        env_prefix = "TOOL_"

class VoiceSettings(BaseSettings):
    """语音交互配置"""
    speech_recognition_enabled: bool = Field(default=False, description="是否启用语音识别")
    text_to_speech_enabled: bool = Field(default=False, description="是否启用文本转语音")
    speech_recognition_language: str = Field(default="zh-CN", description="语音识别语言")
    
    class Config:
        env_prefix = "VOICE_"

class SystemSettings(BaseSettings):
    """系统配置"""
    debug_mode: bool = Field(default=False, description="调试模式")
    log_level: str = Field(default="INFO", description="日志级别：DEBUG, INFO, WARNING, ERROR")
    max_concurrent_tasks: int = Field(default=5, description="最大并发任务数")
    data_directory: str = Field(default="./data", description="数据存储目录")
    
    class Config:
        env_prefix = "SYSTEM_"

class Settings(BaseSettings):
    """全局配置"""
    system: SystemSettings = SystemSettings()
    model: ModelSettings = ModelSettings()
    memory: MemorySettings = MemorySettings()
    tool: ToolSettings = ToolSettings()
    voice: VoiceSettings = VoiceSettings()
    
    # 从环境变量更新配置
    def update_from_env(self):
        """从环境变量更新配置"""
        load_dotenv()
        
        # 更新系统配置
        if os.getenv("DEBUG_MODE"):
            self.system.debug_mode = os.getenv("DEBUG_MODE").lower() == "true"
        if os.getenv("LOG_LEVEL"):
            self.system.log_level = os.getenv("LOG_LEVEL")
            
        # 更新模型配置
        if os.getenv("MODEL_NAME"):
            self.model.model_name = os.getenv("MODEL_NAME")
        if os.getenv("MODEL_PROVIDER"):
            self.model.model_provider = os.getenv("MODEL_PROVIDER")
        if os.getenv("OPENAI_API_KEY"):
            self.model.api_key = os.getenv("OPENAI_API_KEY")
            
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            "system": self.system.model_dump(),
            "model": self.model.model_dump(),
            "memory": self.memory.model_dump(),
            "tool": self.tool.model_dump(),
            "voice": self.voice.model_dump(),
        }
    
    def save_to_file(self, filepath: str = "./config/settings.json"):
        """保存配置到文件"""
        import json
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, filepath: str = "./config/settings.json"):
        """从文件加载配置"""
        import json
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return cls(**data)
        return cls()

# 创建全局配置实例
settings = Settings().update_from_env()