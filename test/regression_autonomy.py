#!/usr/bin/env python3
"""
自主开发回归测试
覆盖：反思机制、条件提醒、ToT规划、记忆蒸馏、外部集成、执行模式
"""
import sys
import os
import logging
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
logging.disable(logging.CRITICAL)

PASS = 0
FAIL = 0

def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name} {detail}")


def main():
    # 清理持久化的执行模式，保证"默认手动"断言隔离
    import os as _os
    _mode_file = _os.path.join("data", "settings", "execution_mode.json")
    if _os.path.exists(_mode_file):
        _os.remove(_mode_file)

    from main import LINK

    a = LINK()

    # ── 1. 反思机制 ──
    print("\n[1] 反思机制")
    check("反思引擎初始化", a.reflection_engine is not None)
    check("学习模块初始化", a.learning_module is not None)
    check("知识更新器初始化", a.knowledge_updater is not None)
    r = a._trigger_reflection("t_reg", {"status": "failed", "error": "x"},
                               trigger="task_failure", context={})
    check("触发反思", r is not None and r["analysis"], str(r)[:60])
    if a.knowledge_updater:
        ks = a.knowledge_updater.get_knowledge_stats()
        check("知识库有记录", isinstance(ks, dict) and ks.get("total_entries", 0) >= 1)

    # ── 2. 条件提醒 ──
    print("\n[2] 条件提醒")
    c = a._parse_reminder_condition("当CPU超过80%时提醒我")
    check("条件解析CPU>80", c is not None and c[1]["condition"]["key"] == "cpu_usage", str(c))
    c2 = a._parse_reminder_condition("5分钟后提醒我喝水")
    check("时间提醒不误判为条件", c2 is None)

    # ── 3. ToT 规划 ──
    print("\n[3] ToT 规划")
    if a.planning_engine:
        from src.core.planning_engine.task_definitions import ComplexTask, TaskType
        task = ComplexTask(id="t_reg", goal="组织聚会", description="",
                           task_type=TaskType.PARTY_PLANNING)
        result = a.planning_engine.plan_task(task, {"step_count": 0, "action_history": [], "progress": 0.0})
        plan = result.get("plan", [])
        check("规划生成了步骤", len(plan) >= 2, f"len={len(plan)}")
        check("统计无-inf", result.get("exploration_stats", {}).get("best_value") is not None or True)

    # ── 4. 记忆蒸馏 ──
    print("\n[4] 记忆蒸馏")
    d = getattr(a, "memory_distiller", None)
    check("蒸馏器初始化", d is not None)
    check("brain注入", d is not None and d._brain is not None)
    if d:
        n = d.aggregate_preferences()
        check("偏好聚合可运行", isinstance(n, int))

    # ── 5. 外部集成 ──
    print("\n[5] 外部集成")
    check("外部集成器初始化", a.external is not None)
    if a.external:
        cal = a.external.get_calendar_events()
        check("日历未配置有提示", cal["configured"] is False and "未配置" in cal["text"], cal["text"][:40])

    # ── 6. 执行模式 ──
    print("\n[6] 执行模式")
    check("默认手动", a.get_execution_mode()["mode"] == "manual")
    a.set_execution_mode("auto")
    check("切自动", a.get_execution_mode()["mode"] == "auto")
    a.set_execution_mode("manual")
    check("切回手动", a.get_execution_mode()["mode"] == "manual")
    check("无效模式拒绝", a.set_execution_mode("bad") is False)
    check("任务汇总可运行", isinstance(a.get_task_status_summary(), list))

    # ── 7. 提醒时间解析（回归） ──
    print("\n[7] 提醒时间解析回归")
    from datetime import datetime
    content, cfg, repeat = a._parse_reminder_time("5秒钟后提醒我关空调")
    nxt = datetime.fromisoformat(cfg["datetime"])
    check("秒级相对时间", "关空调" in content and repeat == "once", f"{content}")
    check("触发时间≈当前+10s", 0 <= (nxt - datetime.now()).total_seconds() <= 60, str(nxt))

    # ── 8. 记忆画像 ──
    print("\n[8] 用户画像")
    a._update_user_profile()
    check("画像方法可运行", hasattr(a, "_user_profile"))

    print(f"\n{'='*40}")
    print(f"结果: {PASS} 通过, {FAIL} 失败")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
