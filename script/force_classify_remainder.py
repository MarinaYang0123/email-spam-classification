"""对规则未命中的样本做强制五类归类（假定均为垃圾邮件）。

合并原 labels 与补充分类，写出 *_full.* 产物（不覆盖默认 outputs）。
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from rule_classify import (
    CONCAT_FILE,
    EMPTY_CLUSTER_ID,
    PHISH_DATING_BAIT,
    RECORD_IDS_FILE,
    STRUCT_FILE,
    TOKENIZED_FILE,
    UNCLASSIFIED_ID,
    SchemeConfig,
    assign_rule_label,
    flatten_taxonomy,
    keyword_hits,
    load_json,
    load_struct,
    load_text_map,
    load_tokens,
    rule_scores,
)


@dataclass(frozen=True)
class SchemeProfile:
    invoice: str
    ads: str
    academic: str
    gambling: str | None


def _profile(rule_categories: tuple[str, ...]) -> SchemeProfile:
    cats = set(rule_categories)
    return SchemeProfile(
        invoice="发票营销" if "发票营销" in cats else "广告营销",
        ads="商业广告" if "商业广告" in cats else "广告营销",
        academic="学术营销" if "学术营销" in cats else "学术会议/期刊营销",
        gambling="赌博博彩" if "赌博博彩" in cats else None,
    )


def _norm_tokens(tokens: list[str]) -> list[str]:
    return [t.lower() if isinstance(t, str) and t.isascii() else t for t in tokens]


def _text_blob(cleaned: dict | None) -> str:
    if not cleaned:
        return ""
    parts = [
        cleaned.get("subject") or "",
        cleaned.get("content") or "",
        cleaned.get("fromname") or "",
    ]
    return " ".join(parts).lower()


def _best_rule_category(
    tokens: list[str],
    struct: dict,
    taxonomy: dict[str, list[str]],
    rule_categories: tuple[str, ...],
    rule_priority: dict[str, int],
) -> tuple[str | None, dict[str, float], str]:
    kw = dict(
        w_mismatch=2.0,
        w_url_susp=2.0,
        w_url_mismatch=0.5,
        short_token_max=8,
    )
    scores, _, _ = rule_scores(tokens, struct, taxonomy, rule_categories, **kw)
    cat = assign_rule_label(scores, rule_priority, min_score=1.0)
    if cat:
        return cat, scores, "rule_min1"
    cat = assign_rule_label(scores, rule_priority, min_score=0.5)
    if cat:
        return cat, scores, "rule_any"
    best = max(scores, key=lambda c: (scores[c], -rule_priority[c]))
    if scores[best] > 0:
        return best, scores, "rule_weak"
    return None, scores, "heuristic"


def _heuristic_category(
    tokens: list[str],
    struct: dict,
    cleaned: dict | None,
    profile: SchemeProfile,
) -> tuple[str, str]:
    ts = set(tokens)
    blob = _text_blob(cleaned)
    lang = struct.get("lang") or "unknown"

    def zh(*words: str) -> bool:
        return any(w in ts or w in blob for w in words)

    def en(*words: str) -> bool:
        return any(w in ts or w in blob for w in words)

    # --- 赌博博彩（仅方案1）---
    if profile.gambling and (
        zh("bbin", "葡京", "澳门", "百家乐", "打码", "彩金", "特邀", "博彩", "棋牌", "彩票", "赌场", "投注", "真人", "电子游戏", "满壹千送", "晋升为", "vip", "彩金", "采金", "任你玩")
        or en("bbin", "casino", "betting", "gambling", "lottery", "jackpot", "poker", "slot")
    ):
        return profile.gambling, "heuristic_gambling"

    # --- 发票/广告（发票类）---
    if zh("普增", "住宿服务", "做账报", "帐报", "账报", "税票", "增值税", "核定征收", "普票及", "有税票", "各地", "kai", "开票", "代开", "发票", "增值", "专用发票"):
        return profile.invoice, "heuristic_invoice"
    if en("invoice", "fapiao", "piao") or (en("text") and len(ts) <= 8):
        return profile.invoice, "heuristic_invoice_short"

    # --- 暴力色情 ---
    if zh("换妻", "拳交", "白虎", "吞了", "淫乐", "娇羞", "限制级", "人操", "剧情片", "重口味", "约炮", "裸聊"):
        return "暴力色情", "heuristic_porn_zh"
    if "[url]" in ts and lang in ("en", "mixed"):
        bait = ts & PHISH_DATING_BAIT
        if bait or en(
            "evening", "morning", "howdy", "greetings", "whats", "wut", "hey", "hello",
            "goodbye", "spero", "auguro", "bonjour", "giornata", "indecorous", "solitary",
            "breathtaking", "fellow", "pal", "man", "girl", "woman", "dating", "lonely",
            "desire", "sexual", "urges",
        ):
            return "暴力色情", "heuristic_dating_url"
        return "暴力色情", "heuristic_url_en"
    if en("erectile", "dysfunction") or (en("ed", "pill") and en("health", "treatment", "drug", "medicine")):
        return "暴力色情", "heuristic_ed_spam"

    # --- 钓鱼邮件 ---
    if zh("邮箱限制", "cass spam", "注册岭赢", "冻结", "验证码", "异常登录", "解封", "重新激活"):
        return "钓鱼邮件", "heuristic_phish_zh"
    if en(
        "unclaimed", "god almighty", "treasury department", "impostors", "criminal minded",
        "malware detect", "microsoft monitoring", "buraya tikla", "quarantine", "blocked incoming",
        "validation error", "release these message", "quarantined", "wire transfer", "urgent business",
        "inheritance", "lottery", "congratulations", "verify your", "account suspended", "linkedin com",
        "global buyers", "order request", "participates and complete",
    ):
        return "钓鱼邮件", "heuristic_phish_en"
    if struct.get("url_sender_mismatch") and len(tokens) <= 15:
        return "钓鱼邮件", "heuristic_url_mismatch_short"
    if struct.get("display_domain_mismatch") or struct.get("url_suspicious"):
        return "钓鱼邮件", "heuristic_struct_phish"

    # --- 学术 ---
    if zh(
        "研修", "培训班", "实验技术", "全国高校", "高教", "培训中心", "订阅邮件", "专利",
        "审查意见", "知识产权", "论文", "期刊", "会议", "征稿", "投稿", "sci", "ei", "cpci",
        "版面费", "实验教学", "mol", "pnas", "doi", "tensorflow", "卷积网络", "人工智能",
        "赛默飞", "invitrogen", "jove", "integle", "电子实验", "学术", "研究院所", "中培号",
    ):
        return profile.academic, "heuristic_academic"
    if en(
        "manuscript", "journal", "conference", "abstract submission", "call papers", "sci",
        "research", "pnas", "tensorflow", "jove", "invitrogen", "tech transfer",
    ):
        return profile.academic, "heuristic_academic_en"

    # --- 商业/广告推广 ---
    if zh(
        "谈判", "研讨会", "展会", "产业园", "招聘", "丰田", "精益", "研修之旅", "法轮功",
        "共产党", "三退", "九评", "网易", "邮箱大师", "欢迎", "使用", "日报", "烽火", "催办",
        "崩溃", "告警", "alert", "nagios", "grafana", "采购", "培训", "违纪", "离职", "劳动合同",
        "茵泰科", "称重", "工业", "联想", "退订", "红包", "大学生就业", "核定征收", "帮税",
        "代办", "住宿", "广告", "促销", "优惠", "报价", "招商", "领取", "葡京", "打码",
    ):
        return profile.ads, "heuristic_ads_zh"
    if en(
        "crashlytics", "fatal issue", "nagios", "grafana", "tomcatlog", "memcache", "delivered",
        "delivery notification", "collected mail notifier", "predictive index", "digital directory",
        "web hosting", "purchase order", "request for quotation", "due diligence", "mergers",
        "veteran", "discount", "shop now", "unsubscribe", "newsletter", "commercial message",
        "killer drink", "weight loss", "diabetes", "obesity", "product of the day", "claim discounts",
        "supervisor business", "consumer electronics", "chart advisor", "quora digest",
        "automatic reply", "out of office", "having trouble viewing", "view this email online",
    ):
        return profile.ads, "heuristic_ads_en"

    if lang == "zh" or any("\u4e00" <= c <= "\u9fff" for t in tokens for c in str(t)):
        return profile.ads, "heuristic_default_zh"
    if len(tokens) <= 6:
        return "钓鱼邮件", "heuristic_default_short"
    if lang in ("en", "mixed"):
        return "暴力色情", "heuristic_default_en"
    return profile.ads, "heuristic_default"


def force_classify_record(
    tokens: list[str],
    struct: dict,
    cleaned: dict | None,
    taxonomy: dict[str, list[str]],
    rule_categories: tuple[str, ...],
    rule_priority: dict[str, int],
    profile: SchemeProfile,
) -> tuple[str, str]:
    tokens = _norm_tokens(tokens)
    cat, _, method = _best_rule_category(
        tokens, struct, taxonomy, rule_categories, rule_priority,
    )
    if cat:
        return cat, method
    return _heuristic_category(tokens, struct, cleaned, profile)


def run_force_classify_scheme(
    cfg: SchemeConfig,
    *,
    variant: str = "full",
    base_labels_path: Path | None = None,
) -> Counter:
    for path in (TOKENIZED_FILE, STRUCT_FILE, cfg.taxonomy_path, CONCAT_FILE, RECORD_IDS_FILE):
        if not path.exists():
            raise SystemExit(f"找不到输入文件：{path}")

    base_labels_path = base_labels_path or (cfg.output_dir / "labels.jsonl")
    if not base_labels_path.exists():
        raise SystemExit(f"找不到基础标签：{base_labels_path}")

    tokens_map = load_tokens(TOKENIZED_FILE)
    struct_map = load_struct(STRUCT_FILE)
    taxonomy = flatten_taxonomy(load_json(cfg.taxonomy_path))
    record_ids = load_json(RECORD_IDS_FILE)
    text_map = load_text_map(CONCAT_FILE)
    profile = _profile(cfg.rule_categories)

    cleaned_map: dict[str, dict] = {}
    cleaned_path = TOKENIZED_FILE.parent / "cleaned_emails.jsonl"
    if cleaned_path.exists():
        with cleaned_path.open("r", encoding="utf-8") as fin:
            for line in fin:
                if not line.strip():
                    continue
                obj = json.loads(line)
                cleaned_map[str(obj.get("record_id", ""))] = obj

    base_cat: dict[str, str] = {}
    base_label: dict[str, int] = {}
    with base_labels_path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            rid = str(obj.get("record_id", ""))
            base_cat[rid] = obj.get("category", "未分类")
            base_label[rid] = int(obj.get("cluster_id", UNCLASSIFIED_ID))

    final_cat: dict[str, str] = {}
    final_label: dict[str, int] = {}
    rule_hit_tokens: dict[str, Counter] = {c: Counter() for c in cfg.rule_categories}
    audit_rows: list[dict] = []
    method_stats = Counter()

    for rid in record_ids:
        tokens = tokens_map.get(rid, [])
        if not tokens:
            final_cat[rid] = "空样本"
            final_label[rid] = EMPTY_CLUSTER_ID
            continue

        prev = base_cat.get(rid, "未分类")
        if prev != "未分类":
            final_cat[rid] = prev
            final_label[rid] = base_label[rid]
            hits = keyword_hits(_norm_tokens(tokens), taxonomy.get(prev, []))
            for w in hits:
                rule_hit_tokens[prev][w] += 1
            continue

        cat, method = force_classify_record(
            tokens,
            struct_map.get(rid, {}),
            cleaned_map.get(rid),
            taxonomy,
            cfg.rule_categories,
            cfg.rule_priority,
            profile,
        )
        final_cat[rid] = cat
        final_label[rid] = cfg.category_id[cat]
        method_stats[method] += 1
        hits = keyword_hits(_norm_tokens(tokens), taxonomy.get(cat, []))
        for w in hits:
            rule_hit_tokens[cat][w] += 1
        audit_rows.append({
            "record_id": rid,
            "previous_category": prev,
            "category": cat,
            "cluster_id": final_label[rid],
            "method": method,
            "token_count": len(tokens),
            "text_preview": (text_map.get(rid, "")[:200]),
        })

    out_dir = cfg.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{variant}" if variant else ""

    vcfg = SchemeConfig(
        name=f"{cfg.name}（全量归类 · {variant}）",
        rule_categories=cfg.rule_categories,
        rule_priority=cfg.rule_priority,
        category_id=cfg.category_id,
        taxonomy_path=cfg.taxonomy_path,
        output_dir=out_dir,
    )

    _write_variant_outputs(
        cfg=vcfg,
        variant=variant,
        record_ids=record_ids,
        final_label=final_label,
        final_cat=final_cat,
        rule_hit_tokens=rule_hit_tokens,
        text_map=text_map,
    )

    dist = Counter(final_cat[rid] for rid in record_ids)
    report_path = out_dir / f"report{suffix}.md"
    _write_variant_report(
        vcfg, dist, len(record_ids), rule_hit_tokens, report_path, method_stats, len(audit_rows),
    )

    audit_path = out_dir / f"force_classify_audit{suffix}.jsonl"
    with audit_path.open("w", encoding="utf-8") as fout:
        for row in audit_rows:
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")

    return dist


def _write_variant_outputs(
    *,
    cfg: SchemeConfig,
    variant: str,
    record_ids,
    final_label,
    final_cat,
    rule_hit_tokens,
    text_map,
    keywords_per_cluster: int = 20,
    samples_per_cluster: int = 10,
):
    import csv
    from collections import defaultdict

    suffix = f"_{variant}" if variant else ""
    out = cfg.output_dir

    labels_path = out / f"labels{suffix}.jsonl"
    submit_path = out / f"submit{suffix}.csv"
    keywords_path = out / f"keywords{suffix}.csv"

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
    wb.save(out / f"samples{suffix}.xlsx")


def _write_variant_report(
    cfg: SchemeConfig,
    dist: Counter,
    total: int,
    rule_hit_tokens: dict[str, Counter],
    report_path: Path,
    method_stats: Counter,
    forced_count: int,
):
    lines = [
        f"# {cfg.name} 分类报告",
        "",
        f"- 总样本：**{total}**",
        f"- 未分类：**{dist.get('未分类', 0)}**",
        f"- 空样本：**{dist.get('空样本', 0)}**",
        f"- 本轮强制归类：**{forced_count}** 条（原「未分类」）",
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

    if method_stats:
        lines += ["", "## 强制归类方法统计", ""]
        for k, v in method_stats.most_common():
            lines.append(f"- {k}: {v}")

    lines += ["", "## 规则 Top 命中词", ""]
    for cat in cfg.rule_categories:
        top = "、".join(f"{w}({c})" for w, c in rule_hit_tokens[cat].most_common(15))
        lines.append(f"- **{cat}**：{top}")

    report_path.write_text("\n".join(lines), encoding="utf-8")
