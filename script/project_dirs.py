"""被 .gitignore 的产出目录；脚本写入前应 ensure。"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
TFIDF_DIR = DATA_DIR / "tfidf"
REPORTS_DIR = ROOT / "reports"
EXCEL_DIR = ROOT / "excel"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
