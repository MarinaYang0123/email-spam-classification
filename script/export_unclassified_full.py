#!/usr/bin/env python3
"""从 cleaned_emails / concat_email 导出各方案「未分类」条目 JSONL。

默认从 cleaned_emails.jsonl 导出全字段；可选同时或单独从 concat_email.jsonl 导出。
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from project_dirs import DATA_DIR, REPORTS_DIR

ROOT = Path(__file__).resolve().parent.parent
CLEANED_DEFAULT = DATA_DIR / "cleaned_emails.jsonl"
CONCAT_DEFAULT = DATA_DIR / "concat_email.jsonl"

SCHEMES: dict[str, Path] = {
    "scheme1": ROOT / "schemes" / "scheme1_semantic5",
    "scheme2": ROOT / "schemes" / "scheme2_balanced5",
}

OUT_NAME_CLEANED = "unclassified_full.jsonl"
OUT_NAME_CONCAT = "unclassified_concat.jsonl"

SOURCE_SPECS: dict[str, dict[str, str | Path]] = {
    "cleaned": {
        "label": "cleaned_emails",
        "default_path": CLEANED_DEFAULT,
        "out_name": OUT_NAME_CLEANED,
    },
    "concat": {
        "label": "concat_email",
        "default_path": CONCAT_DEFAULT,
        "out_name": OUT_NAME_CONCAT,
    },
}


def load_labels(labels_path: Path) -> dict[str, dict]:
    """record_id -> {cluster_id, category}"""
    if labels_path.suffix == ".jsonl":
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

    out = {}
    with labels_path.open("r", encoding="utf-8-sig", newline="") as fin:
        for row in csv.DictReader(fin):
            rid = str(row.get("record_id", ""))
            out[rid] = {
                "cluster_id": int(row["cluster_id"]) if row.get("cluster_id", "").lstrip("-").isdigit() else row.get("cluster_id"),
                "category": row.get("category", ""),
            }
    return out


def resolve_labels_path(scheme_dir: Path) -> Path:
    labels = scheme_dir / "outputs" / "labels.jsonl"
    if labels.exists():
        return labels
    submit = scheme_dir / "outputs" / "submit.csv"
    if submit.exists():
        return submit
    raise FileNotFoundError(f"找不到标签文件：{labels} 或 {submit}")


def collect_target_ids(
    labels: dict[str, dict],
    categories: tuple[str, ...],
) -> set[str]:
    return {
        rid for rid, meta in labels.items()
        if meta.get("category") in categories
    }


def export_scheme(
    *,
    scheme_key: str,
    scheme_dir: Path,
    source_path: Path,
    source_label: str,
    categories: tuple[str, ...],
    output_path: Path | None,
    default_out_name: str,
) -> int:
    labels_path = resolve_labels_path(scheme_dir)
    labels = load_labels(labels_path)
    target_ids = collect_target_ids(labels, categories)
    out_path = output_path or (scheme_dir / "outputs" / default_out_name)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    n_written = 0
    written_ids: set[str] = set()

    with source_path.open("r", encoding="utf-8") as fin, out_path.open("w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            rid = str(obj.get("record_id", ""))
            if rid not in target_ids:
                continue
            meta = labels[rid]
            record = dict(obj)
            record["scheme"] = scheme_key
            record["cluster_id"] = meta["cluster_id"]
            record["category"] = meta["category"]
            fout.write(json.dumps(record, ensure_ascii=False) + "\n")
            n_written += 1
            written_ids.add(rid)

    missing_in_source = sorted(target_ids - written_ids)

    print(f"[{scheme_key}] 标签文件：{labels_path.relative_to(ROOT)}")
    print(f"  数据源 {source_label}：{source_path.relative_to(ROOT)}")
    print(f"  目标类别 {categories}：{len(target_ids)} 条")
    print(f"  已写入：{n_written} 条 → {out_path.relative_to(ROOT)}")
    if missing_in_source:
        print(f"  警告：{len(missing_in_source)} 条在 {source_label} 中未找到（前 5：{missing_in_source[:5]}）")
    return n_written


def main() -> None:
    parser = argparse.ArgumentParser(description="导出未分类邮件到各方案 outputs/")
    parser.add_argument(
        "--scheme",
        choices=("scheme1", "scheme2", "all"),
        default="all",
        help="scheme1 / scheme2 / all（默认 all）",
    )
    parser.add_argument(
        "--source",
        choices=("cleaned", "concat", "both"),
        default="cleaned",
        help="数据源：cleaned_emails（默认）/ concat_email / 两者都导出",
    )
    parser.add_argument(
        "--cleaned",
        type=Path,
        default=CLEANED_DEFAULT,
        help=f"cleaned JSONL，默认 {CLEANED_DEFAULT.relative_to(ROOT)}",
    )
    parser.add_argument(
        "--concat",
        type=Path,
        default=CONCAT_DEFAULT,
        help=f"concat JSONL，默认 {CONCAT_DEFAULT.relative_to(ROOT)}",
    )
    parser.add_argument(
        "--categories",
        type=str,
        default="未分类",
        help="逗号分隔要导出的类别，默认仅「未分类」",
    )
    parser.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="cleaned 导出路径（仅单个 --scheme 时）",
    )
    parser.add_argument(
        "--concat-output",
        type=Path,
        default=None,
        help="concat 导出路径（仅单个 --scheme 时）",
    )
    args = parser.parse_args()

    sources: list[tuple[str, Path, Path | None]] = []
    if args.source in ("cleaned", "both"):
        sources.append(("cleaned", args.cleaned, args.output))
    if args.source in ("concat", "both"):
        sources.append(("concat", args.concat, args.concat_output))

    for key, path, _ in sources:
        if not path.exists():
            raise SystemExit(f"找不到 {path}")

    categories = tuple(c.strip() for c in args.categories.split(",") if c.strip())
    if not categories:
        raise SystemExit("--categories 不能为空")

    keys = list(SCHEMES) if args.scheme == "all" else [args.scheme]
    if (args.output or args.concat_output) and len(keys) != 1:
        raise SystemExit("-o / --concat-output 仅能在指定单个 --scheme 时使用")

    total = 0
    for scheme_key in keys:
        for source_key, source_path, output_path in sources:
            spec = SOURCE_SPECS[source_key]
            total += export_scheme(
                scheme_key=scheme_key,
                scheme_dir=SCHEMES[scheme_key],
                source_path=source_path,
                source_label=str(spec["label"]),
                categories=categories,
                output_path=output_path if len(keys) == 1 else None,
                default_out_name=str(spec["out_name"]),
            )
    print(f"合计导出 {total} 条（按方案×数据源分别计数）")


if __name__ == "__main__":
    main()
