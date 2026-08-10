"""
Tree of Thoughts (ToT) 规划器

基于Tree of Thoughts算法的规划器，支持多路径探索和优化决策。
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
import time
import random
import copy
from enum import Enum
import math

from .task_definitions import TaskStep, ComplexTask, TaskConstraint


class NodeStatus(str, Enum):
    """节点状态枚举"""
    UNEXPLORED = "unexplored"  # 未探索
    EXPLORING = "exploring"    # 探索中
    PRUNED = "pruned"          # 被剪枝
    EXPANDED = "expanded"      # 已扩展
    TERMINAL = "terminal"      # 终止节点


@dataclass
class ThoughtNode:
    """思维树节点"""
    id: str
    state: Dict[str, Any]  # 状态描述
    parent_id: Optional[str] = None  # 父节点ID
    children_ids: List[str] = field(default_factory=list)  # 子节点ID列表
    depth: int = 0  # 节点深度
    status: NodeStatus = NodeStatus.UNEXPLORED  # 节点状态
    value: Optional[float] = None  # 节点价值评估
    confidence: float = 0.0  # 置信度
    action: Optional[str] = None  # 到达此状态的动作
    cost: float = 0.0  # 到达此节点的累计成本
    constraints_satisfied: bool = True  # 约束是否满足
    metadata: Dict[str, Any] = field(default_factory=dict)  # 元数据
    
    def is_leaf(self) -> bool:
        """是否为叶子节点"""
        return len(self.children_ids) == 0
    
    def is_terminal(self) -> bool:
        """是否为终止节点（已完成状态）"""
        return self.status == NodeStatus.TERMINAL
    
    def get_path_to_root(self, node_map: Dict[str, 'ThoughtNode']) -> List['ThoughtNode']:
        """获取到根节点的路径"""
        path = []
        current = self
        while current is not None:
            path.append(current)
            if current.parent_id is None:
                break
            current = node_map.get(current.parent_id)
            if current is None:
                break
        return list(reversed(path))


class ToTPlanner:
    """Tree of Thoughts规划器"""
    
    def __init__(self, 
                 max_depth: int = 3,
                 max_width: int = 5,
                 max_iterations: int = 100,
                 exploration_factor: float = 0.3,
                 temperature: float = 0.7):
        """
        初始化ToT规划器
        
        Args:
            max_depth: 最大搜索深度
            max_width: 最大分支宽度
            max_iterations: 最大迭代次数
            exploration_factor: 探索因子（控制探索与利用的平衡）
            temperature: 温度参数，控制随机性
        """
        self.max_depth = max_depth
        self.max_width = max_width
        self.max_iterations = max_iterations
        self.exploration_factor = exploration_factor
        self.temperature = temperature
        
        # 状态跟踪
        self.nodes: Dict[str, ThoughtNode] = {}
        self.root_node_id: Optional[str] = None
        self.current_iteration = 0
        self.logger = None
        
        # 统计信息
        self.stats = {
            "nodes_created": 0,
            "nodes_expanded": 0,
            "nodes_pruned": 0,
            "best_value": float('-inf'),
            "search_time": 0.0,
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
    
    def plan(self, task: ComplexTask, initial_state: Dict[str, Any]) -> List[TaskStep]:
        """
        为任务创建规划
        
        Args:
            task: 要规划的任务
            initial_state: 初始状态描述
            
        Returns:
            规划出的任务步骤序列
        """
        start_time = time.time()
        self._log("info", f"开始为任务 '{task.goal}' 进行ToT规划")
        self._log("debug", f"规划参数: max_depth={self.max_depth}, max_width={self.max_width}")
        
        # 重置状态
        self._reset()
        
        # 创建根节点
        root_node = self._create_node(
            state=initial_state,
            parent_id=None,
            action="初始状态"
        )
        self.root_node_id = root_node.id
        
        # 主搜索循环
        best_plan = None
        best_value = float('-inf')
        
        for iteration in range(self.max_iterations):
            self.current_iteration = iteration
            self._log("debug", f"迭代 {iteration + 1}/{self.max_iterations}")
            
            # 1. 选择要扩展的节点
            selected_node = self._select_node_to_expand()
            if selected_node is None:
                self._log("debug", "没有可扩展的节点，停止搜索")
                break
            
            # 2. 扩展节点
            if not self._should_expand_node(selected_node):
                selected_node.status = NodeStatus.PRUNED
                self.stats["nodes_pruned"] += 1
                continue
            
            expanded_nodes = self._expand_node(selected_node, task)
            self.stats["nodes_expanded"] += 1
            
            # 3. 评估新节点
            for node in expanded_nodes:
                node.value = self._evaluate_node(node, task)
                node.confidence = self._calculate_confidence(node, task)
                
                # 更新最佳值
                if node.value is not None and node.value > self.stats["best_value"]:
                    self.stats["best_value"] = node.value
                    self._log("debug", f"找到更好的节点: value={node.value:.3f}, depth={node.depth}")
            
            # 4. 回溯更新
            self._backpropagate(selected_node)
            
            # 5. 检查终止条件（search_time 在循环内实时更新，使超时机制真正生效）
            self.stats["search_time"] = time.time() - start_time
            if self._should_terminate():
                self._log("debug", f"达到终止条件，停止搜索")
                break
        
        # 获取最佳规划
        best_plan_nodes = self._extract_best_plan()
        if best_plan_nodes:
            best_plan = self._convert_nodes_to_steps(best_plan_nodes, task)
            self._log("info", f"规划完成，找到包含 {len(best_plan)} 个步骤的规划")
        else:
            self._log("warning", "未找到有效的规划")
            best_plan = self._create_fallback_plan(task)
        
        # 记录统计信息
        self.stats["search_time"] = time.time() - start_time
        self._log_stats()
        
        return best_plan
    
    def _reset(self):
        """重置规划器状态"""
        self.nodes.clear()
        self.root_node_id = None
        self.current_iteration = 0
        self.stats = {
            "nodes_created": 0,
            "nodes_expanded": 0,
            "nodes_pruned": 0,
            "best_value": float('-inf'),
            "search_time": 0.0,
        }
    
    def _create_node(self, 
                    state: Dict[str, Any], 
                    parent_id: Optional[str] = None,
                    action: Optional[str] = None) -> ThoughtNode:
        """创建新节点"""
        node_id = f"node_{self.stats['nodes_created']}"
        
        # 计算深度
        depth = 0
        if parent_id is not None:
            parent = self.nodes.get(parent_id)
            if parent:
                depth = parent.depth + 1
        
        node = ThoughtNode(
            id=node_id,
            state=copy.deepcopy(state) if isinstance(state, dict) else state,
            parent_id=parent_id,
            depth=depth,
            action=action,
            cost=depth * 0.1,  # 简单成本模型：深度越深成本越高
        )
        
        self.nodes[node_id] = node
        self.stats["nodes_created"] += 1
        
        # 添加到父节点的子节点列表
        if parent_id is not None and parent_id in self.nodes:
            self.nodes[parent_id].children_ids.append(node_id)
        
        return node
    
    def _select_node_to_expand(self) -> Optional[ThoughtNode]:
        """选择要扩展的节点（使用UCT算法）"""
        # 获取所有可扩展的节点（叶子节点且未终止）
        expandable_nodes = []
        for node in self.nodes.values():
            if node.is_leaf() and not node.is_terminal() and node.status != NodeStatus.PRUNED:
                expandable_nodes.append(node)
        
        if not expandable_nodes:
            return None
        
        # UCT算法：平衡探索与利用
        if random.random() < self.exploration_factor:
            # 探索：随机选择一个节点
            return random.choice(expandable_nodes)
        else:
            # 利用：选择价值最高的节点
            best_node = None
            best_score = float('-inf')

            for node in expandable_nodes:
                # 获取访问次数（简化版）
                visit_count = len(node.children_ids)

                # 父节点访问次数
                parent_visit_count = 0
                if node.parent_id and node.parent_id in self.nodes:
                    parent_node = self.nodes[node.parent_id]
                    parent_visit_count = len(parent_node.children_ids)

                # UCT公式：value + C * sqrt(log(N) / (n + 1))
                # 未访问节点（value 为 None 或 visit_count==0）给予有限的高分，避免退化回随机
                if node.value is None or visit_count == 0:
                    uct_score = 100.0 + self.exploration_factor * math.sqrt(
                        math.log(parent_visit_count + 2))
                else:
                    exploration_term = math.sqrt(math.log(parent_visit_count + 1) / (visit_count + 1))
                    uct_score = node.value + self.exploration_factor * exploration_term

                if uct_score > best_score:
                    best_score = uct_score
                    best_node = node

            return best_node or random.choice(expandable_nodes)
    
    def _should_expand_node(self, node: ThoughtNode) -> bool:
        """判断是否应该扩展节点"""
        # 检查深度限制
        if node.depth >= self.max_depth:
            return False
        
        # 检查成本限制
        if node.cost > 10.0:  # 简单成本阈值
            return False
        
        return True
    
    def _expand_node(self, node: ThoughtNode, task: ComplexTask) -> List[ThoughtNode]:
        """扩展节点，生成子节点"""
        self._log("debug", f"扩展节点 {node.id} (深度: {node.depth})")
        
        # 生成可能的下一步动作
        possible_actions = self._generate_possible_actions(node, task)
        
        # 限制分支宽度
        if len(possible_actions) > self.max_width:
            # 选择最有希望的动作
            possible_actions = self._select_best_actions(possible_actions, self.max_width)
        
        # 为每个动作创建子节点
        expanded_nodes = []
        for action in possible_actions:
            # 模拟执行动作，得到新状态
            new_state = self._simulate_action(node.state, action, task)
            
            # 检查约束
            constraints_satisfied = self._check_constraints(new_state, task.constraints)
            
            # 创建子节点
            child_node = self._create_node(
                state=new_state,
                parent_id=node.id,
                action=action
            )
            child_node.constraints_satisfied = constraints_satisfied
            
            # 标记为终止节点（如果达到目标状态）
            if self._is_goal_state(child_node.state, task):
                child_node.status = NodeStatus.TERMINAL
            
            expanded_nodes.append(child_node)
        
        node.status = NodeStatus.EXPANDED
        self._log("debug", f"节点 {node.id} 扩展完成，生成 {len(expanded_nodes)} 个子节点")
        
        return expanded_nodes
    
    def _generate_possible_actions(self, node: ThoughtNode, task: ComplexTask) -> List[str]:
        """生成可能的下一步动作"""
        # 基于任务类型生成动作
        actions = []
        state = node.state
        
        # 通用动作
        generic_actions = [
            "分析需求",
            "收集信息",
            "制定计划",
            "执行任务",
            "检查进度",
            "调整策略",
            "完成交付",
        ]
        
        # 根据任务类型添加特定动作
        if task.task_type == "party_planning":
            actions.extend([
                "确定参与人员",
                "选择时间和地点",
                "预订场地",
                "发送邀请",
                "准备餐饮",
                "确认安排",
            ])
        elif task.task_type == "travel_planning":
            actions.extend([
                "确定目的地",
                "查询交通",
                "预订住宿",
                "规划行程",
                "准备材料",
                "设置提醒",
            ])
        elif task.task_type == "project_management":
            actions.extend([
                "分析目标",
                "分解任务",
                "分配资源",
                "制定时间线",
                "监控进度",
                "管理风险",
                "交付成果",
            ])
        else:
            actions.extend(generic_actions)
        
        # 根据当前状态过滤不合适的动作（不截断，由 _expand_node 的宽度控制决定）
        filtered_actions = []
        for action in actions:
            if self._is_action_applicable(state, action, task):
                filtered_actions.append(action)

        # 若动作池为空，补充一个通用动作，避免扩展僵死
        if not filtered_actions:
            filtered_actions = ["推进下一步"]

        return filtered_actions
    
    def _select_best_actions(self, actions: List[str], count: int) -> List[str]:
        """选择最有希望的动作"""
        if len(actions) <= count:
            return actions

        # 启发式优先级：靠近"完成/交付/确认"的动作优先保留（能更快到达目标状态）
        completion_keywords = ("完成", "交付", "确认", "发送", "预订", "准备", "确定")
        scored = []
        for action in actions:
            score = 0.0
            for i, kw in enumerate(completion_keywords):
                if kw in action:
                    score += (len(completion_keywords) - i)
            scored.append((score, action))

        # 按启发式分数降序，保留前 count 个；分数相同时保留顺序
        scored.sort(key=lambda x: -x[0])
        return [a for _, a in scored[:count]]
    
    def _simulate_action(self, current_state: Dict[str, Any], action: str, task: ComplexTask) -> Dict[str, Any]:
        """模拟执行动作，返回新状态（深拷贝，避免子节点间共享可变状态）"""
        new_state = copy.deepcopy(current_state)
        
        # 添加动作到历史
        if "action_history" not in new_state:
            new_state["action_history"] = []
        new_state["action_history"].append(action)
        
        # 更新状态描述
        new_state["last_action"] = action
        new_state["step_count"] = new_state.get("step_count", 0) + 1
        
        # 根据动作类型更新特定状态字段
        if "确定" in action or "选择" in action:
            new_state["decisions_made"] = new_state.get("decisions_made", 0) + 1
        elif "预订" in action or "准备" in action:
            new_state["resources_allocated"] = new_state.get("resources_allocated", 0) + 1
        elif "完成" in action or "交付" in action:
            # 完成/交付类动作：进度达到 1.0（需先经过足够步骤，否则节点不会展开到这里）
            new_state["progress"] = 1.0
            new_state["completed"] = True

        return new_state
    
    def _check_constraints(self, state: Dict[str, Any], constraints: List[TaskConstraint]) -> bool:
        """检查状态是否满足约束"""
        # 简化实现：检查基本约束
        for constraint in constraints:
            if constraint.is_required and constraint.value is None:
                return False
        
        return True
    
    def _is_goal_state(self, state: Dict[str, Any], task: ComplexTask) -> bool:
        """判断是否为目标状态"""
        action_history = state.get("action_history", [])
        step_count = len(action_history)

        # 完成/交付动作只有在已执行过至少 1 个其他步骤时才视为终点
        # （避免"第一动作即完成"的退化规划）
        last_action = state.get("last_action", "")
        is_finish_action = ("完成" in last_action or "交付" in last_action or "确认" in last_action)
        if is_finish_action:
            if step_count >= 2 or "completed" in state:
                return True
            return False

        # 检查进度
        progress = state.get("progress", 0.0)
        if progress >= 0.9:
            return True

        # 动作历史达到最大深度 → 视为完整路径
        if step_count >= max(2, self.max_depth):
            return True

        return False
    
    def _is_action_applicable(self, state: Dict[str, Any], action: str, task: ComplexTask) -> bool:
        """判断动作在当前状态下是否适用"""
        # 检查动作历史，避免重复
        action_history = state.get("action_history", [])
        if action in action_history:
            return False  # 避免重复执行相同动作

        # 终局动作（完成/交付）需先经过至少一个中间步骤，避免一步到位
        if ("完成" in action or "交付" in action) and len(action_history) < 1:
            return False

        # 确认类动作需至少一个前置步骤（原硬编码"先发送邀请"只适用派对场景，
        # 会误拦旅行/会议等任务的"确认安排"，改为通用前置约束）
        if "确认" in action and len(action_history) < 1:
            return False

        return True
    
    def _evaluate_node(self, node: ThoughtNode, task: ComplexTask) -> float:
        """评估节点价值"""
        if not node.constraints_satisfied:
            return float('-inf')  # 不满足约束的节点价值为负无穷
        
        # 基础价值
        value = 0.0
        
        # 1. 进度奖励
        progress = node.state.get("progress", 0.0)
        value += progress * 100
        
        # 2. 步骤效率奖励（步骤越少越好）
        step_count = node.state.get("step_count", 0)
        if step_count > 0:
            value += 50.0 / step_count
        
        # 3. 决策质量奖励
        decisions_made = node.state.get("decisions_made", 0)
        value += decisions_made * 5
        
        # 4. 资源分配奖励
        resources_allocated = node.state.get("resources_allocated", 0)
        value += resources_allocated * 3
        
        # 5. 深度惩罚（鼓励浅层解决方案）
        value -= node.depth * 2
        
        # 6. 成本惩罚
        value -= node.cost * 10
        
        # 7. 目标完成奖励
        if self._is_goal_state(node.state, task):
            value += 200
        
        # 添加随机噪声（受温度参数影响）
        noise = random.gauss(0, self.temperature * 10)
        value += noise
        
        return value
    
    def _calculate_confidence(self, node: ThoughtNode, task: ComplexTask) -> float:
        """计算节点置信度"""
        # 基于多个因素计算置信度
        factors = []
        
        # 1. 约束满足度
        factors.append(1.0 if node.constraints_satisfied else 0.0)
        
        # 2. 进度
        progress = node.state.get("progress", 0.0)
        factors.append(progress)
        
        # 3. 动作历史长度（适度）
        action_history = node.state.get("action_history", [])
        action_factor = min(len(action_history) / 10.0, 1.0)
        factors.append(action_factor)
        
        # 4. 决策数量（适度）
        decisions_made = node.state.get("decisions_made", 0)
        decision_factor = min(decisions_made / 5.0, 1.0)
        factors.append(decision_factor)
        
        # 5. 是否为终止节点
        factors.append(1.0 if node.is_terminal() else 0.5)
        
        # 加权平均
        weights = [0.3, 0.3, 0.2, 0.1, 0.1]
        confidence = sum(f * w for f, w in zip(factors, weights))
        
        return min(max(confidence, 0.0), 1.0)
    
    def _backpropagate(self, node: ThoughtNode):
        """回溯更新从当前节点到根节点路径上所有祖先的价值。

        父节点价值取子节点价值的加权平均（考虑子节点数量），
        使搜索能逐步向高价值分支收敛。
        """
        current = node
        visited = 0
        while current is not None and current.parent_id is not None and visited < 100:
            parent = self.nodes.get(current.parent_id)
            if parent is None:
                break
            # 用子节点价值平均值更新父节点价值（仅当有子节点价值时）
            valued_children = [c.value for cid in parent.children_ids
                               for c in [self.nodes.get(cid)] if c is not None and c.value is not None]
            if valued_children:
                parent.value = sum(valued_children) / len(valued_children)
            current = parent
            visited += 1
    
    def _should_terminate(self) -> bool:
        """判断是否应该终止搜索"""
        # 检查迭代次数（iteration 从 0 开始，max_iterations=100 → 0..99）
        if self.current_iteration >= self.max_iterations - 1:
            return True

        # 检查时间限制（search_time 由主循环实时更新）
        if self.stats.get("search_time", 0) > 30.0:  # 30秒超时
            return True

        # 检查是否找到足够好的解决方案（找到终止节点即视为收敛）
        has_terminal = any(n.is_terminal() for n in self.nodes.values())
        if has_terminal and self.stats["best_value"] > 50.0:
            return True

        return False
    
    def _extract_best_plan(self) -> List[ThoughtNode]:
        """提取最佳规划路径。

        优先选择终止节点；其次在非终止节点中选择"价值 × 深度"综合分最高的，
        确保选出的是完整的多步路径而不是浅层单步节点。
        """
        best_node = None
        best_score = float('-inf')

        for node in self.nodes.values():
            if node.value is None or node.status == NodeStatus.PRUNED:
                continue
            # 终止节点优先（大权重），其次综合价值×深度
            if node.is_terminal():
                score = node.value + 1000.0 + node.depth * 10
            else:
                score = node.value + node.depth * 5
            if score > best_score:
                best_score = score
                best_node = node

        if best_node is None:
            return []

        return best_node.get_path_to_root(self.nodes)
    
    def _convert_nodes_to_steps(self, nodes: List[ThoughtNode], task: ComplexTask) -> List[TaskStep]:
        """将节点序列转换为任务步骤"""
        steps = []
        
        for i, node in enumerate(nodes):
            if i == 0:
                continue  # 跳过根节点
            
            step_id = str(i)
            description = f"执行: {node.action}" if node.action else f"步骤 {i}"
            
            # 构建依赖关系
            dependencies = []
            if i > 1:
                dependencies.append(str(i - 1))
            
            step = TaskStep(
                id=step_id,
                description=description,
                action=node.action or "执行任务",
                dependencies=dependencies,
            )
            
            steps.append(step)
        
        return steps
    
    def _create_fallback_plan(self, task: ComplexTask) -> List[TaskStep]:
        """创建回退规划"""
        self._log("warning", "创建回退规划")
        
        # 简单的回退规划：3个基本步骤
        steps = [
            TaskStep(
                id="1",
                description=f"分析任务: {task.goal}",
                action="分析任务需求和约束",
                dependencies=[],
            ),
            TaskStep(
                id="2",
                description="制定执行计划",
                action="制定详细执行步骤",
                dependencies=["1"],
            ),
            TaskStep(
                id="3",
                description="执行并监控",
                action="执行计划并监控进度",
                dependencies=["2"],
            ),
        ]
        
        return steps
    
    def _log_stats(self):
        """记录统计信息"""
        if self.logger:
            self._log("info", "ToT规划统计:")
            self._log("info", f"  创建节点数: {self.stats['nodes_created']}")
            self._log("info", f"  扩展节点数: {self.stats['nodes_expanded']}")
            self._log("info", f"  剪枝节点数: {self.stats['nodes_pruned']}")
            self._log("info", f"  最佳价值: {self.stats['best_value']:.3f}")
            self._log("info", f"  搜索时间: {self.stats['search_time']:.2f}秒")


# 便捷函数
def create_tot_planner(max_depth: int = 3, max_width: int = 5, 
                       temperature: float = 0.7) -> ToTPlanner:
    """
    创建ToT规划器的便捷函数
    
    Args:
        max_depth: 最大搜索深度
        max_width: 最大分支宽度
        temperature: 温度参数
        
    Returns:
        ToT规划器实例
    """
    return ToTPlanner(
        max_depth=max_depth,
        max_width=max_width,
        max_iterations=100,
        exploration_factor=0.3,
        temperature=temperature,
    )