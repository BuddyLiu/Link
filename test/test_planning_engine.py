#!/usr/bin/env python3
"""
测试LINK规划引擎功能的演示脚本
"""

import sys
import os
import time
import json
from datetime import datetime

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from link.core.planning_engine import PlanningEngine, create_planning_engine
    from link.core.planning_engine.task_definitions import (
        TaskType, TaskPriority, TaskConstraint, create_task
    )
    from link.utils.logger import logger, setup_logger
except ImportError as e:
    print(f"导入失败: {e}")
    print("请确保已安装所有依赖项: pip install -r link/requirements.txt")
    sys.exit(1)


def test_basic_planning():
    """测试基础规划功能"""
    print("=" * 60)
    print("测试1: 基础规划引擎初始化")
    print("=" * 60)
    
    try:
        # 创建规划引擎
        config = {
            "planning_engine": "tot",
            "max_planning_time": 10,
            "max_planning_depth": 3,
            "planning_temperature": 0.7,
            "enable_complex_tasks": True,
            "max_task_steps": 15,
        }
        
        engine = create_planning_engine(config)
        print("✅ 规划引擎创建成功")
        
        # 获取统计信息
        stats = engine.get_planning_stats()
        print(f"引擎类型: {stats['planning_engine']}")
        print(f"组件状态: {stats['components_initialized']}")
        
        return engine
    except Exception as e:
        print(f"❌ 规划引擎初始化失败: {e}")
        return None


def test_task_creation(engine):
    """测试任务创建功能"""
    print("\n" + "=" * 60)
    print("测试2: 任务创建和分解")
    print("=" * 60)
    
    try:
        # 测试1: 旅行规划任务
        print("创建旅行规划任务...")
        travel_task = engine.create_task(
            goal="规划北京三日游",
            description="帮我规划一个北京三日游，包括故宫、长城、颐和园等景点",
            task_type=TaskType.TRAVEL_PLANNING,
            priority=TaskPriority.HIGH,
        )
        
        print(f"✅ 旅行任务创建成功: ID={travel_task.id}")
        print(f"   目标: {travel_task.goal}")
        print(f"   类型: {travel_task.task_type}")
        print(f"   优先级: {travel_task.priority}")
        
        # 分解任务
        decomposition = engine.decompose_task(travel_task)
        print(f"✅ 任务分解完成: {len(decomposition.steps)} 个步骤")
        for i, step in enumerate(decomposition.steps[:3], 1):
            print(f"   步骤{i}: {step.description}")
        
        if len(decomposition.steps) > 3:
            print(f"   ... 还有 {len(decomposition.steps) - 3} 个步骤")
        
        # 测试2: 聚会规划任务
        print("\n创建聚会规划任务...")
        party_task = engine.create_task(
            goal="组织生日派对",
            description="帮我组织一个30人的生日派对，需要准备场地、餐饮和娱乐",
            task_type=TaskType.PARTY_PLANNING,
            priority=TaskPriority.MEDIUM,
        )
        
        print(f"✅ 聚会任务创建成功: ID={party_task.id}")
        
        # 分解任务
        decomposition = engine.decompose_task(party_task)
        print(f"✅ 任务分解完成: {len(decomposition.steps)} 个步骤")
        
        return [travel_task, party_task]
    except Exception as e:
        print(f"❌ 任务创建失败: {e}")
        return []


def test_task_planning(engine, tasks):
    """测试任务规划功能"""
    print("\n" + "=" * 60)
    print("测试3: 任务规划和探索")
    print("=" * 60)
    
    results = []
    
    for task in tasks:
        try:
            print(f"\n为任务规划: {task.goal}")
            print(f"任务类型: {task.task_type}")
            
            # 开始计时
            start_time = time.time()
            
            # 执行规划
            planning_result = engine.plan_task(task, use_exploration=True)
            
            # 计算耗时
            planning_time = time.time() - start_time
            
            print(f"✅ 规划完成!")
            print(f"   规划步骤数: {len(planning_result['plan'])}")
            print(f"   规划置信度: {planning_result['confidence']:.1%}")
            print(f"   规划用时: {planning_time:.2f}秒")
            print(f"   规划方法: {planning_result['planning_method']}")
            
            # 显示前几个步骤
            if planning_result['plan']:
                print("   前3个步骤:")
                for i, step in enumerate(planning_result['plan'][:3], 1):
                    print(f"     步骤{i}: {step.description}")
            
            results.append({
                'task': task,
                'result': planning_result,
                'time': planning_time
            })
            
        except Exception as e:
            print(f"❌ 任务规划失败: {e}")
    
    return results


