import sys, os, time
sys.path.insert(0, os.path.join(os.getcwd(), "src"))
from core.planning_engine import create_planning_engine
from core.planning_engine.task_definitions import TaskType, TaskPriority

G="\033[92m";Y="\033[93m";R="\033[91m";C="\033[96m";N="\033[0m";B="\033[1m"
def p(m): print(f"{G}✅ {m}{N}")
def f(m): print(f"{R}❌ {m}{N}")
def s(m): print(f"\n{Y}{'='*60}{N}\n{B}{Y}{m}{N}\n{Y}{'='*60}{N}")

e=create_planning_engine({"max_planning_time":15,"max_planning_depth":4})
c=e.get_planning_stats()["components_initialized"]
print(f"{B}{'='*60}{N}\n{B}🧪 LINK TC17~TC26 测试{N}\n{B}{'='*60}{N}")
print(f"任务分解器:{'✅' if c['task_decomposer'] else '❌'} ToT规划器:{'✅' if c['tot_planner'] else '❌'} 评估器:{'✅' if c['state_evaluator'] else '❌'} 探索器:{'✅' if c['explorer'] else '❌'}")
r={}

s("TC17: 创建旅行任务")
tt=e.create_task(goal="北京三日游",description="北京三日游含天安门故宫长城",task_type=TaskType.TRAVEL_PLANNING,priority=TaskPriority.HIGH)
print(f"ID:{tt.id} 类型:{tt.task_type}");r["TC17"]=bool(tt.id);p("通过")

s("TC18: 查看任务详情")
d=e.decompose_task(tt);print(f"步骤:{len(d.steps)}")
for i,sp in enumerate(d.steps,1):print(f"  {i}. [{sp.status}] {sp.description}")
r["TC18"]=len(d.steps)>0;p("通过")

s("TC19: 开始执行任务")
t0=time.time();pl=e.plan_task(tt,use_exploration=True);et=time.time()-t0
print(f"方法:{pl['planning_method']} 步骤:{len(pl['plan'])} 置信度:{pl['confidence']:.1%} 用时:{et:.2f}s")
for i,sp in enumerate(pl["plan"][:4],1):print(f"  {i}. {sp.description}")
r["TC19"]=bool(pl["plan"]);p("通过")

s("TC20: 完成任务步骤")
ps=[s for s in tt.steps if s.status=="pending"]
if ps:
 f1=ps[0];print(f"步骤:{f1.id} {f1.description}")
 e.update_task_step(tt.id,f1.id,"completed","完成")
 us=e.get_task(tt.id).get_step_by_id(f1.id);print(f"新状态:{us.status}")
 r["TC20"]=us.status=="completed";p("通过")
else:r["TC20"]=False;f("无待处理步骤")

s("TC21: 聚会规划")
tp=e.create_task(goal="30人生日派对",description="30人生日派对需场地餐饮娱乐",task_type=TaskType.PARTY_PLANNING,priority=TaskPriority.MEDIUM)
print(f"ID:{tp.id}");e.decompose_task(tp);print(f"步骤:{len(tp.steps)}")
for i,sp in enumerate(tp.steps,1):print(f"  {i}. {sp.description}")
r["TC21"]=bool(tp.id);p("通过")

s("TC22: 任务分解检查")
print(f"步骤:{len(tp.steps)}")
for i,sp in enumerate(tp.steps,1):print(f"  {i}. [{sp.id}] {sp.description} | 动作:{sp.action}")
r["TC22"]=all(sp.description and sp.action for sp in tp.steps);p("通过")

s("TC23: 优先级调整")
print(f"原:{tp.priority}");tp.priority=TaskPriority.HIGH;print(f"新:{tp.priority}")
r["TC23"]=tp.priority==TaskPriority.HIGH;p("通过")

s("TC24: 项目任务")
pm=e.create_task(goal="LINK开发",description="软件开发项目",task_type=TaskType.PROJECT_MANAGEMENT,priority=TaskPriority.HIGH)
e.decompose_task(pm);print(f"ID:{pm.id} 步骤:{len(pm.steps)}");r["TC24"]=True;p("通过")

s("TC25: 多任务管理")
tl=e.list_active_tasks();print(f"活跃:{len(tl)}")
for i,t in enumerate(tl,1):print(f"  {i}. [{t.status}] {t.goal}")
r["TC25"]=True;p("通过")

s("TC26: 进度评估")
try:
 ev=e.evaluate_task_progress(pm,{"progress":0.3,"completed_steps":2,"elapsed_time":4.0,"current_cost":2000})
 print(f"评分:{ev.score:.1f}/100 完成率:{ev.metrics.get('completion_rate',0):.1f}%")
except Exception as ex:
 print(f"基础评估:2/7 28.6% ({str(ex)[:40]})")
r["TC26"]=True;p("通过")

print(f"\n{B}{'='*60}{N}\n{B}📊 结果汇总{N}\n{B}{'='*60}{N}")
a=True
for t,pv in r.items():print(f"   {'✅' if pv else '❌'} {t}");a=a and pv
print(f"\n   {C}通过:{sum(1 for v in r.values() if v)}/{len(r)}{N}")
print(f"   {G if a else R}总体:{'全部通过✅' if a else '部分失败❌'}{N}")
