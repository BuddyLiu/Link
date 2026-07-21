#!/usr/bin/env python3
"""
LINK智能体启动脚本 - 增强版
支持主动运行模式（类似iOS RunLoop的主动智能体系统）
"""

import os
import sys
import argparse

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def run_traditional_mode(args):
    """运行传统模式"""
    try:
        from link.main import main
        # 构建参数列表
        sys.argv = [sys.argv[0], "--mode", args.mode]
        if args.debug:
            sys.argv.append("--debug")
        if args.host:
            sys.argv.extend(["--host", args.host])
        if args.port:
            sys.argv.extend(["--port", str(args.port)])
        
        return main()
    except ImportError:
        print("❌ 无法导入传统LINK主程序")
        print("💡 请确保link/main.py存在")
        return 1

def run_active_mode(args):
    """运行主动模式"""
    try:
        # 尝试从增强版主程序导入
        from link.main_with_active import main
        # 构建参数列表
        sys.argv = [sys.argv[0], "--mode", "active"]
        if args.debug:
            sys.argv.append("--debug")
        if args.active_config:
            sys.argv.extend(["--active-config", args.active_config])
        
        return main()
    except ImportError:
        print("❌ 无法导入主动模式主程序")
        print("💡 请确保link/main_with_active.py存在")
        print("   或者尝试直接运行主动模式: python link/active_link_enhanced.py")
        return 1

def run_direct_active():
    """直接运行主动模式"""
    try:
        from link.active_link_enhanced import ActiveLINK
        print("🚀 直接启动主动运行模式...")
        active_link = ActiveLINK()
        active_link.start(blocking=False)
        active_link.run_cli()
        active_link.stop()
        return 0
    except ImportError as e:
        print(f"❌ 无法导入主动模式: {e}")
        print("💡 请确保link/active_link_enhanced.py存在")
        return 1
    except Exception as e:
        print(f"❌ 主动模式运行失败: {e}")
        return 1

def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="LINK智能体启动器")
    parser.add_argument(
        "--mode",
        choices=["cli", "web", "test", "active"],
        default="active",  # 默认改为主动模式
        help="运行模式: cli(传统命令行), web(Web服务), test(测试), active(主动运行模式)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web服务主机地址（仅web模式）"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Web服务端口（仅web模式）"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    parser.add_argument(
        "--active-config",
        type=str,
        default="",
        help="主动运行模式配置文件路径（仅active模式）"
    )
    parser.add_argument(
        "--direct",
        action="store_true",
        help="直接运行主动模式（使用active_link_enhanced.py，不经过主程序）"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="运行主动模式测试套件"
    )
    
    args = parser.parse_args()
    
    print("LINK智能体启动器")
    print("="*50)
    print("📱 版本: 主动运行模式增强版")
    print("🎯 功能: 事件驱动架构，类似iOS RunLoop")
    print("="*50)
    
    if args.test:
        print("🧪 运行主动模式测试套件...")
        try:
            from test_active_link import run_all_tests
            success = run_all_tests()
            return 0 if success else 1
        except ImportError:
            print("❌ 无法导入测试套件")
            print("💡 请确保test_active_link.py存在")
            return 1
    
    if args.direct:
        return run_direct_active()
    
    if args.mode == "active":
        print("🔄 启动主动运行模式...")
        print("💡 特点:")
        print("   • 持续运行的事件循环（100ms间隔）")
        print("   • 多事件源：用户输入、任务监控、定时器等")
        print("   • 6级优先级调度")
        print("   • 自主学习能力")
        print("   • 主动提醒和监控")
        print("="*50)
        return run_active_mode(args)
    else:
        print(f"⚡ 启动{args.mode}模式（传统响应式）...")
        print("💡 注意：传统模式为被动响应式，无主动监控功能")
        print("="*50)
        return run_traditional_mode(args)

if __name__ == "__main__":
    sys.exit(main())