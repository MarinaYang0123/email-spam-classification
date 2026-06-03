"""字段拼接：把每条记录的 subject / content / doccontent 拼成单个 text 字段。

输入  : data/deep_cleaned_email.jsonl  （由 deep_process.py 生成的深度清洗版）
输出  : data/concat_email.jsonl        （record_id + 拼接后的 text）

设计要点：
  * URL 在深度清洗阶段已被替换成 [URL] 占位符，所以这里不需要单独的 url 字段，
    直接对 TEXT_FIELDS 里的几个字段做顺序拼接即可。
  * 拼接时跳过空串/空白字段，避免出现 "标题  正文" 这种多余分隔。
  * 默认 --sep 用单空格；后续 jieba 会按空白切分，单空格已经足够。
  * 默认只保留 record_id + text 两个字段，让产物足够薄；
    需要保留原字段做对照时用 --keep-fields。

用法：
  python script/concat_fields.py
  python script/concat_fields.py --sep " | " --keep-fields
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from project_dirs import DATA_DIR, ensure_dir

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = DATA_DIR / "deep_cleaned_email.jsonl"
OUTPUT_FILE = DATA_DIR / "concat_email.jsonl"

# 顺序敏感：主题在前更符合人眼/模型的阅读顺序，也方便后续按位置加权
TEXT_FIELDS = ("subject", "content", "doccontent", "fromname")


def concat_record(obj: dict, fields: tuple[str, ...], sep: str) -> str:
    """按 fields 顺序取值，跳过空串/非字符串，用 sep 连接。"""
    parts: list[str] = []
    for f in fields:
        v = obj.get(f)
        if isinstance(v, str):
            v = v.strip()
            if v:
                parts.append(v)
    return sep.join(parts)


def percentile(sorted_vals: list[int], p: float) -> int:
    """简单的最近邻分位数，避免引入 numpy 依赖。"""
    if not sorted_vals:
        return 0
    k = max(0, min(len(sorted_vals) - 1, int(round(p * (len(sorted_vals) - 1)))))
    return sorted_vals[k]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="把 jsonl 中每条记录的多个文本字段拼成一个 text 字段。",
    )
    parser.add_argument("--input", type=Path, default=INPUT_FILE,
                        help=f"输入 jsonl，默认 {INPUT_FILE.relative_to(ROOT)}")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE,
                        help=f"输出 jsonl，默认 {OUTPUT_FILE.relative_to(ROOT)}")
    parser.add_argument("--fields", nargs="+", default=list(TEXT_FIELDS),
                        help=f"参与拼接的字段，按给定顺序拼接，默认 {list(TEXT_FIELDS)}")
    parser.add_argument("--sep", default=" ",
                        help="字段之间的分隔符，默认单空格")
    parser.add_argument("--keep-fields", action="store_true",
                        help="保留原始字段；默认只输出 record_id + text")
    args = parser.parse_args()

    inp: Path = args.input
    out: Path = args.output
    if not inp.exists():
        raise SystemExit(f"找不到输入文件：{inp}")
    ensure_dir(DATA_DIR)
    ensure_dir(out.parent)

    fields = tuple(args.fields)
    sep = args.sep

    n_lines = 0
    n_empty_text = 0
    lengths: list[int] = []
    # 各字段非空命中次数，用来排查"是不是某个字段全是空"
    field_hits = {f: 0 for f in fields}

    with inp.open("r", encoding="utf-8") as fin, out.open("w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)

            for f in fields:
                v = obj.get(f)
                if isinstance(v, str) and v.strip():
                    field_hits[f] += 1

            text = concat_record(obj, fields, sep)
            if not text:
                n_empty_text += 1
            lengths.append(len(text))

            if args.keep_fields:
                out_obj = dict(obj)
                out_obj["text"] = text
            else:
                out_obj = {"record_id": obj.get("record_id", ""), "text": text}

            fout.write(json.dumps(out_obj, ensure_ascii=False) + "\n")
            n_lines += 1

    rel_out = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"处理 {n_lines} 条记录 → {rel_out}")
    print(f"  拼接后 text 为空的记录数：{n_empty_text}"
          f"（占 {n_empty_text / n_lines * 100:.2f}%）" if n_lines else "")

    print("各字段非空命中：")
    for f in fields:
        hit = field_hits[f]
        rate = hit / n_lines * 100 if n_lines else 0.0
        print(f"  {f:<12s}: {hit} ({rate:.2f}%)")

    if lengths:
        lengths.sort()
        avg = sum(lengths) / len(lengths)
        print("text 长度分布（字符数）：")
        print(f"  min={lengths[0]}  "
              f"p50={percentile(lengths, 0.50)}  "
              f"p90={percentile(lengths, 0.90)}  "
              f"p99={percentile(lengths, 0.99)}  "
              f"max={lengths[-1]}  "
              f"avg={avg:.1f}")


if __name__ == "__main__":
    main()
