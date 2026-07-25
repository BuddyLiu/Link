# 分屏聊天 + 任务队列架构设计文档

> 版本: v1.0
> 日期: 2026-07-25
> 分支: `feat/split-view-task-queue`

---

## 一、目标

### 1.1 用户诉求

- 我发的消息 ↔ LINK 回复，左右分屏显示，中间可拖拽调整比例
- LINK 在处理时，我不被阻塞，可以继续发消息
- 我发的所有消息进入队列，LINK 串行处理，随时根据我的新消息调整计划

### 1.2 解决的问题

| 当前问题 | 解决方案 |
|---------|---------|
| 所有消息混排在一个列，靠 left/right 对齐区分 | 物理分屏，左=用户，右=LINK |
| 发送消息后按钮禁用，必须等处理完成 | 非阻塞发送，消息进入队列 |
| 处理中的消息无法取消或打断 | 任务队列 + task_id 追踪 |
| 无法看到排队状态 | 队列状态 UI 显示 |
| 单列集中在 calc(50% - 320px) 区域内 | 分屏后充分利用屏幕宽度 |

---

## 二、架构总览

```
┌──────────────────────────────────────────────────────────┐
│  header                                                 │
├──────────────────────────────────────────────────────────┤
│  status-bar (含队列状态: ⏳ 处理中 第 2/3 个任务)        │
├─────────────────────┬──────┬────────────────────────────┤
│                     │      │                            │
│  用户消息列          │  拖  │  LINK 回复列               │
│  · 我的消息          │  拽  │  · LINK 的回复             │
│  · 历史消息          │  器  │  · 流式输出区域             │
│  · 用户输入回显      │      │  · 思考过程折叠面板         │
│                     │      │  · 反馈按钮 👍👎           │
│                     │      │  · 复制按钮                │
│                     │      │                            │
├─────────────────────┴──────┴────────────────────────────┤
│  input ──── [ 输入消息...                  ] [发送]      │
└──────────────────────────────────────────────────────────┘
```

### 2.1 核心变化

| 维度 | 之前 | 之后 |
|------|------|------|
| 消息容器 | 1 个 `#chat-box` | 2 个 `.chat-column` + 1 个 divider |
| 消息路由 | `chatBox.appendChild(div)` | `role === 'user' → userColumn` / `else → assistantColumn` |
| 发送按钮 | `sendBtn.disabled = true` | 永不禁用 |
| LLM 调用 | 直接 await run_in_executor | 通过 TaskManager 排队调度 |
| 流式输出 | 追加到 `#stream-msg` 在 chatBox 中 | 追加到 assistant-column |
| 状态反馈 | 打字指示器 | 队列状态 + 打字指示器 |
| 历史加载 | append to chatBox | 按 role 分列 append |
| 滚动 | 单列 scroll | 双列独立 scroll |

---

## 三、后端改动

### 3.1 TaskManager 类（新增，`web_active_link.py`）

管理消息队列和任务生命周期：

```
submit(task) → 返回 task_id → 前端立即获得
  ↓
队列（asyncio.Queue）
  ↓
Worker 循环 → 取一个任务 → run_in_executor(LINK.process_input)
                 ↓                ↓
             广播 task_update   流式回调 (chunk → 前端)
              (status=processing)  ↓
                             完成后广播 ASSISTANT + task_update(done)
```

**TaskItem 数据结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | str | UUID |
| text | str | 用户输入文本 |
| status | str | pending / processing / done / error / cancelled |
| created_at | float | 创建时间戳 |
| result | str\|None | 处理结果 |
| reasoning | str\|None | 思考过程 |
| position | int | 队列中位置 |

**Worker 流程：**

```
1. 从队列取 task
2. 广播 task_update(task_id, status=processing, position)
3. 执行 _process_input_direct(text, stream_callback)
4. 广播 ASSISTANT event (含 task_id)
5. 广播 task_update(task_id, status=done)
6. 回到 1
```

### 3.2 WebSocket 消息协议（新增消息类型）

**Server → Client:**

```json
{
  "type": "task_update",
  "task_id": "uuid",
  "status": "processing",
  "position": 1,
  "total": 3
}
```

`task_update` 在以下时机触发：
- 新任务入队 → `status: "pending"`, `position: N`
- 任务开始处理 → `status: "processing"`
- 任务完成 → `status: "done"`
- 任务出错 → `status: "error"`
- 任务取消 → `status: "cancelled"`

### 3.3 `process_input` 的 task_id 追踪（main.py 微调）

当前 `process_input()` 不感知 task_id。作为最小改动，保持原有签名不变，只在 `_process_input_direct` 中通过 logging 关联 task_id。

---

## 四、前端改动

### 4.1 DOM 结构变化

**之前：**
```html
<div id="chat-box" style="flex:1; overflow-y:auto; display:flex; flex-direction:column">
  <!-- 用户消息和 LINK 回复混排 -->
</div>
```

**之后：**
```html
<div id="chat-container" style="flex:1; display:flex; overflow:hidden">
  <div id="user-column" class="chat-column">
    <!-- 用户消息 -->
  </div>
  <div id="column-divider"></div>
  <div id="assistant-column" class="chat-column">
    <!-- LINK 回复 -->
  </div>
</div>
```

### 4.2 CSS 变化

| 选择器 | 之前 | 之后 |
|--------|------|------|
| `#chat-box` | flex column, centered padding | → 删除，改为 `#chat-container` |
| `#chat-container` | — | `display:flex; overflow:hidden` |
| `.chat-column` | — | `overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:12px` |
| `#user-column` | — | `background:#0a0a0f` |
| `#assistant-column` | — | `background:#0d0d18` |
| `#column-divider` | — | `width:6px; cursor:col-resize; background:#1a1a2e; flex-shrink:0` |
| `.msg.user` | `align-self:flex-end` | flex-end 保留（在左列内靠右显示） |
| `.msg.assistant` | `align-self:flex-start` | flex-start 保留（在右列内靠左显示） |

