"""规则分类引擎：在 token + 结构特征上匹配词表，输出标签与报告。

由 schemes/*/classify.py 指定类别、路径；不依赖 KMeans。
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from project_dirs import DATA_DIR, TFIDF_DIR

ROOT = Path(__file__).resolve().parent.parent
TOKENIZED_FILE = DATA_DIR / "tokenized_email.jsonl"
STRUCT_FILE = DATA_DIR / "structural_features.jsonl"
CONCAT_FILE = DATA_DIR / "concat_email.jsonl"
RECORD_IDS_FILE = TFIDF_DIR / "tfidf_record_ids.json"

EMPTY_CLUSTER_ID = -1
UNCLASSIFIED_ID = 5

PHISH_SHORT_TOKEN_MAX = 8
PHISH_DATING_BAIT = frozenset({
    "profile", "visit", "share", "found", "photos", "album", "matched",
    "message", "click", "desire", "relationship", "single", "lonely", "hi", "hey",
})


@dataclass(frozen=True)
class SchemeConfig:
    name: str
    rule_categories: tuple[str, ...]
    rule_priority: dict[str, int]
    category_id: dict[str, int]
    taxonomy_path: Path
    output_dir: Path


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_tokens(path: Path) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            toks = obj.get("tokens", [])
            mapping[str(obj.get("record_id", ""))] = toks if isinstance(toks, list) else []
    return mapping


def load_struct(path: Path) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            mapping[str(obj.get("record_id", ""))] = obj
    return mapping


def load_text_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            text = obj.get("text", "")
            mapping[str(obj.get("record_id", ""))] = text if isinstance(text, str) else ""
    return mapping


def flatten_taxonomy(taxonomy: dict) -> dict[str, list[str]]:
    cats = taxonomy.get("categories", taxonomy)
    out: dict[str, list[str]] = {}
    for cat, groups in cats.items():
        if cat.startswith("_"):
            continue
        words: list[str] = []
        for key in ("zh", "en", "pinyin"):
            for w in groups.get(key, []):
                w = w.strip()
                if not w:
                    continue
                words.append(w.lower() if key in ("en", "pinyin") else w)
        out[cat] = words
    return out


def match_keyword(keyword: str, token_set: set[str]) -> bool:
    if " " in keyword:
        return all(part in token_set for part in keyword.split())
    return keyword in token_set


def keyword_hits(tokens: list[str], words: list[str]) -> list[str]:
    token_set = set(tokens)
    return [w for w in words if match_keyword(w, token_set)]


def is_short_url_bait(tokens: list[str], *, max_tokens: int) -> bool:
    return len(tokens) <= max_tokens


def is_dating_link_bait(tokens: list[str], struct: dict) -> bool:
    if struct.get("lang") not in ("en", "mixed"):
        return False
    ts = set(tokens)
    hits = ts & PHISH_DATING_BAIT
    return len(hits) >= 2 or (len(hits) >= 1 and len(tokens) <= 12)


def rule_scores(
    tokens: list[str],
    struct: dict,
    taxonomy: dict[str, list[str]],
    rule_categories: tuple[str, ...],
    *,
    w_mismatch: float,
    w_url_susp: float,
    w_url_mismatch: float,
    short_token_max: int,
) -> tuple[dict[str, float], dict[str, list[str]], dict[str, bool]]:
    scores: dict[str, float] = {}
    hits: dict[str, list[str]] = {}
    for cat in rule_categories:
        hit = keyword_hits(tokens, taxonomy.get(cat, []))
        hits[cat] = hit
        scores[cat] = 0.5 * len(hit) if cat == "钓鱼邮件" else float(len(hit))

    phish_kw = scores.get("钓鱼邮件", 0.0)
    combo = {
        "strong_mismatch": False,
        "strong_susp": False,
        "combo_kw": False,
        "combo_short": False,
        "combo_dating": False,
    }

    if struct and "钓鱼邮件" in rule_categories:
        if struct.get("display_domain_mismatch"):
            scores["钓鱼邮件"] += w_mismatch
            combo["strong_mismatch"] = True
        if struct.get("url_suspicious"):
            scores["钓鱼邮件"] += w_url_susp
            combo["strong_susp"] = True

        if struct.get("url_sender_mismatch"):
            if phish_kw >= 0.5:
                scores["钓鱼邮件"] += w_url_mismatch
                combo["combo_kw"] = True
            elif is_short_url_bait(tokens, max_tokens=short_token_max):
                scores["钓鱼邮件"] = max(scores["钓鱼邮件"], 1.0)
                combo["combo_short"] = True
            elif is_dating_link_bait(tokens, struct):
                scores["钓鱼邮件"] = max(scores["钓鱼邮件"], 1.0)
                combo["combo_dating"] = True

    return scores, hits, combo


def assign_rule_label(
    scores: dict[str, float],
    rule_priority: dict[str, int],
    *,
    min_score: float,
) -> str | None:
    best = max(scores, key=lambda c: (scores[c], -rule_priority[c]))
    if scores[best] >= min_score:
        return best
    return None


def run_scheme(
    cfg: SchemeConfig,
    *,
    min_rule_score: float = 1.0,
    w_mismatch: float = 2.0,
    w_url_suspicious: float = 2.0,
    w_url_mismatch: float = 0.5,
    phish_short_tokens: int = PHISH_SHORT_TOKEN_MAX,
    keywords_per_cluster: int = 20,
    samples_per_cluster: int = 10,
) -> Counter:
    for path in (TOKENIZED_FILE, STRUCT_FILE, cfg.taxonomy_path, CONCAT_FILE, RECORD_IDS_FILE):
        if not path.exists():
            raise SystemExit(f"找不到输入文件：{path}")

    tokens_map = load_tokens(TOKENIZED_FILE)
    struct_map = load_struct(STRUCT_FILE)
    taxonomy = flatten_taxonomy(load_json(cfg.taxonomy_path))
    record_ids = load_json(RECORD_IDS_FILE)

    final_label: dict[str, int] = {}
    final_cat: dict[str, str] = {}
    rule_hit_tokens: dict[str, Counter] = {c: Counter() for c in cfg.rule_categories}
    signal_stats = Counter()

    for rid in record_ids:
        tokens = tokens_map.get(rid, [])
        if not tokens:
            final_label[rid] = EMPTY_CLUSTER_ID
            final_cat[rid] = "空样本"
            continue
        scores, hits, phish_combo = rule_scores(
            tokens, struct_map.get(rid, {}), taxonomy, cfg.rule_categories,
            w_mismatch=w_mismatch,
            w_url_susp=w_url_suspicious,
            w_url_mismatch=w_url_mismatch,
            short_token_max=phish_short_tokens,
        )
        cat = assign_rule_label(scores, cfg.rule_priority, min_score=min_rule_score)
        if cat is not None:
            final_label[rid] = cfg.category_id[cat]
            final_cat[rid] = cat
            for w in hits[cat]:
                rule_hit_tokens[cat][w] += 1
            if cat == "钓鱼邮件":
                if phish_combo["strong_mismatch"]:
                    signal_stats["phish_mismatch"] += 1
                if phish_combo["strong_susp"]:
                    signal_stats["phish_url_susp"] += 1
                if phish_combo["combo_kw"]:
                    signal_stats["phish_combo_kw"] += 1
                if phish_combo["combo_short"]:
                    signal_stats["phish_combo_short"] += 1
                if phish_combo["combo_dating"]:
                    signal_stats["phish_combo_dating"] += 1
        else:
            final_label[rid] = UNCLASSIFIED_ID
            final_cat[rid] = "未分类"

    out = cfg.output_dir
    out.mkdir(parents=True, exist_ok=True)
    text_map = load_text_map(CONCAT_FILE)
    write_outputs(
        cfg=cfg,
        record_ids=record_ids,
        final_label=final_label,
        final_cat=final_cat,
        rule_hit_tokens=rule_hit_tokens,
        text_map=text_map,
        keywords_per_cluster=keywords_per_cluster,
        samples_per_cluster=samples_per_cluster,
    )

    dist = Counter(final_cat[rid] for rid in record_ids)
    write_report(cfg, dist, len(record_ids), signal_stats, rule_hit_tokens)
    return dist


def write_outputs(
    *,
    cfg: SchemeConfig,
    record_ids,
    final_label,
    final_cat,
    rule_hit_tokens,
    text_map,
    keywords_per_cluster,
    samples_per_cluster,
):
    labels_path = cfg.output_dir / "labels.jsonl"
    submit_path = cfg.output_dir / "submit.csv"
    keywords_path = cfg.output_dir / "keywords.csv"

    with labels_path.open("w", encoding="utf-8") as fout:
        for rid in record_ids:
            fout.write(json.dumps({
                "record_id": rid,
                "cluster_id": final_label[rid],
                "category": final_cat[rid],
            }, ensure_ascii=False) + "\n")

    with submit_path.open("w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(["record_id", "cluster_id", "category"])
        for rid in record_ids:
            writer.writerow([rid, final_label[rid], final_cat[rid]])

    with keywords_path.open("w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(["cluster_id", "category", "rank", "token", "score_or_count"])
        for cat in cfg.rule_categories:
            for rank, (tok, cnt) in enumerate(
                rule_hit_tokens[cat].most_common(keywords_per_cluster), 1,
            ):
                writer.writerow([cfg.category_id[cat], cat, rank, tok, cnt])

    _write_samples(cfg, record_ids, final_label, final_cat, text_map, samples_per_cluster)


def _write_samples(cfg, record_ids, final_label, final_cat, text_map, samples_per_cluster):
    try:
        from openpyxl import Workbook  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 openpyxl：pip install openpyxl") from exc

    by_cat: dict[str, list[str]] = defaultdict(list)
    for rid in record_ids:
        by_cat[final_cat[rid]].append(rid)

    wb = Workbook(write_only=True)
    ws = wb.create_sheet("samples")
    ws.append(["cluster_id", "category", "rank", "record_id", "text_preview"])
    for cat, ids in sorted(by_cat.items()):
        for rank, rid in enumerate(ids[:samples_per_cluster], 1):
            text = text_map.get(rid, "")
            preview = text[:200] + ("..." if len(text) > 200 else "")
            ws.append([final_label[rid], cat, rank, rid, preview])
    wb.save(cfg.output_dir / "samples.xlsx")


def write_report(cfg, dist, total, signal_stats, rule_hit_tokens):
    lines = [
        f"# {cfg.name} 分类报告",
        "",
        f"- 总样本：**{total}**",
        f"- 未分类：**{dist.get('未分类', 0)}**",
        f"- 空样本：**{dist.get('空样本', 0)}**",
        "",
        "## 类别分布",
        "",
        "| cluster_id | 类别 | 数量 | 占比 |",
        "|---:|---|---:|---:|",
    ]
    name_to_id = dict(cfg.category_id)
    name_to_id["空样本"] = EMPTY_CLUSTER_ID
    name_to_id["未分类"] = UNCLASSIFIED_ID
    for cat, cnt in sorted(dist.items(), key=lambda x: -x[1]):
        cid = name_to_id.get(cat, "?")
        lines.append(f"| {cid} | {cat} | {cnt} | {cnt/total*100:.1f}% |")

    if signal_stats:
        lines += ["", "## 钓鱼结构信号", ""]
        for k, v in signal_stats.most_common():
            lines.append(f"- {k}: {v}")

    lines += ["", "## 规则 Top 命中词", ""]
    for cat in cfg.rule_categories:
        top = "、".join(f"{w}({c})" for w, c in rule_hit_tokens[cat].most_common(15))
        lines.append(f"- **{cat}**：{top}")

    (cfg.output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
