---
name: link-tools
description: 工具调用能力（14个 Function Calling 工具：文件/网络/命令/计算/记忆/时间/系统/项目）
trigger: 文件, 读取, 写入, 编辑, 删除, 搜索, 列出, 计算, 命令, 搜索网络, 记住, 保存信息, 项目信息
core: |
  工具选择决策：
  - 浏览目录/判断相关性 → list_files（返回大小/时间）；找文件名 → glob_files；找文件内容 → grep_files（支持 context_lines）
  - 读文件 → read_file（大文件用 offset/limit 分块）；写/编辑 → write_file / edit_file（old 需精确匹配）
  - 数学 → calculate（幂用 **，^ 是异或；支持 sin/cos/atan/pi/e）；时间 → get_time；系统 → get_system_info
  - 搜索网络 → search_web（不知道/实时信息必用，不要说自己不知道）
  - 执行命令 → execute_command（仅白名单 ls/cat/git status 等；禁 sudo/rm/shell元字符）
  - 用户个人信息 → save_user_fact（类别自由：姓名/职业/偏好/地址/生日等）
  - 项目技术栈 → get_project_info（自动扫描）
  路径语义：相对路径→工作目录 ~/LINK-Workspace；源码目录只读，写需授权。
---

# LINK 工具调用能力（Function Calling）

> **用途**：元模型（DeepSeek 等）在 LINK 的**在线模式**下通过 Function Calling 可调用的全部工具。
> **触发机制**：LINK 在请求中附带 `tools` 定义，元模型返回 `tool_calls`，LINK 执行后回传结果。
> **适用场景**：处理用户请求时，按需选择工具；无合适工具时直接文本回复。

---

## 工具总览

| 工具名 | 类别 | 一句话描述 |
|--------|------|-----------|
| `save_user_fact` | 记忆 | 保存用户个人信息到记忆 |
| `read_file` | 文件 | 读取文件内容 |
| `write_file` | 文件 | 创建或覆盖写入文件 |
| `edit_file` | 文件 | 字符串匹配替换编辑文件 |
| `delete_file` | 文件 | 删除文件 |
| `list_files` | 文件 | 列出目录内容 |
| `glob_files` | 文件 | 按模式匹配文件名 |
| `grep_files` | 文件 | 在文件中搜索文本 |
| `search_web` | 网络 | 搜索互联网信息 |
| `execute_command` | 系统 | 执行安全系统命令 |
| `calculate` | 工具 | 执行数学计算 |
| `get_time` | 工具 | 获取当前日期时间 |
| `get_system_info` | 工具 | 获取系统信息 |
| `get_project_info` | 工具 | 获取项目技术栈/架构 |

---

## 工具详细说明

### 1. save_user_fact — 保存用户个人信息

- **用途**：用户提到个人信息（姓名/职业/手机号/偏好/地址/年龄/生日/技能/项目等）时调用，供长期记忆。
- **参数**：
  - `category`（string，必填）：`姓名` / `职业` / `手机号` / `偏好` / `地址` / `年龄` / `生日` / `技能` / `项目` / `其他` 等（自由类别）
  - `value`（string，必填）：具体信息内容
- **示例**：用户说"我叫李雷，喜欢游泳，1990年出生" →
  ```json
  {"category": "姓名", "value": "李雷"}
  {"category": "偏好", "value": "游泳"}
  {"category": "生日", "value": "1990年"}
  ```
- **注意**：一条信息一个调用；多条信息可并行调用多个。

### 2. read_file — 读取文件

- **参数**：
  - `path`（string，必填）文件路径
  - `encoding`（string）文件编码，默认 `utf-8`
  - `offset`（integer）起始行号（从1开始），分块读取大文件用
  - `limit`（integer）读取行数，默认全部
- **返回**：文件元信息头 + 内容：
  ```
  --- demo.md | 69B | 共20行 | 显示1-20行 | 08-11 23:19 ---
  正文内容...
  ```
- **注意**：相对路径落到工作目录（`~/LINK-Workspace`）；读源码目录需用绝对路径。**大文件分块读取**：先 `wc -l` 查行数（execute_command），再按 offset/limit 分段读。

### 3. write_file — 写入文件

- **参数**：`path`（string，必填）、`content`（string，必填，完整内容）
- **注意**：覆盖写入；目录不存在时自动创建；写源码目录需先授权。

### 4. edit_file — 编辑文件（字符串替换）

- **参数**：
  - `path`（string，必填）
  - `old`（string，必填）被替换的原内容（需精确匹配）
  - `new`（string，必填）替换后的内容
- **注意**：适合小范围修改；`old` 必须与文件内容完全一致。

