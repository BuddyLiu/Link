#!/usr/bin/env python3
"""
JARVIS智能体启动脚本
解决导入路径问题
"""

import os
import sys

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入并运行主程序
from jarvis.main import main

if __name__ == "__main__":
    sys.exit(main())