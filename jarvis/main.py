#!/usr/bin/env python3
"""
JARVIS智能体基座主入口文件
"""

import sys
import argparse
from typing import Optional

# 修复导入路径问题
try:
    from config.settings import settings
    from utils.logger import logger, setup_logger
    from tools import tool_manager
except ImportError:
    from .config.settings import settings
    from .utils.logger import logger, setup_logger
    from .tools import tool_manager


class JARVIS:
    """JARVIS智能体主类"""
    
    def __init__(self):
        """初始化JARVIS智能体"""
        self.logger = logger.getChild("jarvis")
        self.settings = settings
        self.tool_manager = tool_manager
        
        # 初始化组件
        self._initialize_components()
        
        self.logger.info("JARVIS智能体初始化完成")
    
    def _initialize_components(self):
        """初始化所有组件"""
        self.logger.info("开始初始化JARVIS组件...")
        
        # 初始化工具
        self._initialize_tools()
        
        # 初始化记忆（第二阶段实现）
        # self._initialize_memory()
        
        # 初始化模型（将在本地模型部署后实现）
        # self._initialize_model()
        
        self.logger.info("JARVIS组件初始化完成")
    
    def _initialize_tools(self):
        """初始化系统工具"""
        try:
            # 修复导入路径问题
            try:
                from tools.system_tools import initialize_system_tools
            except ImportError:
                from .tools.system_tools import initialize_system_tools
            
            initialize_system_tools(self.tool_manager)
            tool_count = len(self.tool_manager.get_tool_names())
            self.logger.info(f"已初始化 {tool_count} 个系统工具")
        except Exception as e:
            self.logger.error(f"工具初始化失败: {str(e)}")
            self.logger.warning("继续运行，但部分功能可能不可用")
    
    def process_input(self, input_text: str) -> str:
        """
        处理用户输入
        
        Args:
            input_text: 用户输入文本
            
        Returns:
            str: 处理结果
        """
        self.logger.info(f"处理用户输入: {input_text}")
        
        # 第一阶段简单实现：直接调用工具
        response = self._simple_response(input_text)
        
        self.logger.info(f"生成响应: {response[:50]}...")
        return response
    
    def _simple_response(self, input_text: str) -> str:
        """
        简单响应逻辑（第一阶段）
        
        Args:
            input_text: 用户输入文本
            
        Returns:
            str: 响应文本
        """
        # 简单的关键字匹配
        input_lower = input_text.lower()
        
        if "时间" in input_lower or "几点了" in input_lower:
            try:
                result = self.tool_manager.execute_tool("get_time")
                return f"当前时间是：{result}"
            except Exception as e:
                self.logger.error(f"获取时间失败: {str(e)}")
                return "抱歉，我无法获取当前时间。"
        
        elif "天气" in input_lower:
            # 暂时不支持天气查询
            return "天气查询功能将在后续版本中实现。"
        
        elif "帮助" in input_lower or "help" in input_lower:
            return self._get_help_text()
        
        else:
            return f"我已经收到你的消息：'{input_text}'。第一阶段功能有限，后续版本将提供更智能的交互。"
    
    def _get_help_text(self) -> str:
        """获取帮助文本"""
        tool_names = self.tool_manager.get_tool_names()
        
        help_text = "JARVIS智能体第一阶段可用功能：\n\n"
        help_text += "1. 基础功能：\n"
        help_text += "   - 询问时间：可以说'现在几点了'或'告诉我时间'\n"
        help_text += "   - 获取帮助：可以说'帮助'或'help'\n\n"
        
        if tool_names:
            help_text += "2. 可用工具：\n"
            for tool_name in tool_names:
                help_text += f"   - {tool_name}\n"
        
        help_text += "\n"
        help_text += "后续版本将支持：\n"
        help_text += "1. 语音交互\n"
        help_text += "2. 智能家居控制\n"
        help_text += "3. 复杂任务规划\n"
        help_text += "4. 长期记忆\n"
        
        return help_text
    
    def run_cli(self):
        """运行命令行交互界面"""
        print("\n" + "="*50)
        print("JARVIS智能体 v1.0 - 第一阶段")
        print("="*50)
        print("输入 '退出' 或 'exit' 结束程序")
        print("输入 '帮助' 或 'help' 查看可用功能")
        print("="*50 + "\n")
        
        while True:
            try:
                user_input = input(">>> ").strip()
                
                if not user_input:
                    continue
                
                if user_input.lower() in ["退出", "exit", "quit"]:
                    print("再见！")
                    break
                
                if user_input.lower() in ["帮助", "help"]:
                    print(self._get_help_text())
                    continue
                
                # 处理用户输入
                response = self.process_input(user_input)
                print(f"JARVIS: {response}\n")
                
            except KeyboardInterrupt:
                print("\n\n程序已中断")
                break
            except Exception as e:
                self.logger.error(f"处理输入时出错: {str(e)}")
                print(f"抱歉，处理时出现错误: {str(e)}\n")
    
    def run_web(self, host: str = "127.0.0.1", port: int = 8000):
        """运行Web服务（第二阶段实现）"""
        self.logger.info(f"Web服务将在 {host}:{port} 启动")
        return "Web服务将在后续版本中实现"