### 5. delete_file — 删除文件

- **参数**：`path`（string，必填）

### 6. list_files — 列出目录

- **参数**：
  - `path`（string）目录路径（默认工作目录）
  - `recursive`（boolean）是否递归
- **返回**：每条目带类型图标/大小/修改时间：
  ```
  📄 report.md (2.0KB 08-11 23:19)
  📁 sub (64B 08-11 23:19)
  ```
- **用途**：浏览目录、判断文件相关性（从大小/时间推断），**减少盲目逐个 read_file**。找特定名字用 glob_files，找内容用 grep_files。

### 7. glob_files — 按模式搜索文件名

- **参数**：`pattern`（string，必填）如 `**/*.py`、`src/*.ts`

### 8. grep_files — 搜索文件内容

- **参数**：
  - `pattern`（string，必填）搜索关键词（不区分大小写子串）
  - `path`（string）搜索路径，默认工作目录
  - `include`（string）后缀过滤，如 `.py,.txt`
  - `max_results`（integer）最大结果数，默认 20
  - `context_lines`（integer）匹配行前后上下文行数（0-5），默认 0
- **返回**：匹配统计 + 每文件最多 5 处匹配 + 可选上下文：
  ```
  匹配 import: 3 处 / 1 个文件（扫描 2 个）
  a.py:1: import os
  a.py:3: import sys
  ```
  （带 context_lines 时用 `>` 标记匹配行）
- **用途**：多文件定位关键词，**比逐个 read_file 高效**。定位后可再 read_file 精确读取。

### 9. search_web — 搜索互联网

- **参数**：
  - `query`（string，必填）搜索关键词（尽量具体）
  - `max_results`（integer）最大结果数，默认 5
  - `source`（string）搜索源：`web`（默认）/ `bing`
- **返回**：标题 + URL + 来源域名 + 摘要
- **用途**：天气、新闻、实时信息、未知内容查询。**不要说自己不知道，应主动搜索。**

### 10. execute_command — 执行系统命令

- **参数**：
  - `command`（string，必填）安全命令
  - `timeout`（integer）超时秒数，默认 30，上限 60
- **限制**：仅白名单安全命令（`ls`/`cat`/`pwd`/`git status` 等）。**禁止**：`rm`/`sudo`/`mkfs`/`shutdown`/`reboot`、shell 元字符（`;`/`|`/`$`/`` ` ``）、提权（`sudo`/`su`）、危险模式（`rm -rf`/`dd`/`mkfs`）。
- **注意**：命令在**工作目录**（`~/LINK-Workspace`）执行，不是源码目录。

### 11. calculate — 数学计算

- **参数**：`expression`（string，必填）数学表达式
- **支持**：算术（`+ - * / **`）、取模（`%`）、整除（`//`）、位运算（`& | ^ << >>`）、取负（`-x`）
- **函数**：`abs`/`round`/`max`/`min`/`sum`/`len`/`sqrt`/`sin`/`cos`/`tan`/`asin`/`acos`/`atan`/`atan2`/`sinh`/`cosh`/`tanh`/`log`/`log2`/`log10`/`exp`/`degrees`/`radians`/`floor`/`ceil`/`trunc`/`fabs`/`hypot`
- **常量**：`pi`/`e`（可直接裸用，如 `2*pi`）
- **示例**：`2*asin(1)*180/pi`（=180）、`sqrt(16)`（=4）、`1 + 6350*2.71**2/324859`（≈1.1436）
- **注意**：幂运算用 `**`（`^` 是异或）；科学计数法可用（`1.327e11`）。

### 12. get_time — 获取时间

- **参数**：`format`（string）`full`（完整）/`date`（仅日期）/`time`（仅时间）/`timestamp`（时间戳）

### 13. get_system_info — 系统信息

- **参数**：`detail`（boolean）是否详细信息
- **返回**：平台、架构、Python 版本、CPU 等。

### 14. get_project_info — 项目信息

- **无参数**
- **返回**：当前项目技术栈、架构、目录结构。

---

## 使用规范

1. **精确选择工具**：优先选最匹配的单一工具，避免无关工具。
2. **参数完整性**：必填参数必须提供；可选参数按需提供。
3. **并行调用**：多个独立工具调用（如读多个文件、存多个事实）可并行返回。
4. **路径语义**：相对路径 → 工作目录 `~/LINK-Workspace`；源码目录只读，写入需授权。
5. **失败处理**：工具返回错误时，可调整参数重试，或改用文本回复。
6. **不要伪造结果**：工具调用由 LINK 执行，返回真实结果；不要杜撰。
