"""
探索器模块

负责探索不同的规划路径、生成备选方案和优化搜索策略。
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import random
import time

from .task_definitions import TaskStep, ComplexTask
from .tot_planner import ToTPlanner, ThoughtNode
from .state_evaluator import StateEvaluator, EvaluationResult


class ExplorationStrategy(str, Enum):
    """探索策略枚举"""
    DEPTH_FIRST = "depth_first"  # 深度优先
    BREADTH_FIRST = "breadth_first"  # 广度优先
    BEAM_SEARCH = "beam_search"  # 束搜索
    RANDOM_WALK = "random_walk"  # 随机游走
    ADAPTIVE = "adaptive"  # 自适应


@dataclass
class ExplorationResult:
    """探索结果"""
    best_plan: List[TaskStep]  # 最佳规划
    alternative_plans: List[List[TaskStep]]  # 备选规划
    exploration_stats: Dict[str, Any]  # 探索统计
    evaluation_results: List[EvaluationResult]  # 各规划评估结果
    confidence: float  # 总体置信度
    metadata: Dict[str, Any] = None


class Explorer:
    """规划探索器"""
    
    def __init__(self, 
                 strategy: ExplorationStrategy = ExplorationStrategy.ADAPTIVE,
                 max_alternatives: int = 3,
                 exploration_time_limit: int = 30):
        """
        初始化探索器
        
        Args:
            strategy: 探索策略
            max_alternatives: 最大备选方案数
            exploration_time_limit: 探索时间限制（秒）
        """
        self.strategy = strategy
        self.max_alternatives = max_alternatives
        self.exploration_time_limit = exploration_time_limit
        
        # 组件
        self.tot_planner = None
        self.state_evaluator = None
        self.logger = None
        
        # 状态
        self.exploration_start_time = 0
        self.stats = {
            "paths_explored": 0,
            "nodes_generated": 0,
            "plans_evaluated": 0,
            "time_spent": 0.0,
        }
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
        if self.tot_planner:
            self.tot_planner.set_logger(logger)
        if self.state_evaluator:
            self.state_evaluator.set_logger(logger)
    
    def set_components(self, tot_planner: ToTPlanner, state_evaluator: StateEvaluator):
        """设置组件"""
        self.tot_planner = tot_planner
        self.state_evaluator = state_evaluator
        
        # 传递日志记录器
        if self.logger:
            self.tot_planner.set_logger(self.logger)
            self.state_evaluator.set_logger(self.logger)
    
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
    
    def explore(self, task: ComplexTask, initial_state: Dict[str, Any]) -> ExplorationResult:
        """
        探索规划方案
        
        Args:
            task: 要规划的任务
            initial_state: 初始状态
            
        Returns:
            探索结果
        """
        self._log("info", f"开始探索任务规划: {task.goal}")
        self._log("debug", f"探索策略: {self.strategy}, 时间限制: {self.exploration_time_limit}秒")
        
        # 重置状态
        self._reset()
        self.exploration_start_time = time.time()
        
        # 根据策略选择探索方法
        if self.strategy == ExplorationStrategy.DEPTH_FIRST:
            plans = self._depth_first_exploration(task, initial_state)
        elif self.strategy == ExplorationStrategy.BREADTH_FIRST:
            plans = self._breadth_first_exploration(task, initial_state)
        elif self.strategy == ExplorationStrategy.BEAM_SEARCH:
            plans = self._beam_search_exploration(task, initial_state)
        elif self.strategy == ExplorationStrategy.RANDOM_WALK:
            plans = self._random_walk_exploration(task, initial_state)
        elif self.strategy == ExplorationStrategy.ADAPTIVE:
            plans = self._adaptive_exploration(task, initial_state)
        else:
            # 默认使用自适应策略
            plans = self._adaptive_exploration(task, initial_state)
        
        # 评估所有规划
        evaluated_plans = self._evaluate_plans(plans, task)
        
        # 选择最佳规划和备选方案
        best_plan, alternative_plans = self._select_best_and_alternatives(evaluated_plans)
        
        # 更新统计信息
        self.stats["time_spent"] = time.time() - self.exploration_start_time
        
        # 创建结果
        result = ExplorationResult(
            best_plan=best_plan,
            alternative_plans=alternative_plans,
            exploration_stats=self.stats.copy(),
            evaluation_results=[eval_result for _, eval_result in evaluated_plans],
            confidence=self._calculate_overall_confidence(evaluated_plans),
            metadata={
                "task_id": task.id,
                "task_type": task.task_type,
                "strategy_used": self.strategy,
            }
        )
        
        self._log_stats()
        return result
    
    def _reset(self):
        """重置探索器状态"""
        self.exploration_start_time = 0
        self.stats = {
            "paths_explored": 0,
            "nodes_generated": 0,
            "plans_evaluated": 0,
            "time_spent": 0.0,
        }
    
    def _depth_first_exploration(self, task: ComplexTask, initial_state: Dict[str, Any]) -> List[List[TaskStep]]:
        """深度优先探索"""
        self._log("debug", "使用深度优先策略探索")
        
        if not self.tot_planner:
            self._log("error", "ToT规划器未设置")
            return []
        
        # 配置深度优先参数
        original_max_depth = self.tot_planner.max_depth
        original_max_width = self.tot_planner.max_width
        
        # 深度优先：深度较大，宽度较小
        self.tot_planner.max_depth = min(original_max_depth + 2, 6)
        self.tot_planner.max_width = max(original_max_width - 1, 2)
        
        # 运行规划
        plan = self.tot_planner.plan(task, initial_state)
        
        # 恢复原始参数
        self.tot_planner.max_depth = original_max_depth
        self.tot_planner.max_width = original_max_width
        
        # 记录统计
        self.stats["paths_explored"] += 1
        self.stats["nodes_generated"] += self.tot_planner.stats.get("nodes_created", 0)
        
        return [plan]
    
    def _breadth_first_exploration(self, task: ComplexTask, initial_state: Dict[str, Any]) -> List[List[TaskStep]]:
        """广度优先探索"""
        self._log("debug", "使用广度优先策略探索")
        
        if not self.tot_planner:
            self._log("error", "ToT规划器未设置")
            return []
        
        # 配置广度优先参数
        original_max_depth = self.tot_planner.max_depth
        original_max_width = self.tot_planner.max_width
        
        # 广度优先：深度较小，宽度较大
        self.tot_planner.max_depth = max(original_max_depth - 1, 2)
        self.tot_planner.max_width = min(original_max_width + 2, 8)
        
        # 运行规划
        plan = self.tot_planner.plan(task, initial_state)
        
        # 恢复原始参数
        self.tot_planner.max_depth = original_max_depth
        self.tot_planner.max_width = original_max_width
        
        # 记录统计
        self.stats["paths_explored"] += 1
        self.stats["nodes_generated"] += self.tot_planner.stats.get("nodes_created", 0)
        
        return [plan]
    
    def _beam_search_exploration(self, task: ComplexTask, initial_state: Dict[str, Any]) -> List[List[TaskStep]]:
        """束搜索探索"""
        self._log("debug", "使用束搜索策略探索")
        
        if not self.tot_planner:
            self._log("error", "ToT规划器未设置")
            return []
        
        plans = []
        beam_width = 3  # 束宽度
        
        for i in range(beam_width):
            self._log("debug", f"束搜索迭代 {i+1}/{beam_width}")
            
            # 调整温度参数以获得多样性
            original_temperature = self.tot_planner.temperature
            self.tot_planner.temperature = original_temperature * (1.0 + i * 0.2)
            
            # 运行规划
            plan = self.tot_planner.plan(task, initial_state)
            plans.append(plan)
            
            # 恢复温度
            self.tot_planner.temperature = original_temperature
            
            # 记录统计
            self.stats["paths_explored"] += 1
            self.stats["nodes_generated"] += self.tot_planner.stats.get("nodes_created", 0)
            
            # 检查时间限制
            if self._should_stop_exploration():
                self._log("debug", "达到时间限制，停止束搜索")
                break
        
        return plans
    
    def _random_walk_exploration(self, task: ComplexTask, initial_state: Dict[str, Any]) -> List[List[TaskStep]]:
        """随机游走探索"""
        self._log("debug", "使用随机游走策略探索")
        
        if not self.tot_planner:
            self._log("error", "ToT规划器未设置")
            return []
        
        plans = []
        max_random_walks = 5
        
        for i in range(max_random_walks):
            self._log("debug", f"随机游走迭代 {i+1}/{max_random_walks}")
            
            # 增加随机性
            original_exploration_factor = self.tot_planner.exploration_factor
            original_temperature = self.tot_planner.temperature
            
            self.tot_planner.exploration_factor = 0.8  # 高探索性
            self.tot_planner.temperature = 1.0  # 高随机性
            
            # 运行规划
            plan = self.tot_planner.plan(task, initial_state)
            plans.append(plan)
            
            # 恢复参数
            self.tot_planner.exploration_factor = original_exploration_factor
            self.tot_planner.temperature = original_temperature
            
            # 记录统计
            self.stats["paths_explored"] += 1
            self.stats["nodes_generated"] += self.tot_planner.stats.get("nodes_created", 0)
            
            # 检查时间限制
            if self._should_stop_exploration():
                self._log("debug", "达到时间限制，停止随机游走")
                break
        
        return plans
    
    def _adaptive_exploration(self, task: ComplexTask, initial_state: Dict[str, Any]) -> List[List[TaskStep]]:
        """自适应探索"""
        self._log("debug", "使用自适应策略探索")
        
        # 根据任务类型选择策略
        task_type = task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type)
        
        if task_type in ["party_planning", "travel_planning"]:
            # 聚会和旅行规划：使用束搜索
            return self._beam_search_exploration(task, initial_state)
        elif task_type == "project_management":
            # 项目管理：使用深度优先
            return self._depth_first_exploration(task, initial_state)
        else:
            # 其他任务：使用混合策略
            return self._hybrid_exploration(task, initial_state)
    
    def _hybrid_exploration(self, task: ComplexTask, initial_state: Dict[str, Any]) -> List[List[TaskStep]]:
        """混合探索策略"""
        self._log("debug", "使用混合策略探索")
        
        all_plans = []
        
        # 尝试多种策略
        strategies_to_try = [
            (ExplorationStrategy.DEPTH_FIRST, "深度优先"),
            (ExplorationStrategy.BREADTH_FIRST, "广度优先"),
            (ExplorationStrategy.BEAM_SEARCH, "束搜索"),
        ]
        
        original_strategy = self.strategy
        
        for strategy, strategy_name in strategies_to_try:
            if self._should_stop_exploration():
                self._log("debug", "达到时间限制，停止混合探索")
                break
            
            self._log("debug", f"尝试 {strategy_name} 策略")
            self.strategy = strategy
            
            # 使用当前策略探索
            strategy_plans = self.explore(task, initial_state)
            if strategy_plans.best_plan:
                all_plans.append(strategy_plans.best_plan)
            
            # 限制计划数量
            if len(all_plans) >= self.max_alternatives * 2:
                break
        
        # 恢复原始策略
        self.strategy = original_strategy
        
        return all_plans
    
    def _should_stop_exploration(self) -> bool:
        """检查是否应该停止探索"""
        current_time = time.time()
        elapsed = current_time - self.exploration_start_time
        
        if elapsed > self.exploration_time_limit:
            return True
        
        return False
    
    def _evaluate_plans(self, plans: List[List[TaskStep]], task: ComplexTask) -> List[Tuple[List[TaskStep], EvaluationResult]]:
        """评估所有规划"""
        if not self.state_evaluator:
            self._log("error", "状态评估器未设置")
            return []
        
        evaluated_plans = []
        
        for i, plan in enumerate(plans):
            if not plan:
                continue
            
            self._log("debug", f"评估规划 {i+1}/{len(plans)} (包含 {len(plan)} 个步骤)")
            
            # 创建模拟状态
            simulated_state = {
                "step_count": len(plan),
                "completed_steps": len(plan),  # 假设所有步骤都已完成
                "progress": 1.0,
                "plan_index": i,
            }
            
            # 创建步骤状态映射
            step_statuses = {step.id: "completed" for step in plan}
            
            # 评估规划
            evaluation = self.state_evaluator.evaluate_task_state(
                task=task,
                current_state=simulated_state,
                step_statuses=step_statuses
            )
            
            evaluated_plans.append((plan, evaluation))
            self.stats["plans_evaluated"] += 1
        
        return evaluated_plans
    
    def _select_best_and_alternatives(self, evaluated_plans: List[Tuple[List[TaskStep], EvaluationResult]]) -> Tuple[List[TaskStep], List[List[TaskStep]]]:
        """选择最佳规划和备选方案"""
        if not evaluated_plans:
            self._log("warning", "没有可用的规划")
            return [], []
        
        # 按评分排序
        sorted_plans = sorted(evaluated_plans, key=lambda x: x[1].score, reverse=True)
        
        # 最佳规划
        best_plan, best_evaluation = sorted_plans[0]
        self._log("info", f"最佳规划评分: {best_evaluation.score:.1f}")
        
        # 备选规划（排除最佳规划）
        alternative_plans = []
        seen_plans = set()
        
        # 使用规划内容的哈希来去重
        for plan, evaluation in sorted_plans[1:]:
            # 生成规划签名（简化去重）
            plan_signature = self._generate_plan_signature(plan)
            
            if plan_signature in seen_plans:
                continue
            
            # 检查与最佳规划的差异性
            if self._is_significantly_different(plan, best_plan):
                alternative_plans.append(plan)
                seen_plans.add(plan_signature)
            
            if len(alternative_plans) >= self.max_alternatives:
                break
        
        self._log("info", f"选择了 {len(alternative_plans)} 个备选规划")
        
        return best_plan, alternative_plans
    
    def _generate_plan_signature(self, plan: List[TaskStep]) -> str:
        """生成规划签名用于去重"""
        if not plan:
            return "empty"
        
        # 使用步骤描述的前几个字符作为签名
        signatures = []
        for step in plan[:5]:  # 只取前5个步骤
            desc = step.description[:20] if step.description else ""
            signatures.append(desc)
        
        return "|".join(signatures)
    
    def _is_significantly_different(self, plan_a: List[TaskStep], plan_b: List[TaskStep]) -> bool:
        """检查两个规划是否显著不同"""
        if len(plan_a) != len(plan_b):
            return True
        
        # 检查步骤描述的相似性
        similar_steps = 0
        min_steps = min(len(plan_a), len(plan_b))
        
        for i in range(min_steps):
            desc_a = plan_a[i].description.lower() if plan_a[i].description else ""
            desc_b = plan_b[i].description.lower() if plan_b[i].description else ""
            
            # 简单相似性检查
            if desc_a and desc_b:
                # 检查是否有相同的关键词
                words_a = set(desc_a.split())
                words_b = set(desc_b.split())
                common_words = words_a.intersection(words_b)
                
                if len(common_words) >= 2:
                    similar_steps += 1
        
        # 如果超过一半的步骤相似，则认为不够不同
        similarity_ratio = similar_steps / min_steps if min_steps > 0 else 0
        return similarity_ratio < 0.5
    
    def _calculate_overall_confidence(self, evaluated_plans: List[Tuple[List[TaskStep], EvaluationResult]]) -> float:
        """计算总体置信度"""
        if not evaluated_plans:
            return 0.0
        
        # 基于最佳规划的置信度和备选规划的数量计算
        best_plan_evaluation = evaluated_plans[0][1]
        base_confidence = best_plan_evaluation.confidence
        
        # 有多个备选规划增加置信度
        plan_count = len(evaluated_plans)
        diversity_bonus = min(0.2, (plan_count - 1) * 0.05)
        
        # 规划质量影响置信度
        quality_factor = min(1.0, best_plan_evaluation.score / 100.0)
        
        overall_confidence = base_confidence * quality_factor + diversity_bonus
        return min(max(overall_confidence, 0.0), 1.0)
    
    def _log_stats(self):
        """记录统计信息"""
        if self.logger:
            self._log("info", "探索器统计:")
            self._log("info", f"  探索路径数: {self.stats['paths_explored']}")
            self._log("info", f"  生成节点数: {self.stats['nodes_generated']}")
            self._log("info", f"  评估规划数: {self.stats['plans_evaluated']}")
            self._log("info", f"  探索时间: {self.stats['time_spent']:.2f}秒")


# 便捷函数
def create_explorer(strategy: str = "adaptive", 
                   max_alternatives: int = 3,
                   exploration_time_limit: int = 30) -> Explorer:
    """
    创建探索器的便捷函数
    
    Args:
        strategy: 探索策略，可选值: "depth_first", "breadth_first", "beam_search", "random_walk", "adaptive"
        max_alternatives: 最大备选方案数
        exploration_time_limit: 探索时间限制（秒）
        
    Returns:
        探索器实例
    """
    strategy_map = {
        "depth_first": ExplorationStrategy.DEPTH_FIRST,
        "breadth_first": ExplorationStrategy.BREADTH_FIRST,
        "beam_search": ExplorationStrategy.BEAM_SEARCH,
        "random_walk": ExplorationStrategy.RANDOM_WALK,
        "adaptive": ExplorationStrategy.ADAPTIVE,
    }
    
    selected_strategy = strategy_map.get(strategy, ExplorationStrategy.ADAPTIVE)
    return Explorer(
        strategy=selected_strategy,
        max_alternatives=max_alternatives,
        exploration_time_limit=exploration_time_limit,
    )