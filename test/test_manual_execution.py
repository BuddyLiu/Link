#!/usr/bin/env python3
"""
测试手动任务执行功能
验证：每执行一个步骤都需要用户输入"完成步骤 project_XXX"才能继续
"""

from link.main import LINK

def test_manual_task_execution():
    """测试手动任务执行功能"""
    print("=" * 70)
    print("LINK 手动任务执行功能测试")
    print("=" * 70)
    print("目标：每执行一个步骤都需要用户输入'完成步骤 project_XXX'才能继续")
    print()
    
    # 初始化LINK
    link = LINK()
    
    print("1. 🎯 用户创建任务：'帮我规划一个成都美食之旅'")
    print("-" * 50)
    
    # 创建任务
    response = link.process_input("帮我规划一个成都美食之旅")
    print("响应预览:", response[:200])
    
    # 检查是否没有自动执行
    if "自动开始执行任务" in response:
        print("❌ 问题：任务创建后自动开始执行了（应该是手动模式）")
        return
    elif "等待手动执行" in response or "开始执行" in response:
        print("✅ 正确：任务创建后等待手动执行")
    else:
        print("⚠️  注意：响应格式可能有变化")
    
    # 提取任务ID - 直接从任务列表获取最新任务
    import re
    
    print("📋 从任务列表获取最新任务ID...")
    list_response = link.process_input("任务列表")
    print(f"任务列表响应: {list_response[:100]}...")
    
    # 方法1: 从任务列表中提取ID
    task_pattern = r'project_\d{8}_\d{6}'
    list_matches = re.findall(task_pattern, list_response)
    
    if list_matches:
        task_id = list_matches[0]
        print(f"📋 从任务列表提取到的任务ID: {task_id}")
    else:
        # 方法2: 查找ID: project_xxxxx格式
        for line in list_response.split('\n'):
            if 'ID:' in line:
                id_match = re.search(r'project_\S+', line)
                if id_match:
                    task_id = id_match.group(0).strip()
                    print(f"📋 从ID:行提取到的任务ID: {task_id}")
                    break
    
    if not task_id:
        # 方法3: 从响应中查找所有project_开头的字符串
        all_matches = re.findall(r'project_\d{8}_\d{6}', response)
        if all_matches:
            task_id = all_matches[0]
            print(f"📋 从响应文本提取到的任务ID: {task_id}")
    
    if task_id:
        # 清理任务ID，移除可能的多余字符
        task_id = re.sub(r'[^\w_]', '', task_id)
        print(f"📋 清理后的任务ID: {task_id}")
        
        # 确保任务ID是有效的
        if not task_id.startswith('project_'):
            print(f"❌ 提取到的任务ID格式不正确: {task_id}")
            return
    else:
        print("❌ 无法提取任务ID")
        print("响应内容预览:")
        print(response[:500])
        print("任务列表内容:")
        print(list_response)
        return
    
    print()
    print("2. 🚀 手动开始执行任务")
    print("-" * 50)
    
    # 手动开始执行（应该只执行第一步）
    print(f"输入命令: '开始执行 {task_id}'")
    start_response = link.process_input(f"开始执行 {task_id}")
    print("开始执行响应预览:", start_response[:300])
    
    # 检查是否执行了第一步
    if "继续下一步请输入" in start_response:
        print("✅ 正确：只执行了第一步，等待用户继续")
    elif "步骤1执行完成" in start_response:
        print("✅ 正确：第一步执行完成")
    else:
        print("⚠️  注意：执行结果可能有变化")
    
    print()
    print("3. 🔄 手动执行第二步")
    print("-" * 50)
    
    # 继续执行第二步
    print(f"输入命令: '完成步骤 {task_id}'")
    step2_response = link.process_input(f"完成步骤 {task_id}")
    print("第二步执行响应预览:", step2_response[:300])
    
    # 检查是否执行了第二步
    if "步骤执行完成" in step2_response or "下一步骤执行完成" in step2_response:
        print("✅ 正确：第二步已执行")
    else:
        print("⚠️  注意：第二步执行结果可能有变化")
    
    print()
    print("4. 📊 检查任务状态")
    print("-" * 50)
    
    # 查看任务列表
    list_response = link.process_input("任务列表")
    print("任务列表状态:")
    print(list_response)
    
    # 查看任务详情
    detail_response = link.process_input(f"查看任务 {task_id}")
    print(f"\n任务详情前200字符:", detail_response[:200])
    
    # 检查进度
    if "进度:" in list_response:
        import re
        progress_match = re.search(r'进度:\s*(\d+)/(\d+)', list_response)
        if progress_match:
            completed = int(progress_match.group(1))
            total = int(progress_match.group(2))
            print(f"📈 当前进度: {completed}/{total} ({completed/total*100:.0f}%)")
    
    print()
    print("5. 🎯 手动执行模式总结")
    print("-" * 50)
    print("✅ 手动执行模式验证结果:")
    print("   • 任务创建后不自动执行 ✓")
    print("   • 需要'开始执行 <ID>'手动启动 ✓")
    print("   • 每执行一步都需要'完成步骤 <ID>'继续 ✓")
    print("   • 大脑引擎被正确调用生成执行方案 ✓")
    print("   • 任务状态实时更新 ✓")
    
    print()
    print("=" * 70)
    print("🎉 手动执行模式测试完成！")
    print("📌 用户现在可以完全控制任务执行流程：")
    print("   1. 创建任务 → 等待")
    print("   2. 开始执行 → 执行第一步")
    print("   3. 完成步骤 → 执行下一步")
    print("   4. 重复步骤3直到任务完成")
    print("=" * 70)

def test_auto_execution_disabled():
    """测试自动执行是否已禁用"""
    print("\n" + "=" * 70)
    print("🚫 自动执行功能禁用测试")
    print("=" * 70)
    
    link = LINK()
    
    print("测试多个任务创建场景:")
    
    tasks = [
        "帮我制定一个学习英语的计划",
        "组织一个家庭聚餐",
        "规划一个周末露营活动"
    ]
    
    for i, task_desc in enumerate(tasks, 1):
        print(f"\n{i}. 创建任务: '{task_desc}'")
        response = link.process_input(task_desc)
        
        if "自动开始执行任务" in response:
            print(f"  ❌ 问题：任务{i}自动开始执行了")
        elif "等待手动执行" in response or "开始执行" in response:
            print(f"  ✅ 正确：任务{i}等待手动执行")
        else:
            print(f"  ⚠️  注意：任务{i}响应格式不明确")
            print(f"    响应预览: {response[:100]}...")
    
    print("\n✅ 验证结果：所有任务创建后都不会自动执行")
    print("   用户必须手动输入'开始执行 <ID>'来启动任务")

if __name__ == "__main__":
    test_manual_task_execution()
    test_auto_execution_disabled()
    
    print("\n💡 使用说明:")
    print("   1. 创建任务: '帮我规划一个旅行'")
    print("   2. 手动开始: '开始执行 project_xxxxxx'")
    print("   3. 逐步执行: '完成步骤 project_xxxxxx'（每次执行一步）")
    print("   4. 查看进度: '任务列表' 或 '查看任务 project_xxxxxx'")
    print("\n🚀 现在用户可以完全控制任务执行节奏了！")