"""JSONL → Excel 单文件转换器。

输入：任意一份逐行 JSON（每行一个对象）
输出：一张 `emails` 工作表的 .xlsx；列 = 输入中所有键的首次出现顺序

注意：Excel 单元格硬上限是 32767 字符，超长字符串会被截断并以 ...[TRUNC] 结尾。
"""

from __future__ import annotations

import argparse
import json
from collections import OrderedDict
from pathlib import Path

from project_dirs import DATA_DIR, EXCEL_DIR, ensure_dir

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = DATA_DIR / "cleaned_emails.jsonl"
DEFAULT_OUTPUT_DIR = EXCEL_DIR

_EXCEL_MAX_CELL = 32767
_EXCEL_TRUNC_TAIL = "...[TRUNC]"


def derive_output(input_path: Path) -> Path:
    """没传 --output 时，按输入文件名同名生成 excel/<stem>.xlsx。"""
    return DEFAULT_OUTPUT_DIR / f"{input_path.stem}.xlsx"


def write_excel(jsonl_path: Path, xlsx_path: Path) -> None:
    """把 jsonl_path 转成 xlsx_path。两次扫描：先收表头，再流式写行。"""
    try:
        from openpyxl import Workbook
        from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    except ImportError as exc:  # pragma: no cover
        raise SystemExit(
            "需要 openpyxl 才能输出 Excel；请先执行：pip install openpyxl"
        ) from exc

    if not jsonl_path.exists():
        raise SystemExit(f"找不到输入 JSONL：{jsonl_path}")

    # 1) 先扫一遍收集所有键的「首次出现顺序」作为表头
    headers: "OrderedDict[str, None]" = OrderedDict()
    with jsonl_path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            for k in json.loads(line):
                headers.setdefault(k, None)
    cols = list(headers)

    # 2) 流式写：write_only 模式不在内存中保存整张表，适合 2~5 万行
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("emails")
    ws.append(cols)

    n_rows = n_truncated = 0
    with jsonl_path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            row = []
            for k in cols:
                v = obj.get(k, "")
                if isinstance(v, str):
                    v = ILLEGAL_CHARACTERS_RE.sub("", v)
                    if len(v) > _EXCEL_MAX_CELL:
                        keep = _EXCEL_MAX_CELL - len(_EXCEL_TRUNC_TAIL)
                        v = v[:keep] + _EXCEL_TRUNC_TAIL
                        n_truncated += 1
                row.append(v)
            ws.append(row)
            n_rows += 1

    ensure_dir(xlsx_path.parent)
    try:
        wb.save(xlsx_path)
    except PermissionError as exc:
        raise SystemExit(
            f"无法写入 {xlsx_path}：{exc}。"
            f"请确认该文件未被 Excel 或预览程序占用，关掉后重试。"
        ) from exc

    note = f"（{n_truncated} 个超长单元格已截断）" if n_truncated else ""
    try:
        rel = xlsx_path.relative_to(ROOT)
    except ValueError:
        rel = xlsx_path
    print(f"Excel ({n_rows} 行 × {len(cols)} 列) → {rel}{note}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把 JSONL 转成 Excel（每行一条邮件，列 = JSONL 字段）。",
    )
    parser.add_argument(
        "--input", "-i", default=str(DEFAULT_INPUT),
        help=f"输入 JSONL 路径（默认：{DEFAULT_INPUT.relative_to(ROOT)}）",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help=f"输出 XLSX 路径（不传则取 {DEFAULT_OUTPUT_DIR.relative_to(ROOT)}/<输入同名>.xlsx）",
    )
    args = parser.parse_args()

    inp = Path(args.input)
    out = Path(args.output) if args.output else derive_output(inp)
    ensure_dir(EXCEL_DIR)
    write_excel(inp, out)


if __name__ == "__main__":
    main()
