### JARVIS智能体基座

JARVIS（Just A Rather Very Intelligent System）是一个模块化、可扩展的智能体基座系统，旨在构建类似《钢铁侠》中贾维斯的AI助手。项目遵循Order.txt中定义的三个阶段路线图，现已完成第三阶段功能开发。

## 项目状态

- **当前阶段**：第三阶段（复杂任务规划、反思和主动提醒）
- **版本**：3.0
- **架构**：模块化分层设计
- **目标**：构建具备全局记忆、主动预判、无缝操控能力的数字管家

## 统一启动入口

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

## 项目架构

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