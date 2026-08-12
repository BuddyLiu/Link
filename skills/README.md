# LINK 能力 Skill 文档索引

> **用途**：供元远程大模型（DeepSeek 等）在 LINK 交互过程中查阅，了解可调用的全部能力。
> **使用方式**：`.skill.md` 文件由 LINK 运行时按用户意图**自动加载**（见下"Skill 加载机制"）；本 README 提供索引与决策表。

---

## Skill 加载机制

LINK 借鉴主流 AI 智能体（Claude Code 等）的 skill 设计，实现了**运行时按需加载**：

- 每个 skill 是带 frontmatter 的 `*.skill.md` 文件
- frontmatter 含 `name`（技能名）/ `description`（简介）/ `trigger`（触发关键词）/ `core`（注入 system prompt 的精简指令）
- LINK 每次交互按用户输入匹配 `trigger`，把匹配 skill 的 `core` 注入 system prompt（渐进披露，≤1200 字符）
- 完整文档 `body` 保留供开发者参考，不全部注入（节省 token）

实现：`src/core/skills/skill_loader.py`（解析/匹配/注入）。

### 新增/修改 Skill

1. 创建 `skills/<name>.skill.md`
2. 写 frontmatter：`name`、`description`、`trigger`（逗号分隔关键词）、`core`（`|` 多行精简指令）
3. 正文写完整文档
4. 重启服务生效（skill 加载器启动时读取）

---

## 文档导航

| 文档 | 覆盖能力 | 适用场景 |
|------|---------|---------|
| [link-tools.skill.md](link-tools.skill.md) | **Function Calling 14 工具**（文件/网络/命令/计算/记忆/时间/系统/项目） | 工具选择决策 |
| [link-actions.skill.md](link-actions.skill.md) | **离线 ACTION 标记 16 种**（任务/文件/搜索/命令/项目/学习） | 文本模式操作标记 |
| [link-meta.skill.md](link-meta.skill.md) | **元能力**（记忆/任务/规划/提醒/外部查询/反思/安全边界） | 系统级能力与路由 |

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
