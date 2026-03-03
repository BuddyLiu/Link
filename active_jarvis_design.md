# JARVIS主动运行模式设计方案

## 问题分析

当前JARVIS系统的局限性：
1. **被动响应式架构**：等待用户输入 → 处理 → 返回结果
2. **无自主运行能力**：没有用户指令时完全空闲
3. **缺乏持续监控**：不主动检查任务状态、记忆变化或环境条件
4. **无学习进化机制**：不会根据历史经验主动学习新技能

## 设计目标

构建类似iOS RunLoop的主动智能体系统：

1. **事件驱动循环**：持续运行的主循环，处理多种事件源
2. **优先级调度**：智能安排任务执行顺序
3. **自主学习能力**：根据记忆和经验主动学习新技能
4. **周期性任务**：定时执行维护、学习和检查任务
5. **状态监控**：实时监控系统状态和外部环境变化

## 系统架构设计

### 核心组件

```
JARVIS主动运行系统
├── EventLoop (主事件循环)
├── Event Sources (事件源)
│   ├── UserInputSource (用户输入)
│   ├── TaskStatusSource (任务状态监控)
│   ├── MemoryUpdateSource (记忆更新)
│   ├── TimerSource (定时器)
│   ├── ExternalEventSource (外部事件)
│   └── SelfLearningSource (自主学习)
├── Event Handlers (事件处理器)
│   ├── TaskExecutor (任务执行器)
│   ├── ReminderChecker (提醒检查器)
│   ├── MemoryProcessor (记忆处理器)
│   ├── LearningTrigger (学习触发器)
│   └── StatusReporter (状态报告器)
└── Scheduler (调度器)
    ├── PriorityQueue (优先级队列)
    ├── ResourceManager (资源管理)
    └── LoadBalancer (负载均衡)
```

### 事件循环流程

```python
class ActiveJARVIS:
    def __init__(self):
        self.event_loop = EventLoop()
        self.is_running = False
    
    def run(self):
        """主动运行模式主循环"""
        self.is_running = True
        
        # 初始化所有事件源
        self._initialize_event_sources()
        
        # 主循环
        while self.is_running:
            # 1. 收集所有事件
            events = self._collect_events()
            
            # 2. 优先级排序
            prioritized_events = self._prioritize_events(events)
            
            # 3. 处理事件（限制并发数量）
            self._process_events(prioritized_events)
            
            # 4. 执行周期性任务
            self._run_periodic_tasks()
            
            # 5. 状态更新和清理
            self._update_state()
            
            # 6. 短暂休眠避免CPU占用过高
            time.sleep(0.1)  # 100ms
    
    def _collect_events(self):
        """从所有事件源收集事件"""
        events = []
        for source in self.event_sources:
            source_events = source.poll()
            events.extend(source_events)
        return events
```

## 事件源设计

### 1. 用户输入源 (UserInputSource)
- 监听命令行、WebSocket、API等用户输入通道
- 将用户输入转换为高优先级事件
- 支持异步输入处理

### 2. 任务状态监控源 (TaskStatusSource)
- 监控所有活跃任务的状态变化
- 检测阻塞、失败、超时的任务
- 触发重试、回退或通知事件

### 3. 记忆更新源 (MemoryUpdateSource)
- 监控记忆系统的更新
- 检测重要记忆变化（用户偏好、关键事件等）
- 触发关联分析和主动建议

### 4. 定时器源 (TimerSource)
- 周期性任务调度
- 定时提醒和检查
- 系统维护任务

### 5. 外部事件源 (ExternalEventSource)
- 集成外部API（日历、天气、新闻等）
- 环境变化检测（位置、时间、设备状态）
- 第三方系统通知

### 6. 自主学习源 (SelfLearningSource)
- 分析任务执行历史
- 识别知识缺口和技能需求
- 触发主动学习和技能获取

## 事件处理器设计

### 1. 任务执行器 (TaskExecutor)
- 执行规划引擎生成的任务步骤
- 资源分配和并发控制
- 错误处理和重试机制

