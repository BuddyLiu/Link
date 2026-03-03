"""
规划引擎主模块

整合所有规划组件，提供完整的复杂任务规划能力。
"""

from typing import List, Dict, Any, Optional, Tuple
import time
from datetime import datetime

from .task_definitions import (
    ComplexTask, TaskType, TaskPriority, TaskConstraint, TaskStep,
    TaskTemplateRegistry, task_template_registry, create_task
)
from .task_decomposer import TaskDecomposer, DecompositionStrategy, DecompositionResult
from .tot_planner import ToTPlanner
from .state_evaluator import StateEvaluator, EvaluationResult
from .explorer import Explorer, ExplorationStrategy, ExplorationResult


class PlanningEngine:
    """规划引擎主类"""
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        初始化规划引擎
        
        Args:
            config: 配置参数
        """
        # 默认配置
        self.config = {
            "planning_engine": "tot",
            "max_planning_time": 30,
            "max_planning_depth": 3,
            "planning_temperature": 0.7,
            "enable_complex_tasks": True,
            "max_task_steps": 20,
            "exploration_strategy": "adaptive",
            "max_alternatives": 3,
        }
        
        # 更新配置
        if config:
            self.config.update(config)
        
        # 初始化组件
        self.task_decomposer = None
        self.tot_planner = None
        self.state_evaluator = None
        self.explorer = None
        self.logger = None
        
        # 状态跟踪
        self.active_tasks: Dict[str, ComplexTask] = {}
        self.planning_history: List[Dict[str, Any]] = []
        
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化所有组件"""
        # 任务分解器
        self.task_decomposer = TaskDecomposer(
            strategy=DecompositionStrategy.TEMPLATE_BASED
        )
        
        # ToT规划器
        self.tot_planner = ToTPlanner(
            max_depth=self.config.get("max_planning_depth", 3),
            max_width=5,
            max_iterations=100,
            exploration_factor=0.3,
            temperature=self.config.get("planning_temperature", 0.7),
        )
        
        # 状态评估器
        self.state_evaluator = StateEvaluator()
        
        # 探索器
        self.explorer = Explorer(
            strategy=ExplorationStrategy(self.config.get("exploration_strategy", "adaptive")),
            max_alternatives=self.config.get("max_alternatives", 3),
            exploration_time_limit=self.config.get("max_planning_time", 30),
        )
        
        # 设置组件依赖
        self.explorer.set_components(self.tot_planner, self.state_evaluator)
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
        self.task_decomposer.set_logger(logger)
        self.tot_planner.set_logger(logger)
        self.state_evaluator.set_logger(logger)
        self.explorer.set_logger(logger)
    
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
    
    def create_task(self, 
                    goal: str, 
                    description: str, 
                    task_type: Optional[TaskType] = None,
                    constraints: Optional[List[TaskConstraint]] = None,
                    priority: TaskPriority = TaskPriority.MEDIUM,
                    **kwargs) -> ComplexTask:
        """
        创建复杂任务
        
        Args:
            goal: 任务目标
            description: 任务描述
            task_type: 任务类型（如果为None则自动检测）
            constraints: 约束条件
            priority: 优先级
            **kwargs: 其他参数
            
        Returns:
            创建的复杂任务
        """
        self._log("info", f"创建任务: {goal}")
        
        # 自动检测任务类型
        if task_type is None:
            task_type = self.task_decomposer.detect_task_type(description)
            if task_type is None:
                task_type = TaskType.PROJECT_MANAGEMENT  # 默认类型
            self._log("debug", f"自动检测到任务类型: {task_type}")
        
        # 创建任务
        task = create_task(task_type, goal, description, **kwargs)
        if not task:
            # 如果模板创建失败，使用通用方式创建
            task = ComplexTask(
                id=f"task_{int(time.time())}",
                goal=goal,
                description=description,
                task_type=task_type,
                priority=priority,
            )
        
        # 添加约束
        if constraints:
            for constraint in constraints:
                task.add_constraint(constraint)
        
        # 设置其他属性
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
            else:
                task.metadata[key] = value
        
        # 存储任务
        self.active_tasks[task.id] = task
        
        self._log("info", f"任务创建成功，ID: {task.id}")
        return task
    
    def decompose_task(self, task: ComplexTask, context: Dict[str, Any] = None) -> DecompositionResult:
        """
        分解复杂任务
        
        Args:
            task: 要分解的任务
            context: 上下文信息
            
        Returns:
            分解结果
        """
        self._log("info", f"分解任务: {task.goal}")
        
        if not self.task_decomposer:
            self._log("error", "任务分解器未初始化")
            raise RuntimeError("任务分解器未初始化")
        
        # 执行分解
        result = self.task_decomposer.decompose(task, context)
        
        # 更新任务步骤
        if result.steps:
            task.steps = result.steps.copy()
            task.status = "planning"
            task.updated_at = datetime.now()
            
            self._log("info", f"任务分解完成，生成 {len(result.steps)} 个步骤")
        
        return result
    
    def plan_task(self, 
                  task: ComplexTask, 
                  initial_state: Optional[Dict[str, Any]] = None,
                  use_exploration: bool = True) -> Dict[str, Any]:
        """
        为任务创建规划
        
        Args:
            task: 要规划的任务
            initial_state: 初始状态（如果为None则使用默认状态）
            use_exploration: 是否使用探索器（否则直接使用ToT规划器）
            
        Returns:
            规划结果
        """
        self._log("info", f"开始规划任务: {task.goal}")
        
        start_time = time.time()
        
        # 准备初始状态
        if initial_state is None:
            initial_state = self._create_default_initial_state(task)
        
        # 执行规划
        if use_exploration and self.explorer:
            self._log("debug", "使用探索器进行规划")
            exploration_result = self.explorer.explore(task, initial_state)
            
            # 提取最佳规划
            best_plan = exploration_result.best_plan
            
            # 构建结果
            result = {
                "plan": best_plan,
                "alternative_plans": exploration_result.alternative_plans,
                "exploration_stats": exploration_result.exploration_stats,
                "evaluation_results": exploration_result.evaluation_results,
                "confidence": exploration_result.confidence,
                "planning_method": "exploration",
                "planning_time": time.time() - start_time,
                "task_id": task.id,
            }
        else:
            self._log("debug", "直接使用ToT规划器")
            if not self.tot_planner:
                self._log("error", "ToT规划器未初始化")
                raise RuntimeError("ToT规划器未初始化")
            
            plan = self.tot_planner.plan(task, initial_state)
            
            # 评估规划
            evaluation = None
            if self.state_evaluator and plan:
                simulated_state = {
                    "step_count": len(plan),
                    "completed_steps": len(plan),
                    "progress": 1.0,
                }
                step_statuses = {step.id: "completed" for step in plan}
                evaluation = self.state_evaluator.evaluate_task_state(
                    task, simulated_state, step_statuses
                )
            
            result = {
                "plan": plan,
                "alternative_plans": [],
                "exploration_stats": self.tot_planner.stats.copy(),
                "evaluation_results": [evaluation] if evaluation else [],
                "confidence": evaluation.confidence if evaluation else 0.5,
                "planning_method": "direct_tot",
                "planning_time": time.time() - start_time,
                "task_id": task.id,
            }
        
        # 更新任务状态
        if result["plan"]:
            task.steps = result["plan"]
            task.status = "executing"
            task.updated_at = datetime.now()
            self._log("info", f"规划完成，生成 {len(result['plan'])} 个步骤")
        else:
            self._log("warning", "规划失败，未生成有效步骤")
        
        # 记录规划历史
        history_entry = {
            "task_id": task.id,
            "timestamp": datetime.now(),
            "planning_time": result["planning_time"],
            "step_count": len(result["plan"]) if result["plan"] else 0,
            "confidence": result["confidence"],
            "method": result["planning_method"],
        }
        self.planning_history.append(history_entry)
        
        return result
    
    def _create_default_initial_state(self, task: ComplexTask) -> Dict[str, Any]:
        """创建默认初始状态"""
        return {
            "task_id": task.id,
            "goal": task.goal,
            "task_type": task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type),
            "constraints": [c.type for c in task.constraints],
            "priority": task.priority.value if hasattr(task.priority, 'value') else str(task.priority),
            "step_count": 0,
            "progress": 0.0,
            "decisions_made": 0,
            "resources_allocated": 0,
            "action_history": [],
            "start_time": time.time(),
        }
    
    def evaluate_task_progress(self, task: ComplexTask, current_state: Dict[str, Any]) -> EvaluationResult:
        """
        评估任务进度
        
        Args:
            task: 要评估的任务
            current_state: 当前状态
            
        Returns:
            评估结果
        """
        self._log("debug", f"评估任务进度: {task.goal}")
        
        if not self.state_evaluator:
            self._log("error", "状态评估器未初始化")
            raise RuntimeError("状态评估器未初始化")
        
        # 创建步骤状态映射
        step_statuses = {}
        for step in task.steps:
            step_statuses[step.id] = step.status
        
        # 执行评估
        evaluation = self.state_evaluator.evaluate_task_state(
            task=task,
            current_state=current_state,
            step_statuses=step_statuses
        )
        
        self._log("info", f"任务评估完成，评分: {evaluation.score:.1f}")
        return evaluation
    
    def compare_plans(self, 
                      plan_a: List[TaskStep], 
                      plan_b: List[TaskStep], 
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
        self._log("info", "比较两个规划方案")
        
        if not self.state_evaluator:
            self._log("error", "状态评估器未初始化")
            raise RuntimeError("状态评估器未初始化")
        
        comparison = self.state_evaluator.compare_plans(plan_a, plan_b, task)
        
        self._log("info", f"方案比较完成，优胜者: 方案{comparison['winner']}")
        return comparison
    
    def update_task_step(self, 
                         task_id: str, 
                         step_id: str, 
                         status: str, 
                         result: Any = None) -> bool:
        """
        更新任务步骤状态
        
        Args:
            task_id: 任务ID
            step_id: 步骤ID
            status: 新状态
            result: 执行结果
            
        Returns:
            是否成功更新
        """
        task = self.active_tasks.get(task_id)
        if not task:
            self._log("error", f"任务不存在: {task_id}")
            return False
        
        # 查找步骤
        step = task.get_step_by_id(step_id)
        if not step:
            self._log("error", f"步骤不存在: {step_id}")
            return False
        
        # 更新步骤
        old_status = step.status
        step.status = status
        step.result = result
        task.updated_at = datetime.now()
        
        self._log("info", f"更新任务步骤: {task_id}.{step_id} {old_status} -> {status}")
        
        # 检查任务是否完成
        self._check_task_completion(task)
        
        return True
    
    def _check_task_completion(self, task: ComplexTask):
        """检查任务是否完成"""
        if not task.steps:
            return
        
        # 检查所有步骤是否完成
        all_completed = all(step.status == "completed" for step in task.steps)
        
        if all_completed and task.status != "completed":
            task.status = "completed"
            task.updated_at = datetime.now()
            self._log("info", f"任务完成: {task.goal}")
    
    def get_task(self, task_id: str) -> Optional[ComplexTask]:
        """根据ID获取任务"""
        return self.active_tasks.get(task_id)
    
    def list_active_tasks(self) -> List[ComplexTask]:
        """列出所有活动任务"""
        return list(self.active_tasks.values())
    
    def get_task_template_types(self) -> List[str]:
        """获取可用的任务模板类型"""
        if hasattr(task_template_registry, 'list_available_templates'):
            templates = task_template_registry.list_available_templates()
            return [t.value if hasattr(t, 'value') else str(t) for t in templates]
        return []
    
    def get_planning_stats(self) -> Dict[str, Any]:
        """获取规划统计信息"""
        stats = {
            "active_tasks": len(self.active_tasks),
            "planning_history_count": len(self.planning_history),
            "planning_engine": self.config.get("planning_engine", "tot"),
            "components_initialized": {
                "task_decomposer": self.task_decomposer is not None,
                "tot_planner": self.tot_planner is not None,
                "state_evaluator": self.state_evaluator is not None,
                "explorer": self.explorer is not None,
            }
        }
        
        # 添加最近的规划历史
        if self.planning_history:
            recent = self.planning_history[-5:]  # 最近5条记录
            stats["recent_planning_history"] = recent
        
        return stats
    
    def export_task_plan(self, task_id: str, format: str = "json") -> Dict[str, Any]:
        """
        导出任务规划
        
        Args:
            task_id: 任务ID
            format: 导出格式（目前仅支持json）
            
        Returns:
            导出的规划数据
        """
        task = self.get_task(task_id)
        if not task:
            self._log("error", f"任务不存在: {task_id}")
            return {"error": f"任务不存在: {task_id}"}
        
        # 转换为字典
        task_dict = {
            "id": task.id,
            "goal": task.goal,
            "description": task.description,
            "task_type": task.task_type.value if hasattr(task.task_type, 'value') else str(task.task_type),
            "priority": task.priority.value if hasattr(task.priority, 'value') else str(task.priority),
            "status": task.status,
            "created_at": task.created_at.isoformat() if hasattr(task.created_at, 'isoformat') else str(task.created_at),
            "updated_at": task.updated_at.isoformat() if hasattr(task.updated_at, 'isoformat') else str(task.updated_at),
            "constraints": [
                {
                    "type": c.type,
                    "description": c.description,
                    "value": c.value,
                    "is_required": c.is_required,
                }
                for c in task.constraints
            ],
            "steps": [
                {
                    "id": s.id,
                    "description": s.description,
                    "action": s.action,
                    "dependencies": s.dependencies,
                    "estimated_duration": str(s.estimated_duration) if s.estimated_duration else None,
                    "assigned_to": s.assigned_to,
                    "status": s.status,
                    "result": str(s.result) if s.result else None,
                }
                for s in task.steps
            ],
            "metadata": task.metadata,
        }
        
        return task_dict


# 便捷函数
def create_planning_engine(config: Dict[str, Any] = None) -> PlanningEngine:
    """
    创建规划引擎的便捷函数
    
    Args:
        config: 配置参数
        
    Returns:
        规划引擎实例
    """
    return PlanningEngine(config)