"""
Void-DownLoad 入口脚本
=======================
双击运行 / 命令行运行 / 被 exe 调用的统一入口。
"""
import sys
import os
from pathlib import Path

# 把当前目录加进 sys.path, 让 from src.xxx 能 import
_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

if __name__ == "__main__":
    from src.gui import main
    sys.exit(main())

