# LINK 启动教程

> 覆盖 LINK 的启动方式、服务架构与常见问题排查。
> 适用环境：macOS，Python 3.13 venv。

---

## 一、服务架构（先搞懂两个端口）

LINK 由**两个服务**组成，全部由**唯一入口** `link_manager.py` 管理：

```text
link_manager.py  (唯一入口，管理控制台)
   :8899 ── 管理界面：查看状态 / 启动、停止 LINK / 实时日志
      │
      │  启动时自动拉起 + 可在界面手动启停 (POST /api/start|stop|restart)
      ▼
web_active_link.py  (LINK Web 服务)
   :8011 ── 前后端一体的 Web 界面 + WebSocket 对话
```

| 端口       | 服务          | 作用                                 |
|----------|-------------|------------------------------------|
| **8899** | 管理控制台       | 唯一入口。一键启停 LINK、看实时日志、端口状态          |
| **8011** | LINK Web 服务 | 实际与 LLM 对话的界面（FastAPI + WebSocket） |

**要点**：`link_manager.py` 启动时**自动拉起** Web 服务(8011)。也可用 `--no-auto-start` 只起管理台，之后在界面点「启动 LINK」按钮。

---

## 二、快速启动（推荐流程）

### 1. 确认虚拟环境

项目里有 `venv` 和 `.venv` 两个目录，**只能用 `venv`**（`.venv` 已损坏，bin 下没有 python）：

```bash
cd /Users/liubo/Codes/LINK
venv/bin/python --version                          # 应输出 Python 3.13.x
venv/bin/python -c "import fastapi; print(fastapi.__version__)"   # 应有输出版本号
```

### 2. 确认配置（provider.json）

```bash
grep -E '"mode"|"api_key"|"model"' data/settings/provider.json
```

- `"mode": "online"` + `"api_key"` 非空 → 可在线对话
- `api_key` 为空 → 打开 `data/settings/provider.json` 填入 `sk-...` 再启动
- 文件缺失 → 服务会自动重建模板，但需填 key 后重启

### 3. 一键启动（唯一入口）

```bash
cd /Users/liubo/Codes/LINK
nohup venv/bin/python link_manager.py --host 127.0.0.1 --port 8899 \
  >> data/logs/manager.log 2>&1 &
```

启动后**自动拉起** Web 服务(8011)，无需额外操作。也可打开 **`http://localhost:8899/`** 看实时日志，或在界面手动启停。

### 4. 验证全部就绪

```bash
curl -s -o /dev/null -w "8899 -> HTTP %{http_code}\n" http://127.0.0.1:8899/
curl -s -o /dev/null -w "8011 -> HTTP %{http_code}\n" http://127.0.0.1:8011/
```

两个都返回 `HTTP 200` 即就绪。然后访问 **`http://localhost:8011/`** 开始对话。

---

## 三、备用启动方式

### 方式 A：仅启动管理台（不自动拉起 Web）

```bash
venv/bin/python link_manager.py --no-auto-start
```

之后在 8899 界面点「启动 LINK」手动拉起，适合调试时逐步启动。

### 方式 B：直接命令行起 Web（跳过管理端，调试用）

```bash
cd /Users/liubo/Codes/LINK
nohup venv/bin/python web_active_link.py >> data/logs/web_service.log 2>&1 &
```

前台运行（`venv/bin/python web_active_link.py`）Ctrl+C 停止，日志直接打到终端，适合排障。

> ℹ️ 已删除的历史入口：`run_link.py`、`run_link_enhanced.py`、`linkctl.sh`、`active_link*.py`、`main_with_active.py` 等 14 个脚本已清理，唯一入口为 `link_manager.py`。

---

## 四、常见问题排查

### ❌ 问题 1：`No module named 'fastapi'`

**症状**：Web 服务启动即退出，日志报 `无法导入Web主程序: No module named 'fastapi'`。

**根因**：用了错误的 Python 解释器（最常见是 `.venv`，它已损坏；或系统 `/usr/bin/python3` 没有装依赖）。

**解决**：

```bash
venv/bin/python -c "import fastapi; print(fastapi.__version__)"  # 验证
# 必须统一用 venv/bin/python 启动
venv/bin/python link_manager.py
```

> 注：`data/logs/web.log` 里的 fastapi 报错可能是**历史遗留**——当前版本 web 由管理端拉起后日志走 WebSocket 推送，不写 web.log。判断"当前是否运行"以 `lsof -i :8011` 为准，别只看旧日志。

### ❌ 问题 2：端口被占用

**症状**：`Address already in use` 或服务起不来。

**解决**：

```bash
# 查看占用
lsof -i :8011 -P | grep LISTEN
lsof -i :8899 -P | grep LISTEN
# 强制释放（确认是旧进程后）
lsof -ti :8011 | xargs kill -9
lsof -ti :8899 | xargs kill -9
```

### ❌ 问题 3：`provider.json` 缺失或 api_key 为空