### 2. 提醒检查器 (ReminderChecker)
- 集成现有的提醒系统
- 条件触发检查和通知发送
- 重复提醒管理

### 3. 记忆处理器 (MemoryProcessor)
- 记忆归档和整理
- 关联分析和模式识别
- 知识图谱构建和更新

### 4. 学习触发器 (LearningTrigger)
- 基于记忆分析触发学习
- 技能获取和优化
- 模型参数调整

### 5. 状态报告器 (StatusReporter)
- 系统状态监控和报告
- 性能指标收集
- 异常检测和告警

## 优先级调度策略

### 事件优先级等级

| 优先级 | 事件类型 | 处理延迟 | 示例 |
|--------|----------|----------|------|
| **P0** | 关键系统事件 | 立即 | 系统错误、内存不足、任务失败 |
| **P1** | 用户交互事件 | < 1秒 | 用户命令、紧急请求 |
| **P2** | 时间敏感事件 | < 5秒 | 定时提醒、实时通知 |
| **P3** | 常规处理事件 | < 30秒 | 任务执行、数据处理 |
| **P4** | 后台维护事件 | 分钟级 | 记忆整理、模型训练、系统优化 |
| **P5** | 学习进化事件 | 小时级 | 技能学习、知识获取、长期优化 |

### 调度算法
```python
class PriorityScheduler:
    def prioritize(self, events):
        # 基于多个因素的优先级计算
        scores = []
        for event in events:
            score = self._calculate_priority_score(event)
            scores.append((score, event))
        
        # 按分数降序排序
        scores.sort(key=lambda x: x[0], reverse=True)
        return [event for _, event in scores]
    
    def _calculate_priority_score(self, event):
        score = 0
        
        # 1. 基础优先级权重
        score += event.base_priority * 100
        
        # 2. 时间紧迫性（越接近截止时间分数越高）
        if event.deadline:
            time_left = (event.deadline - datetime.now()).total_seconds()
            if time_left > 0:
                score += max(0, 100 - time_left)  # 时间越少分数越高
        
        # 3. 资源可用性
        score += self._resource_availability_factor(event)
        
        # 4. 用户影响因子
        score += event.user_importance * 50
        
        # 5. 系统重要性
        score += event.system_importance * 75
        
        return score
```

## 自主学习机制

### 学习触发条件

1. **任务失败分析**
   - 当任务重复失败时触发学习
   - 分析失败原因，学习正确方法
   - 更新技能库和知识库

2. **知识缺口检测**
   - 监控无法处理的任务类型
   - 识别需要的新技能
   - 主动寻找或学习相关技能

3. **性能优化学习**
   - 分析任务执行效率
   - 学习优化策略
   - 更新模型参数和算法

4. **用户偏好学习**
   - 分析用户行为和反馈
   - 学习个性化偏好
   - 调整服务和响应方式

### 学习流程

```python
class SelfLearningSystem:
    def __init__(self):
        self.learning_triggers = []
        self.knowledge_base = KnowledgeBase()
        self.skill_library = SkillLibrary()
    
    def monitor_and_learn(self):
        """监控并触发学习"""
        # 1. 收集学习信号
        signals = self._collect_learning_signals()
        
        # 2. 分析学习需求
        learning_needs = self._analyze_learning_needs(signals)
        
        # 3. 制定学习计划
        for need in learning_needs:
            plan = self._create_learning_plan(need)
            
            # 4. 执行学习
            result = self._execute_learning(plan)
            
            # 5. 验证和应用
            if result.success:
                self._apply_learning_result(result)
```

## 周期性任务设计

### 高频任务（秒级）
1. 心跳检查
2. 任务状态监控
3. 用户输入检查

### 中频任务（分钟级）
1. 提醒检查（可配置间隔）
2. 记忆归档
3. 性能指标收集

### 低频任务（小时级）
1. 系统维护
2. 模型重新训练
3. 知识库整理
4. 备份和清理

