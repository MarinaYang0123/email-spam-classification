"""大批量扫描 cleaned_emails.jsonl，做细粒度主题画像，辅助设计均衡类别划分。

不写正式产物，只在控制台 + reports/results/balance_explore.md 打印统计：
  1) 每个细粒度主题的多标签命中数（可重叠）
  2) 按优先级做"单一最佳主题"归属后的分布
  3) 把细粒度主题聚合成候选宏类时各宏类的占比

用法：
  python script/explore_balance.py
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONCAT = DATA / "concat_email.jsonl"
TOKENS = DATA / "tokenized_email.jsonl"
STRUCT = DATA / "structural_features.jsonl"
OUT_MD = ROOT / "reports" / "results" / "balance_explore.md"


def load_jsonl(path: Path, key: str):
    out: dict[str, object] = {}
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            out[str(obj.get("record_id", ""))] = obj.get(key)
    return out


# ---- 细粒度主题检测器：每个返回该主题命中的"证据词"数量 ----
# 关键词在 token 集合或拼接文本（小写）里出现即记一次。

THEMES: dict[str, list[str]] = {
    # 色情：视频/图片/媒体类
    "porn_media": [
        "av", "无码", "有码", "国产", "偷拍", "自拍", "出兽", "罗莉", "幼女", "少妇",
        "成人", "城人", "情色", "色情", "三级", "做爱", "性爱", "裸聊", "裸照", "porn",
        "sex", "xxx", "adult", "视频", "影片", "电影", "私聊", "九电偷", "青城",
    ],
    # 色情：交友/约炮/约会诱导
    "porn_dating": [
        "约炮", "约会", "交友", "一夜情", "同城", "寂寞", "美女", "夜情", "找小姐",
        "dating", "single", "lonely", "profile", "desire", "relationship", "hookup",
        "naughty", "flirt", "match", "girl", "woman",
    ],
    # 壮阳/医药保健
    "health_pharma": [
        "壮阳", "伟哥", "减肥", "丰胸", "增大", "保健", "性功能", "早泄", "阳痿",
        "viagra", "cialis", "erectile", "dysfunction", "pill", "weight", "loss",
        "diabetes", "obesity", "pharmacy", "medicine",
    ],
    # 发票/财税
    "invoice": [
        "发票", "开票", "代开", "增值税", "专用发票", "普通发票", "报销", "报消",
        "税票", "核定征收", "做账", "记账", "设计费", "服务费", "广告费", "材料费",
        "劳务费", "培训费", "fapiao", "invoice",
    ],
    # 赌博博彩
    "gambling": [
        "葡京", "澳门", "bbin", "百家乐", "彩金", "打码", "博彩", "棋牌", "彩票",
        "赌场", "投注", "真人", "电子游戏", "晋升为", "任你玩", "特邀", "领彩",
        "企鹅", "casino", "betting", "gambling", "lottery", "jackpot", "poker", "slot",
    ],
    # 商业推广/展会/产品营销
    "commercial": [
        "展会", "展览", "产品", "报价", "招商", "促销", "优惠", "厂家", "批发",
        "供应", "采购", "设备", "机械", "公司", "招聘", "研讨会", "峰会", "论坛",
        "培训班", "研修", "贷款", "理财", "信用卡", "promotion", "discount", "newsletter",
        "unsubscribe", "shop", "purchase", "quotation", "wholesale",
    ],
    # 钓鱼：账号/邮箱/凭证
    "phish_account": [
        "account", "login", "登录", "登陆", "帐户", "账户", "password", "verify",
        "security", "confirm", "mailbox", "邮箱", "upgrade", "administrator", "suspend",
        "冻结", "解封", "验证码", "异常登录", "重新激活", "quarantine", "blocked",
    ],
    # 钓鱼/诈骗：中奖/继承/转账
    "phish_scam": [
        "lottery", "inheritance", "transfer", "winner", "congratulations", "fund",
        "beneficiary", "million", "dollars", "中奖", "继承", "汇款", "遗产", "swift",
        "wire", "payment", "claim", "prize",
    ],
    # 学术：会议/期刊/论文
    "academic": [
        "journal", "conference", "research", "international", "submit", "paper", "papers",
        "manuscript", "abstract", "issn", "sci", "ei", "science", "会议", "期刊", "论文",
        "投稿", "检索", "征稿", "学术", "版面费", "cpci", "doi",
    ],
}

# 用于"单一最佳主题"的优先级（数字小=优先），近似两套方案里的 rule_priority 思路
PRIORITY = [
    "porn_media", "porn_dating", "health_pharma", "gambling",
    "phish_account", "phish_scam", "invoice", "academic", "commercial",
]


def compile_word(w: str):
    # 纯英文/字母数字用词边界匹配；含中文直接 substring
    if re.fullmatch(r"[a-z0-9]+", w):
        return ("en", re.compile(r"\b" + re.escape(w) + r"\b"))
    return ("zh", w)


COMPILED = {t: [compile_word(w) for w in ws] for t, ws in THEMES.items()}


def theme_scores(blob: str) -> dict[str, int]:
    scores: dict[str, int] = {}
    for theme, words in COMPILED.items():
        c = 0
        for kind, pat in words:
            if kind == "en":
                if pat.search(blob):
                    c += 1
            else:
                if pat in blob:
                    c += 1
        scores[theme] = c
    return scores


def main() -> None:
    text_map = load_jsonl(CONCAT, "text")
    tokens_map = load_jsonl(TOKENS, "tokens")
    struct_map = {}
    with STRUCT.open("r", encoding="utf-8") as fin:
        for line in fin:
            if line.strip():
                o = json.loads(line)
                struct_map[str(o.get("record_id", ""))] = o

    rids = list(text_map.keys())
    total = len(rids)

    multi = Counter()           # 多标签：命中该主题(>0)的邮件数
    best = Counter()            # 单一最佳主题
    no_theme = 0
    struct_phish_only = 0       # 无词命中但结构钓鱼信号

    per_record_best: dict[str, str] = {}

    for rid in rids:
        text = text_map.get(rid) or ""
        toks = tokens_map.get(rid) or []
        if not text and not toks:
            best["__empty__"] += 1
            per_record_best[rid] = "__empty__"
            continue
        blob = (text + " " + " ".join(str(t) for t in toks)).lower()
        sc = theme_scores(blob)
        for t, v in sc.items():
            if v > 0:
                multi[t] += 1
        # 单一最佳：分数最高，平局按 PRIORITY
        ranked = sorted(sc.items(), key=lambda kv: (-kv[1], PRIORITY.index(kv[0])))
        top_theme, top_score = ranked[0]
        st = struct_map.get(rid, {})
        if top_score == 0:
            # 无词命中 → 看结构钓鱼信号
            if st.get("display_domain_mismatch") or st.get("url_suspicious") or st.get("url_sender_mismatch"):
                best["phish_account"] += 1
                per_record_best[rid] = "phish_account"
                struct_phish_only += 1
            else:
                best["__none__"] += 1
                per_record_best[rid] = "__none__"
                no_theme += 1
        else:
            best[top_theme] += 1
            per_record_best[rid] = top_theme

    lines: list[str] = []
    lines.append("# 均衡探索：细粒度主题画像\n")
    lines.append(f"- 总样本：**{total}**")
    lines.append(f"- 无任何词命中且无结构钓鱼信号：**{no_theme}**")
    lines.append(f"- 仅靠结构信号判钓鱼：**{struct_phish_only}**\n")

    lines.append("## 1. 多标签命中数（可重叠，单封邮件可命中多个主题）\n")
    lines.append("| 主题 | 命中邮件数 | 占比 |")
    lines.append("|---|---:|---:|")
    for t, c in multi.most_common():
        lines.append(f"| {t} | {c} | {c/total*100:.1f}% |")

    lines.append("\n## 2. 单一最佳主题分布（互斥，按分数+优先级）\n")
    lines.append("| 主题 | 数量 | 占比 |")
    lines.append("|---|---:|---:|")
    for t, c in best.most_common():
        lines.append(f"| {t} | {c} | {c/total*100:.1f}% |")

    # 候选宏类聚合方案
    groupings = {
        "方案A · 5类(拆色情)": {
            "色情视频媒体": ["porn_media"],
            "色情交友/医药诱导": ["porn_dating", "health_pharma"],
            "财税发票+商业广告": ["invoice", "commercial"],
            "钓鱼/诈骗": ["phish_account", "phish_scam"],
            "赌博+学术营销": ["gambling", "academic"],
        },
        "方案B · 5类(色情合并)": {
            "色情低俗": ["porn_media", "porn_dating", "health_pharma"],
            "发票财税": ["invoice"],
            "钓鱼诈骗": ["phish_account", "phish_scam"],
            "学术+赌博": ["academic", "gambling"],
            "商业广告": ["commercial"],
        },
        "方案C · 4类(各~25%)": {
            "色情低俗": ["porn_media", "porn_dating", "health_pharma"],
            "财税+商业营销": ["invoice", "commercial", "gambling"],
            "钓鱼诈骗": ["phish_account", "phish_scam"],
            "学术营销": ["academic"],
        },
    }

    lines.append("\n## 3. 候选宏类聚合（基于单一最佳主题）\n")
    for gname, mapping in groupings.items():
        lines.append(f"### {gname}\n")
        lines.append("| 宏类 | 细粒度主题 | 数量 | 占比 |")
        lines.append("|---|---|---:|---:|")
        covered = 0
        for macro, subs in mapping.items():
            cnt = sum(best.get(s, 0) for s in subs)
            covered += cnt
            lines.append(f"| {macro} | {'+'.join(subs)} | {cnt} | {cnt/total*100:.1f}% |")
        rest = total - covered
        lines.append(f"| (未覆盖: none/empty) | __none__/__empty__ | {rest} | {rest/total*100:.1f}% |")
        lines.append("")

    # ---- 4. 推荐 4 类：互斥归属，结构钓鱼仅作兜底，零未分类 ----
    # 优先级：色情 > 发票财税 > 学术 > 博彩 > 商业 > 钓鱼关键词；
    # 仍无命中再用结构钓鱼信号；最后语言兜底。
    MACRO_OF = {
        "porn_media": "色情低俗", "porn_dating": "色情低俗", "health_pharma": "色情低俗",
        "invoice": "财税发票",
        "academic": "商业·学术·博彩营销", "gambling": "商业·学术·博彩营销", "commercial": "商业·学术·博彩营销",
        "phish_account": "网络钓鱼与诈骗", "phish_scam": "网络钓鱼与诈骗",
    }
    MACRO_PRIORITY = ["porn_media", "porn_dating", "health_pharma",
                      "invoice", "academic", "gambling", "commercial",
                      "phish_account", "phish_scam"]
    four = Counter()
    for rid in rids:
        text = text_map.get(rid) or ""
        toks = tokens_map.get(rid) or []
        st = struct_map.get(rid, {})
        if not text and not toks:
            four["空样本"] += 1
            continue
        blob = (text + " " + " ".join(str(t) for t in toks)).lower()
        sc = theme_scores(blob)
        ranked = sorted(sc.items(), key=lambda kv: (-kv[1], MACRO_PRIORITY.index(kv[0])))
        top_theme, top_score = ranked[0]
        if top_score > 0:
            four[MACRO_OF[top_theme]] += 1
        elif st.get("display_domain_mismatch") or st.get("url_suspicious") or st.get("url_sender_mismatch"):
            four["网络钓鱼与诈骗"] += 1
        else:
            # 兜底：英文短文本/含URL→钓鱼，纯中文→商业，否则钓鱼
            if any("\u4e00" <= c <= "\u9fff" for c in blob):
                four["商业·学术·博彩营销"] += 1
            else:
                four["网络钓鱼与诈骗"] += 1

    lines.append("\n## 4. 【推荐】4 类互斥归属（零未分类）\n")
    lines.append("| 类别 | 数量 | 占比 |")
    lines.append("|---|---:|---:|")
    for t, c in four.most_common():
        lines.append(f"| {t} | {c} | {c/total*100:.1f}% |")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[written] {OUT_MD}")


if __name__ == "__main__":
    main()
