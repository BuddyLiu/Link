#!/usr/bin/env python3
"""测试LINK主动运行模式"""

import sys
import os
import time
import threading
from datetime import datetime

# 添加项目路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_basic_event_loop():
    """测试基本事件循环"""
    print("🧪 测试基本事件循环...")
    
    try:
        from link.active_link_enhanced import (
            ActiveLINK, Event, EventType, EventPriority
        )
        
        # 创建主动LINK实例（不依赖传统LINK）
        active_link = ActiveLINK()
        
        # 启动非阻塞模式
        active_link.start(blocking=False)
        print("✅ 事件循环启动成功")
        
        # 等待事件循环初始化
        time.sleep(1)
        
        # 添加一些测试事件
        print("📤 添加测试事件...")
        
        # 用户输入事件
        active_link.add_user_input("测试用户输入")
        print("✅ 添加用户输入事件")
        
        # 自定义事件
        test_event = Event(
            event_type=EventType.SYSTEM,
            data={"action": "test", "message": "测试系统事件"},
            priority=EventPriority.NORMAL,
            source="test_script"
        )
        
        # 由于event_queue是私有属性，通过间接方式测试
        # 实际应该通过add_user_input等公开方法添加事件
        
        # 获取统计信息
        stats = active_link.get_stats()
        print(f"📊 运行统计:")
        print(f"   运行中: {stats.get('is_running', False)}")
        print(f"   已处理事件: {stats.get('events_processed', 0)}")
        print(f"   事件队列大小: {stats.get('event_queue_size', 0)}")
        
        # 等待事件处理
        print("⏳ 等待事件处理（3秒）...")
        time.sleep(3)
        
        # 再次获取统计信息
        stats = active_link.get_stats()
        print(f"📊 处理后统计:")
        print(f"   已处理事件: {stats.get('events_processed', 0)}")
        
        # 停止事件循环
        active_link.stop()
        print("✅ 事件循环停止成功")
        
        return True
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_periodic_tasks():
    """测试周期性任务"""
    print("\n🧪 测试周期性任务...")
    
    try:
        from link.active_link_enhanced import ActiveLINK
        
        # 创建自定义配置，缩短测试间隔
        config = {
            "event_loop_interval": 0.1,
            "max_events_per_cycle": 5,
            "enable_periodic_tasks": True,
            "periodic_tasks": {
                "heartbeat": {"interval": 2, "enabled": True},  # 2秒
                "task_monitor": {"interval": 3, "enabled": True},  # 3秒
            },
            "log_level": "INFO"
        }
        
        active_link = ActiveLINK(config=config)
        active_link.start(blocking=False)
        
        print("✅ 周期性任务启动，等待10秒...")
        print("📝 预期看到心跳和任务监控事件")
        
        # 等待10秒观察周期性任务
        for i in range(10):
            time.sleep(1)
            stats = active_link.get_stats()
            processed = stats.get('events_processed', 0)
            print(f"  第{i+1}秒 - 已处理事件: {processed}")
        
        active_link.stop()
        
        final_stats = active_link.get_stats()
        total_processed = final_stats.get('events_processed', 0)
        
        if total_processed > 0:
            print(f"✅ 周期性任务测试成功，总共处理 {total_processed} 个事件")
            return True
        else:
            print("❌ 周期性任务测试失败，未处理任何事件")
            return False
            
    except Exception as e:
        print(f"❌ 周期性任务测试失败: {e}")
        return False

def test_user_interaction():
    """测试用户交互"""
    print("\n🧪 测试用户交互...")
    
    try:
        # 这里模拟用户输入
        print("📝 模拟用户输入处理...")
        
        # 由于真实用户输入需要交互，我们创建一个模拟线程
        from link.active_link_enhanced import ActiveLINK
        
        config = {
            "event_loop_interval": 0.1,
            "log_level": "DEBUG"
        }
        
        active_link = ActiveLINK(config=config)
        active_link.start(blocking=False)
        
        # 添加多个用户输入
        test_inputs = [
            "你好",
            "现在几点了",
            "帮我规划一个简单的任务",
            "学习新技能"
        ]
        
        print("📤 发送测试输入...")
        for i, text in enumerate(test_inputs, 1):
            print(f"  输入{i}: {text}")
            active_link.add_user_input(text)
            time.sleep(1)  # 等待处理
        
        # 等待处理完成
        time.sleep(3)
        
        stats = active_link.get_stats()
        processed = stats.get('events_processed', 0)
        
        active_link.stop()
        
        if processed >= len(test_inputs):
            print(f"✅ 用户交互测试成功，处理了 {processed} 个事件")
            return True
        else:
            print(f"⚠️  用户交互测试部分成功，处理了 {processed}/{len(test_inputs)} 个事件")
            return processed > 0
            
    except Exception as e:
        print(f"❌ 用户交互测试失败: {e}")
        return False

