"""
复杂任务类型定义模块

定义LINK智能体支持的复杂任务类型、模板和约束条件。
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from enum import Enum
from datetime import datetime, timedelta


class TaskType(str, Enum):
    """任务类型枚举"""
    PARTY_PLANNING = "party_planning"  # 聚会安排
    TRAVEL_PLANNING = "travel_planning"  # 旅行规划
    PROJECT_MANAGEMENT = "project_management"  # 项目管理
    LEARNING_PLAN = "learning_plan"  # 学习计划
    DAILY_ROUTINE = "daily_routine"  # 日常安排
    EVENT_COORDINATION = "event_coordination"  # 活动协调


class TaskPriority(int, Enum):
    """任务优先级枚举"""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    URGENT = 4


@dataclass
class TaskConstraint:
    """任务约束条件"""
    type: str  # 约束类型: time, budget, location, resource, etc.
    description: str  # 约束描述
    value: Any  # 约束值
    is_required: bool = True  # 是否为必需约束


@dataclass
class TaskStep:
    """任务步骤"""
    id: str
    description: str
    action: str  # 需要执行的动作
    dependencies: List[str] = field(default_factory=list)  # 依赖的步骤ID
    estimated_duration: Optional[timedelta] = None  # 预计耗时
    assigned_to: Optional[str] = None  # 分配给谁
    status: str = "pending"  # 状态: pending, in_progress, completed, failed
    result: Optional[Any] = None  # 执行结果


@dataclass
class ComplexTask:
    """复杂任务定义"""
    id: str
    goal: str
    description: str
    task_type: TaskType
    constraints: List[TaskConstraint] = field(default_factory=list)
    priority: TaskPriority = TaskPriority.MEDIUM
    deadline: Optional[datetime] = None
    steps: List[TaskStep] = field(default_factory=list)
    status: str = "pending"  # 状态: pending, planning, executing, completed, failed
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_constraint(self, constraint: TaskConstraint):
        """添加约束条件"""
        self.constraints.append(constraint)
        self.updated_at = datetime.now()

    def add_step(self, step: TaskStep):
        """添加任务步骤"""
        self.steps.append(step)
        self.updated_at = datetime.now()

    def get_step_by_id(self, step_id: str) -> Optional[TaskStep]:
        """根据ID获取任务步骤"""
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def update_step_status(self, step_id: str, status: str, result: Any = None):
        """更新步骤状态"""
        step = self.get_step_by_id(step_id)
        if step:
            step.status = status
            step.result = result
            self.updated_at = datetime.now()


class TaskTemplate:
    """任务模板基类"""
    
    def __init__(self, task_type: TaskType):
        self.task_type = task_type
        self.common_steps = []
        self.common_constraints = []
        self._init_template()
    
    def _init_template(self):
        """初始化模板（子类实现）"""
        pass
    
    def create_task(self, goal: str, description: str, **kwargs) -> ComplexTask:
        """根据模板创建任务"""
        raise NotImplementedError("子类必须实现此方法")


class PartyPlanningTemplate(TaskTemplate):
    """聚会安排模板"""
    
    def _init_template(self):
        self.task_type = TaskType.PARTY_PLANNING
        
        # 常见约束
        self.common_constraints = [
            TaskConstraint("time", "聚会时间", None, True),
            TaskConstraint("budget", "预算限制", None, False),
            TaskConstraint("location", "地点要求", None, True),
            TaskConstraint("participants", "参与人数", None, True),
        ]
        
        # 常见步骤
        self.common_steps = [
            TaskStep("1", "确定参与人员", "确定聚会参与人员名单"),
            TaskStep("2", "选择时间和地点", "根据参与人员时间协调聚会时间和地点"),
            TaskStep("3", "预订场地", "预订餐厅、活动场地或准备家庭聚会空间"),
            TaskStep("4", "发送邀请", "通过消息、邮件等方式发送邀请"),
            TaskStep("5", "准备活动内容", "规划聚会活动、餐饮、娱乐等"),
            TaskStep("6", "确认参与情况", "确认参与人员并做最终安排"),
        ]
    
    def create_task(self, goal: str, description: str, **kwargs) -> ComplexTask:
        """创建聚会安排任务"""
        task = ComplexTask(
            id=f"party_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            goal=goal,
            description=description,
            task_type=self.task_type,
            constraints=self.common_constraints.copy(),
        )
        
        # 添加步骤
        for step in self.common_steps:
            task.add_step(step)
        
        # 设置约束值
        if "time" in kwargs:
            task.constraints[0].value = kwargs["time"]
        if "budget" in kwargs:
            task.constraints[1].value = kwargs["budget"]
        if "location" in kwargs:
            task.constraints[2].value = kwargs["location"]
        if "participants" in kwargs:
            task.constraints[3].value = kwargs["participants"]
        
        return task


class TravelPlanningTemplate(TaskTemplate):
    """旅行规划模板"""
    
    def _init_template(self):
        self.task_type = TaskType.TRAVEL_PLANNING
        
        # 常见约束
        self.common_constraints = [
            TaskConstraint("destination", "目的地", None, True),
            TaskConstraint("time_range", "时间范围", None, True),
            TaskConstraint("budget", "预算限制", None, False),
            TaskConstraint("participants", "同行人员", None, False),
            TaskConstraint("preferences", "偏好要求", None, False),
        ]
        
        # 常见步骤
        self.common_steps = [
            TaskStep("1", "确定目的地和日期", "确定旅行目的地和具体时间"),
            TaskStep("2", "查询交通信息", "查询航班、火车或自驾路线"),
            TaskStep("3", "预订交通", "预订机票、火车票等"),
            TaskStep("4", "预订住宿", "预订酒店或民宿"),
            TaskStep("5", "规划行程", "规划每日行程和活动"),
            TaskStep("6", "准备旅行材料", "准备证件、保险、行程单等"),
            TaskStep("7", "设置提醒", "设置出发前提醒和相关提醒"),
        ]
    
    def create_task(self, goal: str, description: str, **kwargs) -> ComplexTask:
        """创建旅行规划任务"""
        task = ComplexTask(
            id=f"travel_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            goal=goal,
            description=description,
            task_type=self.task_type,
            constraints=self.common_constraints.copy(),
        )
        
        # 添加步骤
        for step in self.common_steps:
            task.add_step(step)
        
        # 设置约束值
        if "destination" in kwargs:
            task.constraints[0].value = kwargs["destination"]
        if "time_range" in kwargs:
            task.constraints[1].value = kwargs["time_range"]
        if "budget" in kwargs:
            task.constraints[2].value = kwargs["budget"]
        if "participants" in kwargs:
            task.constraints[3].value = kwargs["participants"]
        if "preferences" in kwargs:
            task.constraints[4].value = kwargs["preferences"]
        
        return task


class ProjectManagementTemplate(TaskTemplate):
    """项目管理模板"""
    
    def _init_template(self):
        self.task_type = TaskType.PROJECT_MANAGEMENT
        
        # 常见约束
        self.common_constraints = [
            TaskConstraint("deadline", "项目截止时间", None, True),
            TaskConstraint("budget", "预算限制", None, False),
            TaskConstraint("resources", "可用资源", None, False),
            TaskConstraint("quality", "质量标准", None, False),
        ]
        
        # 常见步骤
        self.common_steps = [
            TaskStep("1", "项目目标分析", "明确项目目标和期望成果"),
            TaskStep("2", "任务分解", "将项目分解为具体可执行的任务"),
            TaskStep("3", "资源分配", "分配人力、时间和物质资源"),
            TaskStep("4", "时间线规划", "制定项目时间线和里程碑"),
            TaskStep("5", "执行监控", "监控任务执行进度和质量"),
            TaskStep("6", "风险管理", "识别和管理项目风险"),
            TaskStep("7", "成果交付", "交付项目成果并总结"),
        ]
    
    def create_task(self, goal: str, description: str, **kwargs) -> ComplexTask:
        """创建项目管理任务"""
        task = ComplexTask(
            id=f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            goal=goal,
            description=description,
            task_type=self.task_type,
            constraints=self.common_constraints.copy(),
        )
        
        # 添加步骤
        for step in self.common_steps:
            task.add_step(step)
        
        # 设置约束值
        if "deadline" in kwargs:
            task.constraints[0].value = kwargs["deadline"]
        if "budget" in kwargs:
            task.constraints[1].value = kwargs["budget"]
        if "resources" in kwargs:
            task.constraints[2].value = kwargs["resources"]
        if "quality" in kwargs:
            task.constraints[3].value = kwargs["quality"]
        
        return task


class TaskTemplateRegistry:
    """任务模板注册表"""
    
    def __init__(self):
        self.templates: Dict[TaskType, TaskTemplate] = {}
        self._register_default_templates()
    
    def _register_default_templates(self):
        """注册默认模板"""
        self.register_template(PartyPlanningTemplate(TaskType.PARTY_PLANNING))
        self.register_template(TravelPlanningTemplate(TaskType.TRAVEL_PLANNING))
        self.register_template(ProjectManagementTemplate(TaskType.PROJECT_MANAGEMENT))
    
    def register_template(self, template: TaskTemplate):
        """注册任务模板"""
        self.templates[template.task_type] = template
    
    def get_template(self, task_type: TaskType) -> Optional[TaskTemplate]:
        """获取任务模板"""
        return self.templates.get(task_type)
    
    def create_task_from_template(self, task_type: TaskType, goal: str, 
                                  description: str, **kwargs) -> Optional[ComplexTask]:
        """根据模板创建任务"""
        template = self.get_template(task_type)
        if template:
            return template.create_task(goal, description, **kwargs)
        return None
    
    def list_available_templates(self) -> List[TaskType]:
        """列出可用模板类型"""
        return list(self.templates.keys())


# 全局模板注册表实例
task_template_registry = TaskTemplateRegistry()


def create_task(task_type: TaskType, goal: str, description: str, **kwargs) -> Optional[ComplexTask]:
    """
    创建复杂任务的便捷函数
    
    Args:
        task_type: 任务类型
        goal: 任务目标
        description: 任务描述
        **kwargs: 约束条件参数
    
    Returns:
        ComplexTask: 创建的任务，如果失败则返回None
    """
    return task_template_registry.create_task_from_template(task_type, goal, description, **kwargs)