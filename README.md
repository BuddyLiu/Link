# JARVIS智能体基座

JARVIS（Just A Rather Very Intelligent System）是一个模块化、可扩展的智能体基座系统，旨在构建类似电影《钢铁侠》中贾维斯的AI助手。项目遵循Order.txt中定义的三个阶段路线图，目前已完成第三阶段功能开发。

## 🚀 项目状态

- **当前阶段**：第三阶段（复杂任务规划、反思和主动提醒）
- **版本**：3.0
- **架构**：模块化分层设计
- **目标**：构建具备全局记忆、主动预判、无缝操控能力的数字管家

## 📁 统一启动入口

项目提供了一个统一的启动入口，支持多种运行模式：

### 启动方式

```bash
# 启动主动运行模式（默认，事件驱动，类似iOS RunLoop）
python main/run_jarvis.py

# 启动传统CLI模式（响应式，无主动监控）
python main/run_jarvis.py cli

# 启动Web服务模式
python main/run_jarvis.py web --host 0.0.0.0 --port 8030

# 运行测试套件
python main/run_jarvis.py test

# 运行自动执行演示
python main/run_jarvis.py demo

# 启动简单Web界面
python main/run_jarvis.py simple-web
```

### 命令行选项

```
用法：
  python main/run_jarvis.py [模式] [选项]

可用模式：
  active       - 主动运行模式（默认，事件驱动，类似iOS RunLoop）
  cli          - 传统命令行模式（响应式，无主动监控）
  web          - Web服务模式
  test         - 运行测试套件
  demo         - 运行自动执行演示
  simple-web   - 运行简单Web界面

常用选项：
  --debug              启用调试模式
  --host HOST          Web服务主机地址（默认: 127.0.0.1）
  --port PORT          Web服务端口（默认: 8000）
  --active-config FILE 主动模式配置文件路径
  --help              显示帮助信息
```

## 🏗️ 项目架构

### 核心模块

```
JARVIS/
├── main/                    # 启动入口和演示脚本
│   ├── run_jarvis.py       # 🔥 统一启动入口（主要使用这个）
│   ├── main.py             # 传统主程序（第三阶段）
│   ├── active_jarvis_enhanced.py    # 主动运行模式实现
│   ├── main_with_active.py           # 包含主动模式的主程序
│   └── 其他启动脚本...
├── src/                    # 源代码
│   ├── config/            # 配置管理系统
│   ├── core/              # 核心引擎
│   │   ├── model_engine/  # 大脑引擎（OpenAI/Ollama适配器）
│   │   └── planning_engine/ # 规划引擎（Tree of Thoughts）
│   ├── tools/             # 工具系统
│   ├── memory/            # 记忆模块（第二阶段）
│   ├── reflection/        # 反思模块（第三阶段）
│   ├── reminders/         # 提醒模块（第三阶段）
│   └── utils/             # 工具类
├── test/                  # 测试模块
├── docs/                  # 文档和计划
└── data/                  # 数据存储
```

### 功能特性

#### 第一阶段：搭建骨架 ✅
- 基础工具调用（时间、文件、系统命令等）
- 统一配置管理系统
- 模块化架构设计
- 命令行交互界面

#### 第二阶段：赋予记忆 ✅
- 向量数据库集成（Chroma）
- 长期记忆存储和检索
- 分层记忆架构
- 对话摘要和关键实体提取

#### 第三阶段：点燃智慧 ✅
- Tree of Thoughts规划算法
- Reflexion自我反思机制
- 多优先级任务调度
- 事件驱动架构（类似iOS RunLoop）
- 主动提醒和监控

## 🛠️ 快速开始

### 环境要求

- Python 3.10+
- Ollama（本地模型运行，可选）
- 虚拟环境（推荐）

### 安装步骤

1. 克隆项目并进入目录：
   ```bash
   cd /Users/bo.liu/Downloads/2026/ContinuouslyUpdated/Code/JARVIS
   ```

