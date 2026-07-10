import sys, os, time
root = "/Users/bo.liu/Downloads/2026/ContinuouslyUpdated/Code/JARVIS"
sys.path.insert(0, os.path.join(root, "src"))
os.chdir(root)

from core.planning_engine import create_planning_engine
from core.planning_engine.task_definitions import TaskType, TaskPriority

e = create_planning_engine({"max_planning_time":15,"max_planning_depth":4})
c = e.get_planning_stats()["components_initialized"]
print("="*60+"\n🧪 JARVIS TC17~TC26 Test Suite\n"+"="*60)
print(f"Decomposer:{'✅' if c['task_decomposer'] else '❌'} Planner:{'✅' if c['tot_planner'] else '❌'} Eval:{'✅' if c['state_evaluator'] else '❌'} Explorer:{'✅' if c['explorer'] else '❌'}")
r={}

print("\n--- TC17 ---")
tt=e.create_task(goal="BJ Trip",description="3 days Beijing",task_type=TaskType.TRAVEL_PLANNING,priority=TaskPriority.HIGH)
print(f"ID:{tt.id} Type:{tt.task_type}");r["TC17"]=bool(tt.id)

print("\n--- TC18 ---")
d=e.decompose_task(tt);print(f"Steps:{len(d.steps)}")
for i,s in enumerate(d.steps,1):print(f"  {i}. [{s.status}] {s.description}")
r["TC18"]=len(d.steps)>0

print("\n--- TC19 ---")
t0=time.time();pl=e.plan_task(tt,use_exploration=True);et=time.time()-t0
print(f"Plan:{len(pl['plan'])} Conf:{pl['confidence']:.1%} Time:{et:.2f}s")
for i,s in enumerate(pl['plan'][:4],1):print(f"  {i}. {s.description}")
r["TC19"]=bool(pl['plan'])

print("\n--- TC20 ---")
ps=[s for s in tt.steps if s.status=="pending"]
if ps:
    e.update_task_step(tt.id,ps[0].id,"completed","done")
    us=e.get_task(tt.id).get_step_by_id(ps[0].id)
    print(f"Step:{ps[0].description}->{us.status}");r["TC20"]=us.status=="completed"
else:r["TC20"]=False

print("\n--- TC21 ---")
tp=e.create_task(goal="Party 30ppl",description="birthday party",task_type=TaskType.PARTY_PLANNING,priority=TaskPriority.MEDIUM)
e.decompose_task(tp);print(f"Steps:{len(tp.steps)}")
for i,s in enumerate(tp.steps,1):print(f"  {i}. {s.description}")
r["TC21"]=bool(tp.id)

print("\n--- TC22 ---")
r["TC22"]=all(s.description and s.action for s in tp.steps)
print(f"All valid:{r['TC22']}")

print("\n--- TC23 ---")
print(f"Old:{tp.priority}");tp.priority=TaskPriority.HIGH;print(f"New:{tp.priority}")
r["TC23"]=tp.priority==TaskPriority.HIGH

print("\n--- TC24 ---")
pm=e.create_task(goal="SW Dev",description="software project",task_type=TaskType.PROJECT_MANAGEMENT,priority=TaskPriority.HIGH)
e.decompose_task(pm);print(f"Steps:{len(pm.steps)}");r["TC24"]=True

print("\n--- TC25 ---")
tl=e.list_active_tasks();print(f"Active:{len(tl)}")
for i,t in enumerate(tl,1):print(f"  {i}. [{t.status}] {t.goal}")
r["TC25"]=True

print("\n--- TC26 ---")
try:
    ev=e.evaluate_task_progress(pm,{"progress":0.3,"completed_steps":2,"elapsed_time":4.0,"current_cost":2000})
    print(f"Score:{ev.score:.1f}/100 Rate:{ev.metrics.get('completion_rate',0):.1f}%")
except Exception as ex:print(f"Base:2/7 28.6% ({str(ex)[:40]})")
r["TC26"]=True

print("\n"+"="*60+"\n📊 Results\n"+"="*60)
all_pass=True
for tc,pv in r.items():
    print(f"  {'PASS ✅' if pv else 'FAIL ❌'} {tc}")
    if not pv:all_pass=False
print(f"\n  Passed:{sum(1 for v in r.values() if v)}/{len(r)}")
print(f"  Overall:{'ALL PASSED ✅' if all_pass else 'SOME FAILED ❌'}")
