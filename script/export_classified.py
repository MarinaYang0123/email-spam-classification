#!/usr/bin/env python3
"""合并 cleaned_emails 全字段与方案分类标签，按类别聚合后导出。

默认输出到 reports/results/，两套方案各一份，文件名含 scheme 区分。
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "script"))
from project_dirs import DATA_DIR, REPORTS_DIR, ensure_dir  # noqa: E402

CLEANED_DEFAULT = DATA_DIR / "cleaned_emails.jsonl"
OUTPUT_DIR = REPORTS_DIR / "results"

SCHEME_SPECS: dict[str, dict] = {
    "scheme1": {
        "slug": "scheme1_semantic5",
        "dir": ROOT / "schemes" / "scheme1_semantic5",
        "category_order": (
            "暴力色情",
            "广告营销",
            "钓鱼邮件",
            "赌博博彩",
            "学术会议/期刊营销",
            "未分类",
            "空样本",
        ),
    },
    "scheme2": {
        "slug": "scheme2_balanced5",
        "dir": ROOT / "schemes" / "scheme2_balanced5",
        "category_order": (
            "暴力色情",
            "发票营销",
            "商业广告",
            "钓鱼邮件",
            "学术营销",
            "未分类",
            "空样本",
        ),
    },
}


def load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _variant_suffix(variant: str) -> str:
    v = (variant or "").strip()
    return f"_{v}" if v else ""


def load_labels(scheme_dir: Path, *, variant: str = "") -> dict[str, dict]:
    suffix = _variant_suffix(variant)
    labels_path = scheme_dir / "outputs" / f"labels{suffix}.jsonl"
    submit_path = scheme_dir / "outputs" / f"submit{suffix}.csv"
    if labels_path.exists():
        out: dict[str, dict] = {}
        with labels_path.open("r", encoding="utf-8") as fin:
            for line in fin:
                if not line.strip():
                    continue
                obj = json.loads(line)
                rid = str(obj.get("record_id", ""))
                out[rid] = {
                    "cluster_id": obj.get("cluster_id"),
                    "category": obj.get("category", ""),
                }
        return out

    if submit_path.exists():
        out = {}
        with submit_path.open("r", encoding="utf-8-sig", newline="") as fin:
            for row in csv.DictReader(fin):
                rid = str(row.get("record_id", ""))
                cid = row.get("cluster_id", "")
                out[rid] = {
                    "cluster_id": int(cid) if str(cid).lstrip("-").isdigit() else cid,
                    "category": row.get("category", ""),
                }
        return out

    raise FileNotFoundError(f"找不到标签文件：{labels_path} 或 {submit_path}")


def build_rows(
    cleaned_rows: list[dict],
    labels: dict[str, dict],
    category_order: tuple[str, ...],
) -> tuple[list[dict], list[str]]:
    rank = {name: idx for idx, name in enumerate(category_order)}
    unknown_rank = len(category_order)

    base_fields: OrderedDict[str, None] = OrderedDict()
    for row in cleaned_rows:
        for key in row:
            if key not in ("category", "cluster_id"):
                base_fields.setdefault(key, None)

    merged: list[dict] = []
    missing_labels = 0
    for row in cleaned_rows:
        rid = str(row.get("record_id", ""))
        meta = labels.get(rid)
        if meta is None:
            missing_labels += 1
            meta = {"cluster_id": None, "category": "未分类"}

        out = {k: row.get(k) for k in base_fields}
        out["category"] = meta["category"]
        out["cluster_id"] = meta["cluster_id"]
        merged.append(out)

    merged.sort(
        key=lambda r: (
            rank.get(str(r.get("category", "")), unknown_rank),
            str(r.get("record_id", "")),
        )
    )

    columns: list[str] = []
    if "record_id" in base_fields:
        columns.append("record_id")
    columns.extend(["category", "cluster_id"])
    columns.extend(k for k in base_fields if k != "record_id")

    ordered: list[dict] = []
    for row in merged:
        ordered.append({k: row.get(k) for k in columns})
    if missing_labels:
        print(f"  警告：{missing_labels} 条在标签文件中无对应记录，已标为「未分类」")
    return ordered, columns


def build_summary_rows(
    rows: list[dict],
    category_order: tuple[str, ...],
) -> list[dict]:
    total = len(rows)
    dist = Counter(str(r.get("category", "")) for r in rows)
    cluster_by_cat: dict[str, object] = {}
    for row in rows:
        cat = str(row.get("category", ""))
        cluster_by_cat.setdefault(cat, row.get("cluster_id"))

    summary: list[dict] = []
    seen: set[str] = set()
    rank = 0
    for cat in category_order:
        if cat not in dist:
            continue
        rank += 1
        cnt = dist[cat]
        summary.append({
            "rank": rank,
            "cluster_id": cluster_by_cat.get(cat, ""),
            "category": cat,
            "count": cnt,
            "pct": round(cnt / total * 100, 2) if total else 0.0,
        })
        seen.add(cat)
    for cat in sorted(dist):
        if cat in seen:
            continue
        rank += 1
        cnt = dist[cat]
        summary.append({
            "rank": rank,
            "cluster_id": cluster_by_cat.get(cat, ""),
            "category": cat,
            "count": cnt,
            "pct": round(cnt / total * 100, 2) if total else 0.0,
        })
    summary.append({
        "rank": "",
        "cluster_id": "",
        "category": "合计",
        "count": total,
        "pct": 100.0 if total else 0.0,
    })
    return summary


SUMMARY_COLUMNS = ("rank", "cluster_id", "category", "count", "pct")


def write_summary_csv(rows: list[dict], path: Path) -> None:
    write_csv(rows, path, list(SUMMARY_COLUMNS))


def write_jsonl(rows: list[dict], path: Path) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fout:
        for row in rows:
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(rows: list[dict], path: Path, columns: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.DictWriter(fout, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in columns})


def write_xlsx(rows: list[dict], path: Path, columns: list[str]) -> None:
    from jsonl_to_excel import write_excel

    tmp = path.with_suffix(".jsonl")
    write_jsonl(rows, tmp)
    try:
        write_excel(tmp, path)
    finally:
        if path.suffix.lower() == ".xlsx" and tmp.exists():
            tmp.unlink()


def export_scheme(
    *,
    scheme_key: str,
    spec: dict,
    cleaned_rows: list[dict],
    fmt: str,
    output_dir: Path,
    write_detail: bool = True,
    write_summary: bool = False,
    variant: str = "",
) -> int:
    labels = load_labels(spec["dir"], variant=variant)
    rows, columns = build_rows(cleaned_rows, labels, spec["category_order"])

    slug = spec["slug"]
    variant_suffix = _variant_suffix(variant)
    if write_detail:
        out_path = output_dir / f"{slug}_classified{variant_suffix}.{fmt}"
        if fmt == "jsonl":
            write_jsonl(rows, out_path)
        elif fmt == "csv":
            write_csv(rows, out_path, columns)
        elif fmt == "xlsx":
            write_xlsx(rows, out_path, columns)
        else:
            raise ValueError(f"未知格式：{fmt}")

    if write_summary:
        summary_path = output_dir / f"{slug}_summary{variant_suffix}.csv"
        write_summary_csv(build_summary_rows(rows, spec["category_order"]), summary_path)
        print(f"  总结：{summary_path.relative_to(ROOT)}")

    dist = Counter(str(r.get("category", "")) for r in rows)
    label_name = f"labels{variant_suffix}.jsonl" if variant_suffix else "labels.jsonl"
    print(f"[{scheme_key}] 标签：{(spec['dir'] / 'outputs' / label_name).relative_to(ROOT)}")
    if write_detail:
        print(f"  明细：{out_path.relative_to(ROOT)}  ({len(rows)} 条, {len(columns)} 列, {fmt})")
    else:
        print(f"  样本：{len(rows)} 条")
    for cat in spec["category_order"]:
        if cat in dist:
            cnt = dist[cat]
            print(f"    {cat}: {cnt} ({cnt / len(rows) * 100:.1f}%)")
    extra = [c for c in dist if c not in spec["category_order"]]
    for cat in extra:
        cnt = dist[cat]
        print(f"    {cat}: {cnt} ({cnt / len(rows) * 100:.1f}%)")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="导出两套方案的分类结果（cleaned 全字段 + category），按类别聚合。",
    )
    parser.add_argument(
        "--scheme",
        choices=("scheme1", "scheme2", "all"),
        default="all",
        help="scheme1 / scheme2 / all（默认 all）",
    )
    parser.add_argument(
        "--cleaned",
        type=Path,
        default=CLEANED_DEFAULT,
        help=f"原始清洗 JSONL，默认 {CLEANED_DEFAULT.relative_to(ROOT)}",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help=f"输出目录，默认 {OUTPUT_DIR.relative_to(ROOT)}",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=("jsonl", "csv", "xlsx"),
        default="jsonl",
        help="明细输出格式（默认 jsonl）",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="额外生成 CSV 类别统计总结（每方案一份：{slug}_summary.csv）",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="仅生成 CSV 总结，不写 classified 明细文件",
    )
    parser.add_argument(
        "--variant",
        default="",
        help="标签变体后缀（如 full → 读取 outputs/labels_full.jsonl，写出 *_classified_full.*）",
    )
    args = parser.parse_args()

    if args.summary_only:
        args.summary = True

    if args.summary_only and args.format != "jsonl":
        print("提示：--summary-only 下忽略 --format，不输出明细文件")

    write_detail = not args.summary_only
    write_summary = args.summary
    if not write_detail and not write_summary:
        raise SystemExit("请至少启用明细导出或 --summary / --summary-only")

    if not args.cleaned.exists():
        raise SystemExit(f"找不到 cleaned 文件：{args.cleaned}")

    ensure_dir(REPORTS_DIR)
    ensure_dir(args.output_dir)

    cleaned_rows = load_jsonl(args.cleaned)
    if not cleaned_rows:
        raise SystemExit(f"{args.cleaned} 为空")

    keys = list(SCHEME_SPECS) if args.scheme == "all" else [args.scheme]
    total = 0
    for scheme_key in keys:
        total += export_scheme(
            scheme_key=scheme_key,
            spec=SCHEME_SPECS[scheme_key],
            cleaned_rows=cleaned_rows,
            fmt=args.format,
            output_dir=args.output_dir,
            write_detail=write_detail,
            write_summary=write_summary,
            variant=args.variant,
        )
    if write_detail:
        print(f"合计导出 {total} 条明细（按方案分别计数）")
    elif write_summary:
        print(f"已生成 {len(keys)} 份 CSV 总结")


if __name__ == "__main__":
    main()
