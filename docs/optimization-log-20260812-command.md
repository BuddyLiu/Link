# LINK 终端命令执行深度优化日志（分级授权）

**日期**：2026-08-12（4 小时专项）
**目标**：补齐 LINK 执行终端命令的短板，参考 Claude Code Bypass permissions 安全版，让 LINK 具备常见安全命令执行能力 + 一定范围自动执行，同时防破坏性命令事故

---

## 一、原短板

| 问题 | 影响 |
|------|------|
| 纯白名单无分级 | 要么全放行（safe）要么拒绝（unknown），无"需确认"中间层 |
| 白名单过窄 | 缺 mkdir/touch/cp/git写/pip/构建/压缩等日常开发命令，模型频繁受挫 |
| 无自动执行 | 所有 safe 命令都走主循环，无"常用只读命令直接执行"的加速 |
| 无参数级防护 | `cat /etc/passwd`（白名单内）可能泄露敏感文件 |

## 二、分级授权设计（对齐 Bypass permissions 安全版）

| 层级 | 命令类型 | 行为 |
|------|---------|------|
| **Tier 0 自动执行** | 只读无副作用（ls/cat/head/grep/pwd/git status/date/find/du/df） | 免确认直接执行 |
| **Tier 1 需确认** | 有副作用（mkdir/touch/cp/mv/rm/git add/commit/pip install/make/压缩） | 触发权限确认，授权后会话内放行 |
| **Tier 2 拒绝** | 破坏性/提权（rm -rf/dd/mkfs/shutdown/sudo/su） | 强制拒绝 |

## 三、安全防护（防事故）

1. **参数级防护**：白名单命令 + 危险参数 → 降级拒绝
   - `cat /etc/passwd`、`curl -o /etc/x`、`echo x > /etc/hosts`、`cp a /usr/bin` 全部拦截
2. **命令提取兜底**：模型传整句（"执行命令 pwd 看看"）时，提取真正的命令；**绝不提取提权/危险命令**（`执行命令 sudo ls` → 只提取 `ls`）
3. **授权后仍安全**：`rm` 授权后 `rm -rf /` 仍拒绝（参数防护不随授权失效）
4. **会话内已授权集合**（`authorize_command`）：confirm 命令授权后放行，避免重试死循环
5. **shell=False + 元字符拦截**：防注入、防多语句拼接

## 四、其他修复

- **provider.json 健壮性**：配置缺失时自动重建默认配置 + 告警（避免服务静默降级导致"OpenAI适配器未初始化"）
- **TOOL_DEFS 描述**：明确 command 只放命令本身，不含自然语言

## 五、验证

- ✅ 5 项分级单测（tier0/1/2 分类、参数防护、授权后执行）
- ✅ 78 pytest 全过
- ✅ 端到端：`pwd` 自动执行返回工作目录；`git` 命令执行成功
- ✅ 授权流程工具层验证：授权前拒 → 授权后执行 → 危险仍拒
- ✅ 命令提取：`执行命令 pwd 看看当前目录在哪` → `pwd`；`执行命令 sudo ls` → `ls`

## 服务状态

LINK Web 服务正常（8011）。注意：provider.json 已重建模板，**需填入 API key 后重启**才能使用在线 LLM 功能。