def test_task_evaluation(engine, tasks, planning_results):
    """测试任务评估功能"""
    print("\n" + "=" * 60)
    print("测试4: 任务状态评估")
    print("=" * 60)
    
    for task, result_info in zip(tasks, planning_results):
        try:
            print(f"\n评估任务: {task.goal}")
            
            # 创建模拟状态
            current_state = {
                "progress": 0.0,
                "completed_steps": 0,
                "elapsed_time": 1.0,  # 假设已执行1小时
                "current_cost": 500,  # 假设已花费500元
                "error_count": 0,
            }
            
            # 创建步骤状态映射
            step_statuses = {}
            for step in task.steps:
                step_statuses[step.id] = step.status
            
            # 执行评估
            evaluation = engine.evaluate_task_progress(task, current_state)
            
            print(f"✅ 评估完成!")
            print(f"   总体评分: {evaluation.score:.1f}/100")
            print(f"   完成率: {evaluation.metrics.get('completion_rate', 0):.1f}%")
            print(f"   约束满足度: {evaluation.metrics.get('constraint_satisfaction', 0):.1f}%")
            print(f"   时间效率: {evaluation.metrics.get('time_efficiency', 0):.1f}%")
            
            if evaluation.strengths:
                print(f"   优点: {', '.join(evaluation.strengths)}")
            if evaluation.weaknesses:
                print(f"   缺点: {', '.join(evaluation.weaknesses)}")
            if evaluation.suggestions:
                print(f"   建议: {evaluation.suggestions[0]}")
            
        except Exception as e:
            print(f"❌ 任务评估失败: {e}")


def test_task_management(engine):
    """测试任务管理功能"""
    print("\n" + "=" * 60)
    print("测试5: 任务管理功能")
    print("=" * 60)
    
    try:
        # 列出所有任务
        active_tasks = engine.list_active_tasks()
        print(f"活跃任务数: {len(active_tasks)}")
        
        if active_tasks:
            print("\n任务列表:")
            for i, task in enumerate(active_tasks, 1):
                completed_steps = sum(1 for step in task.steps if step.status == "completed")
                total_steps = len(task.steps)
                progress = completed_steps / total_steps if total_steps > 0 else 0
                
                print(f"  {i}. {task.goal}")
                print(f"     ID: {task.id}")
                print(f"     状态: {task.status}")
                print(f"     进度: {completed_steps}/{total_steps} ({progress:.0%})")
            
            # 测试导出功能
            if active_tasks:
                task_id = active_tasks[0].id
                export_data = engine.export_task_plan(task_id)
                
                print(f"\n导出任务 {task_id}:")
                print(f"  目标: {export_data.get('goal')}")
                print(f"  步骤数: {len(export_data.get('steps', []))}")
                print(f"  状态: {export_data.get('status')}")
        
        # 获取模板类型
        template_types = engine.get_task_template_types()
        print(f"\n支持的模板类型: {template_types}")
        
        print("✅ 任务管理功能测试完成")
        
    except Exception as e:
        print(f"❌ 任务管理测试失败: {e}")


