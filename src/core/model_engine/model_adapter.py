"""
模型适配器基类

定义统一的模型接口，支持多种模型提供商。
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field
from datetime import datetime
import json


@dataclass
class ModelResponse:
    """模型响应数据结构"""
    text: str  # 模型生成的文本
    model: str  # 使用的模型名称
    tokens_used: int  # 使用的token数量
    finish_reason: str  # 完成原因
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "text": self.text,
            "model": self.model,
            "tokens_used": self.tokens_used,
            "finish_reason": self.finish_reason,
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ModelResponse":
        """从字典创建"""
        # 处理时间戳
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        return cls(
            text=data.get("text", ""),
            model=data.get("model", ""),
            tokens_used=data.get("tokens_used", 0),
            finish_reason=data.get("finish_reason", "stop"),
            metadata=data.get("metadata", {}),
            created_at=created_at or datetime.now(),
        )


class ModelAdapter(ABC):
    """模型适配器抽象基类"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化模型适配器
        
        Args:
            config: 配置参数
        """
        self.config = config
        self.model_name = config.get("model_name", "unknown")
        self.logger = None
        self._initialized = False
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def _log(self, level: str, message: str):
        """记录日志"""
        if self.logger:
            if level == "debug":
                self.logger.debug(message)
            elif level == "info":
                self.logger.info(message)
            elif level == "warning":
                self.logger.warning(message)
            elif level == "error":
                self.logger.error(message)
    
    @abstractmethod
    def initialize(self) -> bool:
        """
        初始化适配器
        
        Returns:
            是否初始化成功
        """
        pass
    
    @abstractmethod
    def chat_completion(self,
                        messages: List[Dict[str, str]],
                        temperature: float = 0.7,
                        max_tokens: int = 1024,
                        **kwargs) -> ModelResponse:
        """
        聊天完成接口
        
        Args:
            messages: 消息列表，格式如 [{"role": "user", "content": "你好"}]
            temperature: 温度参数，控制随机性
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            模型响应
        """
        pass
    
    def simple_query(self, query: str, system_prompt: str = None, extra_messages: list = None) -> str:
        """
        简单查询接口

        Args:
            query: 用户查询
            system_prompt: 系统提示（可选）
            extra_messages: 额外的消息列表（可选），如对话历史。
                           每条消息格式为 {"role": str, "content": str}，
                           插入在 system_prompt 和当前 user 消息之间。

        Returns:
            模型生成的文本
        """
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        if extra_messages:
            messages.extend(extra_messages)

        messages.append({"role": "user", "content": query})
        
        try:
            response = self.chat_completion(messages)
            return response.text
        except Exception as e:
            self._log("error", f"简单查询失败: {str(e)}")
            return f"查询失败: {str(e)}"
    
    def generate_with_prompt(self, 
                             prompt: str, 
                             system_prompt: str = None,
                             temperature: float = 0.7,
                             max_tokens: int = 1024) -> str:
        """
        使用提示词生成文本
        
        Args:
            prompt: 提示词
            system_prompt: 系统提示（可选）
            temperature: 温度参数
            max_tokens: 最大token数
            
        Returns:
            生成的文本
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        try:
            response = self.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            return response.text
        except Exception as e:
            self._log("error", f"生成失败: {str(e)}")
            return f"生成失败: {str(e)}"
    
    def intent_analysis(self, user_input: str) -> Dict[str, Any]:
        """
        意图分析 - 分析用户输入的意图
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            意图分析结果
        """
        system_prompt = """你是一个意图分析助手。分析用户输入的意图，并返回以下JSON格式的结果：
        {
            "intent": "意图类别",
            "confidence": 0.0-1.0的置信度,
            "action": "建议执行的动作",
            "parameters": {"key": "value"} 参数信息,
            "needs_confirmation": true/false 是否需要确认,
            "alternative_intents": [{"intent": "替代意图", "confidence": 0.0}]
        }
        
        意图类别包括：查询、命令、规划、反思、提醒、闲聊、求助、工具调用等。
        """
        
        user_prompt = f"分析以下用户输入的意图：\n\n{user_input}"
        
        try:
            response = self.simple_query(user_prompt, system_prompt)
            
            # 尝试解析JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result_json = json_match.group()
                return json.loads(result_json)
            else:
                # 如果无法解析JSON，返回简单结果
                return {
                    "intent": "未知",
                    "confidence": 0.5,
                    "action": "回复",
                    "parameters": {},
                    "needs_confirmation": False,
                    "alternative_intents": []
                }
        except Exception as e:
            self._log("error", f"意图分析失败: {str(e)}")
            return {
                "intent": "分析失败",
                "confidence": 0.0,
                "action": "回复错误信息",
                "parameters": {"error": str(e)},
                "needs_confirmation": False,
                "alternative_intents": []
            }
    
    def task_planning(self, task_description: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        任务规划 - 为给定任务生成规划
        
        Args:
            task_description: 任务描述
            context: 上下文信息（可选）
            
        Returns:
            任务规划结果
        """
        system_prompt = """你是一个任务规划专家。分析任务描述，生成详细的执行规划。返回以下JSON格式：
        {
            "task_name": "任务名称",
            "steps": [
                {
                    "step_id": 1,
                    "description": "步骤描述",
                    "action": "具体动作",
                    "estimated_time": "预估时间",
                    "dependencies": [] 依赖步骤,
                    "tools_needed": [] 所需工具
                }
            ],
            "estimated_total_time": "总预估时间",
            "complexity": "简单/中等/复杂",
            "potential_issues": ["潜在问题1", "潜在问题2"],
            "success_criteria": ["成功标准1", "成功标准2"]
        }
        """
        
        context_str = ""
        if context:
            context_str = f"\n上下文信息：{json.dumps(context, ensure_ascii=False, indent=2)}"
        
        user_prompt = f"请为以下任务生成详细规划：\n\n任务描述：{task_description}{context_str}"
        
        try:
            response = self.simple_query(user_prompt, system_prompt)
            
            # 尝试解析JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                result_json = json_match.group()
                return json.loads(result_json)
            else:
                # 如果无法解析JSON，返回简单规划
                return {
                    "task_name": task_description[:50],
                    "steps": [
                        {
                            "step_id": 1,
                            "description": "分析任务需求",
                            "action": "理解任务目标和要求",
                            "estimated_time": "5分钟",
                            "dependencies": [],
                            "tools_needed": ["分析工具"]
                        }
                    ],
                    "estimated_total_time": "未知",
                    "complexity": "中等",
                    "potential_issues": ["无法解析复杂需求"],
                    "success_criteria": ["完成基本分析"]
                }
        except Exception as e:
            self._log("error", f"任务规划失败: {str(e)}")
            return {
                "task_name": "规划失败",
                "steps": [],
                "estimated_total_time": "未知",
                "complexity": "未知",
                "potential_issues": [f"规划失败: {str(e)}"],
                "success_criteria": ["无"]
            }
    
    def response_generation(self, 
                            user_input: str,
                            context: Dict[str, Any] = None,
                            style: str = "professional") -> str:
        """
        回复生成 - 基于用户输入和上下文生成回复
        
        Args:
            user_input: 用户输入
            context: 上下文信息（可选）
            style: 回复风格（professional, friendly, concise, detailed）
            
        Returns:
            生成的回复
        """
        style_prompts = {
            "professional": "请用专业、礼貌的语气回复。",
            "friendly": "请用友好、亲切的语气回复。",
            "concise": "请用简洁明了的语言回复，避免冗长。",
            "detailed": "请提供详细、全面的回复。"
        }
        
        style_prompt = style_prompts.get(style, style_prompts["professional"])
        
        system_prompt = f"""你是一个智能助手LINK。{style_prompt}
        基于用户输入和上下文信息生成合适的回复。
        如果上下文中有相关信息，请利用这些信息提供更准确的回答。
        如果不知道答案，请诚实说明，不要编造信息。"""
        
        context_str = ""
        if context:
            context_str = f"\n\n上下文信息：\n{json.dumps(context, ensure_ascii=False, indent=2)}"
        
        user_prompt = f"用户输入：{user_input}{context_str}"
        
        try:
            response = self.simple_query(user_prompt, system_prompt)
            return response
        except Exception as e:
            self._log("error", f"回复生成失败: {str(e)}")
            return f"抱歉，生成回复时出现错误：{str(e)}"
    
    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        try:
            # 发送一个简单的测试消息
            test_response = self.simple_query("Hello", "You are a test assistant.")
            
            return {
                "status": "healthy",
                "model": self.model_name,
                "response_time": "正常",
                "test_response": test_response[:100] if test_response else "无响应",
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "model": self.model_name,
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }
    
    def get_model_info(self) -> Dict[str, Any]:
        """
        获取模型信息
        
        Returns:
            模型信息
        """
        return {
            "model_name": self.model_name,
            "adapter_type": self.__class__.__name__,
            "config": self.config,
            "initialized": self._initialized
        }