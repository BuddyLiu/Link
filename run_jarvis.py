#!/usr/bin/env python3
"""
JARVIS智能体统一启动入口
支持多种启动模式：传统CLI、Web服务、主动运行模式等

说明：这个文件位于项目根目录，所有导入路径已修复
"""

import os
import sys
import argparse
import signal
import time
from typing import Optional

# 修复导入路径问题 - 确保可以导入当前目录和src目录下的模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)  # 添加当前目录（项目根目录）
src_dir = os.path.join(current_dir, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)  # 添加src目录

# 全局变量，用于存储运行中的JARVIS实例，便于优雅退出
_active_jarvis_instance = None


def handle_exit_signal(signum, frame):
    """处理退出信号，优雅关闭JARVIS"""
    print(f"\n📴 收到退出信号 ({signal.Signals(signum).name})，正在关闭JARVIS...")
    
    global _active_jarvis_instance
    if _active_jarvis_instance is not None:
        try:
            if hasattr(_active_jarvis_instance, 'stop'):
                _active_jarvis_instance.stop()
                print("✅ JARVIS已优雅关闭")
            elif hasattr(_active_jarvis_instance, 'shutdown'):
                _active_jarvis_instance.shutdown()
                print("✅ JARVIS已优雅关闭")
        except Exception as e:
            print(f"⚠️  关闭JARVIS时出错: {e}")
    
    sys.exit(0)


def register_signal_handlers():
    """注册信号处理器"""
    signal.signal(signal.SIGINT, handle_exit_signal)
    signal.signal(signal.SIGTERM, handle_exit_signal)
    # 在Unix-like系统上注册SIGQUIT
    if hasattr(signal, 'SIGQUIT'):
        signal.signal(signal.SIGQUIT, handle_exit_signal)


def run_traditional_mode(args) -> int:
    """
    运行传统模式（响应式CLI/Web）

    Args:
        args: 命令行参数

    Returns:
        退出码
    """
    try:
        # 尝试直接导入main.py（位于同一目录）
        from main import main as main_func
        print("⚡ 启动传统响应式模式...")
        print("💡 特点: 被动响应式，用户输入触发，无主动监控")
        print("="*50)

        # 构建参数列表（用 try/finally 确保异常时也能恢复 sys.argv）
        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0], "--mode", args.mode]
        if args.debug:
            sys.argv.append("--debug")
        if args.host is not None:
            sys.argv.extend(["--host", args.host])
        if args.port is not None:
            sys.argv.extend(["--port", str(args.port)])

        try:
            result = main_func()
            return result
        finally:
            sys.argv = original_argv

    except ImportError as e:
        print(f"❌ 无法导入传统主程序: {e}")
        print("💡 请确保main.py存在且可导入")
        return 1
    except Exception as e:
        print(f"❌ 传统模式运行失败: {e}")
        return 1


def run_active_mode(args) -> int:
    """
    运行主动模式（事件驱动，类似iOS RunLoop）

    Args:
        args: 命令行参数

    Returns:
        退出码
    """
    try:
        print("🔄 启动主动运行模式...")
        print("💡 特点:")
        print("   • 持续运行的事件循环（100ms间隔）")
        print("   • 多事件源：用户输入、任务监控、定时器等")
        print("   • 6级优先级调度")
        print("   • 自主学习能力")
        print("   • 主动提醒和监控")
        print("="*50)

        # 尝试导入main_with_active.py
        from main_with_active import main as main_func

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0], "--mode", "active"]
        if args.debug:
            sys.argv.append("--debug")
        if args.active_config:
            sys.argv.extend(["--active-config", args.active_config])

        try:
            result = main_func()
            return result
        finally:
            sys.argv = original_argv

    except ImportError as e:
        print(f"❌ 无法导入主动模式主程序: {e}")
        print("💡 请确保main_with_active.py存在")
        print("   尝试直接运行主动模式实现...")
        return run_direct_active(args)
    except Exception as e:
        print(f"❌ 主动模式运行失败: {e}")
        return 1


