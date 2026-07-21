#!/usr/bin/env python3
"""
测试大脑引擎功能
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from link.core.model_engine import create_brain_engine, BrainEngine
from link.core.model_engine.model_adapter import ModelResponse
import time


def test_ollama_connection():
    """测试Ollama连接"""
    print("🔌 测试Ollama连接...")
    
    try:
        import requests
        response = requests.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            print(f"✅ Ollama服务正常，找到 {len(models)} 个模型")
            for model in models:
                print(f"   - {model.get('name')}")
            return True
        else:
            print(f"❌ Ollama服务返回错误状态码: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ 无法连接到Ollama服务: {str(e)}")
        print("   请确保Ollama正在运行: ollama serve")
        return False


def test_brain_engine_initialization():
    """测试大脑引擎初始化"""
    print("\n🧠 测试大脑引擎初始化...")
    
    try:
        # 创建大脑引擎
        config = {
            "model_provider": "ollama",
            "model_name": "deepseek-r1:7b",
            "base_url": "http://localhost:11434",
            "timeout": 30,
        }
        
        engine = create_brain_engine(config)
        
        # 健康检查
        health = engine.health_check()
        print(f"✅ 大脑引擎初始化成功")
        print(f"   模型: {health.get('brain_engine', {}).get('config', {}).get('model_name')}")
        print(f"   状态: {health.get('overall_status', 'unknown')}")
        
        return engine, True
    except Exception as e:
        print(f"❌ 大脑引擎初始化失败: {str(e)}")
        return None, False


def test_intent_analysis(engine: BrainEngine):
    """测试意图分析"""
    print("\n🎯 测试意图分析...")
    
    test_inputs = [
        "帮我规划一个周末旅行",
        "现在几点了？",
        "打开客厅的灯",
        "今天的天气怎么样？",
        "学习Python的最佳方法是什么？"
    ]
    
    results = []
    for i, user_input in enumerate(test_inputs[:2], 1):  # 只测试前2个
        print(f"   测试 {i}: '{user_input}'")
        
        try:
            start_time = time.time()
            result = engine.analyze_intent(user_input)
            elapsed = time.time() - start_time
            
            intent = result.get("intent", "未知")
            confidence = result.get("confidence", 0)
            
            print(f"      → 意图: {intent} (置信度: {confidence:.2f}, 耗时: {elapsed:.2f}s)")
            results.append((True, intent, confidence))
        except Exception as e:
            print(f"      → 错误: {str(e)}")
            results.append((False, str(e), 0))
    
    # 总结
    success_count = sum(1 for success, _, _ in results if success)
    if success_count == len(results):
        print("✅ 意图分析测试全部通过")
        return True
    else:
        print(f"⚠️  意图分析测试 {success_count}/{len(results)} 通过")
        return success_count > 0


def test_response_generation(engine: BrainEngine):
    """测试回复生成"""
    print("\n💬 测试回复生成...")
    
    test_queries = [
        "你好，介绍一下你自己",
        "什么是人工智能？",
    ]
    
    results = []
    for i, query in enumerate(test_queries, 1):
        print(f"   测试 {i}: '{query}'")
        
        try:
            start_time = time.time()
            response = engine.generate_response(query)
            elapsed = time.time() - start_time
            
            if response and len(response) > 0:
                print(f"      → 回复长度: {len(response)} 字符, 耗时: {elapsed:.2f}s")
                print(f"      → 预览: {response[:80]}...")
                results.append(True)
            else:
                print(f"      → 错误: 返回空回复")
                results.append(False)
        except Exception as e:
            print(f"      → 错误: {str(e)}")
            results.append(False)
    
    # 总结
    success_count = sum(1 for success in results if success)
    if success_count == len(results):
        print("✅ 回复生成测试全部通过")
        return True
    else:
        print(f"⚠️  回复生成测试 {success_count}/{len(results)} 通过")
        return success_count > 0


def test_task_planning(engine: BrainEngine):
    """测试任务规划"""
    print("\n📋 测试任务规划...")
    
    test_tasks = [
        "规划一个简单的Python学习计划",
        "组织一个生日派对"
    ]
    
    results = []
    for i, task in enumerate(test_tasks[:1], 1):  # 只测试1个
        print(f"   测试 {i}: '{task}'")
        
        try:
            start_time = time.time()
            plan = engine.plan_task(task)
            elapsed = time.time() - start_time
            
            task_name = plan.get("task_name", "未知任务")
            steps = plan.get("steps", [])
            complexity = plan.get("complexity", "未知")
            
            print(f"      → 任务: {task_name}")
            print(f"      → 复杂度: {complexity}")
            print(f"      → 步骤数: {len(steps)}")
            print(f"      → 耗时: {elapsed:.2f}s")
            
            if steps:
                print(f"      → 前3个步骤:")
                for j, step in enumerate(steps[:3], 1):
                    desc = step.get("description", "未知步骤")
                    print(f"         {j}. {desc}")
            
            results.append(True)
        except Exception as e:
            print(f"      → 错误: {str(e)}")
            results.append(False)
    
    # 总结
    success_count = sum(1 for success in results if success)
    if success_count == len(results):
        print("✅ 任务规划测试全部通过")
        return True
    else:
        print(f"⚠️  任务规划测试 {success_count}/{len(results)} 通过")
        return success_count > 0


def test_chat_completion(engine: BrainEngine):
    """测试聊天完成"""
    print("\n💭 测试聊天完成...")
    
    try:
        messages = [
            {"role": "system", "content": "你是一个有用的助手。"},
            {"role": "user", "content": "用一句话介绍Python编程语言。"}
        ]
        
        print(f"   发送聊天请求...")
        start_time = time.time()
        response = engine.chat_completion(messages, temperature=0.7, max_tokens=100)
        elapsed = time.time() - start_time
        
        if response and response.text:
            print(f"      → 回复: {response.text}")
            print(f"      → 使用token: {response.tokens_used}")
            print(f"      → 耗时: {elapsed:.2f}s")
            print("✅ 聊天完成测试通过")
            return True
        else:
            print(f"      → 错误: 返回空响应")
            return False
    except Exception as e:
        print(f"      → 错误: {str(e)}")
        return False


def main():
    """主函数"""
    print("=" * 60)
    print("🧪 LINK 大脑引擎测试")
    print("=" * 60)
    
    # 检查虚拟环境
    venv_path = os.path.join(os.path.dirname(__file__), ".venv")
    if os.path.exists(venv_path):
        print("🔧 检测到虚拟环境")
    
    test_results = []
    
    # 测试Ollama连接
    ollama_ok = test_ollama_connection()
    test_results.append(("Ollama连接", ollama_ok))
    
    if not ollama_ok:
        print("\n⚠️  Ollama连接失败，部分测试将跳过")
        print("   请确保Ollama正在运行并已安装deepseek-r1:7b模型")
        print("   安装命令: ollama pull deepseek-r1:7b")
    
    # 测试大脑引擎初始化
    engine, init_ok = test_brain_engine_initialization()
    test_results.append(("大脑引擎初始化", init_ok))
    
    if init_ok and engine:
        # 运行功能测试
        test_results.append(("意图分析", test_intent_analysis(engine)))
        test_results.append(("回复生成", test_response_generation(engine)))
        test_results.append(("任务规划", test_task_planning(engine)))
        test_results.append(("聊天完成", test_chat_completion(engine)))
        
        # 显示最终健康状态
        print("\n📊 最终健康检查:")
        health = engine.health_check()
        print(f"   整体状态: {health.get('overall_status', 'unknown')}")
        print(f"   交互历史: {health.get('brain_engine', {}).get('interaction_history_count', 0)} 条")
    
    # 总结
    print("\n" + "=" * 60)
    print("📋 测试结果总结")
    print("=" * 60)
    
    passed = 0
    for name, success in test_results:
        status = "✅ 通过" if success else "❌ 失败"
        print(f"{name}: {status}")
        if success:
            passed += 1
    
    total = len(test_results)
    print(f"\n🎯 总计: {passed}/{total} 通过")
    
    if passed == total:
        print("✨ 所有测试通过！大脑引擎已准备就绪。")
        return 0
    elif passed > 0:
        print("⚠️  部分测试通过，大脑引擎基本功能可用。")
        return 1
    else:
        print("❌ 所有测试失败，请检查配置和依赖。")
        return 2


if __name__ == "__main__":
    sys.exit(main())