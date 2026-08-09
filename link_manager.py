#!/usr/bin/env python3
"""
LINK 服务管理控制台
独立进程运行，管理主 LINK 服务的启动/停止/重启，实时显示运行日志。

用法:
  python3 link_manager.py [--port 8899]

访问:
  http://localhost:8899
"""

import sys, os, signal, asyncio, subprocess, json, time, argparse
from datetime import datetime
from typing import Optional

# 路径修复
_this_dir = os.path.dirname(os.path.abspath(__file__))
if _this_dir not in sys.path:
    sys.path.insert(0, _this_dir)

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import uvicorn

# ── 配置 ──
MANAGER_PORT = 8899
LINK_PORT = 8011
LINK_CMD = [sys.executable, "run_link.py", "web", "--port", str(LINK_PORT)]

app = FastAPI(title="LINK 管理控制台")

# ── 全局状态 ──
_process: Optional[subprocess.Popen] = None
_log_clients: list[WebSocket] = []
_process_start_time: Optional[float] = None
_log_buffer: list[dict] = []  # 日志环形缓冲，供新连接回放
_MAX_BUFFER = 500             # 最多保留 500 条
_pipe_tasks: list = []        # 日志管道 asyncio.Task 列表（重启时清理）


# ── 进程管理 ──

async def _pipe_stdout(stream):
    """从子进程管道读取 stdout/stderr，广播给所有 WebSocket 客户端"""
    import re
    # 过滤规则
    _heartbeat_pattern = re.compile(
        r'(heartbeat|心跳|💓|系统心跳|heart beat|check.*alive|alive.*check|'
        r'periodic|periodic_task|task_monitor|learning_cycle)', re.I
    )
    _http_log_pattern = re.compile(
        r'-\s+"(?:GET|POST|PUT|DELETE|PATCH|OPTIONS)\s+/.*?"\s+\d+'
    )
    try:
        loop = asyncio.get_event_loop()
        while True:
            # 带超时的读取：取消任务时 wait_for 能抛 CancelledError，
            # 避免 readline 永久阻塞导致旧管道任务残留
            try:
                line = await asyncio.wait_for(
                    loop.run_in_executor(None, stream.readline), timeout=2.0)
            except asyncio.TimeoutError:
                # 2 秒无输出：检查是否被取消，未被取消则继续等待
                task = asyncio.current_task()
                if task and task.cancelling():
                    break
                continue
            except asyncio.CancelledError:
                break
            if not line:
                break
            line = line.rstrip("\n\r")
            if not line:
                continue

            # HTTP 访问日志直接过滤掉
            if _http_log_pattern.search(line):
                continue

            is_heartbeat = bool(_heartbeat_pattern.search(line))

            entry = {
                "t": datetime.now().isoformat(),
                "m": line,
                "type": "heartbeat" if is_heartbeat else "",
            }

            # 追加到环形缓冲（供新连接回放）
            _log_buffer.append(entry)
            if len(_log_buffer) > _MAX_BUFFER:
                del _log_buffer[:len(_log_buffer) - _MAX_BUFFER]

            dead = []
            for ws in _log_clients[:]:
                try:
                    await ws.send_json(entry)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                _log_clients.remove(ws)
            await asyncio.sleep(0)  # 让出事件循环，避免阻塞其他任务
    except Exception:
        pass


async def _watch_process():
    """监控子进程退出，通知前端"""
    global _process
    try:
        returncode = await asyncio.get_event_loop().run_in_executor(None, _process.wait)
        _process = None
        dead = []
        for ws in _log_clients[:]:
            try:
                await ws.send_json({"t": datetime.now().isoformat(),
                                    "m": f"[系统] LINK 进程已退出 (返回码: {returncode})",
                                    "type": "system"})
            except Exception:
                dead.append(ws)
        for ws in dead:
            _log_clients.remove(ws)
    except Exception:
        pass