**症状**：日志提示 `provider.json 缺失，已重建默认配置`；对话返回「模型未初始化」。

**解决**：编辑 `data/settings/provider.json`，填 `api_key`，重启服务：

```bash
# 停止旧的
lsof -ti :8899 | xargs kill -9; lsof -ti :8011 | xargs kill -9
# 重新启动（见"快速启动"）
```

### ❌ 问题 4：`Ollama 服务不可用`（Connection refused）

**症状**：启动日志有红字警告 `Ollama 服务不可用`，随后 `嵌入服务未就绪，记忆搜索功能可能受限`。

**说明**：这是**非致命警告**。LINK 会降级为「随机嵌入 + 关键词搜索」，对话、记忆存取不受影响，只是语义检索精度下降。

**解决（可选）**：

```bash
# 本机启动 Ollama（若已安装）
ollama serve
```

### ❌ 问题 5：管理端在，但 8011 没起来

**症状**：8899 能访问，8011 连接被拒。

**原因**：管理端默认自动拉起 web；若用 `--no-auto-start` 启动，则需手动拉起。

**解决**：

```bash
curl -s -X POST http://127.0.0.1:8899/api/start
# {"status":"started","pid":...,"msg":"LINK 已启动"}
```

### ❌ 问题 6：对话没反应 / 返回「我已经收到你的消息」

**排查顺序**：

1. `curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8011/` → 应 200
2. 检查 `provider.json` 的 `api_key` 是否有效
3. 看服务日志有无报错（管理端实时日志，或 `/tmp` 下直接启动时的输出）
4. 检查网络：`venv/bin/python -c "import urllib.request; print(urllib.request.urlopen('https://api.deepseek.com', timeout=5).status)"`

### ❌ 问题 7：用错了启动脚本（active_link_enhanced.py / python3）

**症状**：运行 `python3 active_link_enhanced.py`，进程在但 8011/8899 起不来。

**原因**：两个错误叠加：

1. **`active_link_enhanced.py` 不是 Web 启动器** —— 它是「主动运行模式」的**交互式 CLI** 程序，代码里没有 uvicorn / 8011 / 8899 逻辑，永远不会起 web 端口。（该文件已随精简删除）
2. 裸 `python3` 是系统自带的 Xcode Python 3.9，**没有项目依赖**（fastapi 等），即便运行 web 也会报 `No module named`。

**解决**：

```bash
# 1. 停掉误启动的进程
pkill -f active_link_enhanced 2>/dev/null
# 2. 用 venv/bin/python + 唯一入口
venv/bin/python link_manager.py --host 127.0.0.1 --port 8899   # 管理端（自动拉起 web）
curl -s -X POST http://127.0.0.1:8899/api/start                # 幂等，已运行则跳过
```

**经验**：LINK 的 web 服务由 `web_active_link.py` 承载，唯一入口 `link_manager.py` 自动拉起它。主动运行模式 CLI 已随精简删除，项目为纯 Web。

### ❌ 问题 8：想重启整套服务

```bash
cd /Users/liubo/Codes/LINK
# 1. 全停
lsof -ti :8899 | xargs kill -9 2>/dev/null
lsof -ti :8011 | xargs kill -9 2>/dev/null
# 2. 确认释放
lsof -i :8899 -P; lsof -i :8011 -P   # 均无 LISTEN
# 3. 重启管理端 → 界面点启动 → 验证
nohup venv/bin/python link_manager.py --host 127.0.0.1 --port 8899 >> data/logs/manager.log 2>&1 &
curl -s -X POST http://127.0.0.1:8899/api/start
```

---

## 五、日志位置

| 文件 | 内容 |
|------|------|
| `data/logs/manager.log` | 管理端日志 |
| `data/logs/web.log` | 旧版 web 日志（**当前 web 日志走管理端 WebSocket 实时推送**，此文件可能过期） |
| `data/logs/web_service.log` | 方式 A 直接启动时 web 的输出 |
| `data/logs/web.err` | 历史脚本（linkctl.sh，已删除）的 stderr |

> **经验**：看「服务是否活着」永远以 `lsof -i :端口` 为准；看「为什么挂」去对应日志文件的**最新尾部**（`tail -50`），别被历史报错误导。

---

## 附：本次实测记录

- `link_manager.py` 一键启动：管理端(8899) 自动拉起 Web(8011)，均 HTTP 200
- 精简清理：`run_link.py`、`run_link_enhanced.py`、`linkctl.sh`、`active_link*.py` 等 14 个历史/重复脚本已删除，唯一入口为 `link_manager.py`
- Web 服务模型 `deepseek-reasoner` 状态 healthy
- 排查确认：历史 `No module named 'fastapi'` 报错源于损坏的 `.venv`，改用 `venv/bin/python` 后正常
- 记忆模块 95 条记忆正常加载；Ollama 不可用时自动降级（非致命）
