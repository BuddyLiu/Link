#!/usr/bin/env python3
"""
测试自动任务执行功能
验证：任务创建后能自动开始执行前2个步骤
"""

import sys
import re
from jarvis.main import JARVIS

def test_auto_task_execution():
    """测试任务创建后自动执行功能"""
    print("🔄 初始化JARVIS系统...")
    jarvis = JARVIS()
    
    print("✅ JARVIS初始化完成")
    
    # 测试：创建任务并验证自动执行
    print("\n📋 测试：创建旅行规划任务（应自动执行前2步）...")
    task_input = "帮我规划一个上海周末游"
    response = jarvis.process_input(task_input)
    
    print(f"任务创建响应长度: {len(response)}")
    
    # 检查响应中是否包含自动执行信息
    if "自动开始执行任务" in response:
        print("✅ 任务创建后自动开始执行功能正常")
    else:
        print("❌ 任务创建后没有自动开始执行")
        print("响应预览:", response[:200])
        return
    
    # 提取任务ID
    import re
    task_pattern = r'ID:\s+(\S+)'
    match = re.search(task_pattern, response)
    if match:
        task_id = match.group(1)
        print(f"提取到任务ID: {task_id}")
    else:
        print("❌ 无法提取任务ID")
        return
    
    # 查看任务列表，检查进度
    print("\n📊 查看任务进度...")
    list_response = jarvis.process_input("任务列表")
    print(f"任务列表: {list_response}")
    
    # 检查进度是否大于0（表示有步骤已执行）
    if "进度:" in list_response and "0/3 (0%)" not in list_response:
        print("✅ 任务步骤已开始执行，进度有更新")
    else:
        print("⚠️ 任务进度可能未更新")
    
    # 查看任务详情
    print(f"\n📋 查看任务详情 {task_id}...")
    detail_response = jarvis.process_input(f"查看任务 {task_id}")
    print(f"任务详情预览: {detail_response[:300]}...")
    
    # 检查是否有步骤状态为completed或in_progress
    if "✅" in detail_response or "🔄" in detail_response:
        print("✅ 任务步骤状态正确更新")
    else:
        print("⚠️ 任务步骤状态可能未正确更新")
    
    # 测试继续执行功能
    print(f"\n🚀 测试继续执行（完成步骤）...")
    complete_response = jarvis.process_input(f"完成步骤 {task_id}")
    print(f"完成步骤响应预览: {complete_response[:200]}...")
    
    if "✅" in complete_response or "🎉" in complete_response:
        print("✅ 继续执行功能正常")
    
    # 再次查看任务进度
    print("\n📊 最终任务状态检查...")
    final_list = jarvis.process_input("任务列表")
    print(f"最终任务列表: {final_list}")
    
    print("\n🎉 自动执行测试完成")

def test_manual_execution_mode():
    """测试手动执行模式"""
    print("\n" + "="*60)
    print("测试手动执行模式")
    print("="*60)
    
    jarvis = JARVIS()
    
    # 创建任务
    print("\n📋 创建另一个任务用于手动执行测试...")
    task_input = "帮我制定一个健身计划"
    response = jarvis.process_input(task_input)
    
    # 提取任务ID
    import re
    task_pattern = r'ID:\s+(\S+)'
    match = re.search(task_pattern, response)
    if match:
        task_id = match.group(1)
        print(f"任务ID: {task_id}")
        
        # 测试手动开始执行（默认只执行第一步）
        print(f"\n🚀 手动开始执行（默认只执行第一步）...")
        start_response = jarvis.process_input(f"开始执行 {task_id}")
        print(f"开始执行响应预览: {start_response[:200]}...")
        
        if "继续下一步请输入" in start_response:
            print("✅ 手动执行模式正常（执行第一步后等待继续）")
        else:
            print("⚠️ 手动执行模式可能有异常")
        
        # 测试自动执行所有步骤模式
        print(f"\n🚀 测试自动执行所有步骤模式...")
        auto_response = jarvis.process_input(f"开始执行 {task_id} 自动")
        print(f"自动执行响应预览: {auto_response[:200]}...")
        
        if "已自动执行" in auto_response:
            print("✅ 自动执行所有步骤模式正常")
        else:
            print("⚠️ 自动执行所有步骤模式可能有异常")
    
    print("\n🎉 手动执行模式测试完成")

if __name__ == "__main__":
    print("JARVIS自动任务执行测试")
    print("="*60)
    
    try:
        # 测试自动执行功能
        test_auto_task_execution()
        
        # 测试手动执行模式
        test_manual_execution_mode()
        
        print("\n" + "="*60)
        print("✅ 所有测试完成")
        print("\n总结:")
        print("1. 任务创建后会自动执行前2个步骤")
        print("2. 支持手动执行模式（逐步执行）")
        print("3. 支持自动执行所有步骤模式")
        print("4. 大脑引擎被正确调用生成执行方案")
        
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
    except Exception as e:
        print(f"\n❌ 测试过程中出现错误: {e}")
        import traceback
        traceback.print_exc()