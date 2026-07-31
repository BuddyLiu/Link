"""
大脑引擎主类

基于Order.txt中3.1基座核心模块要求实现意图理解、任务规划、回复生成功能。
整合模型适配器，提供统一的智能接口。
"""

import json
import time
from typing import Dict, Any, List, Optional, Union
from datetime import datetime

from .model_adapter import ModelAdapter, ModelResponse
from .model_factory import ModelFactory, create_model_adapter


class BrainEngine:
    """大脑引擎主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化大脑引擎
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "model_provider": "ollama",
            "model_name": "deepseek-r1:7b",
            "enable_intent_analysis": True,
            "enable_task_planning": True,
            "enable_response_generation": True,
            "default_temperature": 0.7,
            "default_max_tokens": 1024,
            "response_style": "professional",
            "log_interactions": True,
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 初始化组件
        self.model_adapter = None
        self.logger = None
        self.interaction_history: List[Dict[str, Any]] = []
        
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化所有组件"""
        self._log("info", "初始化大脑引擎组件...")
        
        try:
            # 创建模型适配器
            model_config = {
                "model_provider": self.config.get("model_provider", "ollama"),
                "model_name": self.config.get("model_name", "deepseek-r1:7b"),
            }
            
            # 复制其他相关配置（兼容 base_url 和 api_base 两种 key）
            url = self.config.get("api_base") or self.config.get("base_url")
            if url:
                # OpenAI 适配器用 api_base，Ollama 用 base_url
                model_config["api_base"] = url
                model_config["base_url"] = url
            if self.config.get("api_key"):
                model_config["api_key"] = self.config["api_key"]
            if self.config.get("timeout"):
                model_config["timeout"] = self.config["timeout"]
            
            self.model_adapter = create_model_adapter(model_config)
            
            if self.logger:
                self.model_adapter.set_logger(self.logger)
            
            # 初始化适配器
            if not self.model_adapter.initialize():
                self._log("error", "模型适配器初始化失败")
            else:
                self._log("info", f"模型适配器初始化成功: {self.model_adapter.get_model_info()['model_name']}")
                
        except Exception as e:
            self._log("error", f"初始化模型适配器失败: {str(e)}")
            # 继续运行，但功能受限
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
        if self.model_adapter:
            self.model_adapter.set_logger(logger)
    
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
        else:
            # 简单控制台输出
            print(f"[{level.upper()}] {message}")
    
    def _log_interaction(self, 
                         interaction_type: str,
                         input_data: Any,
                         output_data: Any,
                         metadata: Dict[str, Any] = None):
        """记录交互历史"""
        if not self.config.get("log_interactions", True):
            return
        
        interaction = {
            "timestamp": datetime.now().isoformat(),
            "type": interaction_type,
            "input": input_data,
            "output": output_data,
            "metadata": metadata or {},
        }
        
        self.interaction_history.append(interaction)
        
        # 保持历史记录大小限制
        max_history = self.config.get("max_interaction_history", 100)
        if len(self.interaction_history) > max_history:
            self.interaction_history = self.interaction_history[-max_history:]
    
    def process_user_input(self, 
                           user_input: str,
                           context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        处理用户输入（主入口点）
        
        Args:
            user_input: 用户输入文本
            context: 上下文信息
            
        Returns:
            处理结果，包含意图分析、规划、回复等
        """
        self._log("info", f"处理用户输入: {user_input[:50]}...")
        
        start_time = time.time()
        result = {
            "success": False,
            "user_input": user_input,
            "processing_time": 0,
            "error": None,
        }
        
        try:
            # 1. 意图分析
            intent_result = None
            if self.config.get("enable_intent_analysis", True) and self.model_adapter:
                intent_result = self.analyze_intent(user_input)
                result["intent_analysis"] = intent_result
            
            # 2. 根据意图进行任务规划或直接生成回复
            if intent_result and intent_result.get("intent") == "规划":
                # 如果是规划意图，进行任务规划
                if self.config.get("enable_task_planning", True) and self.model_adapter:
                    task_description = user_input
                    task_context = context or {}
                    if intent_result.get("parameters"):
                        task_context.update(intent_result["parameters"])
                    
                    planning_result = self.plan_task(task_description, task_context)
                    result["task_planning"] = planning_result
                    
                    # 基于规划结果生成回复
                    reply = self._generate_planning_response(planning_result, intent_result)
                    result["response"] = reply
                    result["response_type"] = "planning"
                    
            else:
                # 其他意图，直接生成回复
                if self.config.get("enable_response_generation", True) and self.model_adapter:
                    reply = self.generate_response(user_input, context, intent_result)
                    result["response"] = reply
                    result["response_type"] = "direct"
            
            result["success"] = True
            
        except Exception as e:
            self._log("error", f"处理用户输入失败: {str(e)}")
            result["error"] = str(e)
            result["response"] = f"抱歉，处理您的请求时出现错误: {str(e)}"
        
        # 计算处理时间
        result["processing_time"] = time.time() - start_time
        
        # 记录交互
        self._log_interaction(
            "user_input",
            user_input,
            result,
            {"context": context, "timestamp": datetime.now().isoformat()}
        )
        
        self._log("debug", f"处理完成，耗时{result['processing_time']:.2f}秒")
        return result
    
    def analyze_intent(self, user_input: str) -> Dict[str, Any]:
        """
        分析用户意图
        
        Args:
            user_input: 用户输入文本
            
        Returns:
            意图分析结果
        """
        if not self.model_adapter:
            self._log("warning", "模型适配器未初始化，无法进行意图分析")
            return {
                "intent": "未知",
                "confidence": 0.0,
                "action": "回复",
                "parameters": {},
                "needs_confirmation": False,
                "alternative_intents": []
            }
        
        self._log("debug", f"分析意图: {user_input[:30]}...")
        
        try:
            intent_result = self.model_adapter.intent_analysis(user_input)
            
            # 记录交互
            self._log_interaction(
                "intent_analysis",
                user_input,
                intent_result,
                {"model": self.model_adapter.model_name}
            )
            
            self._log("info", f"意图分析结果: {intent_result.get('intent')} (置信度: {intent_result.get('confidence', 0):.2f})")
            return intent_result
            
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
    
    def plan_task(self, 
                  task_description: str, 
                  context: Dict[str, Any] = None) -> Dict[str, Any]:
        """
        任务规划
        
        Args:
            task_description: 任务描述
            context: 上下文信息
            
        Returns:
            任务规划结果
        """
        if not self.model_adapter:
            self._log("warning", "模型适配器未初始化，无法进行任务规划")
            return {
                "task_name": "规划失败",
                "steps": [],
                "estimated_total_time": "未知",
                "complexity": "未知",
                "potential_issues": ["模型适配器未初始化"],
                "success_criteria": ["无"]
            }
        
        self._log("debug", f"任务规划: {task_description[:30]}...")
        
        try:
            planning_result = self.model_adapter.task_planning(task_description, context)
            
            # 记录交互
            self._log_interaction(
                "task_planning",
                {"task_description": task_description, "context": context},
                planning_result,
                {"model": self.model_adapter.model_name}
            )
            
            self._log("info", f"任务规划完成: {planning_result.get('task_name', '未知任务')} ({len(planning_result.get('steps', []))} 个步骤)")
            return planning_result
            
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
    
    def generate_response(self, 
                          user_input: str,
                          context: Dict[str, Any] = None,
                          intent_result: Dict[str, Any] = None) -> str:
        """
        生成回复
        
        Args:
            user_input: 用户输入
            context: 上下文信息
            intent_result: 意图分析结果（可选）
            
        Returns:
            生成的回复
        """
        if not self.model_adapter:
            self._log("warning", "模型适配器未初始化，使用默认回复")
            return f"我已经收到你的消息：'{user_input}'。目前模型引擎未就绪。"
        
        self._log("debug", f"生成回复: {user_input[:30]}...")
        
        # 准备上下文
        response_context = context or {}
        if intent_result:
            response_context["intent"] = intent_result
        
        # 获取回复风格
        style = self.config.get("response_style", "professional")
        
        try:
            response = self.model_adapter.response_generation(
                user_input=user_input,
                context=response_context,
                style=style
            )
            
            # 记录交互
            self._log_interaction(
                "response_generation",
                {"user_input": user_input, "context": response_context},
                response,
                {"model": self.model_adapter.model_name, "style": style}
            )
            
            self._log("debug", f"回复生成完成，长度: {len(response)} 字符")
            return response
            
        except Exception as e:
            self._log("error", f"回复生成失败: {str(e)}")
            return f"抱歉，生成回复时出现错误：{str(e)}"
    
    def _generate_planning_response(self, 
                                   planning_result: Dict[str, Any],
                                   intent_result: Dict[str, Any]) -> str:
        """基于规划结果生成回复"""
        task_name = planning_result.get("task_name", "任务")
        steps = planning_result.get("steps", [])
        complexity = planning_result.get("complexity", "未知")
        
        response = f"✅ 我已经为您规划了'{task_name}'任务。\n\n"
        
        response += f"📋 任务概况:\n"
        response += f"   • 复杂度: {complexity}\n"
        response += f"   • 步骤数: {len(steps)}\n"
        
        if "estimated_total_time" in planning_result:
            response += f"   • 预估时间: {planning_result['estimated_total_time']}\n"
        
        if steps:
            response += f"\n📝 执行步骤:\n"
            for i, step in enumerate(steps[:5], 1):  # 只显示前5个步骤
                response += f"   {i}. {step.get('description', '未知步骤')}\n"
                if step.get('estimated_time'):
                    response += f"      ⏱️  {step['estimated_time']}\n"
            
            if len(steps) > 5:
                response += f"   ... 还有 {len(steps) - 5} 个步骤\n"
        
        if planning_result.get("potential_issues"):
            response += f"\n⚠️  潜在问题:\n"
            for issue in planning_result["potential_issues"][:3]:  # 只显示前3个问题
                response += f"   • {issue}\n"
        
        response += f"\n🎯 您希望我:\n"
        response += f"1. 开始执行这个规划\n"
        response += f"2. 调整某些步骤\n"
        response += f"3. 查看详细规划\n"
        response += f"4. 取消这个任务\n"
        
        return response
    
    def chat_completion(self,
                        messages: List[Dict[str, str]],
                        temperature: float = None,
                        max_tokens: int = None,
                        **kwargs) -> ModelResponse:
        """
        直接聊天完成接口
        
        Args:
            messages: 消息列表
            temperature: 温度参数
            max_tokens: 最大生成token数
            **kwargs: 其他参数
            
        Returns:
            模型响应
        """
        if not self.model_adapter:
            raise RuntimeError("模型适配器未初始化")
        
        if temperature is None:
            temperature = self.config.get("default_temperature", 0.7)
        if max_tokens is None:
            max_tokens = self.config.get("default_max_tokens", 1024)
        
        self._log("debug", f"直接聊天完成，消息数: {len(messages)}")
        
        try:
            response = self.model_adapter.chat_completion(
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                **kwargs
            )
            
            # 记录交互
            self._log_interaction(
                "chat_completion",
                {"messages_count": len(messages), "temperature": temperature, "max_tokens": max_tokens},
                response.text,
                {"model": self.model_adapter.model_name, "tokens_used": response.tokens_used}
            )
            
            return response
            
        except Exception as e:
            self._log("error", f"聊天完成失败: {str(e)}")
            raise
    
    def simple_query(self, query: str, system_prompt: str = None, extra_messages: list = None) -> str:
        """
        简单查询接口

        Args:
            query: 查询文本
            system_prompt: 系统提示（可选）
            extra_messages: 额外的消息列表（可选），如对话历史。

        Returns:
            模型生成的文本
        """
        if not self.model_adapter:
            return f"模型适配器未初始化，无法处理查询: {query}"

        self._log("debug", f"简单查询: {query[:30]}...")

        try:
            response = self.model_adapter.simple_query(query, system_prompt, extra_messages)

            # 记录交互
            self._log_interaction(
                "simple_query",
                {"query": query, "system_prompt": system_prompt,
                 "history_count": len(extra_messages) if extra_messages else 0},
                response,
                {"model": self.model_adapter.model_name}
            )

            return response

        except Exception as e:
            self._log("error", f"简单查询失败: {str(e)}")
            return f"查询失败: {str(e)}"

    def chat_with_tools(self, messages: list, tools: list,
                        tool_executor: callable = None,
                        max_rounds: int = 50,
                        stream_callback: callable = None,
                        plan_callback: callable = None) -> dict:
        """
        带工具调用的对话接口（支持 Function Calling 循环 + 流式推理）。

        流程：发送消息+工具定义 → DeepSeek 可能返回 tool_calls →
        执行工具 → 结果发回 → DeepSeek 继续 → 直到返回纯文本。

        Args:
            messages: 消息列表
            tools: 工具定义列表（OpenAI Function Calling 格式）
            tool_executor: 工具执行回调，接收 (tool_name, args_dict) 返回结果字符串
            max_rounds: 最大工具调用轮数
            stream_callback: 流式回调，接收 (chunk_type, text)，用于实时展示思考过程
            plan_callback: 计划回调，接收 (plan_text)，首次返回计划时触发

        Returns:
            最终回复文本
        """
        if not self.model_adapter:
            return "模型适配器未初始化"

        for round_num in range(max_rounds):
            self._log("info", f"LLM 调用轮次 #{round_num + 1}, 消息数: {len(messages)}")
            try:
                # 所有轮次均启用流式回调，确保最终回答也能实时展示
                use_stream = stream_callback is not None
                resp = self.model_adapter.chat_completion(
                    messages, temperature=0.7,
                    max_tokens=self.config.get("default_max_tokens", 4096),
                    tools=tools,
                    stream_callback=stream_callback if use_stream else None,
                )

                text = resp.text or ""
                reasoning = resp.metadata.get("reasoning", "")
                tool_calls = resp.metadata.get("tool_calls", [])
                is_tool_call = resp.finish_reason == "tool_calls" or bool(tool_calls)

                if reasoning:
                    self._log("debug", f"  → 推理: {reasoning[:100]}...")
                if text:
                    self._log("debug", f"  → 文本: {text[:80]}...")

                if not is_tool_call:
                    self._log("info", f"  → 纯文本回复 (长度 {len(text)})")
                    return {"text": text, "reasoning": reasoning}  # 纯文本回复，完成

                # 首次返回计划（DeepSeek 在 tool_calls 前通常会描述计划）
                if round_num == 0 and plan_callback and text:
                    plan_callback(text)

                # 有工具调用 → 执行并追加结果

                # 去重：合并相同工具+相同参数的调用
                seen = set()
                unique_tool_calls = []
                for tc in tool_calls:
                    key = f"{tc['function']['name']}({tc['function']['arguments'][:100]})"
                    if key not in seen:
                        seen.add(key)
                        unique_tool_calls.append(tc)
                if len(unique_tool_calls) < len(tool_calls):
                    self._log("info", f"  去重: {len(tool_calls)}→{len(unique_tool_calls)} 个工具调用")
                    tool_calls = unique_tool_calls

                # DeepSeek 要求：多轮工具调用必须传回 reasoning_content
                asst_msg = {
                    "role": "assistant",
                    "content": text if text else None,
                }
                if tool_calls:
                    asst_msg["tool_calls"] = tool_calls
                if reasoning:
                    asst_msg["reasoning_content"] = reasoning
                messages.append(asst_msg)

                # 检测重复工具调用（跨轮次比较）
                self._last_tool_sigs = getattr(self, '_last_tool_sigs', [])
                current_sigs = sorted([
                    f"{tc['function']['name']}({tc['function']['arguments'][:50]})"
                    for tc in tool_calls
                ])
                if self._last_tool_sigs and current_sigs == self._last_tool_sigs:
                    self._log("warning", "检测到工具调用循环（连续两轮相同），强制退出")
                    sig_detail = current_sigs[0][:100] if current_sigs else ""
                    last_text = ""
                    if len(messages) >= 2 and messages[-2].get("role") == "assistant":
                        last_text = (messages[-2].get("content") or "")[:500]
                    if last_text:
                        return {"text": f"{last_text}\n\n[检测到工具调用循环，已中断]", "reasoning": ""}
                    # 按工具类型汇总输出
                    op_counts = {}
                    file_ops = []
                    for mi in range(len(messages)):
                        if messages[mi].get("role") == "tool" and messages[mi].get("content"):
                            c = str(messages[mi]["content"])
                            if c.startswith("找到"):
                                name = c.split(chr(10))[0][:50] if chr(10) in c else c[:50]
                                op_counts["搜索"] = op_counts.get("搜索", 0) + 1
                                file_ops.append(f"  • {name}")
                            elif c.startswith("已写入"):
                                op_counts["写入"] = op_counts.get("写入", 0) + 1
                                file_ops.append(f"  • {c[:70]}")
                            elif c.startswith("已保存"):
                                op_counts["记忆"] = op_counts.get("记忆", 0) + 1
                            elif c.startswith("错误") or c.startswith("执行失败"):
                                op_counts["失败"] = op_counts.get("失败", 0) + 1
                            elif c.startswith("{") or c.startswith("命令"):
                                op_counts["命令"] = op_counts.get("命令", 0) + 1
                                so_idx = c.find("'stdout': '")
                                if so_idx >= 0:
                                    snippet = c[so_idx+11:so_idx+70]
                                    file_ops.append(f"  • 命令: {snippet}")
                            else:
                                op_counts["读取"] = op_counts.get("读取", 0) + 1
                    if op_counts:
                        counts = " | ".join([f"{k}×{v}" for k, v in sorted(op_counts.items())])
                        lines = [f"已完成: {counts}"]
                        lines.extend(file_ops[:10])
                        if len(file_ops) > 10:
                            lines.append(f"  ... 还有 {len(file_ops) - 10} 项")
                        return {"text": chr(10).join(lines), "reasoning": ""}
                    return {"text": f"遇到工具调用异常，已中断。\n重复调用的工具: {sig_detail}\n\n建议：确认文件路径是否正确，或换个方式描述需求。", "reasoning": ""}
                self._last_tool_sigs = current_sigs

                for tc in tool_calls:
                    func_name = tc["function"]["name"]
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        args_str = {k: (str(v)[:80] + "..." if len(str(v)) > 80 else str(v)) for k, v in args.items()}
                        self._log("info", f"  → 工具调用: {func_name}({args_str})")
                        if tool_executor:
                            result = tool_executor(func_name, args)
                            self._log("info", f"  → 工具结果 ({func_name}): {str(result)[:120]}")
                        else:
                            result = f"未知工具: {func_name}"
                    except json.JSONDecodeError as e:
                        # JSON 解析失败：给出明确的格式提示，帮助模型自纠
                        self._log("error", f"  → 参数 JSON 解析失败 ({func_name}): {e}")
                        # 从工具定义中提取期望的参数结构
                        schema_hint = ""
                        for t_def in (tools or []):
                            if t_def.get("function", {}).get("name") == func_name:
                                props = t_def["function"].get("parameters", {}).get("properties", {})
                                schema_hint = ", ".join(
                                    f"{k} ({v.get('type','string')})" for k, v in props.items()
                                )
                                break
                        result = (
                            f"参数格式错误: 传给 {func_name} 的 arguments 不是合法的 JSON。\n"
                            f"期望的参数: {schema_hint or '参考工具定义'}\n"
                            f"解析错误: {e}\n"
                            f"请重新生成工具调用，确保 arguments 是合法 JSON 字符串，"
                            f"字符串值内的引号/反斜杠/换行需正确转义（用 \\\" 和 \\\\ 和 \\n）"
                        )
                    except Exception as e:
                        self._log("error", f"  → 工具执行异常: {e}")
                        result = f"执行出错: {e}"

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": str(result),
                    })

            except Exception as e:
                self._log("error", f"工具对话失败: {e}")
                return {"text": f"查询失败: {e}", "reasoning": ""}

        return {"text": "已达最大工具调用轮数", "reasoning": ""}

    def health_check(self) -> Dict[str, Any]:
        """
        健康检查
        
        Returns:
            健康状态信息
        """
        health_info = {
            "timestamp": datetime.now().isoformat(),
            "brain_engine": {
                "initialized": self.model_adapter is not None,
                "config": {
                    "model_provider": self.config.get("model_provider"),
                    "model_name": self.config.get("model_name"),
                },
                "interaction_history_count": len(self.interaction_history),
            }
        }
        
        if self.model_adapter:
            try:
                model_health = self.model_adapter.health_check()
                health_info["model_adapter"] = model_health
                health_info["overall_status"] = model_health.get("status", "unknown")
            except Exception as e:
                health_info["model_adapter"] = {
                    "status": "error",
                    "error": str(e)
                }
                health_info["overall_status"] = "error"
        else:
            health_info["model_adapter"] = {
                "status": "not_initialized",
                "error": "模型适配器未初始化"
            }
            health_info["overall_status"] = "not_initialized"
        
        return health_info
    
    def get_interaction_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """
        获取交互历史
        
        Args:
            limit: 返回数量限制
            
        Returns:
            交互历史列表
        """
        history = self.interaction_history.copy()
        history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        return history[:limit]
    
    def clear_interaction_history(self):
        """清空交互历史"""
        self.interaction_history.clear()
        self._log("info", "交互历史已清空")


# 便捷函数
def create_brain_engine(config: Dict[str, Any] = None) -> BrainEngine:
    """
    创建大脑引擎的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        大脑引擎实例
    """
    return BrainEngine(config)