2. 创建并激活虚拟环境：
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   # 或 venv\Scripts\activate  # Windows
   ```

3. 安装依赖：
   ```bash
   pip install -r src/requirements.txt
   ```

4. （可选）配置本地模型：
   ```bash
   # 安装Ollama并拉取模型
   ollama pull deepseek-r1:7b
   ```

### 基本使用

1. **启动主动运行模式**（推荐）：
   ```bash
   python main/run_jarvis.py
   ```

2. **传统CLI交互**：
   ```bash
   python main/run_jarvis.py cli
   ```

3. **查看帮助信息**：
   ```bash
   python main/run_jarvis.py --help
   ```

### 使用示例

启动后会显示交互界面，可以尝试以下命令：

```
>>> 现在几点了
JARVIS: 当前时间是：2026年03月03日 17:30:45

>>> 帮我规划一个周末聚会
JARVIS: ✅ 任务创建成功！...

>>> 任务列表
JARVIS: 📋 活跃任务 (3个):...

>>> 规划引擎
JARVIS: 🎯 规划引擎信息：...
```

## 🔧 高级配置

### 模型配置

项目支持多种模型后端：

1. **本地模型（推荐）**：
   ```bash
   export MODEL_PROVIDER=ollama
   export MODEL_NAME=deepseek-r1:7b
   export OLLAMA_BASE_URL=http://localhost:11434
   ```

2. **OpenAI API**：
   ```bash
   export MODEL_PROVIDER=openai
   export MODEL_NAME=gpt-3.5-turbo
   export OPENAI_API_KEY=your_api_key_here
   ```

### 主动模式配置

创建配置文件 `config/active_config.json`：

```json
{
  "event_loop_interval": 100,
  "priority_levels": 6,
  "enable_auto_reflection": true,
  "reminder_check_interval": 60,
  "max_concurrent_tasks": 5
}
```

使用配置启动：
```bash
python main/run_jarvis.py active --active-config config/active_config.json
```

## 📚 文档

详细文档请查看 `docs/` 目录：

- `Order.txt` - 项目整体路线图（100天计划）
- `docs/第一阶段完成报告.md` - 第一阶段实施总结
- `docs/第二阶段详细执行计划.md` - 记忆系统设计
- `docs/第三阶段功能验证与下一步计划.md` - 主动智能实现
- `docs/手动执行模式说明.md` - 复杂任务执行指南

## 🧪 测试

### 运行完整测试套件

```bash
python main/run_jarvis.py test
```

### 运行特定测试

```bash
# 主动模式测试
python -m test.test_active_jarvis

# 规划引擎测试
python -m test.test_planning_engine

# 任务执行测试
python -m test.test_task_execution
```

## 🔄 开发工作流

### 添加新功能

1. **添加新工具**：
   - 在 `src/tools/` 下创建新模块
   - 继承 `SystemTool` 类并实现 `execute` 方法
   - 在 `initialize_system_tools` 中注册工具

2. **扩展规划引擎**：
   - 修改 `src/core/planning_engine/` 中的相应模块
   - 添加新的任务模板或规划策略

3. **集成外部服务**：
   - 在 `src/config/settings.py` 中添加配置项
   - 创建适配器模块处理API调用

### 代码规范

- 遵循PEP 8代码风格
- 使用类型注解
- 添加适当的文档字符串
- 编写单元测试

## ⚠️ 注意事项

1. **安全性**：执行命令工具包含安全限制，避免危险操作
2. **性能**：本地大模型需要足够的内存（建议8GB+ RAM）
3. **隐私**：敏感数据默认本地处理，注意API调用时的数据安全
4. **兼容性**：某些系统工具在不同平台上可能有差异

## 📈 路线图更新

根据Order.txt的计划，项目已完成：

- ✅ 第一阶段：基础骨架搭建（1-4周）
- ✅ 第二阶段：记忆系统集成（5-8周）
- ✅ 第三阶段：主动智能实现（9周+）

下一步计划：
- 语音交互集成
- MCP协议支持
- 智能家居控制
- 多模态感知

## 🤝 贡献指南

欢迎提交Issue和Pull Request。请确保：

1. 遵循现有代码风格
2. 添加适当的测试用例
3. 更新相关文档
4. 通过现有测试套件

## 📄 许可证

MIT License

---

**💡 提示**：项目的主要启动入口是 `main/run_jarvis.py`，所有功能都通过这个统一的入口访问。使用 `--help` 参数查看所有可用选项。