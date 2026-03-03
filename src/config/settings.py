"""
JARVIS配置文件管理模块
负责管理环境变量、系统配置和模型参数
"""

import os
from typing import Dict, Any, Optional, List
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
    max_tokens: int = Field(default=4096, description="最大生成token数")
    
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
    chroma_persist_directory: str = Field(default="./data/memory/chroma", description="Chroma持久化目录")
    embedding_model: str = Field(default="all-MiniLM-L6-v2", description="嵌入模型名称")
    similarity_threshold: float = Field(default=0.7, description="相似度阈值")
    max_memories_per_query: int = Field(default=5, description="每次查询最大记忆数量")
    memory_retention_days: int = Field(default=365, description="记忆保留天数")
    enable_auto_summary: bool = Field(default=True, description="是否启用自动摘要")
    summary_min_length: int = Field(default=100, description="触发摘要的最小文本长度")
    
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


class PlanningSettings(BaseSettings):
    """规划系统配置（第三阶段）"""
    planning_engine: str = Field(default="tot", description="规划引擎类型：tot, simple")
    max_planning_time: int = Field(default=30, description="最大规划时间（秒）")
    max_planning_depth: int = Field(default=3, description="最大规划深度")
    planning_temperature: float = Field(default=0.7, description="规划时的模型温度")
    enable_complex_tasks: bool = Field(default=True, description="是否启用复杂任务处理")
    max_task_steps: int = Field(default=20, description="单个任务最大步骤数")
    
    class Config:
        env_prefix = "PLANNING_"


class ReflectionSettings(BaseSettings):
    """反思系统配置（第三阶段）"""
    enable_auto_reflection: bool = Field(default=True, description="是否启用自动反思")
    reflection_triggers: List[str] = Field(default=["failure", "low_confidence"], description="反思触发器")
    max_reflection_iterations: int = Field(default=3, description="最大反思迭代次数")
    reflection_confidence_threshold: float = Field(default=0.7, description="触发反思的置信度阈值")
    save_reflection_history: bool = Field(default=True, description="是否保存反思历史")
    
    class Config:
        env_prefix = "REFLECTION_"


class ReminderSettings(BaseSettings):
    """提醒系统配置（第三阶段）"""
    enable_active_reminders: bool = Field(default=True, description="是否启用主动提醒")
    reminder_check_interval: int = Field(default=60, description="提醒检查间隔（秒）")
    max_reminders_per_user: int = Field(default=100, description="每个用户最大提醒数")
    reminder_types_enabled: List[str] = Field(default=["time", "condition"], description="启用的提醒类型")
    notification_channels: List[str] = Field(default=["cli"], description="通知渠道：cli, desktop, mobile")
    
    class Config:
        env_prefix = "REMINDER_"


class ExternalServicesSettings(BaseSettings):
    """外部服务配置（第三阶段）"""
    calendar_api_enabled: bool = Field(default=False, description="是否启用日历API")
    weather_api_enabled: bool = Field(default=True, description="是否启用天气API")
    location_services_enabled: bool = Field(default=False, description="是否启用位置服务")
    news_api_enabled: bool = Field(default=False, description="是否启用新闻API")
    map_api_enabled: bool = Field(default=False, description="是否启用地图API")
    
    # API配置
    openweathermap_api_key: Optional[str] = Field(default=None, description="OpenWeatherMap API密钥")
    google_calendar_api_key: Optional[str] = Field(default=None, description="Google日历API密钥")
    newsapi_api_key: Optional[str] = Field(default=None, description="NewsAPI API密钥")
    
    class Config:
        env_prefix = "EXTERNAL_"


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
    planning: PlanningSettings = PlanningSettings()
    reflection: ReflectionSettings = ReflectionSettings()
    reminder: ReminderSettings = ReminderSettings()
    external: ExternalServicesSettings = ExternalServicesSettings()
    
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
        if os.getenv("OLLAMA_BASE_URL"):
            self.model.api_base = os.getenv("OLLAMA_BASE_URL")
            
        # 更新第三阶段配置
        if os.getenv("PLANNING_ENGINE"):
            self.planning.planning_engine = os.getenv("PLANNING_ENGINE")
        if os.getenv("ENABLE_ACTIVE_REMINDERS"):
            self.reminder.enable_active_reminders = os.getenv("ENABLE_ACTIVE_REMINDERS").lower() == "true"
        if os.getenv("EXTERNAL_WEATHER_API_ENABLED"):
            self.external.weather_api_enabled = os.getenv("EXTERNAL_WEATHER_API_ENABLED").lower() == "true"
            
        return self
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            "system": self.system.model_dump(),
            "model": self.model.model_dump(),
            "memory": self.memory.model_dump(),
            "tool": self.tool.model_dump(),
            "voice": self.voice.model_dump(),
            "planning": self.planning.model_dump(),
            "reflection": self.reflection.model_dump(),
            "reminder": self.reminder.model_dump(),
            "external": self.external.model_dump(),
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