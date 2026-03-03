#!/usr/bin/env python3
"""
测试任务执行功能，确保大脑引擎被正确调用
"""

import sys
import time
from jarvis.main import JARVIS

def test_task_creation_and_execution():
    """测试任务创建和执行"""
    print("🔄 初始化JARVIS系统...")
    jarvis = JARVIS()
    
    print("✅ JARVIS初始化完成")
    
    # 测试1：创建任务
    print("\n📋 测试1：创建旅行规划任务...")
    task_input = "帮我规划一个北京三日游"
    response = jarvis.process_input(task_input)
    print(f"任务创建响应: {response[:100]}...")
    
    # 提取任务ID - 从任务列表响应中提取更可靠
    task_id = None
    
    # 先尝试从任务列表获取
    list_response = jarvis.process_input("任务列表")
    print(f"任务列表响应: {list_response[:100]}...")
    
    import re
    # 尝试匹配ID: project_xxxxxxxxxx 格式
    task_pattern = r'ID:\s+(\S+)'
    matches = re.findall(task_pattern, list_response)
    if matches:
        task_id = matches[0]
        print(f"从任务列表提取到任务ID: {task_id}")
    
    if not task_id:
        # 如果任务列表没有，尝试从创建响应中提取
        task_pattern = r'ID:\s+(\S+)'
        match = re.search(task_pattern, response)
        if match:
            task_id = match.group(1)
            print(f"从创建响应提取到任务ID: {task_id}")
        
        if not task_id and "任务创建成功" in response:
            # 查找可能的任务ID
            for line in response.split('\n'):
                if 'project_' in line or 'travel_' in line:
                    parts = line.split()
                    for part in parts:
                        if 'project_' in part or 'travel_' in part:
                            # 清理ID，移除可能的标点符号
                            cleaned_id = part.strip(',."\'`')
                            if cleaned_id.startswith('project_') or cleaned_id.startswith('travel_'):
                                task_id = cleaned_id
                                print(f"从文本行提取任务ID: {task_id}")
                                break
                    if task_id:
                        break
    
    if not task_id:
        print("❌ 无法提取任务ID，测试终止")
        return
    
    # 测试2：查看任务列表
    print("\n📋 测试2：查看任务列表...")
    list_response = jarvis.process_input("任务列表")
    print(f"任务列表: {list_response}")
    
    # 测试3：查看任务详情
    print(f"\n📋 测试3：查看任务详情 {task_id}...")
    detail_response = jarvis.process_input(f"查看任务 {task_id}")
    print(f"任务详情: {detail_response[:200]}...")
    
    # 测试4：开始执行任务
    print(f"\n🚀 测试4：开始执行任务 {task_id}...")
    start_response = jarvis.process_input(f"开始执行 {task_id}")
    print(f"开始执行响应: {start_response}")
    
    # 检查是否包含大脑引擎生成的执行方案
    if "大脑引擎生成的执行方案" in start_response:
        print("✅ 大脑引擎成功参与任务执行")
    else:
        print("⚠️ 大脑引擎可能未被调用或未返回预期结果")
        
    # 测试5：完成第一个步骤
    print(f"\n📝 测试5：完成步骤 {task_id}...")
    complete_response = jarvis.process_input(f"完成步骤 {task_id}")
    print(f"完成步骤响应: {complete_response}")
    
    # 再次查看任务状态
    print("\n📋 最终任务状态检查...")
    final_list = jarvis.process_input("任务列表")
    print(f"最终任务列表: {final_list}")
    
    print("\n🎉 测试完成")

def test_brain_engine_direct():
    """直接测试大脑引擎"""
    print("\n🧠 直接测试大脑引擎...")
    from jarvis.core.model_engine import create_brain_engine
    
    config = {
        'model_provider': 'ollama',
        'model_name': 'deepseek-r1:7b',
        'base_url': 'http://localhost:11434',
        'timeout': 30
    }
    
    try:
        engine = create_brain_engine(config)
        health = engine.health_check()
        status = health.get('overall_status', 'unknown')
        
        if status == 'healthy':
            print("✅ 大脑引擎状态良好")
            
            # 测试任务执行提示
            from jarvis.core.planning_engine.task_definitions import (
                TaskType, create_task
            )
            
            # 创建一个示例任务
            task = create_task(
                TaskType.TRAVEL_PLANNING,
                "北京三日游",
                "规划一个北京的周末旅行"
            )
            
            if task and task.steps:
                step = task.steps[0]
                print(f"\n示例任务步骤: {step.description}")
                print(f"步骤动作: {step.action}")
                
                # 测试生成执行提示
                if hasattr(jarvis, '_generate_execution_prompt'):
                    prompt = jarvis._generate_execution_prompt(task, step)
                    print(f"\n生成的提示长度: {len(prompt)}")
                    print(f"提示前200字符: {prompt[:200]}...")
                    
                    # 测试大脑引擎响应
                    print("\n测试大脑引擎响应...")
                    response = engine.simple_query(prompt, system_prompt="你是一个智能任务执行助手")
                    print(f"响应长度: {len(response)}")
                    print(f"响应前200字符: {response[:200]}...")
        else:
            print(f"⚠️ 大脑引擎状态: {status}")
            
    except Exception as e:
        print(f"❌ 大脑引擎直接测试失败: {e}")

if __name__ == "__main__":
    print("🤖 JARVIS任务执行测试")
    print("=" * 60)
    
    try:
        # 测试任务创建和执行
        test_task_creation_and_execution()
        
        # 注意：这里不调用test_brain_engine_direct，因为需要jarvis实例
        # test_brain_engine_direct()
        
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()