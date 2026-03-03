"""
反思引擎核心模块

基于Reflexion算法实现任务执行后的自我反思和分析。
"""

from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
from enum import Enum
import time
import uuid
from dataclasses import dataclass, field


class ReflectionTrigger(Enum):
    """反思触发器类型"""
    TASK_FAILURE = "task_failure"           # 任务失败
    LOW_CONFIDENCE = "low_confidence"       # 低置信度
    USER_FEEDBACK = "user_feedback"         # 用户反馈不满意
    PERIODIC_REVIEW = "periodic_review"     # 定期回顾
    CONSTRAINT_VIOLATION = "constraint_violation"  # 约束违反
    RESOURCE_EXCEEDED = "resource_exceeded"  # 资源超限


@dataclass
class ReflectionResult:
    """反思结果"""
    id: str
    task_id: str
    trigger: ReflectionTrigger
    timestamp: datetime
    analysis: str  # 问题分析
    root_causes: List[str]  # 根本原因
    suggestions: List[str]  # 改进建议
    confidence_impact: float  # 对后续规划置信度的影响（0.0-1.0）
    applied: bool = False  # 是否已应用
    applied_at: Optional[datetime] = None
    applied_results: Optional[List[str]] = None  # 应用后的结果


class ReflectionEngine:
    """反思引擎主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化反思引擎
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "enable_auto_reflection": True,
            "reflection_triggers": ["task_failure", "low_confidence", "user_feedback"],
            "max_reflection_iterations": 3,
            "reflection_confidence_threshold": 0.7,
            "save_reflection_history": True,
            "reflection_depth": 2,  # 反思深度（浅层/深层）
            "learning_enabled": True,
            "min_time_between_reflections": 60,  # 最小反思间隔（秒）
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 状态跟踪
        self.reflection_history: List[ReflectionResult] = []
        self.task_reflection_counts: Dict[str, int] = {}  # 任务反思次数
        self.last_reflection_time: Dict[str, datetime] = {}  # 上次反思时间
        
        # 组件引用
        self.learning_module = None
        self.knowledge_updater = None
        self.logger = None
    
    def set_components(self, learning_module=None, knowledge_updater=None):
        """设置依赖组件"""
        self.learning_module = learning_module
        self.knowledge_updater = knowledge_updater
    
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
    
    def should_reflect(self, 
                       task_id: str, 
                       task_result: Dict[str, Any], 
                       trigger: ReflectionTrigger) -> bool:
        """
        判断是否应该触发反思
        
        Args:
            task_id: 任务ID
            task_result: 任务执行结果
            trigger: 触发器类型
            
        Returns:
            bool: 是否应该触发反思
        """
        # 检查是否启用自动反思
        if not self.config["enable_auto_reflection"]:
            return False
        
        # 检查触发器是否在配置中
        if trigger.value not in self.config.get("reflection_triggers", []):
            return False
        
        # 检查反思次数限制
        reflection_count = self.task_reflection_counts.get(task_id, 0)
        if reflection_count >= self.config["max_reflection_iterations"]:
            self._log("debug", f"任务 {task_id} 已达到最大反思次数限制")
            return False
        
        # 检查时间间隔
        last_time = self.last_reflection_time.get(task_id)
        if last_time:
            time_since_last = (datetime.now() - last_time).total_seconds()
            if time_since_last < self.config["min_time_between_reflections"]:
                self._log("debug", f"任务 {task_id} 距离上次反思时间过短: {time_since_last:.1f}秒")
                return False
        
        # 根据触发器类型检查特定条件
        if trigger == ReflectionTrigger.TASK_FAILURE:
            return task_result.get("status") == "failed"
        
        elif trigger == ReflectionTrigger.LOW_CONFIDENCE:
            confidence = task_result.get("confidence", 1.0)
            threshold = self.config.get("reflection_confidence_threshold", 0.7)
            return confidence < threshold
        
        elif trigger == ReflectionTrigger.USER_FEEDBACK:
            feedback = task_result.get("user_feedback")
            return feedback is not None and feedback.get("satisfaction", 1) < 3  # 假设满意度1-5分
        
        elif trigger == ReflectionTrigger.CONSTRAINT_VIOLATION:
            constraints = task_result.get("violated_constraints", [])
            return len(constraints) > 0
        
        elif trigger == ReflectionTrigger.RESOURCE_EXCEEDED:
            resources = task_result.get("exceeded_resources", {})
            return len(resources) > 0
        
        elif trigger == ReflectionTrigger.PERIODIC_REVIEW:
            # 定期回顾，例如每10个任务或每天一次
            return True
        
        return False
    
    def reflect(self, 
                task_id: str, 
                task_result: Dict[str, Any], 
                trigger: ReflectionTrigger,
                context: Optional[Dict[str, Any]] = None) -> Optional[ReflectionResult]:
        """
        执行反思
        
        Args:
            task_id: 任务ID
            task_result: 任务执行结果
            trigger: 触发器类型
            context: 上下文信息
            
        Returns:
            ReflectionResult: 反思结果，如果反思未触发则返回None
        """
        # 检查是否应该触发反思
        if not self.should_reflect(task_id, task_result, trigger):
            return None
        
        self._log("info", f"开始反思任务 {task_id}, 触发器: {trigger.value}")
        
        # 生成反思ID
        reflection_id = f"reflection_{uuid.uuid4().hex[:8]}"
        
        # 执行反思分析
        analysis_result = self._analyze_failure(task_result, trigger, context)
        
        # 创建反思结果
        reflection_result = ReflectionResult(
            id=reflection_id,
            task_id=task_id,
            trigger=trigger,
            timestamp=datetime.now(),
            analysis=analysis_result["analysis"],
            root_causes=analysis_result["root_causes"],
            suggestions=analysis_result["suggestions"],
            confidence_impact=analysis_result["confidence_impact"],
            applied=False
        )
        
        # 更新状态跟踪
        self.reflection_history.append(reflection_result)
        self.task_reflection_counts[task_id] = self.task_reflection_counts.get(task_id, 0) + 1
        self.last_reflection_time[task_id] = datetime.now()
        
        # 如果启用了学习模块，将反思结果传递给学习模块
        if self.learning_module and self.config.get("learning_enabled", True):
            learning_outcome = self.learning_module.learn_from_reflection(reflection_result, task_result)
            self._log("debug", f"学习模块生成结果: {learning_outcome.summary}")
            
            # 如果启用了知识更新器，更新知识库
            if self.knowledge_updater:
                self.knowledge_updater.update_knowledge(reflection_result, learning_outcome)
        
        self._log("info", f"反思完成: {reflection_id}, 分析: {analysis_result['analysis'][:50]}...")
        
        return reflection_result
    
    def _analyze_failure(self, 
                         task_result: Dict[str, Any], 
                         trigger: ReflectionTrigger,
                         context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        分析失败原因并生成改进建议
        
        Args:
            task_result: 任务执行结果
            trigger: 触发器类型
            context: 上下文信息
            
        Returns:
            Dict[str, Any]: 分析结果
        """
        # 简化版分析逻辑（实际实现中应该使用更复杂的分析算法）
        
        if trigger == ReflectionTrigger.TASK_FAILURE:
            return self._analyze_task_failure(task_result, context)
        
        elif trigger == ReflectionTrigger.LOW_CONFIDENCE:
            return self._analyze_low_confidence(task_result, context)
        
        elif trigger == ReflectionTrigger.USER_FEEDBACK:
            return self._analyze_user_feedback(task_result, context)
        
        elif trigger == ReflectionTrigger.CONSTRAINT_VIOLATION:
            return self._analyze_constraint_violation(task_result, context)
        
        elif trigger == ReflectionTrigger.RESOURCE_EXCEEDED:
            return self._analyze_resource_exceeded(task_result, context)
        
        elif trigger == ReflectionTrigger.PERIODIC_REVIEW:
            return self._analyze_periodic_review(task_result, context)
        
        # 默认分析
        return {
            "analysis": "检测到问题需要反思，但无法确定具体原因。",
            "root_causes": ["未知原因"],
            "suggestions": ["检查任务执行日志，收集更多信息"],
            "confidence_impact": 0.1,
        }
    
    def _analyze_task_failure(self, task_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """分析任务失败原因"""
        error_message = task_result.get("error", "未知错误")
        failed_step = task_result.get("failed_step", "未知步骤")
        
        analysis = f"任务在执行步骤'{failed_step}'时失败，错误信息: {error_message}"
        
        # 常见错误模式识别
        root_causes = []
        suggestions = []
        
        if "timeout" in error_message.lower():
            root_causes.append("执行超时")
            suggestions.append("增加步骤执行时间限制")
            suggestions.append("分解复杂步骤为更小的子步骤")
        
        if "permission" in error_message.lower():
            root_causes.append("权限不足")
            suggestions.append("检查执行权限设置")
            suggestions.append("使用更高权限执行或修改资源权限")
        
        if "not found" in error_message.lower() or "missing" in error_message.lower():
            root_causes.append("资源不存在")
            suggestions.append("检查资源路径或名称是否正确")
            suggestions.append("在执行前验证资源可用性")
        
        if "connection" in error_message.lower() or "network" in error_message.lower():
            root_causes.append("网络连接问题")
            suggestions.append("检查网络连接")
            suggestions.append("添加重试机制")
            suggestions.append("使用本地替代方案")
        
        if not root_causes:
            root_causes = ["执行错误"]
            suggestions = ["查看详细错误日志", "简化任务步骤", "添加错误恢复机制"]
        
        return {
            "analysis": analysis,
            "root_causes": root_causes,
            "suggestions": suggestions,
            "confidence_impact": 0.3,  # 任务失败对置信度影响较大
        }
    
    def _analyze_low_confidence(self, task_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """分析低置信度原因"""
        confidence = task_result.get("confidence", 0)
        
        analysis = f"任务规划置信度较低 ({confidence:.1%})，可能影响执行效果"
        
        root_causes = []
        suggestions = []
        
        # 分析可能的低置信度原因
        if confidence < 0.5:
            root_causes.append("任务复杂度高")
            suggestions.append("分解任务为更简单的子任务")
            suggestions.append("收集更多上下文信息")
        
        if task_result.get("ambiguous_requirements", False):
            root_causes.append("需求不明确")
            suggestions.append("请求用户提供更详细的需求")
            suggestions.append("通过提问澄清模糊点")
        
        if task_result.get("insufficient_information", False):
            root_causes.append("信息不足")
            suggestions.append("在执行前收集必要信息")
            suggestions.append("使用默认值或假设")
        
        if not root_causes:
            root_causes = ["规划不确定性高"]
            suggestions = ["探索更多备选方案", "增加规划深度", "调整规划参数"]
        
        return {
            "analysis": analysis,
            "root_causes": root_causes,
            "suggestions": suggestions,
            "confidence_impact": 0.2,
        }
    
    def _analyze_user_feedback(self, task_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """分析用户反馈"""
        feedback = task_result.get("user_feedback", {})
        satisfaction = feedback.get("satisfaction", 3)
        comments = feedback.get("comments", "")
        
        analysis = f"用户反馈不满意 (满意度: {satisfaction}/5)，评论: {comments}"
        
        root_causes = []
        suggestions = []
        
        # 分析常见反馈问题
        if "slow" in comments.lower() or "慢" in comments:
            root_causes.append("响应速度慢")
            suggestions.append("优化算法性能")
            suggestions.append("添加进度提示")
        
        if "complex" in comments.lower() or "复杂" in comments:
            root_causes.append("交互复杂")
            suggestions.append("简化用户界面")
            suggestions.append("提供更清晰的指导")
        
        if "wrong" in comments.lower() or "错误" in comments or "不准确" in comments:
            root_causes.append("结果不准确")
            suggestions.append("改进算法准确性")
            suggestions.append("添加结果验证")
        
        if "not what i wanted" in comments.lower() or "不是我想要的" in comments:
            root_causes.append("需求理解偏差")
            suggestions.append("改进意图识别")
            suggestions.append("增加确认步骤")
        
        if not root_causes:
            root_causes = ["用户体验问题"]
            suggestions = ["收集更多用户反馈", "改进交互设计", "提供更好的错误处理"]
        
        return {
            "analysis": analysis,
            "root_causes": root_causes,
            "suggestions": suggestions,
            "confidence_impact": 0.25,
        }
    
    def _analyze_constraint_violation(self, task_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """分析约束违反"""
        violated_constraints = task_result.get("violated_constraints", [])
        
        analysis = f"任务违反了 {len(violated_constraints)} 个约束条件"
        
        root_causes = []
        suggestions = []
        
        for constraint in violated_constraints:
            constraint_type = constraint.get("type", "未知")
            constraint_desc = constraint.get("description", "")
            
            root_causes.append(f"违反约束: {constraint_type} - {constraint_desc}")
            
            if constraint_type == "time":
                suggestions.append("优化时间规划")
                suggestions.append("重新评估时间估计")
            
            elif constraint_type == "budget":
                suggestions.append("重新评估预算")
                suggestions.append("寻找更经济的解决方案")
            
            elif constraint_type == "resource":
                suggestions.append("检查资源可用性")
                suggestions.append("寻找替代资源")
            
            elif constraint_type == "quality":
                suggestions.append("提高质量标准")
                suggestions.append("添加质量控制步骤")
        
        if not root_causes:
            root_causes = ["约束条件无法满足"]
            suggestions = ["重新评估约束条件", "与用户协商调整约束"]
        
        return {
            "analysis": analysis,
            "root_causes": root_causes,
            "suggestions": suggestions,
            "confidence_impact": 0.35,
        }
    
    def _analyze_resource_exceeded(self, task_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """分析资源超限"""
        exceeded_resources = task_result.get("exceeded_resources", {})
        
        analysis = f"任务超出了 {len(exceeded_resources)} 种资源限制"
        
        root_causes = []
        suggestions = []
        
        for resource_type, usage in exceeded_resources.items():
            if resource_type == "memory":
                root_causes.append("内存使用超限")
                suggestions.append("优化内存使用")
                suggestions.append("增加内存限制或使用内存管理技术")
            
            elif resource_type == "cpu":
                root_causes.append("CPU使用超限")
                suggestions.append("优化算法复杂度")
                suggestions.append("使用异步处理或分批处理")
            
            elif resource_type == "time":
                root_causes.append("执行时间超限")
                suggestions.append("优化执行效率")
                suggestions.append("设置超时机制")
            
            elif resource_type == "storage":
                root_causes.append("存储空间不足")
                suggestions.append("清理临时文件")
                suggestions.append("使用压缩或外部存储")
        
        if not root_causes:
            root_causes = ["资源使用超预期"]
            suggestions = ["重新评估资源需求", "优化资源管理"]
        
        return {
            "analysis": analysis,
            "root_causes": root_causes,
            "suggestions": suggestions,
            "confidence_impact": 0.3,
        }
    
    def _analyze_periodic_review(self, task_result: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """分析定期回顾"""
        # 定期回顾的分析更侧重于整体改进
        
        analysis = "定期性能回顾：检查系统整体表现和改进机会"
        
        root_causes = [
            "系统持续运行可能积累问题",
            "性能和效果可能随时间变化",
            "用户需求和环境可能发生变化"
        ]
        
        suggestions = [
            "定期清理日志和临时文件",
            "更新算法和模型参数",
            "收集用户反馈并改进系统",
            "监控系统性能和资源使用",
            "备份重要数据和配置"
        ]
        
        return {
            "analysis": analysis,
            "root_causes": root_causes,
            "suggestions": suggestions,
            "confidence_impact": 0.1,
        }
    
    def apply_reflection_result(self, reflection_id: str, application_context: Dict[str, Any]) -> bool:
        """
        应用反思结果
        
        Args:
            reflection_id: 反思ID
            application_context: 应用上下文
            
        Returns:
            bool: 是否成功应用
        """
        # 查找反思结果
        reflection = None
        for ref in self.reflection_history:
            if ref.id == reflection_id:
                reflection = ref
                break
        
        if not reflection:
            self._log("error", f"找不到反思结果: {reflection_id}")
            return False
        
        if reflection.applied:
            self._log("warning", f"反思结果 {reflection_id} 已经应用过")
            return False
        
        # 应用反思建议
        self._log("info", f"应用反思结果 {reflection_id}: {reflection.analysis[:50]}...")
        
        # 在实际实现中，这里应该将反思结果应用到规划引擎或任务执行器
        # 这里简化处理，只是标记为已应用
        
        reflection.applied = True
        reflection.applied_at = datetime.now()
        reflection.applied_results = ["反思建议已应用到系统配置"]
        
        # 如果有知识更新器，通知它反思已应用
        if self.knowledge_updater:
            self.knowledge_updater.mark_reflection_applied(reflection_id)
        
        return True
    
    def get_reflection_history(self, task_id: Optional[str] = None, limit: int = 10) -> List[ReflectionResult]:
        """
        获取反思历史
        
        Args:
            task_id: 任务ID（如果为None则返回所有）
            limit: 返回数量限制
            
        Returns:
            List[ReflectionResult]: 反思历史列表
        """
        if task_id:
            history = [r for r in self.reflection_history if r.task_id == task_id]
        else:
            history = self.reflection_history.copy()
        
        # 按时间倒序排序
        history.sort(key=lambda x: x.timestamp, reverse=True)
        
        return history[:limit]
    
    def get_reflection_stats(self) -> Dict[str, Any]:
        """获取反思统计信息"""
        total_reflections = len(self.reflection_history)
        applied_reflections = sum(1 for r in self.reflection_history if r.applied)
        
        # 按触发器类型统计
        trigger_counts = {}
        for reflection in self.reflection_history:
            trigger = reflection.trigger.value
            trigger_counts[trigger] = trigger_counts.get(trigger, 0) + 1
        
        return {
            "total_reflections": total_reflections,
            "applied_reflections": applied_reflections,
            "application_rate": applied_reflections / total_reflections if total_reflections > 0 else 0,
            "trigger_counts": trigger_counts,
            "most_reflected_task": max(self.task_reflection_counts.items(), key=lambda x: x[1])[0] if self.task_reflection_counts else None,
        }


# 便捷函数
def create_reflection_engine(config: Dict[str, Any] = None) -> ReflectionEngine:
    """
    创建反思引擎的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        反思引擎实例
    """
    return ReflectionEngine(config)