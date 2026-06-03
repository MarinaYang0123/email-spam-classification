"""兼容入口：混合分类已迁至 schemes/scheme1_semantic5/classify.py"""

from __future__ import annotations

import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "schemes" / "scheme1_semantic5" / "classify.py"

if __name__ == "__main__":
    print("提示：hybrid_classify 已迁移至 schemes/scheme1_semantic5/classify.py")
    sys.argv[0] = str(TARGET)
    runpy.run_path(str(TARGET), run_name="__main__")