### 4.3 JavaScript 函数修改

| 函数 | 改动 |
|------|------|
| `addMessage(role, content)` | `chatBox.appendChild` → `(role==='user' ? userColumn : assistantColumn).appendChild` |
| `typewriteMessage(role, text)` | 同上 |
| `createMsgDiv(msg)` | 返回 div 不变，由 `loadHistory` 决定插入哪列 |
| `loadHistory(page)` | 循环中判断 `msg.role`，分别 append 到对应列 |
| `send()` | 移除 `sendBtn.disabled = true` |
| 流式 content_chunk | `#stream-msg` 追加到 `assistantColumn` |
| ASSISTANT event | 追加到 `assistantColumn` |
| `showTyping()` | 追加到 `assistantColumn` |
| `scrollToBottom()` | 分别控制两列 |
| `updateScrollButtons()` | 检查两列的 scroll 状态 |
| 队列状态显示 | 新增函数 `updateTaskQueueStatus()` |

### 4.4 拖拽分隔条

**逻辑：**

```
mousedown on #column-divider
  → 保存 startX, startLeftWidth
  → 添加 .dragging 类（禁用文本选择）

mousemove on document
  → 计算 delta = currentX - startX
  → userColumn.style.width = startLeftWidth + delta
  → 约束: 200px <= width <= (containerWidth - divider - 200px)

mouseup on document
  → 移除 .dragging 类
  → 保存最终宽度到 localStorage（持久化）
```

### 4.5 队列状态 UI

在 `#status-bar` 中增加队列状态显示：

```html
<span id="task-queue-status"></span>
```

由 `updateTaskQueueStatus(current, total)` 函数更新：
- 无任务: 隐藏
- 处理中: `⏳ LINK 正在处理...`
- 队列中有等待: `⏳ 第 2/3 个任务`

---

## 五、消息流完整时序

```
用户: 输入 "读取 README"
  ↓
send() → addMessage('user', "读取 README")  ← 用户列立即显示
  → ws.send({type:"user_input", text:"读取 README"})
  ↓
receive_task → TaskManager.submit("读取 README")
  → 广播 task_update(task_id, status=pending, position=1)
  ↓
Worker 取到任务
  → 广播 task_update(task_id, status=processing)
  → run_in_executor(LINK.process_input)
    ↓
    stream_cb("reasoning", "让我先找到 README 文件...")
      → WebSocket → 右列显示思考过程
    stream_cb("content", "我已经找到 README，内容如下：")
      → WebSocket → 右列流式显示
    ...工具执行...
  → 完成
  ↓
广播 ASSISTANT event(result, reasoning, task_id)
  → 右列显示最终结果
  → 广播 task_update(task_id, status=done)
  ↓
Worker 取下一个任务...

=== 非阻塞演示 ===

用户: 在 LINK 处理 "读取 README" 时，又发送 "帮我改里面的版本号"
  ↓
send() → addMessage('user', "帮我改版本号")  ← 用户列立即显示
  → ws.send → receive_task → TaskManager.submit("改版本号")
  → 广播 task_update(task2, status=pending, position=2)
  ↓
（当前任务继续处理，完成后自动开始 task2）
  → task_update(task2, status=processing)
  ...
```

---

## 六、阶段划分与依赖

| Phase | 内容 | 文件 | 依赖 |
|-------|------|------|------|
| 1 | TaskManager 后端 + 非阻塞发送 | `web_active_link.py` | — |
| 2 | 前端 DOM 分屏 + CSS | `web_active_link.py` | Phase 1 |
| 3 | 消息渲染分列 + 历史加载适配 | `web_active_link.py` | Phase 2 |
| 4 | 拖拽分隔条 | `web_active_link.py` | Phase 2 |
| 5 | 队列状态 UI + 滚动适配 | `web_active_link.py` | Phase 1+3 |

---

## 七、风险与注意事项

1. **并发安全**：`brain_link` 是单例，多次 `process_input` 串行调用没有问题，但并行调用会有状态覆盖风险（`_tool_call_count`、`_progress_callback` 等实例变量）。TaskManager 保持串行执行，不并发。
2. **流式回调隔离**：每个任务的 `_stream_cb` 需要捕获不同的 `task_id`，确保流式内容路由到正确的任务。
3. **历史消息加载**：`loadHistory()` 需要按 role 分列渲染，确保翻页时消息顺序正确。
4. **权限弹窗**：`permission_request` 依然可以正常工作（不依赖 task_id），因为 PRM 是全局单例。
5. **toast**：不影响，仍然是全局组件。

---

## 八、验证清单

- [ ] 左右分屏正常显示，用户消息在左，LINK 回复在右
- [ ] 拖拽分隔条改变宽度，有最小约束
- [ ] 发送消息不阻塞，连续发送多条均进入队列
- [ ] 队列状态显示正确（无任务隐藏/处理中/排队中）
- [ ] LINK 处理中发送新消息，处理后能接着处理下一个
- [ ] 流式输出在右列实时展示
- [ ] 思考过程在右列正常显示
- [ ] 权限弹窗正常弹出和处理
- [ ] 刷新页面后历史消息按角色分列加载
- [ ] 复制按钮 / 反馈按钮在右列正常工作
- [ ] Toast 提示正常
- [ ] 滚动按钮可以控制右列滚动
