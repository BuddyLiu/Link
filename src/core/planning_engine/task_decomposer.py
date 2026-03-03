"""
任务分解器模块

负责将复杂任务分解为可执行的子任务，支持多种分解策略。
"""

from typing import List, Dict, Any, Optional
import re
from dataclasses import dataclass
from enum import Enum
from .task_definitions import TaskStep, ComplexTask, TaskType


class DecompositionStrategy(str, Enum):
    """任务分解策略枚举"""
    RULE_BASED = "rule_based"  # 基于规则分解
    LLM_BASED = "llm_based"    # 基于大语言模型分解
    TEMPLATE_BASED = "template_based"  # 基于模板分解


@dataclass
class DecompositionResult:
    """分解结果"""
    steps: List[TaskStep]
    dependencies: Dict[str, List[str]]  # 步骤ID -> 依赖的步骤ID列表
    estimated_total_time: Optional[float] = None  # 预计总耗时（小时）
    confidence: float = 1.0  # 分解置信度
    metadata: Dict[str, Any] = None


class TaskDecomposer:
    """任务分解器"""
    
    def __init__(self, strategy: DecompositionStrategy = DecompositionStrategy.TEMPLATE_BASED):
        self.strategy = strategy
        self.logger = None  # 将在使用时设置
        self._init_decomposition_rules()
    
    def _init_decomposition_rules(self):
        """初始化分解规则"""
        self.decomposition_rules = {
            TaskType.PARTY_PLANNING: self._decompose_party_planning,
            TaskType.TRAVEL_PLANNING: self._decompose_travel_planning,
            TaskType.PROJECT_MANAGEMENT: self._decompose_project_management,
        }
        
        # 关键词到任务类型的映射
        self.keyword_to_task_type = {
            "聚会": TaskType.PARTY_PLANNING,
            "party": TaskType.PARTY_PLANNING,
            "庆祝": TaskType.PARTY_PLANNING,
            "旅行": TaskType.TRAVEL_PLANNING,
            "旅游": TaskType.TRAVEL_PLANNING,
            "travel": TaskType.TRAVEL_PLANNING,
            "出差": TaskType.TRAVEL_PLANNING,
            "项目": TaskType.PROJECT_MANAGEMENT,
            "project": TaskType.PROJECT_MANAGEMENT,
            "学习": TaskType.LEARNING_PLAN,
            "study": TaskType.LEARNING_PLAN,
        }
    
    def set_logger(self, logger):
        """设置日志记录器"""
        self.logger = logger
    
    def detect_task_type(self, task_description: str) -> Optional[TaskType]:
        """
        从任务描述中检测任务类型
        
        Args:
            task_description: 任务描述文本
            
        Returns:
            检测到的任务类型，如果无法检测则返回None
        """
        if not task_description:
            return None
        
        task_lower = task_description.lower()
        
        # 检查关键词映射
        for keyword, task_type in self.keyword_to_task_type.items():
            if keyword.lower() in task_lower:
                return task_type
        
        # 使用规则匹配
        if re.search(r'(聚会|party|庆祝|聚餐)', task_lower):
            return TaskType.PARTY_PLANNING
        elif re.search(r'(旅行|旅游|travel|出差|度假|vacation)', task_lower):
            return TaskType.TRAVEL_PLANNING
        elif re.search(r'(项目|project|任务|规划|plan)', task_lower) and not re.search(r'(学习|study)', task_lower):
            return TaskType.PROJECT_MANAGEMENT
        elif re.search(r'(学习|study|课程|course)', task_lower):
            return TaskType.LEARNING_PLAN
        elif re.search(r'(日常|routine|安排|schedule)', task_lower):
            return TaskType.DAILY_ROUTINE
        
        return None
    
    def decompose(self, task: ComplexTask, context: Dict[str, Any] = None) -> DecompositionResult:
        """
        分解复杂任务
        
        Args:
            task: 要分解的复杂任务
            context: 上下文信息
            
        Returns:
            分解结果
        """
        if self.logger:
            self.logger.info(f"开始分解任务: {task.goal} (类型: {task.task_type})")
        
        # 根据策略选择分解方法
        if self.strategy == DecompositionStrategy.RULE_BASED:
            return self._decompose_rule_based(task, context)
        elif self.strategy == DecompositionStrategy.LLM_BASED:
            return self._decompose_llm_based(task, context)
        elif self.strategy == DecompositionStrategy.TEMPLATE_BASED:
            return self._decompose_template_based(task, context)
        else:
            # 默认使用模板分解
            return self._decompose_template_based(task, context)
    
    def _decompose_rule_based(self, task: ComplexTask, context: Dict[str, Any]) -> DecompositionResult:
        """基于规则分解"""
        if self.logger:
            self.logger.debug(f"使用规则分解策略分解任务: {task.task_type}")
        
        # 检查是否有特定类型的分解规则
        if task.task_type in self.decomposition_rules:
            return self.decomposition_rules[task.task_type](task, context)
        
        # 默认通用分解
        return self._decompose_generic(task, context)
    
    def _decompose_llm_based(self, task: ComplexTask, context: Dict[str, Any]) -> DecompositionResult:
        """基于大语言模型分解（简化实现）"""
        if self.logger:
            self.logger.debug(f"使用LLM分解策略分解任务: {task.task_type}")
        
        # 这里应该调用LLM API进行任务分解
        # 简化实现：先尝试使用模板分解，如果失败则使用规则分解
        try:
            return self._decompose_template_based(task, context)
        except Exception as e:
            if self.logger:
                self.logger.warning(f"模板分解失败: {str(e)}，回退到规则分解")
            return self._decompose_rule_based(task, context)
    
    def _decompose_template_based(self, task: ComplexTask, context: Dict[str, Any]) -> DecompositionResult:
        """基于模板分解"""
        if self.logger:
            self.logger.debug(f"使用模板分解策略分解任务: {task.task_type}")
        
        # 检查任务是否有预定义的步骤
        if task.steps and len(task.steps) > 0:
            if self.logger:
                self.logger.info(f"任务已有 {len(task.steps)} 个预定义步骤")
            
            # 构建依赖关系
            dependencies = {}
            for step in task.steps:
                dependencies[step.id] = step.dependencies.copy()
            
            return DecompositionResult(
                steps=task.steps.copy(),
                dependencies=dependencies,
                confidence=0.9,
                metadata={"source": "template"}
            )
        
        # 如果没有预定义步骤，使用规则分解
        return self._decompose_rule_based(task, context)
    
    def _decompose_generic(self, task: ComplexTask, context: Dict[str, Any]) -> DecompositionResult:
        """通用任务分解"""
        if self.logger:
            self.logger.debug(f"使用通用分解方法")
        
        # 简单的基于描述的分解
        description = task.description
        
        # 提取动作动词
        action_verbs = ["安排", "规划", "准备", "组织", "完成", "实现", "制作", "创建"]
        
        steps = []
        dependencies = {}
        
        # 简单分解为3-5个步骤
        step_count = min(max(3, len(description) // 50), 7)  # 根据描述长度确定步骤数
        
        for i in range(step_count):
            step_id = str(i + 1)
            step_description = f"步骤{step_id}: 完成任务的第{i+1}部分"
            
            if i == 0:
                step_description = f"理解任务需求: {task.goal}"
            elif i == step_count - 1:
                step_description = f"完成最终交付: {task.goal}"
            
            step = TaskStep(
                id=step_id,
                description=step_description,
                action="执行任务",
                dependencies=[str(j) for j in range(i)],  # 依赖所有前面的步骤
            )
            
            steps.append(step)
            dependencies[step_id] = [str(j) for j in range(i)]
        
        return DecompositionResult(
            steps=steps,
            dependencies=dependencies,
            confidence=0.6,
            metadata={"source": "generic", "step_count": step_count}
        )
    
    def _decompose_party_planning(self, task: ComplexTask, context: Dict[str, Any]) -> DecompositionResult:
        """分解聚会安排任务"""
        if self.logger:
            self.logger.debug("分解聚会安排任务")
        
        steps = [
            TaskStep(
                id="1",
                description="确定参与人员名单",
                action="联系参与人员，确定可用时间",
                dependencies=[],
            ),
            TaskStep(
                id="2",
                description="选择聚会时间和地点",
                action="根据参与人员时间协调，选择合适的时间和地点",
                dependencies=["1"],
            ),
            TaskStep(
                id="3",
                description="预订场地或准备空间",
                action="预订餐厅、活动场地或准备家庭聚会空间",
                dependencies=["2"],
            ),
            TaskStep(
                id="4",
                description="发送邀请和通知",
                action="通过消息、邮件等方式发送邀请",
                dependencies=["2"],
            ),
            TaskStep(
                id="5",
                description="准备活动内容和餐饮",
                action="规划聚会活动、餐饮、娱乐等",
                dependencies=["3"],
            ),
            TaskStep(
                id="6",
                description="确认最终安排",
                action="确认参与人员并做最终安排",
                dependencies=["4", "5"],
            ),
        ]
        
        dependencies = {
            "1": [],
            "2": ["1"],
            "3": ["2"],
            "4": ["2"],
            "5": ["3"],
            "6": ["4", "5"],
        }
        
        return DecompositionResult(
            steps=steps,
            dependencies=dependencies,
            estimated_total_time=10.0,  # 估计10小时
            confidence=0.85,
            metadata={"source": "party_planning_template"}
        )
    
    def _decompose_travel_planning(self, task: ComplexTask, context: Dict[str, Any]) -> DecompositionResult:
        """分解旅行规划任务"""
        if self.logger:
            self.logger.debug("分解旅行规划任务")
        
        steps = [
            TaskStep(
                id="1",
                description="确定目的地和旅行日期",
                action="研究目的地，确定旅行时间和天数",
                dependencies=[],
            ),
            TaskStep(
                id="2",
                description="查询和预订交通",
                action="查询航班、火车或自驾路线，并预订",
                dependencies=["1"],
            ),
            TaskStep(
                id="3",
                description="预订住宿",
                action="根据预算和偏好预订酒店或民宿",
                dependencies=["1"],
            ),
            TaskStep(
                id="4",
                description="规划每日行程",
                action="规划每日活动、景点参观、餐饮等",
                dependencies=["1"],
            ),
            TaskStep(
                id="5",
                description="准备旅行材料",
                action="准备证件、保险、行程单、必需品等",
                dependencies=["2", "3"],
            ),
            TaskStep(
                id="6",
                description="设置旅行提醒",
                action="设置出发前提醒、重要事项提醒等",
                dependencies=["4", "5"],
            ),
        ]
        
        dependencies = {
            "1": [],
            "2": ["1"],
            "3": ["1"],
            "4": ["1"],
            "5": ["2", "3"],
            "6": ["4", "5"],
        }
        
        return DecompositionResult(
            steps=steps,
            dependencies=dependencies,
            estimated_total_time=15.0,  # 估计15小时
            confidence=0.8,
            metadata={"source": "travel_planning_template"}
        )
    
    def _decompose_project_management(self, task: ComplexTask, context: Dict[str, Any]) -> DecompositionResult:
        """分解项目管理任务"""
        if self.logger:
            self.logger.debug("分解项目管理任务")
        
        steps = [
            TaskStep(
                id="1",
                description="项目目标分析和需求收集",
                action="明确项目目标、范围和需求",
                dependencies=[],
            ),
            TaskStep(
                id="2",
                description="任务分解和工作分解结构",
                action="将项目分解为具体可执行的任务",
                dependencies=["1"],
            ),
            TaskStep(
                id="3",
                description="资源分配和时间线规划",
                action="分配人力、时间和资源，制定时间线",
                dependencies=["2"],
            ),
            TaskStep(
                id="4",
                description="任务执行和进度监控",
                action="执行任务并监控进度和质量",
                dependencies=["3"],
            ),
            TaskStep(
                id="5",
                description="风险管理和问题解决",
                action="识别和管理风险，解决问题",
                dependencies=["4"],
            ),
            TaskStep(
                id="6",
                description="成果交付和项目总结",
                action="交付成果，总结经验和教训",
                dependencies=["5"],
            ),
        ]
        
        dependencies = {
            "1": [],
            "2": ["1"],
            "3": ["2"],
            "4": ["3"],
            "5": ["4"],
            "6": ["5"],
        }
        
        return DecompositionResult(
            steps=steps,
            dependencies=dependencies,
            estimated_total_time=40.0,  # 估计40小时
            confidence=0.75,
            metadata={"source": "project_management_template"}
        )


# 便捷函数
def create_task_decomposer(strategy: str = "template_based") -> TaskDecomposer:
    """
    创建任务分解器的便捷函数
    
    Args:
        strategy: 分解策略，可选值: "rule_based", "llm_based", "template_based"
        
    Returns:
        任务分解器实例
    """
    strategy_map = {
        "rule_based": DecompositionStrategy.RULE_BASED,
        "llm_based": DecompositionStrategy.LLM_BASED,
        "template_based": DecompositionStrategy.TEMPLATE_BASED,
    }
    
    selected_strategy = strategy_map.get(strategy, DecompositionStrategy.TEMPLATE_BASED)
    return TaskDecomposer(selected_strategy)