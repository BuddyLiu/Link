"""
LINK 全新初始化测试场景

测试前: 所有记忆、权限、日志均已清空
测试内容:
  1. 问候对话（简单响应，无需工具）
  2. 文件读取（工具调用）
  3. 非阻塞排队（连续发两条消息）
  4. 记忆持久化（发消息后检验是否存入记忆）
"""
import asyncio
import json
import time
import sys
import os

# ── 配置 ──
WS_URL = "ws://127.0.0.1:8011/ws"
API_URL = "http://127.0.0.1:8011"
LOG_FILE = "/tmp/link_test.log"

passed = 0
failed = 0

def log(msg):
    print(f"  {msg}")

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  ✅ {name}")
        passed += 1
    else:
        print(f"  ❌ {name}  {detail}")
        failed += 1

async def test_connection():
    """测试 1: WebSocket 连接"""
    import websockets
    try:
        async with websockets.connect(WS_URL) as ws:
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            check("WebSocket 连接成功", data.get("type") == "event")
    except Exception as e:
        check(f"WebSocket 连接失败: {e}", False)

async def test_greeting():
    """测试 2: 发送问候消息，验证简单响应"""
    import websockets
    async with websockets.connect(WS_URL) as ws:
        # 等待 welcome 消息
        await asyncio.wait_for(ws.recv(), timeout=5)

        # 发送问候
        await ws.send(json.dumps({"type": "user_input", "text": "你好"}))

        # 收集回复（最多等30秒）
        responses = []
        reasoning = []
        start = time.time()
        while time.time() - start < 60:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                data = json.loads(msg)
                if data.get("type") == "content_chunk":
                    responses.append(data.get("data", ""))
                elif data.get("type") == "event":
                    ev = data.get("data", {})
                    if ev.get("event_type") == "ASSISTANT":
                        full = ev.get("result", "") or "".join(responses)
                        log(f"LINK 回复: {full[:100]}...")
                        check("问候得到回复", len(full) > 0)
                        check("回复不含错误", "出错" not in full and "错误" not in full)
                        return
                    elif ev.get("event_type") == "TASK_UPDATE":
                        log(f"任务状态: {ev.get('status')}")
            except asyncio.TimeoutError:
                break

        check("问候回复超时", False, "30秒内未收到完整ASSISTANT事件")

async def test_read_file():
    """测试 3: 读取文件（工具调用）"""
    import websockets
    async with websockets.connect(WS_URL) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)

        await ws.send(json.dumps({"type": "user_input", "text": "读取 README.md 的第一行"}))

        responses = []
        start = time.time()
        has_tool_call_log = False
        while time.time() - start < 30:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                data = json.loads(msg)
                if data.get("type") == "content_chunk":
                    responses.append(data.get("data", ""))
                elif data.get("type") == "event":
                    ev = data.get("data", {})
                    if ev.get("event_type") == "ASSISTANT":
                        full = ev.get("result", "") or "".join(responses)
                        log(f"文件读取回复: {full[:100]}...")
                        check("读取文件有回复", len(full) > 0)
                        return
            except asyncio.TimeoutError:
                break

        check("文件读取回复超时", False)

async def test_nonblocking_queue():
    """测试 4: 连续发送两条消息，验证排队处理"""
    import websockets
    async with websockets.connect(WS_URL) as ws:
        await asyncio.wait_for(ws.recv(), timeout=5)

        # 连续发送两条消息
        await ws.send(json.dumps({"type": "user_input", "text": "第一条消息：今天几号"}))
        await ws.send(json.dumps({"type": "user_input", "text": "第二条消息：现在几点"}))

        assistant_count = 0
        start = time.time()
        while time.time() - start < 45:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=1)
                data = json.loads(msg)
                if data.get("type") == "event":
                    ev = data.get("data", {})
                    if ev.get("event_type") == "ASSISTANT":
                        assistant_count += 1
                        log(f"第 {assistant_count} 条回复收到")
                    elif ev.get("event_type") == "TASK_UPDATE":
                        log(f"队列状态: {ev.get('message', '')}")
            except asyncio.TimeoutError:
                break

        check("两条消息都收到回复", assistant_count >= 2, f"只收到 {assistant_count} 条")

async def test_logs():
    """测试 5: 检查日志文件是否正常写入"""
    if os.path.exists(LOG_FILE):
        size = os.path.getsize(LOG_FILE)
        check("日志文件已创建", size > 0, f"大小: {size} bytes")
        # 检查日志中有无异常
        with open(LOG_FILE, 'r') as f:
            content = f.read()
        check("日志无严重异常", "Traceback" not in content,
              "有 Traceback 异常" if "Traceback" in content else "")
    else:
        check("日志文件不存在", False)

async def test_memory():
    """测试 6: 检查记忆文件是否自动创建"""
    import glob
    mem_files = glob.glob("data/memory/json/*.json")
    check("记忆文件已创建", len(mem_files) > 0 or os.path.exists("data/memory/json/embeddings.npy"),
          f"文件: {mem_files}")

async def main():
    print("=" * 60)
    print("🧪 LINK 全新初始化测试场景")
    print("=" * 60)
    print()

    print("📋 测试 1: WebSocket 连接")
    await test_connection()
    print()

    print("📋 测试 2: 问候对话")
    await test_greeting()
    print()

    print("📋 测试 3: 文件读取（工具调用）")
    await test_read_file()
    print()

    print("📋 测试 4: 非阻塞排队")
    await test_nonblocking_queue()
    print()

    print("📋 测试 5: 日志检查")
    await test_logs()
    print()

    print("📋 测试 6: 记忆持久化")
    await test_memory()
    print()

    print("=" * 60)
    total = passed + failed
    print(f"📊 结果: {passed}/{total} 通过", end="")
    if failed > 0:
        print(f", {failed} 失败 ❌")
    else:
        print(" ✅")

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
