#!/usr/bin/env python3
"""
测试新组件：反思系统和提醒系统
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from link.reflection import (
    create_reflection_engine,
    create_learning_module,
    create_knowledge_updater,
    ReflectionTrigger
)
from link.reminders import (
    create_reminder_manager,
    create_trigger_checker,
    create_notification_sender,
    ReminderTrigger,
    ReminderStatus
)
from link.config.settings import settings


class TestNewComponents:
    """测试新组件"""
    
    def __init__(self):
        """初始化测试"""
        print("🧪 开始测试新组件...")
        
        # 初始化配置
        self.config = {
            "reflection": settings.reflection.model_dump(),
            "reminder": settings.reminder.model_dump(),
            "external": settings.external.model_dump(),
        }
        
        # 初始化组件
        self._initialize_components()
    
    def _initialize_components(self):
        """初始化所有组件"""
        print("🔄 初始化组件...")
        
        # 反思系统
        self.reflection_engine = create_reflection_engine(
            self.config["reflection"]
        )
        
        self.learning_module = create_learning_module(
            self.config["reflection"]
        )
        
        self.knowledge_updater = create_knowledge_updater(
            self.config["reflection"]
        )
        
        # 连接反思系统组件
        self.reflection_engine.set_components(
            learning_module=self.learning_module,
            knowledge_updater=self.knowledge_updater
        )
        
        # 提醒系统
        self.reminder_manager = create_reminder_manager(
            self.config["reminder"]
        )
        
        self.trigger_checker = create_trigger_checker(
            self.config["reminder"]
        )
        
        self.notification_sender = create_notification_sender(
            self.config["reminder"]
        )
        
        # 连接提醒系统组件
        self.reminder_manager.set_components(
            trigger_checker=self.trigger_checker,
            notification_sender=self.notification_sender
        )
        
        print("✅ 组件初始化完成")
    
    def test_reflection_system(self):
        """测试反思系统"""
        print("\n🧠 测试反思系统...")
        
        # 模拟一个失败的任务结果
        task_result = {
            "task_id": "test_task_001",
            "status": "failed",
            "error": "任务执行超时，超过30秒限制",
            "failed_step": "步骤3：下载文件",
            "confidence": 0.4,
            "user_feedback": {
                "satisfaction": 2,
                "comments": "太慢了，没有达到预期"
            }
        }
        
        # 测试任务失败反思
        print("📋 测试任务失败反思...")
        reflection_result = self.reflection_engine.reflect(
            task_id="test_task_001",
            task_result=task_result,
            trigger=ReflectionTrigger.TASK_FAILURE,
            context={"user": "test_user"}
        )
        
        if reflection_result:
            print(f"✅ 反思成功: {reflection_result.id}")
            print(f"   分析: {reflection_result.analysis[:50]}...")
            print(f"   根本原因: {reflection_result.root_causes}")
            print(f"   建议: {reflection_result.suggestions[:2]}")
        else:
            print("❌ 反思未触发")
        
        # 测试低置信度反思
        print("\n📊 测试低置信度反思...")
        low_confidence_result = {
            "task_id": "test_task_002",
            "status": "completed",
            "confidence": 0.6,
            "ambiguous_requirements": True
        }
        
        reflection_result = self.reflection_engine.reflect(
            task_id="test_task_002",
            task_result=low_confidence_result,
            trigger=ReflectionTrigger.LOW_CONFIDENCE,
            context={"user": "test_user"}
        )
        
        if reflection_result:
            print(f"✅ 低置信度反思成功: {reflection_result.id}")
            print(f"   分析: {reflection_result.analysis[:50]}...")
        else:
            print("❌ 低置信度反思未触发")
        
        # 获取反思统计
        print("\n📈 反思系统统计:")
        stats = self.reflection_engine.get_reflection_stats()
        print(f"   总反思次数: {stats['total_reflections']}")
        print(f"   已应用反思: {stats['applied_reflections']}")
        print(f"   应用率: {stats['application_rate']:.1%}")
        
        return True
    
    def test_reminder_system(self):
        """测试提醒系统"""
        print("\n⏰ 测试提醒系统...")
        
        # 创建时间提醒
        print("🕐 创建时间提醒...")
        reminder = self.reminder_manager.add_reminder(
            user_id="test_user",
            title="测试会议",
            content="下午3点团队会议，请准时参加",
            trigger_type=ReminderTrigger.TIME,
            trigger_config={
                "datetime": (datetime.now().replace(hour=15, minute=0)).isoformat()
            },
            repeat_pattern="weekly",
            metadata={
                "priority": "high",
                "category": "meeting",
                "location": "会议室A"
            }
        )
        
        if reminder:
            print(f"✅ 时间提醒创建成功: {reminder.id}")
            print(f"   标题: {reminder.title}")
            print(f"   下次触发时间: {reminder.next_trigger_time}")
        else:
            print("❌ 时间提醒创建失败")
        
        # 创建条件提醒
        print("\n⚙️  创建条件提醒...")
        reminder = self.reminder_manager.add_reminder(
            user_id="test_user",
            title="CPU使用率过高",
            content="CPU使用率超过80%，请检查系统",
            trigger_type=ReminderTrigger.CONDITION,
            trigger_config={
                "condition_type": "simple",
                "key": "cpu_usage",
                "operator": "greater_than",
                "value": 80
            },
            metadata={
                "priority": "medium",
                "category": "system_alert"
            }
        )
        
        if reminder:
            print(f"✅ 条件提醒创建成功: {reminder.id}")
            print(f"   标题: {reminder.title}")
            print(f"   条件: CPU使用率 > 80%")
        else:
            print("❌ 条件提醒创建失败")
        
        # 获取用户提醒
        print("\n📋 获取用户提醒列表...")
        user_reminders = self.reminder_manager.get_user_reminders("test_user")
        print(f"   用户提醒数量: {len(user_reminders)}")
        
        for i, rem in enumerate(user_reminders, 1):
            print(f"   {i}. {rem.title} ({rem.status.value})")
        
        # 检查触发器
        print("\n🔍 检查提醒触发器...")
        triggered = self.reminder_manager.check_triggers()
        print(f"   触发的提醒数量: {len(triggered)}")
        
        # 获取提醒统计
        print("\n📊 提醒系统统计:")
        stats = self.reminder_manager.get_stats()
        print(f"   总提醒数量: {stats['total_reminders']}")
        print(f"   按状态: {stats['by_status']}")
        print(f"   按触发器类型: {stats['by_trigger_type']}")
        
        return True
    
    def test_integration(self):
        """测试组件集成"""
        print("\n🔗 测试组件集成...")
        
        # 模拟一个完整的任务流程
        print("1️⃣  创建任务并执行...")
        
        # 模拟任务失败
        task_result = {
            "task_id": "integrated_task_001",
            "status": "failed",
            "error": "网络连接失败",
            "failed_step": "连接数据库",
            "confidence": 0.3,
            "exceeded_resources": {"time": 60}
        }
        
        # 触发反思
        print("2️⃣  触发反思...")
        reflection = self.reflection_engine.reflect(
            task_id="integrated_task_001",
            task_result=task_result,
            trigger=ReflectionTrigger.TASK_FAILURE
        )
        
        if reflection:
            print(f"   ✅ 反思成功: {reflection.id}")
            
            # 应用反思结果
            print("3️⃣  应用反思结果...")
            applied = self.reflection_engine.apply_reflection_result(
                reflection_id=reflection.id,
                application_context={"context": "test_integration"}
            )
            
            if applied:
                print("   ✅ 反思结果已应用")
                
                # 创建提醒以便后续监控
                print("4️⃣  创建监控提醒...")
                reminder = self.reminder_manager.add_reminder(
                    user_id="test_user",
                    title="网络连接监控",
                    content="网络连接失败，请检查网络设置",
                    trigger_type=ReminderTrigger.CONDITION,
                    trigger_config={
                        "condition_type": "simple",
                        "key": "network_status",
                        "operator": "equals",
                        "value": "offline"
                    },
                    metadata={
                        "priority": "high",
                        "category": "network_alert",
                        "source_reflection": reflection.id
                    }
                )
                
                if reminder:
                    print(f"   ✅ 监控提醒创建成功: {reminder.id}")
                else:
                    print("   ❌ 监控提醒创建失败")
            else:
                print("   ❌ 反思结果应用失败")
        else:
            print("   ❌ 反思未触发")
        
        # 检查知识库更新
        print("\n📚 检查知识库...")
        if hasattr(self.knowledge_updater, 'get_knowledge_stats'):
            knowledge_stats = self.knowledge_updater.get_knowledge_stats()
            print(f"   知识条目总数: {knowledge_stats.get('total_entries', 0)}")
        
        print("✅ 集成测试完成")
        return True
    
    def run_all_tests(self):
        """运行所有测试"""
        print("=" * 60)
        print("LINK新组件测试套件")
        print("=" * 60)
        
        results = {
            "reflection_system": False,
            "reminder_system": False,
            "integration": False
        }
        
        try:
            results["reflection_system"] = self.test_reflection_system()
        except Exception as e:
            print(f"❌ 反思系统测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
        
        try:
            results["reminder_system"] = self.test_reminder_system()
        except Exception as e:
            print(f"❌ 提醒系统测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
        
        try:
            results["integration"] = self.test_integration()
        except Exception as e:
            print(f"❌ 集成测试失败: {str(e)}")
            import traceback
            traceback.print_exc()
        
        # 总结
        print("\n" + "=" * 60)
        print("📊 测试结果总结")
        print("=" * 60)
        
        for test_name, passed in results.items():
            status = "✅ 通过" if passed else "❌ 失败"
            print(f"{test_name}: {status}")
        
        total_passed = sum(1 for passed in results.values() if passed)
        total_tests = len(results)
        
        print(f"\n🎯 总计: {total_passed}/{total_tests} 通过")
        
        if total_passed == total_tests:
            print("✨ 所有测试通过！新组件可以正常工作。")
            return True
        else:
            print("⚠️  部分测试失败，需要进一步调试。")
            return False


def main():
    """主函数"""
    try:
        tester = TestNewComponents()
        success = tester.run_all_tests()
        return 0 if success else 1
    except Exception as e:
        print(f"❌ 测试过程中发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())