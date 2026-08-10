# LINK 自主优化日志（第二轮）

**日期**：2026-08-10 晚（约 2 小时自主优化）
**范围**：知识库/反思、工具调用容错、提醒系统、ToT 规划、前端性能与缺陷、安全加固
**结果**：14 个独立提交，122 项回归测试全部通过

---

## 一、知识库与反思（2 项）

| 提交 | 内容 |
|------|------|
| `1b7ab3f` | **知识检索死代码修复**：`_knowledge_matches_query` 第453行 `return False` 使 root_causes/suggestions 检查成为不可达代码，且 root_causes 从未拼入全文匹配文本 → 按根本原因检索知识永远命中不了。修复：补入全文匹配文本 + 删死代码 |
| `d757cf6` | **知识整合索引残留修复**：`_consolidate_knowledge` 删除低质量条目时只重建保留条目索引，未从 `knowledge_index` 移除被删条目 → 索引残留指向已删除条目。修复：整合时移除被删条目索引 |

## 二、工具调用容错（1 项）

| 提交 | 内容 |
|------|------|
| `c6fbd8e` | **工具参数 JSON 连续失败逃生通道**：真实日志中 write_file 成功写入 7757 字符后，模型下一轮又生成截断的非法 JSON，错误提示让它"重新生成合法 JSON"，模型反复生成同一调用最终陷入"连续3轮相同"循环强制退出。修复：同一工具连续 2 次参数解析失败时，错误提示改为明确要求模型停止调用该工具、改用普通文本直接回复 |

## 三、配置与反射（2 项）

| 提交 | 内容 |
|------|------|
| `d11d10b` | **settings 迁移 Pydantic V2**：`class Config: env_prefix` 在 V2 已弃用（V3 将移除），9 处迁移为 `SettingsConfigDict(env_prefix=...)`，消除弃用警告 |
| `4553387` | **低置信反思路径死代码 + 任务执行空检查**：`_check_and_reflect` 中 `low_conf` 恒为 False，low_confidence 反思路径永远无法触发 → 用"响应过短(<20字符)"作为低置信信号。`_start_task_execution`/`_auto_execute_task_steps` 直接访问 planning_engine 未检查 None → 补空检查与友好提示 |

## 四、前端缺陷修复（2 项）

| 提交 | 内容 |
|------|------|
| `53c6957` | **前端多处缺陷**：① `showToast` 未定义（复制回调抛 ReferenceError 静默失败，补全函数）② `send()` 不检查 WS readyState（断线发送抛异常且按钮永久禁用，加连接检查）③ WebSocket 无重连（断线后页面失去交互需手动刷新，加指数退避自动重连 + wss 兼容 HTTPS）④ `updateStatus` 空 stats 时 TypeError |
| `ed0f90f` | **关键路径静默吞错补日志**：主动维护/执行模式读取/反馈洞察/任务列表/兜底响应等 5 处 `except Exception: pass` 补日志，区分根因（brain 未初始化 vs LLM 异常 vs 响应含查询失败） |

## 五、提醒系统修复（3 项）

| 提交 | 内容 |
|------|------|
| `1e2d938` | **重复提醒首次发送后永久失效**：`send_notifications` 无条件把提醒标 COMPLETED，覆盖 `check_triggers` 对重复提醒设置的 ACTIVE 状态 → 修复：仅 once 提醒标 COMPLETED，重复提醒保持 ACTIVE 保留下次触发时间。**发送失败静默丢弃**：失败时状态卡 TRIGGERED 而 `_get_all_active_reminders` 只查 active → 修复：失败/异常重置回 ACTIVE 以便重试 |
| `ede905a` | **触发条件 eval 安全加固**：`_check_script_condition`/`evaluate_condition` 用 eval + 受限 `__builtins__`，但可通过 `__subclasses__` 链逃逸执行任意代码，且无超时保护（DoS 可挂死进程）。替换为 AST 白名单 `_safe_eval`：仅允许字面量/比较/布尔/算术、明确列出的纯函数内置、上下文变量单层属性访问；禁止函数调用（除白名单）、下标、链式属性、dunder、import、推导式 |
| `94ca0fb` | **AppleScript 注入风险**：macOS 桌面通知直接把 reminder.content 拼进 AppleScript，含引号/反斜杠破坏脚本、含反引号/`$()` 可能执行 shell → 转义字符串字面量。**裸文件名 makedirs 崩溃**：log_file_path/database_path 为裸文件名时 `dirname` 为空，`os.makedirs('')` 抛 FileNotFoundError → 加空目录保护。**蒸馏删除失败静默** → 记录 warning |

## 六、ToT 规划（1 项）

| 提交 | 内容 |
|------|------|
| `993cd62` | **ToT 两个终止条件均为死代码**：① 迭代检查 `current_iteration >= max_iterations(100)` 永不为真（range(100) → 0..99）→ 改为 `>= max-1` ② `search_time` 只在主循环结束后赋值，循环内读到恒为 0 → 30 秒超时形同虚设，最坏跑满 100 次迭代阻塞。修复：循环内实时更新 search_time，超时真正生效 |

## 七、前端性能（2 项）

| 提交 | 内容 |
|------|------|
| `7a850d6` | **打字机渲染节流**：`typewriteMessage` 每 tick 全量 `marked.parser(tokens.slice(0, idx+1))`，500+ token 长回复是 O(n²) 解析 + 每次强制同步布局。修复：每 RENDER_STEP 个 token 才渲染（长内容步长 3），用 rAF 合并渲染避免每 tick 强制布局 |
| `18f77a5` | **scrollToBottom rAF 节流**：原实现每次调用读 `isNearBottom()`（scrollHeight/scrollTop）又写 scrollTop，是强制同步布局。`typeThink` 每字符调用、打字机高频调用时反复触发。修复：rAF 合并同一帧多次滚动请求为一次 |

---

## 关键成果验证

- ✅ **重复提醒全流程**：daily 提醒触发 → 保持 ACTIVE → 发送后仍活跃 → 发送失败重置 ACTIVE 可重试 → 一次性提醒正常 COMPLETED
- ✅ **安全评估**：8 类正常表达式工作正常，6 类恶意 payload（`__subclasses__` 逃逸、`open()`、`__import__`、DoS 推导式、dunder 链）全部被拦截
- ✅ **ToT 终止**：迭代 99/100 正确终止，`search_time=31s` 触发超时终止，完整规划不受影响
- ✅ **前端 CDP 验证**：showToast 显示、scrollToBottom rAF、typewrite 节流、WS 重连、send readyState、wss 兼容、WS 连接，8 项全部 PASS
- ✅ **122 项回归测试全部通过**（test_tools 64 + test_dir_permission 23 + test_workspace 13 + regression_autonomy 22）

## 服务状态

LINK Web 服务运行正常（端口 8011，重启加载新代码），管理后台（8899）。