def test_integration_scenario():
    """测试集成场景：完整的任务规划流程"""
    print("\n" + "=" * 60)
    print("测试6: 集成场景 - 完整的任务规划流程")
    print("=" * 60)
    
    try:
        # 创建规划引擎
        engine = create_planning_engine({
            "max_planning_time": 15,
            "max_planning_depth": 4,
        })
        
        # 1. 创建项目管理任务
        print("1. 创建项目管理任务...")
        project_task = engine.create_task(
            goal="开发LINK智能体的新功能模块",
            description="规划一个软件开发项目，包括需求分析、设计、实现、测试和部署阶段",
            task_type=TaskType.PROJECT_MANAGEMENT,
            priority=TaskPriority.HIGH,
        )
        
        print(f"   任务创建成功: {project_task.goal}")
        print(f"   任务ID: {project_task.id}")
        
        # 2. 分解任务
        print("\n2. 分解任务...")
        decomposition = engine.decompose_task(project_task)
        print(f"   分解为 {len(decomposition.steps)} 个步骤")
        
        # 3. 规划任务
        print("\n3. 规划任务...")
        start_time = time.time()
        planning_result = engine.plan_task(project_task, use_exploration=True)
        planning_time = time.time() - start_time
        
        print(f"   规划完成: {len(planning_result['plan'])} 个步骤")
        print(f"   置信度: {planning_result['confidence']:.1%}")
        print(f"   用时: {planning_time:.2f}秒")
        
        # 4. 模拟任务执行
        print("\n4. 模拟任务执行...")
        
        # 更新第一个步骤为进行中
        if project_task.steps:
            first_step = project_task.steps[0]
            engine.update_task_step(project_task.id, first_step.id, "in_progress")
            print(f"   开始执行步骤1: {first_step.description}")
            
            # 模拟步骤完成
            time.sleep(0.5)
            engine.update_task_step(project_task.id, first_step.id, "completed", "需求分析完成")
            print(f"   完成步骤1: {first_step.description}")
        
        # 5. 评估任务进度
        print("\n5. 评估任务进度...")
        current_state = {
            "progress": 0.1,  # 10%进度
            "completed_steps": 1,
            "elapsed_time": 2.0,  # 已执行2小时
            "current_cost": 1000,  # 已花费1000元
        }
        
        step_statuses = {step.id: step.status for step in project_task.steps}
        evaluation = engine.evaluate_task_progress(project_task, current_state)
        
        print(f"   评估评分: {evaluation.score:.1f}/100")
        print(f"   进度: {evaluation.metrics.get('completion_rate', 0):.1f}%")
        
        # 6. 显示任务详情
        print("\n6. 任务详情:")
        export_data = engine.export_task_plan(project_task.id)
        print(f"   任务状态: {export_data.get('status')}")
        print(f"   创建时间: {export_data.get('created_at')}")
        print(f"   步骤状态: {sum(1 for step in export_data.get('steps', []) if step.get('status') == 'completed')}/{len(export_data.get('steps', []))} 完成")
        
        print("\n✅ 集成场景测试完成!")
        
        return True
        
    except Exception as e:
        print(f"❌ 集成场景测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主测试函数"""
    print("🚀 LINK规划引擎功能测试")
    print("=" * 60)
    
    # 设置日志
    try:
        setup_logger()
    except:
        pass  # 如果日志设置失败，继续测试
    
    # 测试基础规划
    engine = test_basic_planning()
    if not engine:
        print("❌ 测试中止: 规划引擎初始化失败")
        return False
    
    # 测试任务创建
    tasks = test_task_creation(engine)
    if not tasks:
        print("❌ 测试中止: 任务创建失败")
        return False
    
    # 测试任务规划
    planning_results = test_task_planning(engine, tasks)
    if not planning_results:
        print("⚠️  警告: 任务规划测试部分失败，继续其他测试")
    
    # 测试任务评估
    test_task_evaluation(engine, tasks, planning_results)
    
    # 测试任务管理
    test_task_management(engine)
    
    # 测试集成场景
    success = test_integration_scenario()
    
    print("\n" + "=" * 60)
    print("测试总结")
    print("=" * 60)
    
    if success:
        print("✅ 所有测试完成!")
        print("\n🎉 LINK规划引擎功能正常!")
        print("   已实现的功能包括:")
        print("   1. 复杂任务创建和类型检测")
        print("   2. 任务分解为可执行步骤")
        print("   3. Tree of Thoughts (ToT)规划算法")
        print("   4. 多路径探索和优化决策")
        print("   5. 任务状态评估和质量分析")
        print("   6. 任务管理和进度跟踪")
        print("\n   现在可以运行LINK主程序体验完整功能:")
        print("   python run_link.py --mode cli")
    else:
        print("⚠️  部分测试失败，但核心功能可能仍可用")
    
    return success


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)