def _kill_link(port: int) -> bool:
    """杀掉占用指定端口的进程"""
    try:
        import subprocess as sp
        result = sp.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            for pid in result.stdout.strip().split("\n"):
                pid = pid.strip()
                if pid:
                    os.kill(int(pid), signal.SIGTERM)
                    try:
                        os.kill(int(pid), 0)  # 检查是否还活着
                        # 还没死透，等 2 秒再杀
                        import time as _t
                        _t.sleep(2)
                        os.kill(int(pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass  # 已经死了
            return True
    except Exception:
        pass
    return False


def _is_port_open(port: int) -> bool:
    """检查端口是否已被占用"""
    try:
        import socket
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


# ── 路由 ──

MANAGER_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>LINK 管理控制台</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0a0a0f;height:100vh;display:flex;flex-direction:column;color:#e0e0e0}
/* Header */
.header{background:#0d0d14;border-bottom:1px solid #1a1a2e;padding:16px 24px;display:flex;justify-content:space-between;align-items:center;flex-shrink:0}
.header h1{font-size:18px;font-weight:500;letter-spacing:2px;background:linear-gradient(90deg,#6366f1,#8b5cf6);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.header h1 span{font-size:12px;color:#4a4a6a;margin-left:10px;-webkit-text-fill-color:#4a4a6a;background:none}
/* Status bar */
.status-bar{background:#0d0d14;border-bottom:1px solid #1a1a2e;padding:12px 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap;flex-shrink:0}
.status-dot{width:10px;height:10px;border-radius:50%;display:inline-block;transition:all .3s}
.status-dot.running{background:#22c55e;box-shadow:0 0 8px rgba(34,197,94,.5)}
.status-dot.stopped{background:#ef4444;box-shadow:0 0 8px rgba(239,68,68,.5)}
.status-dot.starting{background:#eab308;box-shadow:0 0 8px rgba(234,179,8,.5);animation:pulse .8s ease-in-out infinite}
@keyframes pulse{50%{opacity:.4}}
.status-text{font-size:13px}
.status-text .label{color:#6b7280;margin-right:6px}
.status-text .value{color:#e0e0e0}
/* Heartbeat breathing light */
.heartbeat-wrap{display:flex;align-items:center;gap:6px;font-size:11px;color:#6b7280}
.heartbeat-dot{width:6px;height:6px;border-radius:50%;background:#22c55e;transition:opacity .15s,transform .15s}
.heartbeat-dot.beat{animation:breath .6s ease-in-out}
@keyframes breath{0%{opacity:.3;transform:scale(.8)}50%{opacity:1;transform:scale(1.3)}100%{opacity:.3;transform:scale(.8)}}
.heartbeat-dot.idle{background:#4a4a6a;opacity:.3;animation:none}
.actions{display:flex;gap:8px;margin-left:auto;flex-wrap:wrap}
.actions button{padding:6px 18px;border:none;border-radius:6px;font-size:12px;font-weight:500;cursor:pointer;transition:all .2s;display:flex;align-items:center;gap:4px}
.btn-start{background:#22c55e;color:#fff}
.btn-start:hover{background:#16a34a}
.btn-stop{background:#ef4444;color:#fff}
.btn-stop:hover{background:#dc2626}
.btn-restart{background:#6366f1;color:#fff}
.btn-restart:hover{background:#4f46e5}
.btn-start:disabled,.btn-stop:disabled,.btn-restart:disabled{opacity:.35;cursor:not-allowed}
/* Log area */
#log-box{flex:1;overflow-y:auto;padding:12px 24px;background:#050508;font-family:'SF Mono','Fira Code','Consolas',monospace;font-size:12px;line-height:1.7}
#log-box::-webkit-scrollbar{width:4px}
#log-box::-webkit-scrollbar-track{background:transparent}
#log-box::-webkit-scrollbar-thumb{background:#1a1a2e;border-radius:2px}
.log-line{white-space:pre-wrap;word-break:break-all}
.log-time{color:#4a4a6a;margin-right:8px}
.log-msg{color:#cdd6f4}
.log-msg.system{color:#6366f1;font-weight:500}
.log-msg.error{color:#ef4444}
.log-msg.warn{color:#eab308}
/* Footer */
.footer{flex-shrink:0;padding:8px 24px;background:#0d0d14;border-top:1px solid #1a1a2e;font-size:11px;color:#4a4a6a;display:flex;justify-content:space-between}
</style>
</head>
<body>
<div class="header">
<h1>LINK <span>管理控制台</span></h1>
<a href="http://localhost:8011" target="_blank" style="color:#6366f1;text-decoration:none;font-size:12px;padding:4px 10px;border:1px solid #1a1a2e;border-radius:4px">&#x2197; 打开聊天页面</a>
</div>
<div class="status-bar">
<div class="status-text"><span class="label">状态</span><span id="dot" class="status-dot stopped"></span></div>
<div class="status-text"><span class="label">进程</span><span id="status-text" class="value">检查中...</span></div>
<div class="status-text"><span class="label">启动时间</span><span id="uptime" class="value">--</span></div>
<div class="heartbeat-wrap"><span class="heartbeat-dot idle" id="hb-dot"></span><span id="hb-label">等待心跳</span></div>
<div class="actions">
<button id="btn-start" class="btn-start" onclick="sendAction('start')">&#x25B6; 启动</button>
<button id="btn-stop" class="btn-stop" disabled onclick="sendAction('stop')">&#x25A0; 停止</button>
<button id="btn-restart" class="btn-restart" onclick="sendAction('restart')">&#x21BB; 重启</button>
</div>
</div>
<div id="log-box"></div>
<div class="footer">
<span>LINK 管理控制台 v1.0</span>
<span id="log-count">0 条日志</span>
</div>

<script>
const logBox = document.getElementById('log-box');
const dot = document.getElementById('dot');
const statusText = document.getElementById('status-text');
const uptimeEl = document.getElementById('uptime');
const btnStart = document.getElementById('btn-start');
const btnStop = document.getElementById('btn-stop');
const logCount = document.getElementById('log-count');
var logTotal = 0;

// ── 心跳呼吸灯状态 ──
var hbTimer = null;

function beatHeartbeat() {
  var dot = document.getElementById('hb-dot');
  var label = document.getElementById('hb-label');
  dot.className = 'heartbeat-dot beat';
  label.textContent = '心跳正常';
  if (hbTimer) clearTimeout(hbTimer);
  hbTimer = setTimeout(function(){
    dot.className = 'heartbeat-dot idle';
    label.textContent = '等待心跳';
  }, 3000);
}

// ── WebSocket 日志 ──
// 统一连接函数：每次（重）连都必须绑定全部事件处理器，
// 否则重连后的新连接收不到日志（必须刷新页面才行的根因）。
function connectLogs() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    return ws;
  }
  ws = new WebSocket('ws://' + location.host + '/ws/logs');
  ws.onmessage = function(e) {
    var d = JSON.parse(e.data);
    if (d.type === 'heartbeat') {
      // 心跳日志→触发呼吸灯，不写入日志区
      beatHeartbeat();
    } else {
      addLog(d.t, d.m, d.type || '');
    }
  };
  ws.onclose = function() {
    // 重连前把实例标记为已关闭，避免与 connectLogs 竞态
    ws = null;
    setTimeout(connectLogs, 1500);
  };
  ws.onerror = function() {
    try { ws.close(); } catch(e) {}
  };
  return ws;
}
var ws = null;
connectLogs();

function addLog(time, msg, type) {
  var div = document.createElement('div');
  div.className = 'log-line';
  var ts = document.createElement('span');
  ts.className = 'log-time';
  try {
    var t = time.split('T');
    ts.textContent = t[1] ? t[1].split('.')[0] : time;
  } catch(e) { ts.textContent = time; }
  div.appendChild(ts);
  var ms = document.createElement('span');
  ms.className = 'log-msg' + (type ? ' ' + type : '');
  ms.textContent = msg;
  div.appendChild(ms);
  logBox.appendChild(div);
  // 限制 DOM 节点数，防止长时间运行卡顿
  while (logBox.children.length > 500) {
    logBox.removeChild(logBox.firstChild);
  }
  logTotal++;
  logCount.textContent = logTotal + ' 条日志';
  logBox.scrollTop = logBox.scrollHeight;
}

// ── 操作按钮 ──
async function sendAction(action) {
  btnStart.disabled = true; btnStop.disabled = true;
  try {
    var r = await fetch('/api/' + action, {method: 'POST'});
    var d = await r.json();
    if (d.error) { addLog(new Date().toISOString(), '[系统] 操作失败: ' + d.error, 'error'); }
    else { addLog(new Date().toISOString(), '[系统] ' + (d.msg || action + ' 成功'), 'system'); }
    if (action === 'stop') { setStatus('stopped'); }
    else if (action === 'start') { setStatus('starting'); pollStatus(); }
  } catch(e) { addLog(new Date().toISOString(), '[系统] 请求失败: ' + e, 'error'); }
  setTimeout(updateButtons, 1000);
}

function setStatus(state) {
  dot.className = 'status-dot ' + state;
  if (state === 'running') { statusText.textContent = '运行中'; }
  else if (state === 'stopped') { statusText.textContent = '已停止'; }
  else if (state === 'starting') { statusText.textContent = '启动中...'; }
}

async function updateButtons() {
  try {
    var r = await fetch('/api/status');
    var d = await r.json();
    var running = d.running;
    setStatus(running ? 'running' : 'stopped');
    if (running && d.uptime) { uptimeEl.textContent = d.uptime; }
    else { uptimeEl.textContent = '--'; }
    btnStart.disabled = running;
    btnStop.disabled = !running;
  } catch(e) { /* ignore */ }
}

async function pollStatus() {
  for (var i = 0; i < 30; i++) {
    await new Promise(r => setTimeout(r, 1000));
    try {
      var r = await fetch('/api/status');
      var d = await r.json();
      if (d.running) { setStatus('running'); if (d.uptime) uptimeEl.textContent = d.uptime; break; }
    } catch(e) {}
  }
  updateButtons();
}

// 初始化
updateButtons();
setInterval(updateButtons, 5000);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def get_index():
    return MANAGER_HTML


@app.post("/api/start")
async def api_start():
    """启动 LINK"""
    global _process, _process_start_time

    if _process and _process.poll() is None:
        return {"status": "already_running", "pid": _process.pid}

    # 先清理旧进程
    _kill_link(LINK_PORT)

    # 启动新进程
    try:
        _process = subprocess.Popen(
            LINK_CMD,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            cwd=_this_dir,
        )
        _process_start_time = time.time()

        # 清理旧日志管道任务（防止重启后旧任务残留阻塞新日志）
        for t in _pipe_tasks[:]:
            if not t.done():
                t.cancel()
        _pipe_tasks.clear()

        # 启动日志管道
        task = asyncio.create_task(_pipe_stdout(_process.stdout))
        _pipe_tasks.append(task)
        # 启动进程监控
        asyncio.create_task(_watch_process())

        # 广播日志
        for ws in _log_clients[:]:
            try:
                await ws.send_json({"t": datetime.now().isoformat(),
                                    "m": f"[系统] LINK 已启动 (PID: {_process.pid})",
                                    "type": "system"})
            except Exception:
                _log_clients.remove(ws)

        return {"status": "started", "pid": _process.pid, "msg": f"LINK 已启动 (PID: {_process.pid})"}
    except Exception as e:
        return {"status": "error", "error": str(e), "msg": f"启动失败: {e}"}


@app.post("/api/stop")
async def api_stop():
    """停止 LINK"""
    global _process, _process_start_time

    if not _process or _process.poll() is not None:
        # 没有进程记录，但仍可能有一个占用端口的进程
        killed = _kill_link(LINK_PORT)
        _process = None
        _process_start_time = None
        if killed:
            msg = "已释放端口"
            for ws in _log_clients[:]:
                try:
                    await ws.send_json({"t": datetime.now().isoformat(), "m": "[系统] " + msg, "type": "system"})
                except Exception:
                    _log_clients.remove(ws)
            return {"status": "stopped", "msg": "LINK 已停止"}
        return {"status": "not_running", "msg": "LINK 未在运行"}

    try:
        pid = _process.pid
        os.kill(pid, signal.SIGTERM)

        # 等待进程退出（最多 5 秒）
        try:
            await asyncio.get_event_loop().run_in_executor(None, lambda: _process.wait(timeout=5))
        except subprocess.TimeoutExpired:
            os.kill(pid, signal.SIGKILL)

        _process = None
        _process_start_time = None

        # 取消日志管道任务（可能阻塞在 readline，交由 _pipe_stdout 的 EOF 退出）
        for t in _pipe_tasks[:]:
            if not t.done():
                t.cancel()
        _pipe_tasks.clear()

        # 清空日志缓冲：停止后旧日志不应在新启动时回放混入
        _log_buffer.clear()

        for ws in _log_clients[:]:
            try:
                await ws.send_json({"t": datetime.now().isoformat(),
                                    "m": f"[系统] LINK 已停止 (PID: {pid})",
                                    "type": "system"})
            except Exception:
                _log_clients.remove(ws)

        return {"status": "stopped", "msg": f"LINK 已停止"}
    except Exception as e:
        return {"status": "error", "error": str(e), "msg": f"停止失败: {e}"}


@app.post("/api/restart")
async def api_restart():
    """重启 LINK"""
    stop_result = await api_stop()
    await asyncio.sleep(1)
    start_result = await api_start()
    return {"status": "restarted", "stop": stop_result, "start": start_result, "msg": "LINK 已重启"}


@app.get("/api/status")
async def api_status():
    """获取 LINK 状态"""
    global _process, _process_start_time

    running = False
    pid = None
    uptime_str = None

    if _process and _process.poll() is None:
        running = True
        pid = _process.pid
        if _process_start_time:
            elapsed = int(time.time() - _process_start_time)
            uptime_str = format_uptime(elapsed)
    elif _is_port_open(LINK_PORT):
        running = True
        pid = "unknown (port occupied)"

    return {
        "running": running,
        "pid": pid,
        "uptime": uptime_str,
        "port": LINK_PORT,
        "manager_port": MANAGER_PORT,
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "link-manager"}


@app.websocket("/ws/logs")
async def log_websocket(websocket: WebSocket):
    """日志流 WebSocket（连接时回放缓冲历史）"""
    await websocket.accept()
    _log_clients.append(websocket)
    try:
        # 回放历史日志（避免刷新丢日志）
        for entry in _log_buffer:
            await websocket.send_json(entry)
        while True:
            # 保持连接（接收心跳 ping）
            await websocket.receive_text()
    except WebSocketDisconnect:
        _log_clients.remove(websocket)
    except Exception:
        if websocket in _log_clients:
            _log_clients.remove(websocket)


# ── 工具函数 ──

def format_uptime(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}秒"
    elif seconds < 3600:
        return f"{seconds // 60}分{seconds % 60}秒"
    elif seconds < 86400:
        h = seconds // 3600
        return f"{h}时{seconds % 3600 // 60}分"
    else:
        d = seconds // 86400
        return f"{d}天{seconds % 86400 // 3600}时"


def cleanup():
    """退出时清理子进程"""
    global _process
    if _process and _process.poll() is None:
        try:
            _kill_link(LINK_PORT)
        except Exception:
            pass
    _process = None


# ── 入口 ──

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LINK 管理控制台")
    parser.add_argument("--port", type=int, default=MANAGER_PORT, help=f"管理端口 (默认 {MANAGER_PORT})")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="监听地址 (默认 127.0.0.1)")
    args = parser.parse_args()

    import atexit
    atexit.register(cleanup)

    print(f"⚙️  LINK 管理控制台启动中...")
    print(f"   • 管理地址: http://{args.host}:{args.port}")
    print(f"   • 管理对象: LINK (port {LINK_PORT})")
    print(f"   • 启动命令: {' '.join(LINK_CMD)}")
    print(f"\n打开浏览器访问 http://{args.host}:{args.port} 进入管理控制台\n")

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