def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="JARVIS智能体基座")
    parser.add_argument(
        "--mode",
        choices=["cli", "web", "test"],
        default="cli",
        help="运行模式: cli(命令行), web(Web服务), test(测试)"
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Web服务主机地址"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Web服务端口"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式"
    )
    
    args = parser.parse_args()
    
    # 设置调试模式
    if args.debug:
        settings.system.debug_mode = True
        logger.setLevel("DEBUG")
        logger.debug("调试模式已启用")
    
    try:
        # 创建JARVIS实例
        jarvis = JARVIS()
        
        # 根据模式运行
        if args.mode == "cli":
            jarvis.run_cli()
        elif args.mode == "web":
            jarvis.run_web(args.host, args.port)
        elif args.mode == "test":
            # 运行简单测试
            test_results = run_tests(jarvis)
            print(f"测试完成: {test_results}")
        
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
    except Exception as e:
        logger.error(f"程序运行出错: {str(e)}", exc_info=True)
        return 1
    
    return 0


def run_tests(jarvis: JARVIS) -> dict:
    """运行简单测试"""
    logger.info("开始运行测试...")
    
    test_results = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "details": []
    }
    
    # 测试1：获取时间
    test_results["total"] += 1
    try:
        response = jarvis.process_input("现在几点了")
        logger.info(f"测试1通过: {response[:50]}...")
        test_results["passed"] += 1
        test_results["details"].append("测试1: 获取时间 - 通过")
    except Exception as e:
        logger.error(f"测试1失败: {str(e)}")
        test_results["failed"] += 1
        test_results["details"].append(f"测试1: 获取时间 - 失败: {str(e)}")
    
    # 测试2：帮助功能
    test_results["total"] += 1
    try:
        response = jarvis.process_input("帮助")
        if response and len(response) > 0:
            logger.info("测试2通过: 帮助功能正常")
            test_results["passed"] += 1
            test_results["details"].append("测试2: 帮助功能 - 通过")
        else:
            logger.error("测试2失败: 帮助功能返回空响应")
            test_results["failed"] += 1
            test_results["details"].append("测试2: 帮助功能 - 失败: 返回空响应")
    except Exception as e:
        logger.error(f"测试2失败: {str(e)}")
        test_results["failed"] += 1
        test_results["details"].append(f"测试2: 帮助功能 - 失败: {str(e)}")
    
    # 测试3：工具注册
    test_results["total"] += 1
    try:
        tool_count = len(jarvis.tool_manager.get_tool_names())
        if tool_count > 0:
            logger.info(f"测试3通过: 注册了 {tool_count} 个工具")
            test_results["passed"] += 1
            test_results["details"].append(f"测试3: 工具注册 - 通过 ({tool_count}个工具)")
        else:
            logger.error("测试3失败: 未注册任何工具")
            test_results["failed"] += 1
            test_results["details"].append("测试3: 工具注册 - 失败: 未注册工具")
    except Exception as e:
        logger.error(f"测试3失败: {str(e)}")
        test_results["failed"] += 1
        test_results["details"].append(f"测试3: 工具注册 - 失败: {str(e)}")
    
    logger.info(f"测试完成: {test_results['passed']}/{test_results['total']} 通过")
    return test_results


if __name__ == "__main__":
    sys.exit(main())