def run_direct_active(args) -> int:
    """
    直接运行主动模式（使用active_jarvis_enhanced.py）

    Args:
        args: 命令行参数

    Returns:
        退出码
    """
    try:
        print("🚀 直接启动主动运行模式...")

        # 尝试导入ActiveJARVIS类
        from active_jarvis_enhanced import ActiveJARVIS

        # 创建并启动ActiveJARVIS
        global _active_jarvis_instance
        active_jarvis = ActiveJARVIS()
        _active_jarvis_instance = active_jarvis

        # 启动后台事件循环（非阻塞）
        active_jarvis.start(blocking=False)

        # 运行CLI交互界面
        active_jarvis.run_cli()

        # CLI结束后停止JARVIS
        active_jarvis.stop()
        _active_jarvis_instance = None

        return 0

    except ImportError as e:
        print(f"❌ 无法导入主动模式: {e}")
        print("💡 请确保active_jarvis_enhanced.py存在")
        if _active_jarvis_instance is not None:
            try:
                _active_jarvis_instance.stop()
            except Exception:
                pass
            _active_jarvis_instance = None
        return 1
    except Exception as e:
        print(f"❌ 主动模式运行失败: {e}")
        if _active_jarvis_instance is not None:
            try:
                _active_jarvis_instance.stop()
            except Exception:
                pass
            _active_jarvis_instance = None
        return 1


def run_web_mode(args) -> int:
    """
    运行Web服务模式

    Args:
        args: 命令行参数

    Returns:
        退出码
    """
    try:
        print("🌐 启动Web服务模式...")
        print(f"💡 服务地址: http://{args.host}:{args.port}")

        # 尝试导入main.py
        from main import main as main_func

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0], "--mode", "web", "--host", args.host, "--port", str(args.port)]
        if args.debug:
            sys.argv.append("--debug")

        try:
            result = main_func()
            return result
        finally:
            sys.argv = original_argv

    except ImportError as e:
        print(f"❌ 无法导入Web主程序: {e}")
        print("💡 Web服务模式需要main.py支持")
        return 1
    except Exception as e:
        print(f"❌ Web模式运行失败: {e}")
        return 1


def run_test_mode(args) -> int:
    """
    运行测试模式

    Args:
        args: 命令行参数

    Returns:
        退出码
    """
    try:
        print("🧪 运行测试模式...")

        # 尝试从主程序导入
        from main import main as main_func

        original_argv = sys.argv.copy()
        sys.argv = [sys.argv[0], "--mode", "test"]
        if args.debug:
            sys.argv.append("--debug")

        try:
            result = main_func()
            return result
        finally:
            sys.argv = original_argv

    except ImportError as e:
        print(f"❌ 无法导入测试主程序: {e}")
        print("💡 尝试运行独立的测试套件...")
        return run_test_suite(args)
    except Exception as e:
        print(f"❌ 测试模式运行失败: {e}")
        return 1


def run_test_suite(args) -> int:
    """
    运行独立的测试套件

    Args:
        args: 命令行参数

    Returns:
        退出码
    """
    try:
        all_success = True
        any_ran = False

        # 尝试导入测试模块
        test_suites = [
            ("test.test_active_jarvis", "主动模式测试套件"),
            ("test.test_planning_engine", "规划引擎测试套件"),
            ("test.test_task_execution", "任务执行测试套件"),
        ]

        for module_name, label in test_suites:
            try:
                import importlib
                mod = importlib.import_module(module_name)
                if hasattr(mod, 'run_all_tests'):
                    print(f"📋 运行{label}...")
                    success = mod.run_all_tests()
                    all_success = all_success and success
                    any_ran = True
                else:
                    print(f"⚠️  {module_name} 中没有 run_all_tests 函数，跳过")
            except ImportError:
                print(f"⚠️  {module_name} 未找到，跳过")
            except Exception as e:
                print(f"❌ 运行{label}时出错: {e}")
                all_success = False
                any_ran = True

        if any_ran:
            return 0 if all_success else 1

        print("❌ 未找到测试套件")
        print("💡 可用的测试文件:")
        print("   - test/test_active_jarvis.py")
        print("   - test/test_planning_engine.py")
        print("   - test/test_task_execution.py")
        return 1
        
    except Exception as e:
        print(f"❌ 测试套件运行失败: {e}")
        return 1


