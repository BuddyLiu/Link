"""
反思学习模块

从反思结果中学习，生成可复用的知识和策略改进。
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
from dataclasses import dataclass, field
import uuid
import json
from enum import Enum


class LearningType(Enum):
    """学习类型"""
    PATTERN_RECOGNITION = "pattern_recognition"  # 模式识别
    STRATEGY_IMPROVEMENT = "strategy_improvement"  # 策略改进
    CONSTRAINT_ADJUSTMENT = "constraint_adjustment"  # 约束调整
    RESOURCE_OPTIMIZATION = "resource_optimization"  # 资源优化
    ERROR_RECOVERY = "error_recovery"  # 错误恢复


@dataclass
class LearningOutcome:
    """学习结果"""
    id: str
    learning_type: LearningType
    summary: str  # 学习总结
    key_insights: List[str]  # 关键洞察
    action_items: List[str]  # 行动项
    confidence: float  # 学习置信度 (0.0-1.0)
    applicability_score: float  # 适用性评分 (0.0-1.0)
    created_at: datetime
    applied: bool = False  # 是否已应用
    applied_contexts: List[str] = field(default_factory=list)  # 已应用到的上下文


class LearningModule:
    """学习模块主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化学习模块
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "enable_learning": True,
            "learning_depth": 2,  # 学习深度
            "min_confidence_threshold": 0.6,  # 最小置信度阈值
            "max_learning_items": 100,  # 最大学习项数量
            "pattern_extraction_enabled": True,  # 是否启用模式提取
            "strategy_optimization_enabled": True,  # 是否启用策略优化
            "knowledge_consolidation_interval": 3600,  # 知识整合间隔（秒）
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 学习存储
        self.learning_outcomes: List[LearningOutcome] = []
        self.learning_patterns: Dict[str, List[Dict[str, Any]]] = {}  # 学习模式
        self.strategy_improvements: Dict[str, Any] = {}  # 策略改进
        
        # 状态跟踪
        self.last_consolidation_time = datetime.now()
        self.logger = None
    
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
    
    def learn_from_reflection(self, 
                              reflection_result: Any, 
                              task_result: Dict[str, Any]) -> LearningOutcome:
        """
        从反思结果中学习
        
        Args:
            reflection_result: 反思结果
            task_result: 任务执行结果
            
        Returns:
            LearningOutcome: 学习结果
        """
        if not self.config["enable_learning"]:
            return self._create_default_learning_outcome("学习功能已禁用")
        
        self._log("info", f"从反思中学习: {reflection_result.id}")
        
        # 确定学习类型
        learning_type = self._determine_learning_type(reflection_result, task_result)
        
        # 执行学习分析
        learning_analysis = self._analyze_for_learning(reflection_result, task_result, learning_type)
        
        # 创建学习结果
        learning_outcome = LearningOutcome(
            id=f"learning_{uuid.uuid4().hex[:8]}",
            learning_type=learning_type,
            summary=learning_analysis["summary"],
            key_insights=learning_analysis["key_insights"],
            action_items=learning_analysis["action_items"],
            confidence=learning_analysis["confidence"],
            applicability_score=learning_analysis["applicability_score"],
            created_at=datetime.now(),
            applied=False
        )
        
        # 存储学习结果
        self.learning_outcomes.append(learning_outcome)
        
        # 提取和存储学习模式
        if self.config["pattern_extraction_enabled"]:
            self._extract_learning_patterns(learning_outcome, reflection_result, task_result)
        
        # 生成策略改进
        if self.config["strategy_optimization_enabled"]:
            self._generate_strategy_improvements(learning_outcome, reflection_result, task_result)
        
        # 检查是否需要知识整合
        self._check_knowledge_consolidation()
        
        self._log("info", f"学习完成: {learning_outcome.id}, 类型: {learning_type.value}")
        
        return learning_outcome
    
    def _determine_learning_type(self, reflection_result: Any, task_result: Dict[str, Any]) -> LearningType:
        """确定学习类型"""
        trigger = reflection_result.trigger.value
        
        # 根据触发器和任务结果确定学习类型
        if trigger == "task_failure":
            # 分析失败类型
            error_msg = str(task_result.get("error", "")).lower()
            
            if any(keyword in error_msg for keyword in ["timeout", "time out"]):
                return LearningType.RESOURCE_OPTIMIZATION
            
            elif any(keyword in error_msg for keyword in ["permission", "access denied"]):
                return LearningType.CONSTRAINT_ADJUSTMENT
            
            elif any(keyword in error_msg for keyword in ["not found", "missing", "no such"]):
                return LearningType.PATTERN_RECOGNITION
            
            elif any(keyword in error_msg for keyword in ["connection", "network", "disconnect"]):
                return LearningType.ERROR_RECOVERY
            
            else:
                return LearningType.STRATEGY_IMPROVEMENT
        
        elif trigger == "low_confidence":
            return LearningType.STRATEGY_IMPROVEMENT
        
        elif trigger == "user_feedback":
            return LearningType.STRATEGY_IMPROVEMENT
        
        elif trigger == "constraint_violation":
            return LearningType.CONSTRAINT_ADJUSTMENT
        
        elif trigger == "resource_exceeded":
            return LearningType.RESOURCE_OPTIMIZATION
        
        elif trigger == "periodic_review":
            return LearningType.PATTERN_RECOGNITION
        
        # 默认类型
        return LearningType.STRATEGY_IMPROVEMENT
    
    def _analyze_for_learning(self, 
                              reflection_result: Any, 
                              task_result: Dict[str, Any],
                              learning_type: LearningType) -> Dict[str, Any]:
        """为学习进行分析"""
        
        if learning_type == LearningType.PATTERN_RECOGNITION:
            return self._analyze_pattern_recognition(reflection_result, task_result)
        
        elif learning_type == LearningType.STRATEGY_IMPROVEMENT:
            return self._analyze_strategy_improvement(reflection_result, task_result)
        
        elif learning_type == LearningType.CONSTRAINT_ADJUSTMENT:
            return self._analyze_constraint_adjustment(reflection_result, task_result)
        
        elif learning_type == LearningType.RESOURCE_OPTIMIZATION:
            return self._analyze_resource_optimization(reflection_result, task_result)
        
        elif learning_type == LearningType.ERROR_RECOVERY:
            return self._analyze_error_recovery(reflection_result, task_result)
        
        # 默认分析
        return {
            "summary": f"从反思中学到: {reflection_result.analysis[:100]}...",
            "key_insights": ["需要进一步分析以提取具体洞察"],
            "action_items": ["收集更多数据进行深入分析"],
            "confidence": 0.5,
            "applicability_score": 0.3,
        }
    
    def _analyze_pattern_recognition(self, reflection_result: Any, task_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析模式识别"""
        
        # 分析重复出现的模式
        patterns = []
        
        # 检查是否有重复的错误模式
        error_message = str(task_result.get("error", "")).lower()
        
        if "timeout" in error_message:
            patterns.append("超时模式：某些操作经常超时")
        
        if "not found" in error_message or "missing" in error_message:
            patterns.append("资源缺失模式：某些资源经常不存在")
        
        if "permission" in error_message:
            patterns.append("权限模式：权限不足是常见问题")
        
        if "connection" in error_message:
            patterns.append("连接模式：网络连接不稳定")
        
        summary = f"识别到 {len(patterns)} 个重复模式"
        
        key_insights = [
            "某些问题模式可能重复出现",
            "相似的任务类型可能面临相似的问题",
            "历史数据可以帮助预测和避免常见问题"
        ]
        
        action_items = [
            "记录常见错误模式及其解决方案",
            "建立问题模式库",
            "为常见模式开发预定义解决方案"
        ]
        
        confidence = 0.7 if len(patterns) > 0 else 0.4
        applicability_score = 0.6 if len(patterns) > 0 else 0.3
        
        return {
            "summary": summary,
            "key_insights": key_insights,
            "action_items": action_items,
            "confidence": confidence,
            "applicability_score": applicability_score,
        }
    
    def _analyze_strategy_improvement(self, reflection_result: Any, task_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析策略改进"""
        
        # 分析策略问题
        strategy_issues = []
        
        # 从反思建议中提取策略改进点
        for suggestion in reflection_result.suggestions:
            if "分解" in suggestion or "简化" in suggestion:
                strategy_issues.append("任务分解策略需要优化")
            elif "验证" in suggestion or "检查" in suggestion:
                strategy_issues.append("验证机制需要加强")
            elif "重试" in suggestion or "恢复" in suggestion:
                strategy_issues.append("错误恢复策略不足")
            elif "收集" in suggestion or "信息" in suggestion:
                strategy_issues.append("信息收集策略需要改进")
        
        summary = f"识别到 {len(strategy_issues)} 个策略改进点"
        
        key_insights = [
            "当前策略在某些情况下效果不佳",
            "需要根据上下文调整策略",
            "策略的灵活性和适应性很重要"
        ]
        
        action_items = [
            "优化任务分解算法",
            "增强错误检测和恢复机制",
            "改进上下文信息收集策略",
            "建立策略性能评估机制"
        ]
        
        confidence = 0.75
        applicability_score = 0.7
        
        return {
            "summary": summary,
            "key_insights": key_insights,
            "action_items": action_items,
            "confidence": confidence,
            "applicability_score": applicability_score,
        }
    
    def _analyze_constraint_adjustment(self, reflection_result: Any, task_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析约束调整"""
        
        violated_constraints = task_result.get("violated_constraints", [])
        
        summary = f"检测到 {len(violated_constraints)} 个约束需要调整"
        
        key_insights = [
            "约束条件可能过于严格",
            "约束之间可能存在冲突",
            "约束需要根据实际情况动态调整"
        ]
        
        action_items = [
            "重新评估约束的合理性和必要性",
            "建立约束优先级机制",
            "开发约束协商和调整功能",
            "记录约束违反历史以优化约束设置"
        ]
        
        confidence = 0.8 if len(violated_constraints) > 0 else 0.5
        applicability_score = 0.65 if len(violated_constraints) > 0 else 0.4
        
        return {
            "summary": summary,
            "key_insights": key_insights,
            "action_items": action_items,
            "confidence": confidence,
            "applicability_score": applicability_score,
        }
    
    def _analyze_resource_optimization(self, reflection_result: Any, task_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析资源优化"""
        
        exceeded_resources = task_result.get("exceeded_resources", {})
        
        summary = f"检测到 {len(exceeded_resources)} 个资源需要优化"
        
        key_insights = [
            "资源使用可能效率低下",
            "资源分配策略需要优化",
            "资源监控和预警机制需要加强"
        ]
        
        action_items = [
            "优化算法以减少资源消耗",
            "实现资源使用监控和预警",
            "开发资源分配优化算法",
            "建立资源使用历史分析"
        ]
        
        confidence = 0.7 if len(exceeded_resources) > 0 else 0.4
        applicability_score = 0.6 if len(exceeded_resources) > 0 else 0.3
        
        return {
            "summary": summary,
            "key_insights": key_insights,
            "action_items": action_items,
            "confidence": confidence,
            "applicability_score": applicability_score,
        }
    
    def _analyze_error_recovery(self, reflection_result: Any, task_result: Dict[str, Any]) -> Dict[str, Any]:
        """分析错误恢复"""
        
        error_message = str(task_result.get("error", ""))
        
        summary = "错误恢复机制需要改进"
        
        key_insights = [
            "当前错误恢复机制可能不足",
            "某些错误类型需要特定的恢复策略",
            "错误预防比恢复更重要"
        ]
        
        action_items = [
            "分析常见错误类型及其恢复策略",
            "实现分层错误处理机制",
            "开发错误预防和预警功能",
            "建立错误恢复最佳实践库"
        ]
        
        confidence = 0.65
        applicability_score = 0.55
        
        return {
            "summary": summary,
            "key_insights": key_insights,
            "action_items": action_items,
            "confidence": confidence,
            "applicability_score": applicability_score,
        }
    
    def _extract_learning_patterns(self, 
                                   learning_outcome: LearningOutcome, 
                                   reflection_result: Any, 
                                   task_result: Dict[str, Any]):
        """提取学习模式"""
        
        pattern_type = learning_outcome.learning_type.value
        
        if pattern_type not in self.learning_patterns:
            self.learning_patterns[pattern_type] = []
        
        pattern = {
            "id": learning_outcome.id,
            "timestamp": datetime.now().isoformat(),
            "trigger": reflection_result.trigger.value,
            "task_type": task_result.get("task_type", "unknown"),
            "summary": learning_outcome.summary,
            "insights": learning_outcome.key_insights,
            "confidence": learning_outcome.confidence,
            "metadata": {
                "error": task_result.get("error", ""),
                "constraints": task_result.get("violated_constraints", []),
                "resources": task_result.get("exceeded_resources", {}),
            }
        }
        
        self.learning_patterns[pattern_type].append(pattern)
        
        # 限制模式数量
        max_patterns = self.config.get("max_learning_patterns", 50)
        if len(self.learning_patterns[pattern_type]) > max_patterns:
            self.learning_patterns[pattern_type] = self.learning_patterns[pattern_type][-max_patterns:]
    
    def _generate_strategy_improvements(self, 
                                        learning_outcome: LearningOutcome, 
                                        reflection_result: Any, 
                                        task_result: Dict[str, Any]):
        """生成策略改进"""
        
        improvement_key = f"{learning_outcome.learning_type.value}_{task_result.get('task_type', 'general')}"
        
        if improvement_key not in self.strategy_improvements:
            self.strategy_improvements[improvement_key] = {
                "count": 0,
                "last_updated": datetime.now().isoformat(),
                "suggestions": [],
                "confidence_scores": [],
                "applicability_scores": [],
            }
        
        improvement = self.strategy_improvements[improvement_key]
        improvement["count"] += 1
        improvement["last_updated"] = datetime.now().isoformat()
        
        # 添加学习结果中的行动项作为策略改进建议
        for action_item in learning_outcome.action_items:
            if action_item not in improvement["suggestions"]:
                improvement["suggestions"].append(action_item)
        
        improvement["confidence_scores"].append(learning_outcome.confidence)
        improvement["applicability_scores"].append(learning_outcome.applicability_score)
        
        # 计算平均分数
        if improvement["confidence_scores"]:
            improvement["avg_confidence"] = sum(improvement["confidence_scores"]) / len(improvement["confidence_scores"])
        if improvement["applicability_scores"]:
            improvement["avg_applicability"] = sum(improvement["applicability_scores"]) / len(improvement["applicability_scores"])
    
    def _check_knowledge_consolidation(self):
        """检查知识整合"""
        current_time = datetime.now()
        time_since_last = (current_time - self.last_consolidation_time).total_seconds()
        
        if time_since_last >= self.config.get("knowledge_consolidation_interval", 3600):
            self._consolidate_knowledge()
            self.last_consolidation_time = current_time
    
    def _consolidate_knowledge(self):
        """整合知识"""
        self._log("info", "开始知识整合")
        
        # 整合学习模式
        consolidated_patterns = {}
        for pattern_type, patterns in self.learning_patterns.items():
            if patterns:
                # 按置信度排序
                patterns.sort(key=lambda x: x.get("confidence", 0), reverse=True)
                # 保留高置信度模式
                consolidated_patterns[pattern_type] = patterns[:10]
        
        self.learning_patterns = consolidated_patterns
        
        # 整合策略改进
        consolidated_improvements = {}
        for key, improvement in self.strategy_improvements.items():
            if improvement["count"] >= 2:  # 至少出现2次才保留
                consolidated_improvements[key] = improvement
        
        self.strategy_improvements = consolidated_improvements
        
        self._log("info", f"知识整合完成: {len(consolidated_patterns)} 种模式, {len(consolidated_improvements)} 种策略")
    
    def _create_default_learning_outcome(self, reason: str) -> LearningOutcome:
        """创建默认学习结果"""
        return LearningOutcome(
            id=f"learning_default_{uuid.uuid4().hex[:4]}",
            learning_type=LearningType.STRATEGY_IMPROVEMENT,
            summary=reason,
            key_insights=["学习功能当前不可用"],
            action_items=["启用学习功能以获得更好的改进建议"],
            confidence=0.3,
            applicability_score=0.2,
            created_at=datetime.now(),
            applied=False
        )
    
    def get_learning_patterns(self, pattern_type: Optional[str] = None) -> Dict[str, Any]:
        """获取学习模式"""
        if pattern_type:
            return {pattern_type: self.learning_patterns.get(pattern_type, [])}
        return self.learning_patterns.copy()
    
    def get_strategy_improvements(self, task_type: Optional[str] = None) -> Dict[str, Any]:
        """获取策略改进"""
        if task_type:
            # 获取特定任务类型的改进
            matched_improvements = {}
            for key, improvement in self.strategy_improvements.items():
                if task_type in key:
                    matched_improvements[key] = improvement
            return matched_improvements
        
        return self.strategy_improvements.copy()
    
    def get_learning_stats(self) -> Dict[str, Any]:
        """获取学习统计信息"""
        total_outcomes = len(self.learning_outcomes)
        applied_outcomes = sum(1 for o in self.learning_outcomes if o.applied)
        
        # 按学习类型统计
        type_counts = {}
        for outcome in self.learning_outcomes:
            type_key = outcome.learning_type.value
            type_counts[type_key] = type_counts.get(type_key, 0) + 1
        
        # 模式统计
        total_patterns = sum(len(patterns) for patterns in self.learning_patterns.values())
        
        # 策略改进统计
        total_improvements = len(self.strategy_improvements)
        
        return {
            "total_learning_outcomes": total_outcomes,
            "applied_learning_outcomes": applied_outcomes,
            "application_rate": applied_outcomes / total_outcomes if total_outcomes > 0 else 0,
            "learning_type_counts": type_counts,
            "total_patterns": total_patterns,
            "pattern_types": list(self.learning_patterns.keys()),
            "total_strategy_improvements": total_improvements,
            "last_consolidation": self.last_consolidation_time.isoformat(),
        }
    
    def apply_learning_outcome(self, learning_id: str, context: Dict[str, Any]) -> bool:
        """
        应用学习结果
        
        Args:
            learning_id: 学习结果ID
            context: 应用上下文
            
        Returns:
            bool: 是否成功应用
        """
        # 查找学习结果
        learning_outcome = None
        for outcome in self.learning_outcomes:
            if outcome.id == learning_id:
                learning_outcome = outcome
                break
        
        if not learning_outcome:
            self._log("error", f"找不到学习结果: {learning_id}")
            return False
        
        if learning_outcome.applied:
            self._log("warning", f"学习结果 {learning_id} 已经应用过")
            return False
        
        # 应用学习结果
        self._log("info", f"应用学习结果 {learning_id}: {learning_outcome.summary}")
        
        learning_outcome.applied = True
        learning_outcome.applied_contexts.append(context.get("context_id", "unknown"))
        
        # 在实际实现中，这里应该将学习结果应用到系统配置或策略中
        # 例如：更新规划引擎参数、调整约束设置、优化资源分配等
        
        return True


# 便捷函数
def create_learning_module(config: Dict[str, Any] = None) -> LearningModule:
    """
    创建学习模块的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        学习模块实例
    """
    return LearningModule(config)