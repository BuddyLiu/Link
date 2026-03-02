# JARVIS智能体基座

JARVIS（Just A Rather Very Intelligent System）是一个模块化、可扩展的智能体基座系统，旨在构建类似电影《钢铁侠》中贾维斯的AI助手。

## 第一阶段：搭建骨架（已完成）

第一阶段目标是构建基座1.0，实现基础工具调用和交互功能。

### 功能特性

- ✅ 模块化架构设计
- ✅ 配置管理系统
- ✅ 统一日志记录
- ✅ 工具注册和执行框架
- ✅ 基础系统工具集合
- ✅ 命令行交互界面
- ✅ 简单的意图识别

### 系统工具

当前版本包含以下系统工具：

1. **get_time** - 获取当前日期和时间
2. **get_system_info** - 获取系统信息
3. **list_files** - 列出目录文件
4. **read_file** - 读取文件内容
5. **execute_command** - 执行系统命令（安全限制）
6. **search_web** - 搜索网络信息（模拟）
7. **calculate** - 执行数学计算

### 项目结构

```
jarvis/
├── __init__.py          # 项目入口
├── main.py              # 主程序入口
├── requirements.txt     # 依赖包列表
├── README.md           # 本文档
├── config/
│   └── settings.py     # 配置管理
├── core/               # 核心模块（预留）
├── memory/             # 记忆模块（预留）
├── tools/
│   ├── __init__.py     # 工具管理器
│   └── system_tools.py # 系统工具实现
└── utils/
    └── logger.py       # 日志系统
```

## 安装和运行

### 环境要求

- Python 3.10+
- 推荐使用虚拟环境

### 安装步骤

1. 克隆项目或复制文件到本地
2. 创建虚拟环境：
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/macOS
   # 或 venv\Scripts\activate  # Windows
   ```
3. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```

### 运行方式

#### 命令行交互模式（推荐）

```bash
cd jarvis
python main.py
```

或使用调试模式：

```bash
python main.py --debug
```

#### 测试模式

```bash
python main.py --mode test
```

## 使用示例

启动后，在命令行界面中输入：

```
>>> 现在几点了
JARVIS: 当前时间是：2026年03月02日 15:25:30

>>> 帮助
JARVIS: JARVIS智能体第一阶段可用功能：
...
```

## 配置说明

系统配置支持以下方式：

### 环境变量

```bash
# 调试模式
export DEBUG_MODE=true

# 日志级别
export LOG_LEVEL=DEBUG

# 模型配置
export MODEL_NAME=gpt-3.5-turbo
export MODEL_PROVIDER=openai
export OPENAI_API_KEY=your_api_key_here
```

### 配置文件

配置可通过 `config/settings.py` 管理，支持从 `.env` 文件加载。

## 开发指南

### 添加新工具

1. 在 `tools/` 目录下创建新文件或修改 `system_tools.py`
2. 继承 `SystemTool` 类
3. 实现 `execute` 方法
4. 在 `initialize_system_tools` 函数中注册工具

示例：

```python
class NewTool(SystemTool):
    def __init__(self):
        parameters = {
            "param1": {
                "type": "string",
                "description": "参数说明",
                "required": True
            }
        }
        super().__init__("new_tool", "工具描述", parameters)
    
    def execute(self, **kwargs):
        param1 = kwargs["param1"]
        # 实现工具逻辑
        return "执行结果"
```

### 扩展功能

- **模型集成**：在 `core/` 目录下添加模型模块
- **记忆系统**：在 `memory/` 目录下实现记忆存储
- **Web服务**：扩展 `run_web` 方法
- **语音交互**：添加语音识别和合成模块

## 路线图

### 第一阶段（当前版本）
- [x] 基础架构搭建
- [x] 系统工具实现
- [x] 配置和日志系统
- [ ] 本地大模型集成（待完成）
- [ ] 基础ReAct循环（待完成）

### 第二阶段（记忆系统）
- [ ] 向量数据库集成
- [ ] 长期记忆存储
- [ ] 对话历史管理
- [ ] 个性化用户画像

### 第三阶段（主动智能）
- [ ] 任务规划系统
- [ ] 自我反思机制
- [ ] 主动提醒功能
- [ ] 复杂任务处理

## 注意事项

1. **安全性**：执行命令工具包含安全限制，避免危险操作
2. **性能**：文件读取有限制，避免加载过大文件
3. **兼容性**：系统工具在不同平台上可能有差异
4. **隐私**：当前版本数据处理均在本地

## 贡献指南

欢迎提交Issue和Pull Request。请确保：
- 遵循现有代码风格
- 添加适当的测试
- 更新相关文档

## 许可证

MIT License