def run_auto_execution_demo(args) -> int:
    """
    运行自动执行演示

    Args:
        args: 命令行参数

    Returns:
        退出码
    """
    try:
        print("🎬 运行自动执行演示...")

        # 尝试导入演示模块（demo_auto_execution.py 中没有 main()，应使用 demo_auto_task_execution）
        from demo_auto_execution import demo_auto_task_execution as main_func
        return main_func()

    except ImportError as e:
        print(f"❌ 无法导入自动执行演示: {e}")
        print("💡 请确保demo_auto_execution.py存在")
        return 1
    except Exception as e:
        print(f"❌ 自动执行演示运行失败: {e}")
        return 1


def print_help() -> None:
    """打印详细的帮助信息"""
    help_text = """
JARVIS智能体统一启动器

使用方法:
  python3 run_jarvis.py [模式] [选项]

可用模式:
  active       - 主动运行模式（默认，事件驱动，类似iOS RunLoop）
  cli          - 传统命令行模式（响应式，无主动监控）
  web          - Web服务模式
  test         - 运行测试套件
  demo         - 运行自动执行演示

常用选项:
  --debug              启用调试模式
  --host HOST          Web服务主机地址（默认: 127.0.0.1）
  --port PORT          Web服务端口（默认: 8030）
  --active-config FILE 主动模式配置文件路径
  --help              显示此帮助信息

示例:
  # 启动主动运行模式（默认）
  python3 run_jarvis.py
  
  # 启动传统CLI模式
  python3 run_jarvis.py cli
  
  # 启动Web服务
  python3 run_jarvis.py web --host 127.0.0.1 --port 8030
  
  # 运行测试套件
  python3 run_jarvis.py test
  
  # 运行自动执行演示
  python3 run_jarvis.py demo
  
  # 启动自定义Web服务（指定端口）
  python3 run_jarvis.py web --port 9000

高级用法:
  # 使用自定义配置文件启动主动模式
  python3 run_jarvis.py active --active-config config/active_config.json
  
  # 调试模式运行
  python3 run_jarvis.py --debug

版本信息:
  • 主动运行模式: 事件驱动架构，支持多优先级调度
  • 传统模式: 响应式交互，支持复杂任务规划
  • Web模式: 提供HTTP API和WebSocket接口
  • 测试模式: 运行完整测试套件
"""
    print(help_text)


def parse_arguments():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="JARVIS智能体统一启动器",
        add_help=False  # 自定义帮助处理
    )
    
    # 模式参数（位置参数）
    parser.add_argument(
        "mode",
        nargs="?",
        choices=["active", "cli", "web", "test", "demo"],
        default="active",
        help="启动模式"
    )
    
    # 通用选项
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web服务主机地址"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8030,
        help="Web服务端口"
    )
    parser.add_argument(
        "--active-config",
        type=str,
        default="",
        help="主动运行模式配置文件路径"
    )
    parser.add_argument(
        "--help",
        action="store_true",
        help="显示帮助信息"
    )
    
    return parser.parse_args()


def main() -> int:
    """主函数"""
    # 注册信号处理器
    register_signal_handlers()
    
    # 解析参数
    args = parse_arguments()
    
    # 显示帮助信息
    if args.help:
        print_help()
        return 0
    
    # 显示启动横幅
    print("\n" + "="*60)
    print("JARVIS智能体 - 统一启动入口")
    print("🎯 版本: 3.0 | 架构: 模块化 | 阶段: 第三阶段")
    print("="*60)
    
    # 根据模式选择启动函数
    mode_handlers = {
        "active": run_active_mode,
        "cli": run_traditional_mode,
        "web": run_web_mode,
        "test": run_test_mode,
        "demo": run_auto_execution_demo,
    }
    
    handler = mode_handlers.get(args.mode, run_active_mode)
    
    # 执行启动
    try:
        return_code = handler(args)
        
        if return_code == 0:
            print("\n✅ JARVIS正常退出")
        else:
            print(f"\n❌ JARVIS异常退出 (代码: {return_code})")
        
        return return_code
        
    except KeyboardInterrupt:
        print("\n\n📴 用户中断，正在关闭JARVIS...")
        return 0
    except Exception as e:
        print(f"\n❌ 启动过程中发生未预期错误: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())