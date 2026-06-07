"""诊断方案2：为什么暴力色情偏多、钓鱼偏少。

复用 rule_classify 的打分逻辑，逐封重算分数，统计：
  - 暴力色情 标签里，有多少同时带钓鱼关键词/结构信号（疑似被抢）
  - 钓鱼标签因 0.5 折算 + 优先级输给谁
  - 暴力色情命中里，英文 [URL] 短诱饵（更像钓鱼）的占比
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "script"))

from rule_classify import (  # noqa: E402
    CONCAT_FILE, RECORD_IDS_FILE, STRUCT_FILE, TOKENIZED_FILE,
    flatten_taxonomy, keyword_hits, load_json, load_struct,
    load_text_map, load_tokens, rule_scores,
)

SCHEME = ROOT / "schemes" / "scheme2_balanced5"
TAX = SCHEME / "category_taxonomy.json"
LABELS = SCHEME / "outputs" / "labels.jsonl"

RULE_CATS = ("暴力色情", "发票营销", "商业广告", "钓鱼邮件", "学术营销")
KW = dict(w_mismatch=2.0, w_url_susp=2.0, w_url_mismatch=0.5, short_token_max=8)


def main() -> None:
    tokens_map = load_tokens(TOKENIZED_FILE)
    struct_map = load_struct(STRUCT_FILE)
    taxonomy = flatten_taxonomy(load_json(TAX))
    text_map = load_text_map(CONCAT_FILE)

    label_cat: dict[str, str] = {}
    with LABELS.open(encoding="utf-8") as fin:
        for line in fin:
            if line.strip():
                o = json.loads(line)
                label_cat[str(o["record_id"])] = o["category"]

    porn_ids = [r for r, c in label_cat.items() if c == "暴力色情"]
    phish_ids = [r for r, c in label_cat.items() if c == "钓鱼邮件"]

    # 暴力色情里的钓鱼污染
    porn_with_phish_kw = 0       # 同时命中钓鱼关键词
    porn_with_struct = 0         # 有结构钓鱼信号
    porn_en_url_bait = 0         # 英文+[URL]+短文本，疑似钓鱼/约会诱饵
    porn_tie_over_phish = 0      # 平局靠优先级压过钓鱼
    porn_score1_only = 0         # 仅 1 个色情词命中（弱证据）

    for rid in porn_ids:
        toks = tokens_map.get(rid, [])
        st = struct_map.get(rid, {})
        scores, hits, combo = rule_scores(toks, st, taxonomy, RULE_CATS, **KW)
        porn_s = scores["暴力色情"]
        phish_s = scores["钓鱼邮件"]
        if hits["钓鱼邮件"]:
            porn_with_phish_kw += 1
        if st.get("display_domain_mismatch") or st.get("url_suspicious") or st.get("url_sender_mismatch"):
            porn_with_struct += 1
        if len(hits["暴力色情"]) <= 1:
            porn_score1_only += 1
        if abs(porn_s - phish_s) < 1e-9 and phish_s > 0:
            porn_tie_over_phish += 1
        text = (text_map.get(rid, "") or "")
        toks_l = [str(t).lower() for t in toks]
        is_en = not any("\u4e00" <= c <= "\u9fff" for c in text)
        if is_en and ("[url]" in toks_l) and len(toks) <= 12:
            porn_en_url_bait += 1

    # 钓鱼标签平均得分（看 0.5 折算后还能赢，说明结构信号给力）
    phish_kw_only = 0
    phish_struct_help = 0
    for rid in phish_ids:
        toks = tokens_map.get(rid, [])
        st = struct_map.get(rid, {})
        scores, hits, combo = rule_scores(toks, st, taxonomy, RULE_CATS, **KW)
        if combo["strong_mismatch"] or combo["strong_susp"] or combo["combo_kw"] or combo["combo_short"] or combo["combo_dating"]:
            phish_struct_help += 1
        else:
            phish_kw_only += 1

    # 找出"仅1个色情词 + 有结构钓鱼信号"的邮件，命中的是哪个词（最可能的噪声词）
    noise_word = Counter()
    noise_word_en = Counter()
    for rid in porn_ids:
        toks = tokens_map.get(rid, [])
        st = struct_map.get(rid, {})
        scores, hits, combo = rule_scores(toks, st, taxonomy, RULE_CATS, **KW)
        has_struct = bool(st.get("display_domain_mismatch") or st.get("url_suspicious") or st.get("url_sender_mismatch"))
        if len(hits["暴力色情"]) == 1 and has_struct:
            w = hits["暴力色情"][0]
            noise_word[w] += 1
            if all(ord(c) < 128 for c in w):
                noise_word_en[w] += 1

    print("=== 单色情词 + 结构钓鱼信号 的命中词 Top30（最可能噪声）===")
    for w, c in noise_word.most_common(30):
        print(f"  {w}: {c}")
    print()
    print("=== 方案2 暴力色情 诊断 ===")
    print(f"暴力色情 总数: {len(porn_ids)}")
    print(f"  其中同时命中【钓鱼关键词】: {porn_with_phish_kw} ({porn_with_phish_kw/len(porn_ids)*100:.1f}%)")
    print(f"  其中带【结构钓鱼信号】(域名伪造/可疑URL/发件URL不一致): {porn_with_struct} ({porn_with_struct/len(porn_ids)*100:.1f}%)")
    print(f"  其中【与钓鱼平局靠优先级胜出】: {porn_tie_over_phish}")
    print(f"  其中【仅1个色情词命中】(弱证据): {porn_score1_only} ({porn_score1_only/len(porn_ids)*100:.1f}%)")
    print(f"  其中【英文+[URL]+短文本】疑似钓鱼诱饵: {porn_en_url_bait}")
    print()
    print("=== 方案2 钓鱼邮件 诊断 ===")
    print(f"钓鱼邮件 总数: {len(phish_ids)}")
    print(f"  靠结构信号组合命中: {phish_struct_help}")
    print(f"  纯关键词命中(无结构加成): {phish_kw_only}")

    # 钓鱼关键词折半(0.5)造成的假阴性：raw 钓鱼词数最多，却没被判钓鱼
    print("\n=== 钓鱼 0.5 折算造成的疑似假阴性 ===")
    all_ids = list(label_cat.keys())
    stolen_by = Counter()
    stolen_examples: dict[str, list[str]] = {}
    n_phish_raw_top = 0
    for rid in all_ids:
        toks = tokens_map.get(rid, [])
        st = struct_map.get(rid, {})
        scores, hits, combo = rule_scores(toks, st, taxonomy, RULE_CATS, **KW)
        raw = {c: len(hits[c]) for c in RULE_CATS}
        if raw["钓鱼邮件"] >= 2 and raw["钓鱼邮件"] == max(raw.values()) and label_cat[rid] != "钓鱼邮件":
            n_phish_raw_top += 1
            stolen_by[label_cat[rid]] += 1
            stolen_examples.setdefault(label_cat[rid], [])
            if len(stolen_examples[label_cat[rid]]) < 3:
                stolen_examples[label_cat[rid]].append(
                    f"{rid}: phish_kw={hits['钓鱼邮件'][:4]} -> {label_cat[rid]}_kw={hits[label_cat[rid]][:4]}")
    print(f"钓鱼原始词数>=2 且为最高，却被判别类: {n_phish_raw_top} 封")
    for c, n in stolen_by.most_common():
        print(f"  被『{c}』抢走: {n}")
        for ex in stolen_examples.get(c, []):
            print(f"      {ex}")

    # ===== 全量 what-if：不同 (钓鱼词权重, 优先级) 下重算分布 =====
    base_priority = {"暴力色情": 0, "钓鱼邮件": 1, "发票营销": 2, "学术营销": 3, "商业广告": 4}
    phish_first_priority = {"钓鱼邮件": 0, "暴力色情": 1, "发票营销": 2, "学术营销": 3, "商业广告": 4}

    def relabel(phish_w: float, priority: dict[str, int]) -> Counter:
        dist = Counter()
        for rid in all_ids:
            toks = tokens_map.get(rid, [])
            if not toks:
                dist["空样本"] += 1
                continue
            st = struct_map.get(rid, {})
            scores, hits, combo = rule_scores(toks, st, taxonomy, RULE_CATS, **KW)
            # 用自定义钓鱼词权重重算钓鱼关键词部分（结构加成已含在 scores 里，需扣回再加）
            kw_phish = len(hits["钓鱼邮件"])
            struct_add = scores["钓鱼邮件"] - 0.5 * kw_phish
            scores["钓鱼邮件"] = phish_w * kw_phish + struct_add
            best = max(scores, key=lambda c: (scores[c], -priority[c]))
            dist[best if scores[best] >= 1.0 else "未分类"] += 1
        return dist

    print("\n=== 全量 what-if：不同设置下方案2分布 ===")
    configs = [
        ("当前(钓鱼0.5, 色情优先)", 0.5, base_priority),
        ("钓鱼0.75, 色情优先", 0.75, base_priority),
        ("钓鱼1.0, 色情优先", 1.0, base_priority),
        ("钓鱼0.75, 钓鱼优先(平局)", 0.75, phish_first_priority),
        ("钓鱼1.0, 钓鱼优先(平局)", 1.0, phish_first_priority),
    ]
    for name, pw, pr in configs:
        d = relabel(pw, pr)
        order = ["暴力色情", "发票营销", "商业广告", "钓鱼邮件", "学术营销", "未分类", "空样本"]
        s = "  ".join(f"{c}:{d.get(c,0)}({d.get(c,0)/24000*100:.1f}%)" for c in order)
        print(f"[{name}]\n   {s}")


if __name__ == "__main__":
    main()