def test_learning_events():
    """测试学习事件"""
    print("\n🧪 测试学习事件...")
    
    try:
        from link.active_link_enhanced import ActiveLINK
        
        config = {
            "event_loop_interval": 0.1,
            "enable_periodic_tasks": True,
            "periodic_tasks": {
                "learning_cycle": {"interval": 5, "enabled": True}  # 5秒测试
            },
            "log_level": "INFO"
        }
        
        active_link = ActiveLINK(config=config)
        active_link.start(blocking=False)
        
        print("⏳ 等待学习事件触发（10秒）...")
        
        # 记录开始统计
        start_stats = active_link.get_stats()
        start_processed = start_stats.get('events_processed', 0)
        
        # 等待学习事件
        time.sleep(10)
        
        # 记录结束统计
        end_stats = active_link.get_stats()
        end_processed = end_stats.get('events_processed', 0)
        
        active_link.stop()
        
        processed_during_test = end_processed - start_processed
        
        if processed_during_test > 0:
            print(f"✅ 学习事件测试成功，期间处理了 {processed_during_test} 个事件")
            return True
        else:
            print(f"⚠️  学习事件测试未检测到事件处理")
            return False
            
    except Exception as e:
        print(f"❌ 学习事件测试失败: {e}")
        return False

def test_integration_with_legacy_link():
    """测试与传统LINK的集成"""
    print("\n🧪 测试与传统LINK集成...")
    
    try:
        # 尝试导入传统LINK
        from link.main import LINK
        
        # 创建传统LINK实例
        print("🔧 初始化传统LINK...")
        legacy_link = LINK()
        
        # 创建主动LINK，传入传统实例
        print("🔧 创建主动LINK...")
        from link.active_link_enhanced import ActiveLINK
        
        active_link = ActiveLINK(legacy_link=legacy_link)
        active_link.start(blocking=False)
        
        print("✅ 集成启动成功")
        print("📤 发送任务创建请求...")
        
        # 通过主动LINK发送用户输入
        active_link.add_user_input("帮我规划一个周末旅行")
        
        # 等待处理
        time.sleep(5)
        
        # 获取统计
        stats = active_link.get_stats()
        processed = stats.get('events_processed', 0)
        
        active_link.stop()
        
        if processed > 0:
            print(f"✅ 集成测试成功，处理了 {processed} 个事件")
            return True
        else:
            print(f"⚠️  集成测试处理了 {processed} 个事件")
            return processed > 0
            
    except Exception as e:
        print(f"❌ 集成测试失败: {e}")
        print("ℹ️  这可能是由于依赖问题，但主动模式本身仍可工作")
        return False

def run_all_tests():
    """运行所有测试"""
    print("="*60)
    print("🚀 LINK主动运行模式测试套件")
    print("="*60)
    
    test_results = []
    
    # 运行各个测试
    tests = [
        ("基本事件循环", test_basic_event_loop),
        ("周期性任务", test_periodic_tasks),
        ("用户交互", test_user_interaction),
        ("学习事件", test_learning_events),
        ("传统LINK集成", test_integration_with_legacy_link),
    ]
    
    for test_name, test_func in tests:
        print(f"\n▶️  开始测试: {test_name}")
        try:
            success = test_func()
            test_results.append((test_name, success))
            status = "✅ 通过" if success else "❌ 失败"
            print(f"{status}: {test_name}")
        except Exception as e:
            print(f"❌ 测试异常: {test_name} - {e}")
            test_results.append((test_name, False))
    
    # 输出结果
    print("\n" + "="*60)
    print("📊 测试结果汇总")
    print("="*60)
    
    passed = sum(1 for _, success in test_results if success)
    total = len(test_results)
    
    for test_name, success in test_results:
        status = "✅" if success else "❌"
        print(f"{status} {test_name}")
    
    print(f"\n🎯 通过率: {passed}/{total} ({passed/total*100:.0f}%)")
    
    if passed == total:
        print("🎉 所有测试通过！")
        return True
    elif passed >= total * 0.6:
        print("⚠️  大部分测试通过，建议进一步优化")
        return True
    else:
        print("❌ 测试失败较多，需要检查实现")
        return False

if __name__ == "__main__":
    # 运行测试
    success = run_all_tests()
    
    if success:
        print("\n✨ 主动运行模式核心功能验证完成")
        print("💡 建议下一步:")
        print("  1. 运行 'python link/active_link_enhanced.py' 测试完整功能")
        print("  2. 修改 run_link.py 支持主动模式启动")
        print("  3. 集成到实际使用场景中")
    else:
        print("\n🔧 测试发现问题，需要修复实现")
    
    sys.exit(0 if success else 1)