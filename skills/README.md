# LINK 能力 Skill 文档索引

> **用途**：供元远程大模型（DeepSeek 等）在 LINK 交互过程中查阅，了解可调用的全部能力。
> **使用方式**：根据任务类型打开对应文档，按其中规范调用。

---

## 文档导航

| 文档 | 覆盖能力 | 适用场景 |
|------|---------|---------|
| [link-tools.md](link-tools.md) | **Function Calling 14 工具**（文件/网络/命令/计算/记忆/时间/系统/项目） | 在线模式下按需调用工具 |
| [link-actions.md](link-actions.md) | **离线 ACTION 标记 13 种**（任务/文件/搜索/命令/项目/学习） | 文本模式回复末尾追加操作标记 |
| [link-meta.md](link-meta.md) | **元能力**（记忆/任务/规划/提醒/外部查询/反思/安全边界） | 理解系统级能力与触发方式 |

---

## 快速决策表

遇到用户请求时：

```
简单意图（问候/时间/帮助/天气/提醒）
  → 系统规则自动处理，元模型直接友好回复（link-meta.md 一、四、五）

知识/对话类（解释概念/闲聊）
  → 直接回答，绝不创建任务（link-meta.md 综合决策）

未知内容/实时信息
  → search_web 或外部查询（link-tools.md #9 / link-meta.md 五）

文件/代码操作
  → 浏览: list_files → 找名: glob_files → 找内容: grep_files → 读: read_file
    （link-tools.md #2-8 / link-actions.md 三）

规划/多步骤/项目（用户明确要求安排/组织/计划）
  → CREATE_TASK（link-meta.md 三 / link-actions.md 一）

记住用户信息
  → save_user_fact（自由类别，link-tools.md #1）

安全系统命令
  → execute_command（link-tools.md #10）
```

---

## 关键规范速记

- **路径**：相对路径 → 工作目录 `~/LINK-Workspace`；源码目录只读，写需授权。
- **命令**：仅白名单安全命令；禁 `sudo`/`rm`/`mkfs`/重启/提权。
- **计算**：幂用 `**`（`^` 是异或）；支持三角函数/反三角/常量 `pi`/`e`。
- **标记**：`[[ACTION:操作|参数=值]]` 放在回复**末尾**；无操作不加标记。
- **实时信息**：不要说自己不知道，必须搜索。
