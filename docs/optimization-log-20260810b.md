# LINK 自主优化日志（第三轮）

**日期**：2026-08-10 晚（自主优化）
**方式**：3 个并行探索 agent 扫描前端/main/后端，发现 13 HIGH + 40 MEDIUM + 38 LOW，按严重程度逐一修复
**结果**：10 个独立提交，80 pytest + 22 回归 + 10 ToT 全部通过

---

## 一、真实运行问题（日志驱动，3 项）

| 提交 | 内容 |
|------|------|
| `0fa6bb4` | **calculate 工具缺数学能力**：真实日志显示金星引力辅助任务连续失败——`不支持的函数: asin/atan`（转向角 δ=arcsin(1/e) 算不了）、`不支持的运算符: BitXor`（^）、`不支持的表达式类型: ast.Name`（裸 pi/e 常量）。模型反复尝试不同写法都报错，陷入长思考循环。修复：补反三角（asin/acos/atan/atan2）+ 双曲 + degrees/radians/floor/ceil 等 + 位运算 + ast.Name 常量分支。验证：完整引力辅助公式链全部算通（e=1.1436、转向角 122.02°） |
| `e04fc9f` | **健康检查每10秒真实调用 LLM API**：前端 updateStatus 每 10 秒轮询 /api/debug → health_check() → 真实 API 调用（每小时 360 次）。修复：_cached_model_health TTL 30 秒缓存，5 次轮询只调 1 次真实 API |
| `bb779af` | **WS process_task 单条异常终止整个管道**：任何单条消息处理异常（LLM 调用/流式/广播失败）导致协程退出，客户端 WS 永久失效需刷新。修复：内层 try/except 包裹单条处理，异常发 ERROR 事件后继续循环 |

## 二、代码审查 agent 修复（main.py，2 项）

| 提交 | 内容 |
|------|------|
| `d358695` | **main.py 12 处逻辑 bug**：H4 运算符优先级（含"助手/LINK"的行以句号结尾绕过过滤器）；H2 授权异常返回引用外层 e；H3 max_rounds=5000 无限循环→50；H1 裸 except 吞 BaseException；L7 as_dir 字符串"False"也 truthy；M7 硬编码 3 覆盖配置；M1 7 处静默 except 补日志；L4 死代码；M5 线程池复用；L2/L3/M2 清理 |

## 三、前端 HIGH 修复（web_active_link.py，2 项）

| 提交 | 内容 |
|------|------|
| `7496706` | **5 项 HIGH**：① XSS——marked 未开 sanitize（新版已移除该选项），HTML 标签可穿透 → 新增 sanitizeHTML 白名单（DOMParser 移除 script/iframe/on*/javascript:）② 流式无条件强制滚动拉回底部 → isNearBottom() 守卫 ③ scroll-behavior:smooth 流式卡顿 → 流式期间加 instant-scroll ④ _streamTimer 竞态 → _streamAborted 标志 ⑤ typeChar 递归定时器不可清除 → _typingCharTimer 句柄 |
| `2022166` | **状态轮询健壮性**：updateStatus 静默吞错 → 连接中断红色提示 + fetch 8 秒超时；loadExecMode 同样加超时 |

## 四、后端核心模块修复（2 项）

| 提交 | 内容 |
|------|------|
| `7d1fb23` | **5 项**：① HIGH np.random.seed() 全局竞态 → default_rng 局部 RNG ② HIGH settings.to_dict() 泄露明文 API 密钥 → _mask_secret 前4后4脱敏 ③ ReDoS——matches_regex 无超时病态正则可挂死 → 长度限制+嵌套量词拦截 ④ graph BFS pop(0) O(n) → deque.popleft O(1) ⑤ reminder 缓存失效不完整 + 裸 user_id 键误删 → 统一 _invalidate_cache |
| `ed1765a` | **MEDIUM 项**：蒸馏删除静默吞错补日志；urlopen 响应对象未关闭（5 处）→ with 块；_tool_call_count 非原子自增 → threading.Lock；ToT 硬编码"确认前需先发送"只适用派对场景误拦旅行任务 → 通用前置约束；ExecuteCommandTool 的 sudo 子串匹配误拦 `echo "sudo xxx"` → 首 token 提权检测 |

## 五、性能与健壮性（2 项）

| 提交 | 内容 |
|------|------|
| `e04fc9f` | **嵌入随机回退被 lru_cache 永久缓存**：Ollama 未就绪时随机向量进缓存，服务恢复后记忆检索仍用垃圾向量 → 未就绪抛异常，embed() except 走不缓存随机回退（验证 currsize=0） |
| `dcb1ada` | **调试面板注入转义**：mem.id / archive_id 拼进 onclick 未转义 → escapeHtml + 单引号转义 |

---

## 关键成果验证

- ✅ **calculate 真实公式**：`2*atan(0.87469/sqrt(1-0.87469²))*180/π` = 122.02°、`1+6350*2.71²/324859` = 1.1436，金星引力辅助公式链全部算通（此前连续报错）
- ✅ **健康检查 TTL**：5 次轮询只触发 1 次真实 API 调用（原每小时 360 次）
- ✅ **XSS 净化 CDP 实测**：`<script>alert(2)</script>` / `onerror` / `javascript:` 全移除，markdown 正常渲染，无 JS 错误
- ✅ **滚动守卫**：用户滚到顶部不被流式强制拉回，instant-scroll 抑制 smooth 动画
- ✅ **ReDoS 防护**：正常正则不误伤（`^\w+\d+$` → True），病态 `(a+)+b` 拦截
- ✅ **sudo 修复**：`echo "sudo hello"` 不再误拦，`sudo ls` 仍拒绝
- ✅ **端到端 WS**：真实消息流（思考→内容→ASSISTANT 回复）完整，问候/计算均正常
- ✅ **80 pytest + 22 回归 + 10 ToT 全过**

## 服务状态

LINK Web 服务正常（8011，重启加载全部新代码），管理后台（8899）。
