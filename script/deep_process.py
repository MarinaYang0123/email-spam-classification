"""深度清洗：繁简归一 + 异体字映射 + 联系方式占位符化 + 字符过滤 + 汉字间空格合并。

输入  : data/min_cleaned_email.jsonl    （由 data_explore.py 生成的精简版）
输出  : data/deep_cleaned_email.jsonl   （仅对 subject/content/doccontent 做归一化）

按顺序作用于每条文本字段：

  -1) 主题专用：剥掉 Re: / Fwd: / FW: 这类邮件系统自动前缀。
  0)  异体字 / 火星文兜底（mars_chars.json）：兲 → 天、噺 → 新、囙 → 回 等。
  0.5)繁体 → 简体（OpenCC t2s）：澳門 → 澳门、賺取遊戲 → 赚取游戏。
       注意 mars 必须先于 opencc，否则会被映射成更冷僻的字（紟 → 𫄛）。

  1) 正则替换为统一占位符（顺序敏感：URL 优先；其它带关键字前缀的规则早于
     通用 PHONE 兜底；URL/EMAIL 必须早于第 2 阶段，否则 ://、@、. 等会被
     当作普通标点过滤掉）
       URL             → [URL]（若路径里含 a-b-c 形式的连字符英文，再追加抽出的关键词）
       邮箱            → [EMAIL]
       手机/座机号码   → [PHONE]
       QQ 号           → [QQ]
       微信号          → [WECHAT]
       价格金额(元/圆) → [MONEY]

  2) 字符级过滤：只保留汉字、英文单词、第 1 步产出的占位符；
       其余字符（数字、标点、★ ☆ ◆ ▲ 【】、连续 ++/-- 等）一律丢弃；
       多个保留 token 之间合并为单个空格。

  3) 删掉夹在汉字中间的单个英文字母（"黑丝 D 爆乳" → "黑丝爆乳"），用来打散
       "焚 w 宿 w 庄 w 挨"、"帐户 x 已 w" 这类用单字母打码的对抗写法。
       注意：会顺带丢掉「A股、B超、T台、K线」等少量本身有意义的单字母组合，
       属于既定 trade-off。

  4) 合并被空格分隔的相邻汉字（如「增 值 发 票」→「增值发票」），
       占位符 / 英文 与汉字之间的空格保持原样。

依赖：opencc-python-reimplemented（仅 0.5 步用到）；缺失时自动跳过繁简转换并提示。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from project_dirs import DATA_DIR, REPORTS_DIR, ensure_dir

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = DATA_DIR / "min_cleaned_email.jsonl"
OUTPUT_FILE = DATA_DIR / "deep_cleaned_email.jsonl"
CONFIG_DIR = ROOT / "config"
MARS_FILE = CONFIG_DIR / "mars_chars.json"
PHRASE_FILE = CONFIG_DIR / "phrase_map.json"
WHITELIST_FILE = CONFIG_DIR / "single_en_whitelist.json"
AUDIT_FILE = REPORTS_DIR / "single_en_audit.jsonl"

# 仅对这些字段做深度清洗；其余字段（如 record_id）原样保留
TEXT_FIELDS = ("subject", "content", "doccontent","fromname")


# ---------------------------------------------------------------------------
# 0) 繁简转换 + 异体字映射
# 这两步一起放最前面：先把字面归一化，后面的正则（特别是 MONEY 里的 [元圆]、
# WECHAT 里的"信"、QQ 关键字"号"）才能稳定命中。
# ---------------------------------------------------------------------------

def _try_load_opencc():
    """优雅依赖：opencc 装了就用，没装就回退为恒等函数并给一次提示。"""
    try:
        from opencc import OpenCC  # type: ignore
    except ImportError:
        print(
            "[警告] 未安装 opencc-python-reimplemented，跳过繁简转换。"
            "如需启用：pip install opencc-python-reimplemented"
        )
        return None
    return OpenCC("t2s")  # Traditional → Simplified


_OPENCC = _try_load_opencc()


def _load_mars_table(path: Path) -> dict:
    """读 JSON 字典 → str.translate 用的码点表；忽略 _comment 这类下划线开头的元信息键。"""
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path} 应为 {{...}} 字符映射字典")
    pairs: dict[int, str] = {}
    for k, v in raw.items():
        if k.startswith("_"):
            continue
        if not isinstance(v, str) or len(k) != 1:
            raise SystemExit(f"{path}：键必须是单个字符，值必须是字符串；非法项 {k!r}: {v!r}")
        pairs[ord(k)] = v
    return pairs


_MARS_TABLE: dict[int, str] = _load_mars_table(MARS_FILE)


def normalize_chinese(text: str) -> str:
    """异体字兜底（mars_chars.json）→ 繁体 → 简体（opencc t2s）。

    注意 mars 必须在 opencc 之前：opencc 偶尔会把对抗字符映射到更冷僻的字
    （实测 紟 → 𫄛，落到了 BMP 之外），先用 mars 把已知对抗字直接钉到标准简体，
    后续 opencc 看到的就是规范字符，不会再做奇怪的映射。
    """
    if _MARS_TABLE:
        text = text.translate(_MARS_TABLE)
    if _OPENCC is not None:
        text = _OPENCC.convert(text)
    return text


# ---------------------------------------------------------------------------
# 0.8) 短语级归一（同音不同形）
# 说明：
#   - 仅做“精确子串”替换：适合处理法票→发票、加威信→加微信这类对抗写法；
#   - 放在占位符正则之前，让归一后的“微信/发票”还能被后续规则稳定命中；
#   - 由于第 2 阶段会丢弃标点符号，本层主要针对“字形替换”而非“符号打断”。
# ---------------------------------------------------------------------------

def _load_phrase_map(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{path} 应为 JSON 对象")
    patterns = raw.get("patterns", {})
    if not isinstance(patterns, dict):
        raise SystemExit(f"{path} 的 patterns 应为 {{'old': 'new', ...}}")
    out: dict[str, str] = {}
    for k, v in patterns.items():
        if not isinstance(k, str) or not isinstance(v, str) or not k or not v:
            raise SystemExit(f"{path}：patterns 的键和值都必须是非空字符串；非法项 {k!r}: {v!r}")
        out[k] = v
    return out


_PHRASE_MAP: dict[str, str] = _load_phrase_map(PHRASE_FILE)
_PHRASE_RE: "re.Pattern[str] | None" = (
    re.compile("|".join(re.escape(k) for k in sorted(_PHRASE_MAP, key=len, reverse=True)))
    if _PHRASE_MAP
    else None
)


def normalize_phrases(text: str, counter: Counter) -> str:
    if _PHRASE_RE is None or not text:
        return text

    def _sub(m: "re.Match[str]") -> str:
        src = m.group(0)
        counter[f"PHRASE:{src}"] += 1
        return _PHRASE_MAP.get(src, src)

    # 支持级联归一：例如 "蕟漂" 先变成 "发票"，随后整段
    # "税务代开发票威信" 再变成 "税务代开发票微信"。
    for _ in range(3):
        new_text = _PHRASE_RE.sub(_sub, text)
        if new_text == text:
            break
        text = new_text
    return text


# ---------------------------------------------------------------------------
# 1) 占位符替换正则
# 顺序很重要：URL 最先（URL 本身可能内嵌 @、数字串等，先整体吃掉避免误判）；
# 然后 EMAIL；接着 QQ / 微信（带前缀关键字的更"具体"，应优先于通用 PHONE
# 规则），最后 PHONE / MONEY。
# ---------------------------------------------------------------------------

# URL：http(s)://… 或 www.…；只匹配 ASCII 可见字符（遇到汉字 / 空白即停），
#   避免吞掉中文正文。
URL_RE = re.compile(
    r"https?://[^\s\u4e00-\u9fff]+"
    r"|(?<![A-Za-z0-9])www\.[A-Za-z0-9.\-]+(?:/[^\s\u4e00-\u9fff]*)?",
    re.IGNORECASE,
)

# 「语义片段」：a-b 这种连字符串接的多段纯英文词；用来从 URL 路径里抽关键词，
#   如 dating-site / servic-paypal / online-shop。带数字的随机串（如
#   amme2013-2020）和短链 hash（JjwrV、qiz35Z11）会被这条规则天然过滤掉。
URL_SEMANTIC_RE = re.compile(r"[A-Za-z]{2,}(?:-[A-Za-z]{2,})+")

# 邮箱：local@domain.tld（domain 至少含一个 .）
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# QQ：qq / QQ + 可选"号" + 可选分隔符( : ： ; ； 空白 ) + 5~12 位数字
#   命中样例：qq:1275411573 / QQ958231120 / QQ;1838442881 / 加QQ:1954001114
QQ_RE = re.compile(r"[Qq]{2}\s*号?\s*[:：;；]?\s*\d{5,12}")

# 微信：微信 / 微 信 / 微.信 / wechat / WeChat（不强求后跟号码，号码会被 PHONE 单独命中）
#   命中样例：微信:15813845149 / 微.信.同.号 / 微 信ningxiaolin@... / +微信(苏经理)
WECHAT_RE = re.compile(
    r"微\s*[\.,，]?\s*信(?:\s*号)?"
    r"|[Ww]e\s*[Cc]hat"
)

# 电话：11 位手机号 或 区号(3~4 位) + 7~8 位座机；允许中间用空格 / - 分隔。
# 用 (?<!\d) (?!\d) 避免吞掉超长数字串中的子序列（如订单号、追踪号）。
PHONE_RE = re.compile(
    r"(?<!\d)"
    r"(?:1[3-9]\d[\s\-]?\d{4}[\s\-]?\d{4}"   # 13x-19x 开头的 11 位手机
    r"|0\d{2,3}[\s\-]?\d{7,8})"              # 0xx 开头的座机
    r"(?!\d)"
)

# 价格 / 金额：78元 / 3980元/人 / 188圆 / 1500元/天
MONEY_RE = re.compile(r"\d+(?:\.\d+)?\s*[元圆](?:\s*/\s*[^\s\d/]{1,3})?")


# ---------------------------------------------------------------------------
# 2) 字符过滤：findall 出"汉字串 / 英文串 / 占位符"，其余全部丢掉
# ---------------------------------------------------------------------------
KEEP_RE = re.compile(
    r"\[(?:URL|EMAIL|PHONE|QQ|WECHAT|MONEY)\]"   # 已归一化的占位符
    r"|[\u4e00-\u9fff]+"                         # 连续汉字
    r"|[A-Za-z]+"                                # 连续英文字母
)


# ---------------------------------------------------------------------------
# 主题前缀：Re: / Fwd: / FW: 等邮件系统自动前缀（可堆叠 "Re: Re: Re: 标题"），
#   仅作用于 subject。要求带冒号，避免误伤以 Re/Fw 开头的正常英文词（Reply/Few...）。
# ---------------------------------------------------------------------------
SUBJECT_PREFIX_RE = re.compile(
    r"^(?:(?:Re|Fwd?|FYI|答复|回复|转发)\s*[:：]\s*)+",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# 3a) 把全文中连续 ≥3 个单字母段（"S C I"、"I C A E E"、"R D" 这类）合并成连写
#     大写形式。阈值 3 是为了避开英文撇号缩略（"I m"/"I d"/"a m"/"p m"）和德语
#     变音缩略（"f r" = "für"）—— 这类 ≥2 的 false positive 很多；而 ≥3 的运行段
#     几乎一定是被打散的缩写或专业术语。
#
#     这一步比 SINGLE_EN_BETWEEN_ZH_RE 更通用：不要求两侧是汉字，开头 / 结尾 /
#     紧邻占位符 / 夹在英文中的 "S C I" 都能被吃掉，下游 jieba 才能把 "SCI" 当
#     一个有判别力的 token；否则会被切成 [S, C, I] 三个单字母，全在 min_df 阶段
#     被过滤掉，等于直接丢失这个特征。
# ---------------------------------------------------------------------------
SPACED_ACRONYM_RE = re.compile(
    r"(?<![A-Za-z])(?:[A-Za-z]\s+){2,}[A-Za-z](?![A-Za-z])"
)


def _join_spaced_acronyms(text: str, counter: Counter) -> str:
    """把 'S C I' / 'I C A E E' 等空格分隔的缩写合并为大写连写形式。"""
    def _sub(m: "re.Match[str]") -> str:
        counter["SPACED_ACRONYM_MERGED"] += 1
        return "".join(m.group(0).split()).upper()
    return SPACED_ACRONYM_RE.sub(_sub, text)


# ---------------------------------------------------------------------------
# 3a-bis) 列表驱动的缩写合并：以 single_en_whitelist.json 中 ≥3 字母的纯缩写为
#   基准，把任何被空白拆开的写法（"SC I"、"S CI"、"S C I"、"GS K I"、"G SKI"
#   等）统一合并回连写大写形式。这是对 SPACED_ACRONYM_RE 的兜底——后者要求
#   "全部都是单字母段"，遇到 "SC I" 这种半合并就会断；而本规则不依赖单字母约束。
#
#   只对 ≥3 字母的缩写生效：长度 2（AI / ML / EI...）误伤面太大，"A I am" 里
#   的冠词 + 代词、"E I core" 里的标点切分都可能命中，得不偿失。
# ---------------------------------------------------------------------------

def _compile_known_acronym_re(words: set[str]) -> "re.Pattern[str] | None":
    """从白名单里挑出 ≥3 字母的纯字母缩写，构造一个不区分大小写的合并正则。

    每个缩写 X1X2...Xn 展开为 X1\\s*X2\\s*...\\s*Xn，前后用 (?<![A-Za-z])(?![A-Za-z])
    锁边界，避免吞进 SCIENTIST、ASCII 这类长词的子串。按长度降序排列，让更长
    的缩写在 alternation 里优先匹配，避免 ICAEE 被先匹配成 SCI。
    """
    cands = sorted(
        {w.upper() for w in words if len(w) >= 3 and w.isascii() and w.isalpha()},
        key=lambda x: (-len(x), x),
    )
    if not cands:
        return None
    parts = [r"\s*".join(re.escape(c) for c in w) for w in cands]
    return re.compile(
        r"(?<![A-Za-z])(?:" + "|".join(parts) + r")(?![A-Za-z])",
        re.IGNORECASE,
    )


def _join_known_acronyms(text: str, counter: Counter) -> str:
    """对照 whitelist 中的已知缩写，把任何被空白拆碎的写法合并为大写连写。"""
    if _KNOWN_ACRONYM_RE is None:
        return text

    def _sub(m: "re.Match[str]") -> str:
        merged = "".join(m.group(0).split()).upper()
        # 只在原串与合并后形式不同（即原串确实包含空白）时才计数；纯连写
        # 写法（'SCI'）会被这条规则"原样"替换为自己，不算实质性合并。
        if m.group(0) != merged:
            counter["KNOWN_ACRONYM_MERGED"] += 1
        return merged

    return _KNOWN_ACRONYM_RE.sub(_sub, text)


# ---------------------------------------------------------------------------
# 3b) 删掉夹在汉字中间的单个英文字母：用 (?:\s+[A-Za-z])+ 一次性吃掉一段连续的
#    "汉字 (空格 单字母)+ 空格 汉字" 序列；多字母英文词（VIP / dating / IBM）
#    长度 ≥2 不会被这条规则误伤。
#
#    白名单：A股 / B超 / X光 / SCI / ICAEE 等合法搭配从 single_en_whitelist.json
#    读入；命中时这一段会被原样保留。匹配前会把字母段里的空白吃掉，所以
#    "I C A E E" 也会被规约成 "ICAEE" 后再查表，且大小写不敏感。
# ---------------------------------------------------------------------------
SINGLE_EN_BETWEEN_ZH_RE = re.compile(
    r"(?<=[\u4e00-\u9fff])(?:\s+[A-Za-z])+\s+(?=[\u4e00-\u9fff])"
)


def _normalize_whitelist_entry(entry: str) -> str:
    """对 whitelist 项内 ASCII 字母段做大写化；汉字保持原样。"""
    return "".join(c.upper() if c.isascii() and c.isalpha() else c for c in entry)


def _load_single_en_whitelist(path: Path) -> set[str]:
    """读 single_en_whitelist.json → 大写化（仅字母部分）后的集合。

    支持两种格式：
        {"_comment": "...", "patterns": ["A股", "SCI", ...]}     ← 推荐
        ["A股", "SCI", ...]
    """
    if not path.exists():
        return set()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, dict):
        patterns = raw.get("patterns", [])
    elif isinstance(raw, list):
        patterns = raw
    else:
        raise SystemExit(f"{path}: 应为 patterns 列表或 {{patterns: [...]}} 对象")
    if not all(isinstance(p, str) for p in patterns):
        raise SystemExit(f"{path}: patterns 中每一项必须是字符串")
    return {_normalize_whitelist_entry(p) for p in patterns if p}


_SINGLE_EN_WHITELIST: set[str] = _load_single_en_whitelist(WHITELIST_FILE)
# 列表驱动的缩写合并正则：从同一份 whitelist 抽 ≥3 字母的纯缩写编译而成。
_KNOWN_ACRONYM_RE = _compile_known_acronym_re(_SINGLE_EN_WHITELIST)


# ---------------------------------------------------------------------------
# 4) 把「汉字 + 一段空白 + 汉字」之间的空白吃掉（lookaround 不消耗字符，一次
#    扫描就能处理 "我 们 好" → "我们好"，但保留 "我 [QQ]" / "我 abc" 中的空格）
# ---------------------------------------------------------------------------
ZH_SPACE_RE = re.compile(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])")


def _replace_url(match: "re.Match[str]") -> str:
    """把整段 URL 替换为 [URL]；若路径含 a-b 形式的英文连字符词，再补抽关键词。"""
    url = match.group(0).rstrip(".,;:!?)\"'")
    keywords = URL_SEMANTIC_RE.findall(url)
    if keywords:
        # 连字符在第 2 阶段会被丢掉；这里直接拆成空格分隔的英文词，下游 token 化更友好
        words = " ".join(k.replace("-", " ").lower() for k in keywords)
        return f"[URL] {words}"
    return "[URL]"


def _apply_single_en_filter(
    text: str,
    *,
    counter: Counter,
    record_id: str = "",
    field: str = "",
    audit_buf: list[dict] | None = None,
    ctx_chars: int = 8,
) -> str:
    """逐处判断单字母段是否在白名单里，命中→保留、未命中→剥离。

    audit_buf 不为空时，把"被剥掉"的命中（不含被白名单保留的）写到列表，便于
    人工审计仍在删的内容是否还有漏网之鱼。
    """
    matches = list(SINGLE_EN_BETWEEN_ZH_RE.finditer(text))
    if not matches:
        return text

    pieces: list[str] = []
    last_end = 0
    audit_matches: list[dict] = []

    for m in matches:
        # 把上一段未命中的部分原样接上
        pieces.append(text[last_end:m.start()])

        # 把字母段里所有空白吃掉再大写化："I C A E E" → "ICAEE"，"a" → "A"
        letters_upper = "".join(m.group(0).split()).upper()
        # 紧邻的右侧汉字（lookahead 保证一定存在）
        right_zh = text[m.end():m.end() + 1]

        # 两类命中都视为"白名单"：纯字母缩写（SCI、ICAEE）或字母+紧邻汉字（A股、B超）
        keep = (
            letters_upper in _SINGLE_EN_WHITELIST
            or (letters_upper + right_zh) in _SINGLE_EN_WHITELIST
        )

        if keep:
            # 命中白名单 → 同样输出归一化形式：去掉字母间空白 + 大写化。
            # 两侧补单个空格保留与左右汉字的分界（与 KEEP_RE 的单空格 join 风格一致），
            # 避免后续 ZH_SPACE_RE 把汉字粘到字母上。
            pieces.append(f" {letters_upper} ")
            counter["SINGLE_EN_KEPT"] += 1
        else:
            counter["SINGLE_EN_DROPPED"] += 1
            if audit_buf is not None:
                audit_matches.append({
                    "left":    text[max(0, m.start() - ctx_chars):m.start()],
                    "letters": m.group(0).strip(),
                    "right":   text[m.end():m.end() + ctx_chars],
                })
        last_end = m.end()

    pieces.append(text[last_end:])
    new_text = "".join(pieces)

    if audit_buf is not None and audit_matches:
        audit_buf.append({
            "record_id": record_id,
            "field": field,
            "before": text,
            "after": new_text,
            "matches": audit_matches,
        })

    return new_text


def normalize_text(
    text: str,
    counter: Counter,
    *,
    is_subject: bool = False,
    record_id: str | None = None,
    field: str | None = None,
    audit_buf: list[dict] | None = None,
) -> str:
    """对单个字段值跑「主题前缀 → 字面归一 → 占位符 → 字符过滤 → 单字母剥离 → 汉字合并」全流程。

    audit_buf 不为空时：单字母剥离阶段的每一次命中都会写一条记录到该列表，供
    上层把它落到磁盘做人工审计；不影响最终输出。
    """
    if not isinstance(text, str) or not text:
        return text

    s = text

    # -1) 主题字段：先剥掉 Re:/Fwd:/FW: 等堆叠的自动前缀
    if is_subject:
        s, n = SUBJECT_PREFIX_RE.subn("", s)
        counter["SUBJECT_PREFIX"] += n
        # 前缀剥掉后可能只剩空白；统一 strip
        s = s.strip()
        if not s:
            return ""

    # 0) 字面归一：火星文 → 标准简体（先于 opencc）→ 繁体简化
    s = normalize_chinese(s)
    # 0.8) 短语级归一：同音不同形（法票→发票 / 加威信→加微信 等）
    s = normalize_phrases(s, counter)

    # 1) 占位符替换 —— URL 必须最先（在标点过滤之前替换，否则 :// 与 . / 全没了）
    s, n = URL_RE.subn(_replace_url, s);   counter["URL"]    += n
    s, n = EMAIL_RE.subn("[EMAIL]", s);    counter["EMAIL"]  += n
    s, n = QQ_RE.subn("[QQ]", s);          counter["QQ"]     += n
    s, n = WECHAT_RE.subn("[WECHAT]", s);  counter["WECHAT"] += n
    s, n = PHONE_RE.subn("[PHONE]", s);    counter["PHONE"]  += n
    s, n = MONEY_RE.subn("[MONEY]", s);    counter["MONEY"]  += n

    # 2) 仅保留汉字 / 英文 / 占位符，token 之间用单个空格
    result = " ".join(KEEP_RE.findall(s))
    # 2.5) 二次短语归一：在“标点/数字已被丢弃”后，先合并汉字间空格，
    #      再处理被符号打断但本质是同音不同形的写法（如 "蕟/漂" → "蕟漂"）。
    result = ZH_SPACE_RE.sub("", result)
    result = normalize_phrases(result, counter)
    # 二次归一可能把“威信/薇信/维信”变回“微信”，需要再吃成占位符。
    result, n = WECHAT_RE.subn("[WECHAT]", result)
    counter["WECHAT"] += n

    # 3a) 合并 ≥3 个单字母段："S C I" → "SCI"、"I C A E E" → "ICAEE"
    #     放在 SINGLE_EN_BETWEEN 之前；这样 jieba 拿到的就是连写大写词，
    #     而不是会被切成单字母的 "S C I"。
    result = _join_spaced_acronyms(result, counter)

    # 3a-bis) 列表驱动兜底：把"SC I"/"S CI"/"GS K I"等半合并的已知缩写
    #     按 single_en_whitelist.json 的字典强制合并为连写大写。
    result = _join_known_acronyms(result, counter)

    # 3b) 删掉夹在汉字之间的单个英文字母；white-list 命中的（A股 / SCI / ICAEE 等）保留
    result = _apply_single_en_filter(
        result,
        counter=counter,
        record_id=record_id or "",
        field=field or "",
        audit_buf=audit_buf,
    )

    # 4) 去除两个汉字之间的空格（"增 值 发 票" → "增值发票"）
    return ZH_SPACE_RE.sub("", result)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="对 min_cleaned_email.jsonl 做深度清洗：联系方式占位符化 + 字符过滤。",
    )
    parser.add_argument(
        "--input", default=str(INPUT_FILE),
        help=f"输入 JSONL 路径（默认：{INPUT_FILE.relative_to(ROOT)}）",
    )
    parser.add_argument(
        "--output", default=str(OUTPUT_FILE),
        help=f"输出 JSONL 路径（默认：{OUTPUT_FILE.relative_to(ROOT)}）",
    )
    parser.add_argument(
        "--audit-single-en", nargs="?", const=str(AUDIT_FILE), default=None,
        metavar="PATH",
        help=(
            "把「夹在汉字间的单字母剥离」每一处命中和上下文写到一个 JSONL，便于人工审计 "
            "A 股 / B 超 这类被误伤的合法搭配。不指定参数 = 不审计；只给 --audit-single-en"
            f" 用默认路径 {AUDIT_FILE.relative_to(ROOT)}；或指定具体文件路径。"
        ),
    )
    args = parser.parse_args()

    inp, out = Path(args.input), Path(args.output)
    if not inp.exists():
        raise SystemExit(f"找不到输入：{inp}")
    ensure_dir(DATA_DIR)
    ensure_dir(out.parent)

    counter: Counter = Counter()
    n_lines = 0

    audit_path: Path | None = Path(args.audit_single_en) if args.audit_single_en else None
    audit_fp = None
    if audit_path is not None:
        ensure_dir(REPORTS_DIR)
        ensure_dir(audit_path.parent)
        audit_fp = audit_path.open("w", encoding="utf-8")

    with inp.open("r", encoding="utf-8") as fin, out.open("w", encoding="utf-8") as fout:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            rid = obj.get("record_id", "")

            # 每条记录用一个独立的 audit_buf，flush 后再清空，避免全量驻留内存
            audit_buf: list[dict] | None = [] if audit_fp is not None else None

            for f in TEXT_FIELDS:
                v = obj.get(f)
                if isinstance(v, str) and v:
                    obj[f] = normalize_text(
                        v, counter,
                        is_subject=(f == "subject"),
                        record_id=rid, field=f, audit_buf=audit_buf,
                    )

            if audit_fp is not None and audit_buf:
                for rec in audit_buf:
                    audit_fp.write(json.dumps(rec, ensure_ascii=False) + "\n")

            fout.write(json.dumps(obj, ensure_ascii=False) + "\n")
            n_lines += 1

    if audit_fp is not None:
        audit_fp.close()

    print(f"处理 {n_lines} 条记录 → {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    print("占位符命中次数：")
    for tag in ("URL", "EMAIL", "PHONE", "QQ", "WECHAT", "MONEY"):
        print(f"  [{tag}]: {counter[tag]}")
    print("其它统计：")
    print(f"  剥掉 Re:/Fwd:/FW: 等主题前缀的条数      : {counter['SUBJECT_PREFIX']}")
    print(
        f"  合并 ≥3 个单字母分隔的缩写次数（S C I → SCI 等）       : "
        f"{counter['SPACED_ACRONYM_MERGED']}"
    )
    print(
        f"  按字典合并已知缩写次数（SC I / GS KI 等半合并形式）   : "
        f"{counter['KNOWN_ACRONYM_MERGED']}"
    )
    print(
        f"  夹在汉字间的单字母段：被剥 {counter['SINGLE_EN_DROPPED']} 段，"
        f"被白名单保留 {counter['SINGLE_EN_KEPT']} 段"
        f"（白名单加载 {len(_SINGLE_EN_WHITELIST)} 项）"
    )
    if audit_path is not None:
        print(f"  单字母剥离审计 JSONL                       : {audit_path.relative_to(ROOT) if audit_path.is_relative_to(ROOT) else audit_path}")


if __name__ == "__main__":
    main()
