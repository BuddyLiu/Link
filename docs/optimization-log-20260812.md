# LINK Skill 深度优化日志（第五轮）

**日期**：2026-08-12（自主优化）
**目标**：借鉴主流 AI 代码智能体（Claude Code / CodeX）的 skill 设计，深度优化 LINK 的 Skills
**核心差距**：LINK 原 skills 是站外静态文档，模型看不到；主流智能体的 skills 是**运行时按需加载**
**结果**：3 个提交，77 pytest + 22 回归全过

---

## 一、Skill 运行时加载机制（核心）

### 差距
LINK 之前的 skills（link-tools/link-actions/link-meta）是纯 Markdown 参考手册，**没有接入运行时**——DeepSeek 在对话中看不到这些文档，只能靠 system prompt 里的简短路则。这与 Claude Code 的"技能按需加载"设计有根本差距。

### 实现
借鉴 Claude Code 的 skill 设计（frontmatter + 渐进披露）：

1. **skills/*.skill.md 加 frontmatter**：
   ```markdown
   ---
   name: link-tools
   description: 工具调用能力（14个 Function Calling 工具）
   trigger: 文件, 读取, 写入, 编辑, 搜索, 计算, 命令...
   core: |
     工具选择决策：
     - 浏览目录 → list_files；找文件名 → glob_files；找内容 → grep_files
     ...
   ---
   ```
   - `trigger`：触发关键词，LINK 按用户输入匹配
   - `core`：注入 system prompt 的精简指令（渐进披露，≤1200 字符）

2. **`src/core/skills/skill_loader.py`**：
   - 解析 frontmatter（含 `key: |` 多行块）
   - 按用户意图匹配 trigger（命中数排序）
   - `build_system_context(text)` 生成注入块

3. **接入 system prompt**：`_tool_response`（在线）+ `_simple_response`（离线）都按输入匹配 skill 注入，失败不影响主流程

## 二、渐进披露（token 优化）

| Skill | 完整文档 | core 注入 | 压缩 |
|-------|---------|----------|------|
| link-tools | 4373 字符 | 596 字符 | **-87%** |
| link-meta | ~4500 字符 | 437 字符 | **-90%** |
| link-actions | ~4700 字符 | 713 字符 | **-85%** |

只注入精简决策指令，完整文档保留供开发者参考。

## 三、端到端验证

- ✅ **意图匹配准确**：`读取文件`→link-tools、`设置提醒`→link-meta、`规划旅行`→link-actions、`你好`→无匹配
- ✅ **skill 引导生效**：知识对话（"什么是闭包"）按 link-meta core 指令**直接回答，不误建任务**
- ✅ **工具利用正常**：`读取工作目录`→ 模型生成带大小/时间的完整文件表格
- ✅ **77 pytest + 22 回归全过**（新增 4 项 skill_loader 测试）

## 四、新增/修改 Skill 指引

创建 `skills/<name>.skill.md`：
1. frontmatter：`name`/`description`/`trigger`（逗号关键词）/`core`（`|` 多行精简指令）
2. 正文写完整文档
3. 重启服务生效

---

## 服务状态

LINK Web 服务正常（8011），管理后台（8899）。skills 目录含 4 文件（README + 3 .skill.md）。
