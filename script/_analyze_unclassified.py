"""分析未分类（cluster 5）样本构成。"""
import csv
import json
import random
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

UNCLASS = "未分类"
unclass_ids: set[str] = set()
all_dist = Counter()
SCHEME1 = ROOT / "schemes" / "scheme1_semantic5"
with open(SCHEME1 / "outputs" / "submit.csv", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        all_dist[row["category"]] += 1
        if row["category"] == UNCLASS:
            unclass_ids.add(row["record_id"])

print(f"未分类总数: {len(unclass_ids)} ({len(unclass_ids)/24000*100:.1f}%)")

tokens_map: dict[str, list[str]] = {}
texts_map: dict[str, str] = {}
with open(ROOT / "data" / "tokenized_email.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        rid = o["record_id"]
        if rid in unclass_ids:
            tokens_map[rid] = o.get("tokens", [])
with open(ROOT / "data" / "concat_email.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        rid = o["record_id"]
        if rid in unclass_ids:
            texts_map[rid] = o.get("text", "")

struct_map: dict[str, dict] = {}
with open(ROOT / "data" / "structural_features.jsonl", encoding="utf-8") as f:
    for line in f:
        o = json.loads(line)
        if o["record_id"] in unclass_ids:
            struct_map[o["record_id"]] = o

# token length distribution
tok_lens = [len(t) for t in tokens_map.values()]
print(f"\n=== token 数分布 ===")
for lo, hi, label in [(0, 5, "≤5(极短)"), (6, 10, "6-10"), (11, 30, "11-30"), (31, 999, ">30")]:
    c = sum(1 for n in tok_lens if lo <= n <= hi)
    print(f"  {label}: {c} ({c/len(unclass_ids)*100:.1f}%)")

# language
lang_c = Counter(s.get("lang", "?") for s in struct_map.values())
print(f"\n=== 语言分布 ===")
for k, v in lang_c.most_common():
    print(f"  {k}: {v} ({v/len(unclass_ids)*100:.1f}%)")

# structural signals
print(f"\n=== 结构信号 ===")
for key in ("display_domain_mismatch", "url_suspicious", "url_sender_mismatch"):
    c = sum(1 for s in struct_map.values() if s.get(key))
    print(f"  {key}: {c} ({c/len(unclass_ids)*100:.1f}%)")

# placeholder-only patterns
def has_placeholder(toks: list[str]) -> bool:
    return any(t.startswith("[") and t.endswith("]") for t in toks)

url_only = sum(1 for t in tokens_map.values() if len(t) <= 8 and has_placeholder(t))
print(f"  短文本+URL/电话占位: {url_only} ({url_only/len(unclass_ids)*100:.1f}%)")

# heuristic subtypes (mutually exclusive priority)
HEUR = [
    ("英文dating/色情引流", [
        "dating", "female", "tonight", "sexual", "passion", "desire", "gentleman",
        "boyfriend", "girlfriend", "relationship", "master", "slave", "squeeze",
        "frisky", "climax", "adventurous", "date", "lonely", "girl", "gal",
        "巨奶", "合集", "裸", "激情", "约炮",
    ]),
    ("B2B/产品/零售营销", [
        "产品", "样本", "供货", "保修", "促销", "补货", "礼品", "会员", "festo",
        "sensor", "pneumatic", "catalog", "supplier", "wholesale", "offer",
        "book", "practices", "cost effective", "newsletter", "subscribe",
    ]),
    ("发票/财税漏网", [
        "发票", "普票", "专票", "开票", "增值税", "税点", "代开", "真票",
    ]),
    ("培训/课程/招聘", [
        "培训", "课程", "报名", "招聘", "就业", "专场", "python", "班",
        "register", "course", "webinar", "training",
    ]),
    ("钓鱼/链接诱导", [
        "account", "verify", "confirm", "security", "login", "password",
        "upgrade", "suspended", "mailbox", "click", "share what",
    ]),
    ("博彩漏网", [
        "博彩", "葡京", "彩金", "百家乐", "肖码", "黑庄", "打码", "bbin",
    ]),
    ("学术残片", [
        "conference", "journal", "sci", "papers", "manuscript", "投稿", "会议",
    ]),
    ("中文乱码/变体发票", [
        "普漂", "增普", "电微", "开漂", "项值", "可开",
    ]),
]

def match_any(toks: list[str], kws: list[str]) -> bool:
    joined = " ".join(toks)
    ts = set(toks)
    return any(k in joined or k in ts for k in kws)


def primary_type(rid: str) -> str:
    toks = tokens_map[rid]
    if len(toks) <= 5:
        return "极短/仅URL电话姓名"
    if len(toks) <= 10 and has_placeholder(toks):
        return "短文本+URL/电话"
    for name, kws in HEUR:
        if match_any(toks, kws):
            return name
    st = struct_map.get(rid, {})
    if st.get("url_sender_mismatch") or st.get("url_suspicious"):
        return "可疑链接但无语义词"
    lang = st.get("lang", "?")
    if lang == "en" and len(toks) <= 20:
        return "英文日常体/泛词邮件"
    if lang == "zh" and len(toks) <= 15:
        return "中文短碎片/变体spam"
    return "其他长文未命中"


primary = Counter(primary_type(rid) for rid in unclass_ids)
print(f"\n=== 主类型（互斥，按优先级）===")
for lb, cnt in primary.most_common():
    print(f"  {lb}: {cnt} ({cnt/len(unclass_ids)*100:.1f}%)")

# top tokens in unclassified
tok_freq = Counter()
for toks in tokens_map.values():
    for t in toks:
        if not (t.startswith("[") and t.endswith("]")):
            tok_freq[t] += 1
print(f"\n=== 未分类 Top 30 token ===")
for t, c in tok_freq.most_common(30):
    print(f"  {t}: {c}")

# global top tokens comparison - read from tfidf or cluster keywords
# sample per primary type
random.seed(42)
print(f"\n=== 各主类型抽样 ===")
by_type: dict[str, list[str]] = defaultdict(list)
for rid in unclass_ids:
    by_type[primary_type(rid)].append(rid)

for lb, _ in primary.most_common(8):
    ids = by_type[lb]
    print(f"\n--- {lb} (n={len(ids)}) ---")
    for rid in random.sample(ids, min(3, len(ids))):
        prev = texts_map.get(rid, "")[:140].replace("\n", " ")
        print(f"  [{rid}] {prev}")

# near-miss: would hit existing cats with score 0.5 (phishing single word) or 1
tax = json.load(open(SCHEME1 / "category_taxonomy.json", encoding="utf-8"))

def flatten(cat):
    words = []
    for key in ("zh", "en", "pinyin"):
        for w in tax["categories"][cat].get(key, []):
            words.append(w.lower() if key in ("en", "pinyin") else w)
    return words

def match_kw(kw, ts):
    if " " in kw:
        return all(p in ts for p in kw.split())
    return kw in ts

near_miss = Counter()
for rid, toks in tokens_map.items():
    ts = set(toks)
    for cat in ("暴力色情", "广告营销", "钓鱼邮件", "赌博博彩", "学术会议/期刊营销"):
        hits = sum(1 for w in flatten(cat) if match_kw(w, ts))
        if hits == 1:
            near_miss[cat] += 1
print(f"\n=== 差一词命中（仅1个关键词，未达阈值）===")
for cat, c in near_miss.most_common():
    print(f"  {cat}: {c} ({c/len(unclass_ids)*100:.1f}%)")

# themed overlap buckets
themes = {
    "讲座/培训通知spam": ["讲座", "培训", "通知", "前沿", "选课", "申报", "项目", "研讨会"],
    "技术告警/崩溃模板": ["fatal", "crashlytics", "fabric", "android", "java", "exception", "stack", "issue"],
    "能源/资讯推送": ["能源", "资讯", "订阅", "推送", "公众号", "天然气"],
    "LinkedIn/B2B询盘": ["linkedin", "buyer", "germany", "business", "cooperation", "quantity"],
    "Gmail转发+URL": ["forwarded", "wrote"],
    "中文博彩变体": ["三肖", "六码", "波色", "防码", "高手", "必中", "内幕"],
    "发票火星文变体": ["普票", "增普", "电威", "电微", "可开", "项值", "低验"],
    "中文色情漏网": ["乱交", "艹", "全裸", "天体营", "巨奶", "私聊"],
}
print("\n=== 主题桶（可重叠）===")
for name, kws in themes.items():
    c = sum(1 for t in tokens_map.values() if match_any(t, kws))
    print(f"  {name}: {c} ({c/len(unclass_ids)*100:.1f}%)")
