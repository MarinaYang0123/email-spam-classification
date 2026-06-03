"""并行结构特征流：从全字段 cleaned_emails.jsonl 派生钓鱼 / 风控结构特征。

输入  : data/cleaned_emails.jsonl   （data_explore.py 的全字段产物）
输出  : data/structural_features.jsonl

设计要点：
  * 不动 min_cleaned_email.jsonl / 深度清洗 / TF-IDF 那条文本线，纯只读派生。
  * 用 record_id 与文本特征对齐，供 hybrid_classify.py 的钓鱼规则使用。
  * 派生信号围绕「发件人伪造 + 可疑 URL + 域名信誉」这三类钓鱼核心特征。

字段含义见 README。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from project_dirs import DATA_DIR, ensure_dir

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = DATA_DIR / "cleaned_emails.jsonl"
OUTPUT_FILE = DATA_DIR / "structural_features.jsonl"

# from 字段形如：  "display name" <local@domain>
EMAIL_IN_ANGLE_RE = re.compile(r"<([^<>@\s]+@[^<>\s]+)>")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})")
# 域名样式（用于判断显示名里是否「自称」某个域名）
DOMAIN_RE = re.compile(r"\b([A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+\.[A-Za-z]{2,})\b")
URL_RE = re.compile(r"https?://([^/\s:]+)(?:[:/][^\s]*)?", re.IGNORECASE)
CJK_RE = re.compile(r"[\u4e00-\u9fff]")
ASCII_ALPHA_RE = re.compile(r"[A-Za-z]")

# URL 路径里出现这些片段，强烈暗示「收凭证 / 仿冒登录」型钓鱼
SUSPICIOUS_URL_PARTS = (
    "login", "signin", "sign-in", "verify", "verification", "update",
    "account", "secure", "security", "confirm", "webscr", "password",
    "unlock", "validate", "index.php?email", "wp-login", "auth",
)


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fin:
        for line_no, line in enumerate(fin, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path} 第 {line_no} 行不是合法 JSON：{exc}") from exc


def domain_of_email(value: str) -> str:
    """从 'local@domain' 或含尖括号的 from 串里取真实发件域名（小写）。"""
    if not value:
        return ""
    m = EMAIL_IN_ANGLE_RE.search(value)
    candidate = m.group(1) if m else value
    m2 = EMAIL_RE.search(candidate)
    return m2.group(1).lower() if m2 else ""


def display_name_of(from_value: str, fromname: str) -> str:
    """优先取 from 里引号包着的显示名；否则退回 fromname。"""
    if from_value:
        # 去掉尖括号邮箱部分，剩下的就是显示名候选
        without_email = EMAIL_IN_ANGLE_RE.sub("", from_value).strip().strip('"').strip()
        if without_email:
            return without_email
    return (fromname or "").strip().strip('"').strip()


def domain_in_text(text: str) -> str:
    """文本里第一个像域名的串（小写）；没有返回空。"""
    if not text:
        return ""
    m = DOMAIN_RE.search(text)
    return m.group(1).lower() if m else ""


def extract_url_domains(url_blob: str) -> list[str]:
    """url 字段是空格分隔的混合串，抽出其中 http(s) URL 的域名（小写、去重保序）。"""
    if not url_blob:
        return []
    domains: list[str] = []
    for m in URL_RE.finditer(url_blob):
        d = m.group(1).lower().lstrip("www.")
        if d and d not in domains:
            domains.append(d)
    return domains


def url_is_suspicious(url_blob: str) -> bool:
    if not url_blob:
        return False
    low = url_blob.lower()
    return any(part in low for part in SUSPICIOUS_URL_PARTS)


def domainrep_max(value: str) -> float:
    """'0.02;0.00;0.04;0.92;' → 0.92；解析失败返回 0.0。"""
    if not value:
        return 0.0
    best = 0.0
    for piece in value.split(";"):
        piece = piece.strip()
        if not piece:
            continue
        try:
            best = max(best, float(piece))
        except ValueError:
            continue
    return best


def detect_lang(text: str) -> str:
    """按 CJK / ASCII 字母占比判定 zh / en / mixed / unknown（纯启发式）。"""
    if not text:
        return "unknown"
    cjk = len(CJK_RE.findall(text))
    ascii_alpha = len(ASCII_ALPHA_RE.findall(text))
    total = cjk + ascii_alpha
    if total == 0:
        return "unknown"
    cjk_ratio = cjk / total
    if cjk_ratio >= 0.5:
        return "zh"
    if cjk_ratio <= 0.15:
        return "en"
    return "mixed"


def same_registrable(a: str, b: str) -> bool:
    """粗粒度同域判断：取末两段比较（foo.example.com 与 mail.example.com 视为同域）。"""
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = a.split("."), b.split(".")
    return ta[-2:] == tb[-2:] and len(ta) >= 2 and len(tb) >= 2


def build_features(obj: dict) -> dict:
    record_id = str(obj.get("record_id", ""))
    from_value = obj.get("from", "") or ""
    sender = obj.get("sender", "") or ""
    fromname = obj.get("fromname", "") or ""
    url_blob = obj.get("url", "") or ""
    htmlurl = obj.get("htmlurl", "") or ""
    attach = obj.get("attach", "") or ""
    subject = obj.get("subject", "") or ""
    content = obj.get("content", "") or ""

    sender_domain = domain_of_email(sender) or domain_of_email(from_value)
    display_name = display_name_of(from_value, fromname)
    display_domain = domain_in_text(display_name)

    # 显示名「自称」了某个域名，且与真实发件域不同 → 伪造嫌疑
    display_domain_mismatch = bool(
        display_domain and sender_domain and not same_registrable(display_domain, sender_domain)
    )

    url_domains = extract_url_domains(url_blob) or extract_url_domains(htmlurl)
    url_sender_mismatch = bool(
        sender_domain and url_domains
        and not any(same_registrable(d, sender_domain) for d in url_domains)
    )

    return {
        "record_id": record_id,
        "sender_domain": sender_domain,
        "display_name": display_name,
        "display_domain": display_domain,
        "display_domain_mismatch": display_domain_mismatch,
        "url_count": len(url_domains),
        "url_domains": url_domains,
        "url_sender_mismatch": url_sender_mismatch,
        "url_suspicious": url_is_suspicious(url_blob) or url_is_suspicious(htmlurl),
        "domainrep_max": round(domainrep_max(obj.get("domainrep", "")), 4),
        "has_attach": bool(attach.strip()),
        "lang": detect_lang(f"{subject} {content}"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="从全字段邮件派生钓鱼 / 风控结构特征。")
    parser.add_argument("--input", type=Path, default=INPUT_FILE,
                        help=f"输入全字段 JSONL，默认 {INPUT_FILE.relative_to(ROOT)}")
    parser.add_argument("--output", type=Path, default=OUTPUT_FILE,
                        help=f"输出结构特征 JSONL，默认 {OUTPUT_FILE.relative_to(ROOT)}")
    args = parser.parse_args()

    if not args.input.exists():
        raise SystemExit(f"找不到输入文件：{args.input}")
    ensure_dir(DATA_DIR)
    ensure_dir(args.output.parent)

    n = 0
    stats = {
        "display_domain_mismatch": 0,
        "url_sender_mismatch": 0,
        "url_suspicious": 0,
        "domainrep_high": 0,
        "has_attach": 0,
        "lang_zh": 0,
        "lang_en": 0,
        "lang_mixed": 0,
    }

    with args.output.open("w", encoding="utf-8") as fout:
        for obj in iter_jsonl(args.input):
            feat = build_features(obj)
            fout.write(json.dumps(feat, ensure_ascii=False) + "\n")
            n += 1
            if feat["display_domain_mismatch"]:
                stats["display_domain_mismatch"] += 1
            if feat["url_sender_mismatch"]:
                stats["url_sender_mismatch"] += 1
            if feat["url_suspicious"]:
                stats["url_suspicious"] += 1
            if feat["domainrep_max"] >= 0.5:
                stats["domainrep_high"] += 1
            if feat["has_attach"]:
                stats["has_attach"] += 1
            stats[f"lang_{feat['lang']}"] = stats.get(f"lang_{feat['lang']}", 0) + 1

    print(f"结构特征完成：{n} 条 → {args.output.relative_to(ROOT) if args.output.is_relative_to(ROOT) else args.output}")
    print("  钓鱼相关信号命中：")
    print(f"    显示名域名不一致 : {stats['display_domain_mismatch']}")
    print(f"    URL 与发件域不一致: {stats['url_sender_mismatch']}")
    print(f"    可疑 URL 路径     : {stats['url_suspicious']}")
    print(f"    域名信誉≥0.5      : {stats['domainrep_high']}")
    print(f"    含附件            : {stats['has_attach']}")
    print(f"  语言分布：zh={stats['lang_zh']}  en={stats['lang_en']}  mixed={stats['lang_mixed']}")


if __name__ == "__main__":
    main()
