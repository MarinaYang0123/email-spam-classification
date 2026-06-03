from __future__ import annotations

import argparse
import html
import json
import re
import unicodedata
from collections import Counter, OrderedDict
from datetime import datetime
from pathlib import Path

from project_dirs import DATA_DIR, REPORTS_DIR, ensure_dir

ROOT = Path(__file__).resolve().parent.parent
LOG_FILE = DATA_DIR / "spam_email_data.log"
CLEAN_FILE = DATA_DIR / "cleaned_emails.jsonl"
MIN_CLEAN_FILE = DATA_DIR / "min_cleaned_email.jsonl"
FIELD_STATS_MD = REPORTS_DIR / "_field_stats.md"

_WS_RE = re.compile(r"\s+")
# 邮件「内容载体」字段：只要其中任意一个非空，就认为这条邮件有可用内容
PAYLOAD_FIELDS = ("subject","content", "doccontent")


def is_missing(v) -> bool:
    """None、空串、纯空白一律视为缺失。"""
    return v is None or (isinstance(v, str) and v.strip() == "")


def clean_value(v):
    """对单个字段值做与字段名无关的基础清洗：解码 + 去空白 + 去外层引号"""
    if not isinstance(v, str):
        return v
    s = html.unescape(v) #将字符串中的 HTML 实体字符还原为普通字符。
    s = unicodedata.normalize("NFKC", s) #使用 NFKC（兼容等价分解合并）模式对 Unicode 字符进行规范化。
    s = _WS_RE.sub(" ", s).strip() #将字符串中的连续空格替换为单个空格，并去除两端的空白字符。
    #如果清洗后的字符串为空，则返回空字符串。
    if s == "":
        return ""
    #如果清洗后的字符串为双引号包围的，则去除双引号。
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        s = s[1:-1].strip()
        if s == "":
            return ""
    return s


def parse_ts(s):
    """ISO 时间串 → 规范化字符串；解析失败返回 None。"""
    if not isinstance(s, str) or not s.strip():
        return None
    try:
        return datetime.fromisoformat(s.strip()).isoformat()
    except ValueError:
        return None


def clean_record(rid: str, obj: dict) -> dict:
    """单条原始记录 → 清洗后的字典；保留所有字段、不做优先级筛选。"""
    out: dict = {"record_id": rid}
    for k, v in obj.items():
        if k == "@timestamp":
            out["timestamp"] = parse_ts(v)
        else:
            out[k] = clean_value(v)
    return out


def load_rm_list(arg: str) -> set[str]:
    """加载 JSON 文件，返回待删除字段集合。"""
    candidates = [Path(arg)]
    if not candidates[0].is_absolute():
        candidates.append(ROOT / arg)
    for p in candidates:
        if p.exists():
            path = p
            break
    else:
        raise SystemExit(f"找不到字段列表 JSON：{arg}")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path} 不是合法 JSON：{exc}") from exc
    if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
        raise SystemExit(f"{path} 内容应为字符串数组，例如 [\"timestamp\", \"wlistcnt\"]")
    return set(data)


def write_min_jsonl(src: Path, dst: Path, rm_fields: set[str]) -> None:
    """逐行读取 src JSONL，去掉 rm_fields 中的键后写入 dst"""
    ensure_dir(dst.parent)
    with src.open("r", encoding="utf-8") as fin, dst.open("w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            for k in rm_fields:
                obj.pop(k, None)
            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="邮件原始日志：基础清洗 + 字段统计；可选剥离指定字段输出精简版 JSONL。",
    )
    parser.add_argument(
        "--min_analysis", metavar="REMOVE_LIST_JSON", default=None,
        help="待删除字段列表 JSON 路径，开启后额外输出 min_cleaned_email.jsonl",
    )
    args = parser.parse_args()

    if not LOG_FILE.exists():
        raise SystemExit(f"找不到原始日志：{LOG_FILE}")
    ensure_dir(DATA_DIR)
    ensure_dir(REPORTS_DIR)

    #统计字段出现次数、非空次数、类型
    total = bad = has_payload = 0
    present: Counter = Counter()
    nonempty: Counter = Counter()
    types: dict[str, Counter] = {}
    first_seen: "OrderedDict[str, int]" = OrderedDict()

    with LOG_FILE.open("r", encoding="utf-8", errors="replace") as fin, CLEAN_FILE.open("w", encoding="utf-8") as fout:
        for line_no, raw in enumerate(fin, 1):
            raw = raw.rstrip("\r\n")
            if not raw:
                continue
            rid, _, js = raw.partition("\t")
            try:
                obj = json.loads(js)
            except json.JSONDecodeError:
                bad += 1
                continue
            total += 1
            for k, v in obj.items():
                present[k] += 1
                if not is_missing(v):
                    nonempty[k] += 1
                types.setdefault(k, Counter())[type(v).__name__] += 1
                first_seen.setdefault(k, line_no)
            if any(not is_missing(obj.get(f)) for f in PAYLOAD_FIELDS):
                has_payload += 1
            fout.write(json.dumps(clean_record(rid, obj), ensure_ascii=False) + "\n")

    payload_rate = has_payload / total if total else 0.0
    payload_label = "/".join(PAYLOAD_FIELDS)
    
    #输出字段统计报告
    md = [
        f"- 总记录数：**{total}**",
        f"- 解析失败行数：**{bad}**",
        f"- JSON 中出现过的字段数：**{len(present)}**",
        f"- 有内容载体的记录数（`{payload_label}` 中至少有一个非空）："
        f"**{has_payload}**（占 **{payload_rate*100:.2f}%**）",
        "",
        "| # | 字段 | 出现次数 | 出现率 | 非空次数 | 缺失率 | 取值类型 |",
        "|---:|---|---:|---:|---:|---:|---|",
    ]
    for idx, f in enumerate(first_seen, 1):
        p, ne = present[f], nonempty[f]
        miss = 1 - ne / total if total else 0.0
        pres = p / total if total else 0.0
        t = ",".join(f"{k}:{v}" for k, v in types[f].most_common())
        md.append(f"| {idx} | `{f}` | {p} | {pres*100:.2f}% | {ne} | {miss*100:.2f}% | {t} |")

    FIELD_STATS_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Field stats → {FIELD_STATS_MD.relative_to(ROOT)}")
    print(f"Cleaned JSONL → {CLEAN_FILE.relative_to(ROOT)}")

    if args.min_analysis:
        rm_fields = load_rm_list(args.min_analysis)
        write_min_jsonl(CLEAN_FILE, MIN_CLEAN_FILE, rm_fields)
        print(f"Min JSONL → {MIN_CLEAN_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
