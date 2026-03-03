"""
状态评估器模块

负责评估任务状态、步骤完成情况和规划质量。
"""

from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import math

from .task_definitions import TaskStep, ComplexTask, TaskConstraint


class EvaluationMetric(str, Enum):
    """评估指标枚举"""
    COMPLETION_RATE = "completion_rate"  # 完成率
    CONSTRAINT_SATISFACTION = "constraint_satisfaction"  # 约束满足度
    TIME_EFFICIENCY = "time_efficiency"  # 时间效率
    RESOURCE_UTILIZATION = "resource_utilization"  # 资源利用
    QUALITY_SCORE = "quality_score"  # 质量评分
    CONFIDENCE = "confidence"  # 置信度


@dataclass
class EvaluationResult:
    """评估结果"""
    score: float  # 总体评分（0-100）
    metrics: Dict[EvaluationMetric, float]  # 各项指标得分
    strengths: List[str]  # 优点
    weaknesses: List[str]  # 缺点
    suggestions: List[str]  # 改进建议
    confidence: float = 1.0  # 评估置信度
    metadata: Dict[str, Any] = None


class StateEvaluator:
    """状态评估器"""
    
    def __init__(self):
        self.logger = None
        self._init_evaluation_rules()
    
    def _init_evaluation_rules(self):
        """初始化评估规则"""
        # 不同任务类型的权重配置
        self.task_type_weights = {
            "party_planning": {
                "completion_rate": 0.3,
                "constraint_satisfaction": 0.25,
                "time_efficiency": 0.2,
                "resource_utilization": 0.15,
                "quality_score": 0.1,
            },
            "travel_planning": {
                "completion_rate": 0.25,
                "constraint_satisfaction": 0.3,
                "time_efficiency": 0.25,
                "resource_utilization": 0.1,
                "quality_score": 0.1,
            },
            "project_management": {
                "completion_rate": 0.2,
                "constraint_satisfaction": 0.2,
                "time_efficiency": 0.2,
                "resource_utilization": 0.2,
                "quality_score": 0.2,
            },
            "default": {
                "completion_rate": 0.25,
                "constraint_satisfaction": 0.25,
                "time_efficiency": 0.2,
                "resource_utilization": 0.15,
                "quality_score": 0.15,
            }
        }
    
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
    
    def evaluate_task_state(self, 
                           task: ComplexTask, 
                           current_state: Dict[str, Any],
                           step_statuses: Dict[str, str]) -> EvaluationResult:
        """
        评估任务当前状态
        
        Args:
            task: 任务定义
            current_state: 当前状态描述
            step_statuses: 步骤ID到状态的映射
            
        Returns:
            评估结果
        """
        self._log("debug", f"评估任务状态: {task.goal}")
        
        # 计算各项指标
        metrics = {}
        
        # 1. 完成率
        completion_rate = self._calculate_completion_rate(task, step_statuses)
        metrics[EvaluationMetric.COMPLETION_RATE] = completion_rate
        
        # 2. 约束满足度
        constraint_satisfaction = self._calculate_constraint_satisfaction(task, current_state)
        metrics[EvaluationMetric.CONSTRAINT_SATISFACTION] = constraint_satisfaction
        
        # 3. 时间效率
        time_efficiency = self._calculate_time_efficiency(task, current_state, step_statuses)
        metrics[EvaluationMetric.TIME_EFFICIENCY] = time_efficiency
        
        # 4. 资源利用
        resource_utilization = self._calculate_resource_utilization(task, current_state)
        metrics[EvaluationMetric.RESOURCE_UTILIZATION] = resource_utilization
        
        # 5. 质量评分
        quality_score = self._calculate_quality_score(task, current_state, step_statuses)
        metrics[EvaluationMetric.QUALITY_SCORE] = quality_score
        
        # 6. 总体评分
        overall_score = self._calculate_overall_score(task, metrics)
        
        # 7. 生成分析
        strengths, weaknesses, suggestions = self._generate_analysis(
            task, metrics, current_state, step_statuses
        )
        
        return EvaluationResult(
            score=overall_score,
            metrics=metrics,
            strengths=strengths,
            weaknesses=weaknesses,
            suggestions=suggestions,
            confidence=0.8,  # 默认置信度
            metadata={
                "task_type": task.task_type,
                "step_count": len(task.steps),
                "completed_steps": sum(1 for s in step_statuses.values() if s == "completed"),
            }
        )
    
    def _calculate_completion_rate(self, task: ComplexTask, step_statuses: Dict[str, str]) -> float:
        """计算完成率"""
        if not task.steps:
            return 0.0
        
        completed_count = 0
        total_count = len(task.steps)
        
        for step in task.steps:
            status = step_statuses.get(step.id, "pending")
            if status == "completed":
                completed_count += 1
            elif status == "in_progress":
                completed_count += 0.5  # 进行中的步骤算一半
        
        return (completed_count / total_count) * 100.0
    
    def _calculate_constraint_satisfaction(self, task: ComplexTask, current_state: Dict[str, Any]) -> float:
        """计算约束满足度"""
        if not task.constraints:
            return 100.0  # 没有约束则完全满足
        
        satisfied_count = 0
        total_constraints = len(task.constraints)
        
        for constraint in task.constraints:
            if self._is_constraint_satisfied(constraint, current_state):
                satisfied_count += 1
            elif not constraint.is_required:
                # 非必需约束可以部分满足
                satisfied_count += 0.5
        
        return (satisfied_count / total_constraints) * 100.0
    
    def _is_constraint_satisfied(self, constraint: TaskConstraint, state: Dict[str, Any]) -> bool:
        """检查单个约束是否满足"""
        constraint_type = constraint.type
        
        # 简化的约束检查逻辑
        if constraint_type == "time":
            # 检查时间约束
            deadline = state.get("deadline")
            if deadline and constraint.value:
                # 检查是否在截止时间前
                return True  # 简化实现
            return constraint.value is not None
        
        elif constraint_type == "budget":
            # 检查预算约束
            current_cost = state.get("current_cost", 0)
            budget = constraint.value
            if budget is not None:
                return current_cost <= budget
            return True
        
        elif constraint_type == "location":
            # 检查地点约束
            location = state.get("location")
            if constraint.value and location:
                return str(location).lower() in str(constraint.value).lower()
            return constraint.value is not None
        
        elif constraint_type == "participants":
            # 检查参与人员约束
            participants = state.get("participants", [])
            required_participants = constraint.value
            if isinstance(required_participants, list) and participants:
                # 检查是否包含所有必需参与人员
                return all(p in participants for p in required_participants)
            return constraint.value is not None
        
        # 其他类型的约束
        return constraint.value is not None
    
    def _calculate_time_efficiency(self, task: ComplexTask, 
                                 current_state: Dict[str, Any],
                                 step_statuses: Dict[str, str]) -> float:
        """计算时间效率"""
        # 简化的时间效率计算
        estimated_time = task.metadata.get("estimated_time", 10.0)  # 默认10小时
        elapsed_time = current_state.get("elapsed_time", 0.0)
        
        if elapsed_time <= 0:
            return 100.0  # 还未开始，效率最高
        
        # 计算完成率
        completion_rate = self._calculate_completion_rate(task, step_statuses) / 100.0
        
        if completion_rate <= 0:
            return 0.0
        
        # 理想时间 = 估计时间 * 完成率
        ideal_time = estimated_time * completion_rate
        
        if elapsed_time <= ideal_time:
            # 提前或按时完成
            efficiency = 100.0
        else:
            # 超时，效率降低
            time_ratio = ideal_time / elapsed_time
            efficiency = max(0.0, time_ratio * 100.0)
        
        return efficiency
    
    def _calculate_resource_utilization(self, task: ComplexTask, current_state: Dict[str, Any]) -> float:
        """计算资源利用率"""
        # 简化的资源利用计算
        allocated_resources = current_state.get("allocated_resources", {})
        required_resources = task.metadata.get("required_resources", {})
        
        if not required_resources:
            return 100.0  # 不需要资源
        
        utilization_scores = []
        
        for resource_type, required_amount in required_resources.items():
            allocated_amount = allocated_resources.get(resource_type, 0)
            
            if required_amount <= 0:
                continue
            
            if allocated_amount <= 0:
                utilization = 0.0
            else:
                # 计算利用率，避免过度分配
                utilization = min(1.0, allocated_amount / required_amount)
            
            utilization_scores.append(utilization)
        
        if not utilization_scores:
            return 100.0
        
        # 平均利用率
        avg_utilization = sum(utilization_scores) / len(utilization_scores)
        return avg_utilization * 100.0
    
    def _calculate_quality_score(self, task: ComplexTask,
                               current_state: Dict[str, Any],
                               step_statuses: Dict[str, str]) -> float:
        """计算质量评分"""
        # 基于多个质量因素计算
        quality_factors = []
        
        # 1. 步骤执行质量
        step_quality = self._evaluate_step_quality(task, step_statuses)
        quality_factors.append(step_quality)
        
        # 2. 状态一致性
        consistency = self._evaluate_state_consistency(current_state)
        quality_factors.append(consistency)
        
        # 3. 错误率
        error_rate = current_state.get("error_rate", 0.0)
        error_quality = max(0.0, 1.0 - error_rate)
        quality_factors.append(error_quality)
        
        # 4. 用户满意度（如果有）
        user_satisfaction = current_state.get("user_satisfaction", 0.5)
        quality_factors.append(user_satisfaction)
        
        # 加权平均
        weights = [0.4, 0.3, 0.2, 0.1]
        weighted_sum = sum(f * w for f, w in zip(quality_factors, weights))
        
        return weighted_sum * 100.0
    
    def _evaluate_step_quality(self, task: ComplexTask, step_statuses: Dict[str, str]) -> float:
        """评估步骤执行质量"""
        if not task.steps:
            return 1.0
        
        quality_scores = []
        
        for step in task.steps:
            status = step_statuses.get(step.id, "pending")
            
            if status == "completed":
                # 检查步骤结果
                result = step.result
                if result is not None and "error" not in str(result).lower():
                    quality_scores.append(1.0)
                else:
                    quality_scores.append(0.5)  # 有错误结果
            elif status == "in_progress":
                quality_scores.append(0.7)  # 进行中
            elif status == "failed":
                quality_scores.append(0.0)  # 失败
            else:
                quality_scores.append(0.3)  # 未开始
        
        if not quality_scores:
            return 0.0
        
        return sum(quality_scores) / len(quality_scores)
    
    def _evaluate_state_consistency(self, current_state: Dict[str, Any]) -> float:
        """评估状态一致性"""
        # 检查状态中的矛盾
        contradictions = []
        
        # 示例检查：进度与步骤数的矛盾
        progress = current_state.get("progress", 0.0)
        step_count = current_state.get("step_count", 0)
        completed_steps = current_state.get("completed_steps", 0)
        
        if step_count > 0:
            calculated_progress = completed_steps / step_count
            if abs(progress - calculated_progress) > 0.3:
                contradictions.append("progress_inconsistency")
        
        # 示例检查：资源分配与预算的矛盾
        allocated_cost = current_state.get("allocated_cost", 0)
        budget = current_state.get("budget", float('inf'))
        
        if allocated_cost > budget * 1.2:  # 超出预算20%
            contradictions.append("budget_exceeded")
        
        # 根据矛盾数量计算一致性分数
        if not contradictions:
            return 1.0
        elif len(contradictions) == 1:
            return 0.7
        elif len(contradictions) == 2:
            return 0.4
        else:
            return 0.1
    
    def _calculate_overall_score(self, task: ComplexTask, metrics: Dict[EvaluationMetric, float]) -> float:
        """计算总体评分"""
        # 获取任务类型的权重配置
        task_type = task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type)
        weights = self.task_type_weights.get(task_type, self.task_type_weights["default"])
        
        # 计算加权平均
        weighted_sum = 0.0
        total_weight = 0.0
        
        for metric, score in metrics.items():
            metric_key = metric.value if hasattr(metric, 'value') else str(metric)
            weight = weights.get(metric_key, 0.2)  # 默认权重
            
            # 标准化分数到0-100范围
            normalized_score = min(max(score, 0.0), 100.0)
            
            weighted_sum += normalized_score * weight
            total_weight += weight
        
        if total_weight <= 0:
            return 50.0  # 默认分数
        
        overall_score = weighted_sum / total_weight
        return overall_score
    
    def _generate_analysis(self, task: ComplexTask, metrics: Dict[EvaluationMetric, float],
                          current_state: Dict[str, Any], step_statuses: Dict[str, str]) -> Tuple[List[str], List[str], List[str]]:
        """生成分析报告"""
        strengths = []
        weaknesses = []
        suggestions = []
        
        # 基于指标分析
        completion_rate = metrics.get(EvaluationMetric.COMPLETION_RATE, 0.0)
        constraint_satisfaction = metrics.get(EvaluationMetric.CONSTRAINT_SATISFACTION, 0.0)
        time_efficiency = metrics.get(EvaluationMetric.TIME_EFFICIENCY, 0.0)
        resource_utilization = metrics.get(EvaluationMetric.RESOURCE_UTILIZATION, 0.0)
        quality_score = metrics.get(EvaluationMetric.QUALITY_SCORE, 0.0)
        
        # 识别优点
        if completion_rate >= 80.0:
            strengths.append(f"任务完成率较高 ({completion_rate:.1f}%)")
        if constraint_satisfaction >= 90.0:
            strengths.append(f"约束条件满足良好 ({constraint_satisfaction:.1f}%)")
        if time_efficiency >= 90.0:
            strengths.append(f"时间效率优秀 ({time_efficiency:.1f}%)")
        if resource_utilization >= 85.0:
            strengths.append(f"资源利用合理 ({resource_utilization:.1f}%)")
        if quality_score >= 85.0:
            strengths.append(f"执行质量较高 ({quality_score:.1f}%)")
        
        # 识别缺点
        if completion_rate < 50.0:
            weaknesses.append(f"任务完成率较低 ({completion_rate:.1f}%)")
        if constraint_satisfaction < 70.0:
            weaknesses.append(f"约束条件满足不足 ({constraint_satisfaction:.1f}%)")
        if time_efficiency < 70.0:
            weaknesses.append(f"时间效率较低 ({time_efficiency:.1f}%)")
        if resource_utilization < 60.0:
            weaknesses.append(f"资源利用率不足 ({resource_utilization:.1f}%)")
        if quality_score < 70.0:
            weaknesses.append(f"执行质量有待提高 ({quality_score:.1f}%)")
        
        # 生成建议
        if completion_rate < 80.0:
            suggestions.append("优先完成未完成的步骤，提高整体完成率")
        if constraint_satisfaction < 90.0:
            suggestions.append("检查并满足未达标的约束条件")
        if time_efficiency < 80.0:
            suggestions.append("优化时间分配，减少等待和低效时间")
        if resource_utilization < 75.0:
            suggestions.append("重新评估资源分配，确保关键资源充足")
        if quality_score < 80.0:
            suggestions.append("加强质量控制，减少错误和返工")
        
        # 基于状态的具体建议
        error_count = current_state.get("error_count", 0)
        if error_count > 0:
            suggestions.append(f"处理 {error_count} 个已识别的问题和错误")
        
        pending_steps = [step_id for step_id, status in step_statuses.items() if status == "pending"]
        if pending_steps:
            suggestions.append(f"安排执行 {len(pending_steps)} 个待处理步骤")
        
        # 如果没有缺点，添加鼓励性建议
        if not weaknesses:
            suggestions.append("继续保持良好状态，按时完成剩余工作")
        
        return strengths, weaknesses, suggestions
    
    def compare_plans(self, plan_a: List[TaskStep], plan_b: List[TaskStep], 
                     task: ComplexTask) -> Dict[str, Any]:
        """
        比较两个规划方案
        
        Args:
            plan_a: 规划方案A
            plan_b: 规划方案B
            task: 任务定义
            
        Returns:
            比较结果
        """
        self._log("debug", "比较两个规划方案")
        
        # 评估两个规划
        state_a = {"step_count": len(plan_a)}
        state_b = {"step_count": len(plan_b)}
        
        step_statuses_a = {step.id: "completed" for step in plan_a}
        step_statuses_b = {step.id: "completed" for step in plan_b}
        
        eval_a = self.evaluate_task_state(task, state_a, step_statuses_a)
        eval_b = self.evaluate_task_state(task, state_b, step_statuses_b)
        
        # 确定哪个更好
        winner = "A" if eval_a.score > eval_b.score else "B"
        score_diff = abs(eval_a.score - eval_b.score)
        
        comparison = {
            "plan_a_score": eval_a.score,
            "plan_b_score": eval_b.score,
            "winner": winner,
            "score_difference": score_diff,
            "plan_a_strengths": eval_a.strengths,
            "plan_b_strengths": eval_b.strengths,
            "plan_a_weaknesses": eval_a.weaknesses,
            "plan_b_weaknesses": eval_b.weaknesses,
            "recommendation": self._generate_comparison_recommendation(eval_a, eval_b, winner, score_diff),
        }
        
        return comparison
    
    def _generate_comparison_recommendation(self, eval_a: EvaluationResult, 
                                          eval_b: EvaluationResult,
                                          winner: str, score_diff: float) -> str:
        """生成比较建议"""
        if score_diff < 5.0:
            return "两个方案质量相近，可以根据具体偏好选择"
        elif score_diff < 15.0:
            return f"方案{winner}略优，但两者差距不大"
        elif score_diff < 30.0:
            return f"方案{winner}明显更优，建议采用"
        else:
            return f"方案{winner}显著优于另一方案，强烈推荐采用"


# 便捷函数
def create_state_evaluator() -> StateEvaluator:
    """创建状态评估器的便捷函数"""
    return StateEvaluator()