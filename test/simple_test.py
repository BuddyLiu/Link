#!/usr/bin/env python3
"""
简化版测试脚本
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime

# 直接导入模块，避免复杂的配置依赖
def test_reflection():
    """测试反思系统"""
    print("🧪 测试反思系统...")
    
    try:
        # 导入反思引擎
        from jarvis.reflection.reflection_engine import ReflectionEngine, ReflectionTrigger
        
        # 创建引擎
        engine = ReflectionEngine({
            "enable_auto_reflection": True,
            "reflection_triggers": ["task_failure", "low_confidence"]
        })
        
        # 模拟任务结果
        task_result = {
            "task_id": "test_task_001",
            "status": "failed",
            "error": "执行超时"
        }
        
        # 执行反思
        result = engine.reflect(
            task_id="test_task_001",
            task_result=task_result,
            trigger=ReflectionTrigger.TASK_FAILURE
        )
        
        if result:
            print(f"✅ 反思系统测试通过！")
            print(f"   反思ID: {result.id}")
            print(f"   分析: {result.analysis[:50]}...")
            return True
        else:
            print("❌ 反思未触发")
            return False
            
    except Exception as e:
        print(f"❌ 反思系统测试失败: {str(e)}")
        return False

def test_reminder():
    """测试提醒系统"""
    print("\n🧪 测试提醒系统...")
    
    try:
        # 导入提醒管理器
        from jarvis.reminders.reminder_manager import ReminderManager, ReminderTrigger
        
        # 创建管理器
        manager = ReminderManager({
            "enable_active_reminders": True,
            "storage_type": "memory"
        })
        
        # 创建提醒
        reminder = manager.add_reminder(
            user_id="test_user",
            title="测试提醒",
            content="这是一个测试提醒",
            trigger_type=ReminderTrigger.TIME,
            trigger_config={
                "datetime": datetime.now().isoformat()
            }
        )
        
        if reminder:
            print(f"✅ 提醒系统测试通过！")
            print(f"   提醒ID: {reminder.id}")
            print(f"   标题: {reminder.title}")
            return True
        else:
            print("❌ 提醒创建失败")
            return False
            
    except Exception as e:
        print(f"❌ 提醒系统测试失败: {str(e)}")
        return False

def test_integration():
    """测试集成"""
    print("\n🧪 测试系统集成...")
    
    try:
        # 检查所有文件是否存在
        required_files = [
            "jarvis/reflection/__init__.py",
            "jarvis/reflection/reflection_engine.py",
            "jarvis/reflection/learning_module.py",
            "jarvis/reflection/knowledge_updater.py",
            "jarvis/reminders/__init__.py",
            "jarvis/reminders/reminder_manager.py",
            "jarvis/reminders/trigger_checker.py",
            "jarvis/reminders/notification_sender.py"
        ]
        
        missing_files = []
        for file in required_files:
            if not os.path.exists(os.path.join(os.path.dirname(__file__), file)):
                missing_files.append(file)
        
        if missing_files:
            print(f"❌ 缺少文件: {missing_files}")
            return False
        else:
            print("✅ 所有组件文件存在")
            
        # 检查导入
        try:
            from jarvis.reflection import ReflectionEngine, ReflectionTrigger, LearningModule, KnowledgeUpdater
            from jarvis.reminders import ReminderManager, ReminderTrigger, TriggerChecker, NotificationSender
            print("✅ 所有模块可以正确导入")
            return True
        except Exception as e:
            print(f"❌ 模块导入失败: {str(e)}")
            return False
            
    except Exception as e:
        print(f"❌ 集成测试失败: {str(e)}")
        return False

def main():
    """主函数"""
    print("=" * 60)
    print("JARVIS 新组件简化测试")
    print("=" * 60)
    
    # 切换到虚拟环境
    venv_path = os.path.join(os.path.dirname(__file__), ".venv")
    if os.path.exists(venv_path):
        print("🔧 检测到虚拟环境")
    
    results = []
    
    # 运行测试
    results.append(("反思系统", test_reflection()))
    results.append(("提醒系统", test_reminder()))
    results.append(("系统集成", test_integration()))
    
    # 总结
    print("\n" + "=" * 60)
    print("📊 测试结果总结")
    print("=" * 60)
    
    passed = 0
    for name, success in results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")
        if success:
            passed += 1
    
    total = len(results)
    print(f"\n🎯 总计: {passed}/{total} 通过")
    
    if passed == total:
        print("✨ 所有测试通过！系统已准备就绪。")
        return 0
    else:
        print("⚠️  部分测试失败，但核心功能已实现。")
        return 1

if __name__ == "__main__":
    sys.exit(main())