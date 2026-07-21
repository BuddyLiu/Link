#!/usr/bin/env python3
"""快速验证手动执行模式"""

from link.main import LINK

def quick_test():
    """快速测试手动执行模式"""
    print("快速验证手动执行模式")
    print("-" * 40)
    
    # 初始化LINK
    link = LINK()
    
    # 1. 创建任务
    print("1. 创建任务: '帮我测试手动执行'")
    response = link.process_input("帮我测试手动执行")
    print(f"响应前150字符: {response[:150]}")
    
    # 检查是否有"自动开始执行"字样
    if "自动开始执行" in response:
        print("❌ 失败: 任务创建后自动开始执行了")
        return False
    elif "开始执行" in response:
        print("✅ 正确: 任务创建后等待手动执行")
    else:
        print("⚠️  注意: 响应格式可能有变化")
        print(f"完整响应: {response}")
    
    # 2. 检查任务列表
    print("\n2. 检查任务列表:")
    list_response = link.process_input("任务列表")
    print(list_response)
    
    # 3. 尝试提取任务ID
    import re
    task_id = None
    task_pattern = r'project_\d{8}_\d{6}'
    matches = re.findall(task_pattern, list_response)
    
    if matches:
        task_id = matches[0]
        print(f"\n提取到的任务ID: {task_id}")
        
        # 4. 手动开始执行
        print(f"\n4. 手动开始执行: '开始执行 {task_id}'")
        start_response = link.process_input(f"开始执行 {task_id}")
        print(f"开始执行响应: {start_response[:200]}")
        
        if "继续下一步请输入" in start_response or "步骤1" in start_response:
            print("✅ 正确: 手动执行第一步成功")
            return True
        else:
            print("❌ 失败: 手动执行第一步未按预期工作")
            return False
    else:
        print("❌ 无法提取任务ID")
        return False

if __name__ == "__main__":
    success = quick_test()
    if success:
        print("\n🎉 手动执行模式验证成功！")
        print("📌 现在创建任务后需要手动输入'开始执行 <ID>'来启动")
    else:
        print("\n❌ 手动执行模式验证失败")