### 配置示例
```python
periodic_tasks = {
    "heartbeat": {
        "interval": 1,  # 秒
        "function": self._send_heartbeat,
        "enabled": True
    },
    "task_monitor": {
        "interval": 5,  # 秒
        "function": self._monitor_tasks,
        "enabled": True
    },
    "reminder_check": {
        "interval": 60,  # 秒
        "function": self._check_reminders,
        "enabled": True
    },
    "memory_archive": {
        "interval": 300,  # 5分钟
        "function": self._archive_memories,
        "enabled": True
    }
}
```

## 与现有系统集成方案

### 1. 渐进式迁移
```python
# 第一阶段：保持向后兼容
class HybridJARVIS:
    def __init__(self):
        self.active_mode = False
        self.legacy_jarvis = LegacyJARVIS()  # 现有系统
        self.active_jarvis = None
    
    def run(self, mode="active"):
        if mode == "active":
            self.active_mode = True
            self.active_jarvis = ActiveJARVIS()
            self.active_jarvis.run()
        else:
            # 回退到传统模式
            self.legacy_jarvis.run_cli()
```

### 2. 组件重用
- **重用提醒系统**：集成到定时器事件源
- **重用记忆系统**：集成到记忆更新事件源
- **重用规划引擎**：集成到任务执行器
- **重用大脑引擎**：集成到学习系统

### 3. 配置驱动
```yaml
mode: "active"  # active, hybrid, legacy

active_mode:
  event_loop_interval: 0.1  # 100ms
  max_concurrent_events: 5
  enable_self_learning: true
  periodic_tasks:
    enabled: true
    tasks:
      - name: "heartbeat"
        interval: 1
      - name: "task_monitor"
        interval: 5
```

## 实现步骤

### 第一阶段：基础事件循环
1. 实现基本的事件循环框架
2. 集成用户输入和定时器事件源
3. 实现优先级调度器
4. 测试基本功能

### 第二阶段：集成现有组件
1. 集成提醒系统作为定时器事件源
2. 集成任务系统作为任务状态监控源
3. 实现基本的周期性任务
4. 测试系统稳定性

### 第三阶段：自主学习能力
1. 实现学习触发和监控
2. 集成大脑引擎进行主动学习
3. 实现知识库更新机制
4. 测试学习效果

### 第四阶段：优化和扩展
1. 性能优化和资源管理
2. 扩展外部事件源
3. 实现高级调度策略
4. 系统测试和调优

## 预期效果

### 用户可见改进
1. **更快的响应速度**：事件驱动比轮询更高效
2. **主动服务能力**：系统能主动发现问题并提供帮助
3. **个性化体验**：通过学习理解用户偏好
4. **可靠性提升**：系统监控和自动修复

### 系统性能指标
1. **响应时间**：P1事件 < 1秒，P2事件 < 5秒
2. **资源占用**：CPU < 30%，内存 < 500MB
3. **任务成功率**：> 95%
4. **学习效率**：新技能学习时间 < 24小时

## 风险评估与缓解

### 技术风险
1. **事件循环复杂性**：采用成熟的事件驱动框架
2. **资源竞争**：实现合理的并发控制和资源管理
3. **系统稳定性**：完善的错误处理和恢复机制

### 迁移风险
1. **向后兼容性**：保持传统模式作为回退选项
2. **数据一致性**：确保新旧系统数据同步
3. **用户体验**：逐步迁移，提供切换选项

## 总结

主动运行模式将使JARVIS从一个被动的工具转变为真正的智能助手。通过事件驱动架构、优先级调度和自主学习机制，系统将能够：

1. **主动感知**环境和用户需求
2. **智能决策**任务执行顺序
3. **持续学习**和优化自身能力
4. **可靠运行**并提供稳定服务

这种设计更符合Order.txt中描述的"贾维斯式智能体"愿景，为用户提供真正智能、主动、个性化的AI助手体验。