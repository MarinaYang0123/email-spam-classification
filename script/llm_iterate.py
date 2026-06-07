"""LLM 引导词表迭代：审查未分类样本 → 词表扩充建议 → 语料校验 → 可选写回 taxonomy。

支持 --scheme / --schema scheme1（默认）或 scheme2。
加 --full 时审查该方案下全部「未分类」邮件（可按 --batch-size 分批，默认 50）；默认仍为抽样。
API Key 见 README / .env.example。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import socket
import sys
import textwrap
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from project_dirs import DATA_DIR

ROOT = Path(__file__).resolve().parent.parent

DISCOVERED_PREFIX = "探测类"
RESIDUAL_CATEGORIES = ("未分类", "空样本")
MAX_TEXT_CHARS = 800
SHORT_TOKEN_MAX = 8

KEEP_UNCLASS_POLICY = """
## 「保持未分类」——仅限内容过短（慎用）

- **默认**：每条样本必须在五类中选 **最可能的一类**（暴力色情/发票或广告或学术/钓鱼等），并尽量给出 `suggested_keywords`（来自该条 `tokens`）。
- **仅当**样本字段 `short_content=true` 时，才允许 `suggested_category=保持未分类`：表示当前分词结果过短（≤8 token，或几乎只有占位符+姓名），**本轮不扩词**；这类邮件将留给后续「全字段」分析。
- **禁止**对 `short_content=false` 的样本使用「保持未分类」。长文本、电子报/随笔、技术告警、欢迎信等：若能判断五类则给出类别+关键词；若确实无五类语义则用 `未分类`（可不给关键词），**不要**写「保持未分类」。
- **目标**：`sample_reviews` 里「保持未分类」条数 ≤ 总数的 10%，且每条都必须 `short_content=true`。
- 英文 dating/色情、发票变体、培训/产品、伪物流通知、学术邀稿、博彩话术等，**一律归五类之一**，不要以保持未分类敷衍。
"""

SHARED_TOKENIZED = DATA_DIR / "tokenized_email.jsonl"
SHARED_TEXT = DATA_DIR / "concat_email.jsonl"
SHARED_STRUCT = DATA_DIR / "structural_features.jsonl"


@dataclass(frozen=True)
class LlmSchemeConfig:
    key: str
    dir: Path
    rule_categories: tuple[str, ...]
    boundary_categories: tuple[str, ...]
    classify_cmd: str
    system_prompt: str
    user_instructions: str

    @property
    def labels(self) -> Path:
        return self.dir / "outputs" / "labels.jsonl"

    @property
    def taxonomy(self) -> Path:
        return self.dir / "category_taxonomy.json"

    @property
    def results_dir(self) -> Path:
        return self.dir / "results"

    @property
    def suggested_taxonomy(self) -> Path:
        return self.dir / "category_taxonomy.suggested.json"


def _schema_line(cats: tuple[str, ...]) -> str:
    keys = "|".join(cats) + "|未分类|保持未分类"
    blocks = ",\n    ".join(
        f'"{c}": {{"zh": [], "en": [], "pinyin": []}}' for c in cats
    )
    return keys, blocks


_S1_KEYS, _S1_BLOCKS = _schema_line(
    ("暴力色情", "广告营销", "钓鱼邮件", "赌博博彩", "学术会议/期刊营销")
)
_S2_KEYS, _S2_BLOCKS = _schema_line(
    ("暴力色情", "发票营销", "商业广告", "钓鱼邮件", "学术营销")
)

SCHEME_CONFIGS: dict[str, LlmSchemeConfig] = {
    "scheme1": LlmSchemeConfig(
        key="scheme1",
        dir=ROOT / "schemes" / "scheme1_semantic5",
        rule_categories=("暴力色情", "广告营销", "钓鱼邮件", "赌博博彩", "学术会议/期刊营销"),
        boundary_categories=("广告营销", "学术会议/期刊营销"),
        classify_cmd="python schemes/scheme1_semantic5/classify.py",
        system_prompt=f"""你是邮件安全分类的词表迭代助手。方案1五类：暴力色情、广告营销、钓鱼邮件、赌博博彩、学术会议/期刊营销。
规则在 jieba 分词 token 上精确匹配（多词短语须 tokens 全包含）。

审查「未分类/探测类/空样本」，找出漏网垃圾邮件，给出可写回词表的建议。

边界：广告营销（商业/发票）≠ 学术会议/期刊营销（journal/投稿/sci）；赌博博彩单独一类。

约束：
1. 关键词须来自样本 tokens 或 jieba 可切整词。
2. 避免跨类噪声词（单独「登录」「通知」等）。
3. 全部为垃圾邮件；勿输出「正常邮件」类。
4. 输出单个 JSON，无 markdown。
{KEEP_UNCLASS_POLICY}

JSON schema:
{{
  "summary": "...",
  "sample_reviews": [{{"record_id","current_category","suggested_category":"{_S1_KEYS}","confidence","reason","suggested_keywords"}}],
  "add_keywords": {{ {_S1_BLOCKS} }},
  "reject_keywords": [],
  "new_category_candidates": []
}}""",
        user_instructions=(
            "找出应归入五类之一的漏网邮件；仅 short_content=true 可保持未分类。"
            "区分广告营销与学术会议/期刊营销；赌博博彩单独。"
        ),
    ),
    "scheme2": LlmSchemeConfig(
        key="scheme2",
        dir=ROOT / "schemes" / "scheme2_balanced5",
        rule_categories=("暴力色情", "发票营销", "商业广告", "钓鱼邮件", "学术营销"),
        boundary_categories=("发票营销", "商业广告", "学术营销"),
        classify_cmd="python schemes/scheme2_balanced5/classify.py",
        system_prompt=f"""你是邮件安全分类的词表迭代助手。方案2五类：暴力色情、发票营销、商业广告、钓鱼邮件、学术营销（无赌博类）。
规则在 jieba 分词 token 上精确匹配。

审查「未分类/空样本」，压缩未分类比例：找出漏网邮件并建议 add_keywords。

边界：
- 发票营销：代开发票、各类费用、税票、电微开票等财税话术。
- 商业广告：B2B/产品/培训招生/货代/促销/博彩引流(葡京/bbin/领彩等原无赌博类，可归商业广告)。
- 学术营销：journal/conference/sci/ei、投稿/录用/征稿；≠ 发票营销。
- 发票营销 vs 商业广告：主意图开票→发票；卖货/培训/博彩→商业。

约束同方案1；输出单个 JSON。
{KEEP_UNCLASS_POLICY}

JSON schema:
{{
  "summary": "...",
  "sample_reviews": [{{"record_id","current_category","suggested_category":"{_S2_KEYS}","confidence","reason","suggested_keywords"}}],
  "add_keywords": {{ {_S2_BLOCKS} }},
  "reject_keywords": [],
  "new_category_candidates": []
}}""",
        user_instructions=(
            "压缩未分类：尽量判五类并给 add_keywords；仅 short_content=true 可保持未分类。"
            "区分发票营销、商业广告、学术营销；博彩漏网可归商业广告。"
        ),
    ),
}

ACTIVE: LlmSchemeConfig = SCHEME_CONFIGS["scheme1"]


def load_dotenv(path: Path | None = None) -> None:
    """轻量 .env 加载（不依赖 python-dotenv）。"""
    env_path = path or ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def load_maps(cfg: LlmSchemeConfig) -> tuple[dict[str, str], dict[str, list[str]], dict[str, str], dict[str, dict]]:
    labels = {r["record_id"]: r["category"] for r in read_jsonl(cfg.labels)}
    tokens = {r["record_id"]: r.get("tokens", []) for r in read_jsonl(SHARED_TOKENIZED)}
    texts = {r["record_id"]: r.get("text", "") for r in read_jsonl(SHARED_TEXT)}
    struct = {r["record_id"]: r for r in read_jsonl(SHARED_STRUCT)}
    return labels, tokens, texts, struct


def load_taxonomy(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def flatten_taxonomy_words(taxonomy: dict) -> dict[str, set[str]]:
    cats = taxonomy.get("categories", taxonomy)
    out: dict[str, set[str]] = {}
    for cat, groups in cats.items():
        if cat.startswith("_"):
            continue
        words: set[str] = set()
        for key in ("zh", "en", "pinyin"):
            for w in groups.get(key, []):
                w = w.strip()
                if w:
                    words.add(w if key == "zh" else w.lower())
        out[cat] = words
    return out


def is_short_content(tokens: list[str]) -> bool:
    """与规则分类「短文本」一致：留给后续全字段分析，本轮 LLM 可不扩词。"""
    n = len(tokens)
    if n <= SHORT_TOKEN_MAX:
        return True
    if n > 12:
        return False
    semantic = [
        t for t in tokens
        if not (len(t) >= 3 and t[0] == "[" and t[-1] == "]")
    ]
    return len(semantic) <= 3


def truncate_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    text = re.sub(r"\s+", " ", (text or "").strip())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def cluster_top_tokens(record_ids: list[str], tokens_map: dict[str, list[str]], top_n: int = 25) -> list[str]:
    c = Counter()
    for rid in record_ids:
        for t in tokens_map.get(rid, []):
            if t.startswith("[") and t.endswith("]"):
                continue
            c[t] += 1
    return [w for w, _ in c.most_common(top_n)]


def default_review_categories(by_cat: dict[str, list[str]]) -> list[str]:
    """默认审查对象：探测类* → 否则未分类/空样本。"""
    discovered = sorted(c for c in by_cat if c.startswith(DISCOVERED_PREFIX))
    if discovered:
        return discovered
    residual = [c for c in RESIDUAL_CATEGORIES if by_cat.get(c)]
    if residual:
        return residual
    return []


def is_residual_label(label: str) -> bool:
    return label.startswith(DISCOVERED_PREFIX) or label in RESIDUAL_CATEGORIES


def _make_sample_row(
    rid: str,
    cat: str,
    *,
    tokens_map: dict[str, list[str]],
    texts: dict[str, str],
    struct_map: dict[str, dict],
    max_text_chars: int,
) -> dict:
    st = struct_map.get(rid, {})
    toks = tokens_map.get(rid, [])
    return {
        "record_id": rid,
        "current_category": cat,
        "token_count": len(toks),
        "short_content": is_short_content(toks),
        "text_preview": truncate_text(texts.get(rid, ""), max_text_chars),
        "tokens": toks[:60],
        "structural": {
            "sender_domain": st.get("sender_domain", ""),
            "display_domain_mismatch": st.get("display_domain_mismatch", False),
            "url_suspicious": st.get("url_suspicious", False),
            "url_sender_mismatch": st.get("url_sender_mismatch", False),
            "lang": st.get("lang", ""),
        },
    }


def select_samples(
    labels: dict[str, str],
    tokens_map: dict[str, list[str]],
    texts: dict[str, str],
    struct_map: dict[str, dict],
    *,
    target_categories: list[str] | None,
    per_category: int,
    seed: int,
    max_text_chars: int = MAX_TEXT_CHARS,
    boundary_categories: list[str] | None = None,
    boundary_per_category: int = 0,
    full: bool = False,
) -> tuple[list[dict], list[str]]:
    by_cat: dict[str, list[str]] = defaultdict(list)
    for rid, cat in labels.items():
        by_cat[cat].append(rid)

    if full:
        cats = target_categories or ["未分类"]
        cats = [c for c in cats if c in by_cat]
    elif target_categories:
        cats = [c for c in target_categories if c in by_cat]
    else:
        cats = default_review_categories(by_cat)

    if not cats:
        raise SystemExit(
            "未找到可审查样本。请先跑对应方案的 classify.py，或用 --categories 指定，"
            "例如：--categories 未分类"
        )

    rng = random.Random(seed)
    picked: list[dict] = []
    reviewed_cats: list[str] = list(cats)

    def _pick_from(cat: str, n: int | None) -> None:
        ids = sorted(by_cat[cat]) if full else by_cat[cat][:]
        if not full:
            rng.shuffle(ids)
        limit = len(ids) if n is None else n
        for rid in ids[:limit]:
            picked.append(_make_sample_row(
                rid, cat,
                tokens_map=tokens_map,
                texts=texts,
                struct_map=struct_map,
                max_text_chars=max_text_chars,
            ))

    for cat in cats:
        _pick_from(cat, None if full else per_category)

    if not full and boundary_categories and boundary_per_category > 0:
        for cat in boundary_categories:
            if cat in by_cat and cat not in cats:
                _pick_from(cat, boundary_per_category)
                reviewed_cats.append(f"{cat}(边界对照)")

    return picked, reviewed_cats


def build_user_prompt(
    samples: list[dict],
    taxonomy: dict,
    cluster_stats: dict[str, list[str]],
    cfg: LlmSchemeConfig,
    *,
    batch_index: int | None = None,
    batch_total: int | None = None,
) -> str:
    payload: dict[str, Any] = {
        "scheme": cfg.key,
        "current_taxonomy": taxonomy.get("categories", taxonomy),
        "cluster_high_frequency_tokens": cluster_stats,
        "samples_to_review": samples,
        "instructions": cfg.user_instructions,
    }
    if batch_index is not None and batch_total is not None:
        payload["batch"] = {"index": batch_index, "total": batch_total}
        payload["instructions"] += (
            f" 本批为第 {batch_index}/{batch_total} 批，仅审查 samples_to_review 中的邮件；"
            "add_keywords 只汇总本批样本中的词。"
        )
    return json.dumps(payload, ensure_ascii=False, indent=2)


def iter_batches(items: list[dict], batch_size: int) -> list[list[dict]]:
    if batch_size <= 0:
        raise ValueError("batch_size 必须 > 0")
    return [items[i:i + batch_size] for i in range(0, len(items), batch_size)]


def progress_bar(iterable, *, total: int | None, desc: str):
    try:
        from tqdm import tqdm  # type: ignore
        return tqdm(iterable, total=total, desc=desc, unit="batch")
    except ImportError:

        class _SimpleProgress:
            def __init__(self, it, n: int, label: str):
                self._it = iter(it)
                self._n = 0
                self._total = n
                self._label = label

            def __iter__(self):
                return self

            def __next__(self):
                self._n += 1
                if self._total:
                    print(f"{self._label} {self._n}/{self._total}", file=sys.stderr)
                return next(self._it)

        return _SimpleProgress(iterable, total or 0, desc)


def batch_cluster_stats(
    batch_samples: list[dict],
    tokens_map: dict[str, list[str]],
) -> dict[str, list[str]]:
    by_cat: dict[str, list[str]] = defaultdict(list)
    for s in batch_samples:
        by_cat[s["current_category"]].append(s["record_id"])
    return {
        cat: cluster_top_tokens(rids, tokens_map, 25)
        for cat, rids in by_cat.items()
    }


def merge_proposals(
    batch_proposals: list[dict],
    rule_categories: tuple[str, ...],
) -> dict:
    """合并多批 LLM 输出为单一 proposal。"""
    merged: dict[str, Any] = {
        "summary": "",
        "sample_reviews": [],
        "add_keywords": {c: {"zh": [], "en": [], "pinyin": []} for c in rule_categories},
        "reject_keywords": [],
        "new_category_candidates": [],
    }
    summaries: list[str] = []
    seen_reject: set[str] = set()
    seen_kw: dict[str, dict[str, set[str]]] = {
        c: {"zh": set(), "en": set(), "pinyin": set()} for c in rule_categories
    }
    seen_candidates: set[str] = set()

    for i, prop in enumerate(batch_proposals, 1):
        if prop.get("summary"):
            summaries.append(f"批次 {i}：{prop['summary']}")
        merged["sample_reviews"].extend(prop.get("sample_reviews", []))
        for cat in rule_categories:
            groups = prop.get("add_keywords", {}).get(cat, {})
            for lang in ("zh", "en", "pinyin"):
                for w in groups.get(lang, []):
                    w = w.strip()
                    if not w or w in seen_kw[cat][lang]:
                        continue
                    seen_kw[cat][lang].add(w)
                    merged["add_keywords"][cat][lang].append(w)
        for item in prop.get("reject_keywords", []):
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen_reject:
                seen_reject.add(key)
                merged["reject_keywords"].append(item)
        for item in prop.get("new_category_candidates", []):
            key = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if key not in seen_candidates:
                seen_candidates.add(key)
                merged["new_category_candidates"].append(item)

    merged["summary"] = "\n".join(summaries) if summaries else "（多批合并，见各批次 summary）"
    return merged


def call_chat_api(
    *,
    system: str,
    user: str,
    model: str,
    base_url: str,
    api_key: str,
    timeout: int,
    retries: int = 3,
) -> dict:
    url = base_url.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    last_timeout: BaseException | None = None
    for attempt in range(1, max(1, retries) + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except (TimeoutError, socket.timeout) as exc:
            last_timeout = exc
            if attempt < retries:
                wait = min(60, 10 * attempt)
                print(f"  API 读超时（{timeout}s），{attempt}/{retries} 次失败，{wait}s 后重试…")
                time.sleep(wait)
                continue
            raise SystemExit(
                f"API 读超时（已重试 {retries} 次，timeout={timeout}s）。"
                f"可增大 .env 中 LLM_TIMEOUT，或减小 --batch-size。"
            ) from exc
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SystemExit(f"API HTTP {exc.code}: {detail[:500]}") from exc
        except urllib.error.URLError as exc:
            raise SystemExit(f"API 连接失败：{exc}") from exc
    raise SystemExit(f"API 读超时：{last_timeout}") from last_timeout


def enforce_keep_unclass_policy(samples: list[dict], proposal: dict) -> dict:
    """非 short_content 样本不得「保持未分类」→ 改为「未分类」且不扩词。"""
    short_by_id = {s["record_id"]: bool(s.get("short_content")) for s in samples}
    fixed = 0
    for r in proposal.get("sample_reviews", []):
        if r.get("suggested_category") != "保持未分类":
            continue
        rid = r.get("record_id", "")
        if short_by_id.get(rid):
            continue
        r["suggested_category"] = "未分类"
        r["suggested_keywords"] = []
        r["reason"] = (r.get("reason", "") + " [脚本修正：非短文本，不可用保持未分类]").strip()
        fixed += 1
    if fixed:
        proposal.setdefault("_meta", {})["keep_unclass_downgraded"] = fixed
    return proposal


def extract_json_content(raw: dict) -> dict:
    try:
        content = raw["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"API 响应格式异常：{raw}") from exc
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)
    return json.loads(content)


def token_hit(keyword: str, token_set: set[str]) -> bool:
    if " " in keyword:
        return all(p in token_set for p in keyword.split())
    return keyword in token_set


def validate_proposal(
    proposal: dict,
    tokens_map: dict[str, list[str]],
    labels: dict[str, str],
    taxonomy_words: dict[str, set[str]],
    rule_categories: tuple[str, ...],
) -> dict:
    """统计每个建议词：语料覆盖率、跨类误伤、是否已在词表。"""
    validated_add: dict[str, list[dict]] = {c: [] for c in rule_categories}

    for cat in rule_categories:
        groups = proposal.get("add_keywords", {}).get(cat, {})
        for lang in ("zh", "en", "pinyin"):
            for word in groups.get(lang, []):
                word = word.strip()
                if not word:
                    continue
                norm = word if lang == "zh" else word.lower()
                hit_ids = [rid for rid, toks in tokens_map.items() if token_hit(norm, set(toks))]
                fp_ids = [
                    rid for rid in hit_ids
                    if labels.get(rid) != cat and not is_residual_label(labels.get(rid, ""))
                ]
                validated_add[cat].append({
                    "word": word,
                    "lang": lang,
                    "corpus_hits": len(hit_ids),
                    "false_positive_hits": len(fp_ids),
                    "already_in_taxonomy": norm in taxonomy_words.get(cat, set()),
                    "recommend": len(hit_ids) >= 3 and len(fp_ids) <= max(1, len(hit_ids) * 0.15),
                })

    return {
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "add_keywords": validated_add,
        "reject_keywords": proposal.get("reject_keywords", []),
        "new_category_candidates": proposal.get("new_category_candidates", []),
        "sample_reviews": proposal.get("sample_reviews", []),
        "summary": proposal.get("summary", ""),
    }


def apply_proposal(
    taxonomy: dict,
    proposal: dict,
    validated: dict,
    rule_categories: tuple[str, ...],
) -> dict:
    """只合并 validated 里 recommend=true 且不在词表中的词。"""
    out = json.loads(json.dumps(taxonomy, ensure_ascii=False))
    cats = out.setdefault("categories", {})
    for cat in rule_categories:
        cat_obj = cats.setdefault(cat, {"zh": [], "en": [], "pinyin": []})
        add_block = proposal.get("add_keywords", {}).get(cat, {})
        val_map = {(v["word"], v["lang"]): v for v in validated["add_keywords"].get(cat, [])}
        for lang in ("zh", "en", "pinyin"):
            existing = set(cat_obj.get(lang, []))
            for word in add_block.get(lang, []):
                v = val_map.get((word, lang))
                if v and v["recommend"] and word not in existing:
                    cat_obj.setdefault(lang, []).append(word)
    out["_llm_iterate"] = {
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "note": "由 llm_iterate.py --apply 生成；请人工复核后再替换 category_taxonomy.json",
    }
    return out


def write_report(
    path: Path,
    *,
    cfg: LlmSchemeConfig,
    samples: list[dict],
    proposal: dict | None,
    validated: dict | None,
) -> None:
    lines = [f"# LLM 词表迭代报告（{cfg.key}）", ""]
    lines.append(f"- 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 审查样本数：{len(samples)}")
    if samples:
        n_short = sum(1 for s in samples if s.get("short_content"))
        lines.append(f"- 其中 short_content（允许保持未分类）：{n_short}")
    meta = (proposal or {}).get("_meta") or {}
    if meta.get("full_mode"):
        lines.append(f"- 全量模式：是（batch_size={meta.get('batch_size')}, batches={meta.get('batch_count')}）")
    if proposal:
        reviews = proposal.get("sample_reviews", [])
        n_keep = sum(1 for r in reviews if r.get("suggested_category") == "保持未分类")
        if reviews:
            lines.append(f"- 保持未分类：{n_keep} / {len(reviews)} 条审查")
        if proposal.get("_meta", {}).get("keep_unclass_downgraded"):
            lines.append(
                f"- 脚本修正（非短文本误标保持未分类）："
                f"{proposal['_meta']['keep_unclass_downgraded']} 条"
            )
        lines += ["", "## 模型总结", "", proposal.get("summary", "（无）"), ""]
        if reviews:
            excerpt_n = 20 if not meta.get("full_mode") else 30
            lines += ["## 样本审查（节选）", ""]
            if len(reviews) > excerpt_n:
                lines.append(f"共 {len(reviews)} 条审查记录，以下展示前 {excerpt_n} 条：")
                lines.append("")
            for r in reviews[:excerpt_n]:
                lines.append(
                    f"- `{r.get('record_id')}`：{r.get('current_category')} → "
                    f"**{r.get('suggested_category')}** ({r.get('confidence')}) — {r.get('reason', '')}"
                )
            if meta.get("full_mode") and len(reviews) > excerpt_n:
                lines.append("")
                lines.append("（全量其余条目见 `llm_iterate_proposal.json` 的 `sample_reviews`）")
    if validated:
        lines += ["", "## 建议词校验", ""]
        for cat in cfg.rule_categories:
            items = validated["add_keywords"].get(cat, [])
            if not items:
                continue
            lines.append(f"### {cat}")
            for v in items:
                flag = "✅ 建议采纳" if v["recommend"] else "⚠️ 需人工判断"
                lines.append(
                    f"- `{v['word']}` ({v['lang']})：语料命中 {v['corpus_hits']}，"
                    f"误伤 {v['false_positive_hits']}，已在词表={v['already_in_taxonomy']} — {flag}"
                )
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def ensure_api_config() -> tuple[str, str, str, int]:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit(
            "未找到 OPENAI_API_KEY。\n"
            "请复制 .env.example 为 .env 并填入密钥，或在当前终端设置环境变量。\n"
            "详见 README「LLM 迭代」章节。"
        )
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini").strip()
    timeout = int(os.environ.get("LLM_TIMEOUT", "600"))
    retries = int(os.environ.get("LLM_RETRIES", "3"))
    return api_key, base_url, model, timeout, retries


def load_completed_raw_batches(path: Path) -> dict[int, dict]:
    completed: dict[int, dict] = {}
    if not path.exists():
        return completed
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        completed[int(rec["batch"])] = rec["response"]
    return completed


def effective_timeout(base_timeout: int, *, full_mode: bool, batch_size: int) -> int:
    """全量大批次时按 batch_size 抬高下限，避免 50 条/批在 120s 内读不完。"""
    if not full_mode:
        return base_timeout
    floor = max(300, batch_size * 12)
    return max(base_timeout, floor)


def main() -> None:
    global ACTIVE
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="LLM 引导词表迭代（审查未分类 → 词表建议 → 校验 → 可选 apply）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        全量压缩未分类（须显式 --full，默认 batch_size=50）：
          python script/llm_iterate.py --schema scheme2 --full --dry-run
          python script/llm_iterate.py --schema scheme2 --full
          python script/llm_iterate.py --schema scheme2 --full --batch-size 30
          python script/llm_iterate.py --schema scheme2 --full --validate-only
          python script/llm_iterate.py --schema scheme2 --full --apply
          # 人工复核 suggested 后覆盖 category_taxonomy.json，再：
          python schemes/scheme2_balanced5/classify.py

        抽样模式（默认）：
          python script/llm_iterate.py --dry-run
          python script/llm_iterate.py --schema scheme1 --dry-run
          python script/llm_iterate.py --schema scheme1
        """),
    )
    parser.add_argument(
        "--scheme", "--schema", dest="scheme", choices=tuple(SCHEME_CONFIGS), default="scheme1",
        help="scheme1=语义五类（默认），scheme2=发票/商业拆分五类",
    )
    parser.add_argument(
        "--full", action="store_true",
        help="全量模式：审查全部「未分类」，按 --batch-size 分批调 API",
    )
    parser.add_argument(
        "--batch-size", type=int, default=50,
        help="全量模式下每批送模型的样本数，默认 50",
    )
    parser.add_argument(
        "--resume", action="store_true",
        help="全量模式续跑：跳过 llm_iterate_raw_batches.jsonl 中已有批次，不清空该文件",
    )
    parser.add_argument("--dry-run", action="store_true", help="只抽样并写出 llm_iterate_samples.jsonl，不调 API")
    parser.add_argument("--validate-only", action="store_true", help="校验已有 llm_iterate_proposal.json")
    parser.add_argument("--apply", action="store_true", help="将校验通过的词写入 category_taxonomy.suggested.json")
    parser.add_argument("--categories", type=str, default="",
                        help="逗号分隔要审查的类别；--full 时默认仅「未分类」")
    parser.add_argument("--per-category", type=int, default=25,
                        help="抽样模式：每类最多 N 条（--full 时忽略）")
    parser.add_argument("--boundary-per-category", type=int, default=5,
                        help="默认模式下额外从边界类各抽 N 条对照，0=关闭")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--proposal", type=Path, default=None, help="proposal JSON 路径（默认随 --scheme）")
    parser.add_argument("--max-text-chars", type=int, default=MAX_TEXT_CHARS)
    args = parser.parse_args()

    ACTIVE = SCHEME_CONFIGS[args.scheme]
    out_samples = ACTIVE.results_dir / "llm_iterate_samples.jsonl"
    out_raw = ACTIVE.results_dir / "llm_iterate_raw.json"
    out_proposal = args.proposal or (ACTIVE.results_dir / "llm_iterate_proposal.json")
    out_validated = ACTIVE.results_dir / "llm_iterate_validated.json"
    out_report = ACTIVE.results_dir / "llm_iterate_report.md"
    out_suggested = ACTIVE.suggested_taxonomy

    for p in (ACTIVE.labels, SHARED_TOKENIZED, SHARED_TEXT, ACTIVE.taxonomy):
        if not p.exists():
            raise SystemExit(f"缺少输入文件：{p}（请先跑 {ACTIVE.classify_cmd}）")

    labels, tokens_map, texts, struct_map = load_maps(ACTIVE)
    taxonomy = load_taxonomy(ACTIVE.taxonomy)
    taxonomy_words = flatten_taxonomy_words(taxonomy)

    if args.full:
        target_cats = [c.strip() for c in args.categories.split(",") if c.strip()] or ["未分类"]
    else:
        target_cats = [c.strip() for c in args.categories.split(",") if c.strip()] or None
    boundary_cats = list(ACTIVE.boundary_categories)
    boundary_n = 0 if args.full else (args.boundary_per_category if target_cats is None else 0)

    if (args.validate_only or args.apply) and out_samples.exists():
        samples = read_jsonl(out_samples)
        reviewed_cats = sorted({s["current_category"] for s in samples})
        print(f"从已保存样本包加载：{out_samples.relative_to(ROOT)}（{len(samples)} 条）")
    else:
        samples, reviewed_cats = select_samples(
            labels, tokens_map, texts, struct_map,
            target_categories=target_cats,
            per_category=args.per_category,
            seed=args.seed,
            max_text_chars=args.max_text_chars,
            boundary_categories=boundary_cats,
            boundary_per_category=boundary_n,
            full=args.full,
        )

    by_cat_ids: dict[str, list[str]] = defaultdict(list)
    for rid, cat in labels.items():
        by_cat_ids[cat].append(rid)
    stats_cats = {s["current_category"] for s in samples}
    stats_cats.update(c for c in by_cat_ids if c.startswith(DISCOVERED_PREFIX) or c in RESIDUAL_CATEGORIES)
    cluster_stats = {
        cat: cluster_top_tokens(by_cat_ids[cat], tokens_map, 25)
        for cat in stats_cats
        if cat in by_cat_ids
    }

    out_samples.parent.mkdir(parents=True, exist_ok=True)
    with out_samples.open("w", encoding="utf-8") as fout:
        for row in samples:
            fout.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"[{ACTIVE.key}] 样本包：{out_samples.relative_to(ROOT)}（{len(samples)} 条）")
    print(f"  审查类别：{', '.join(reviewed_cats)}")

    if args.dry_run:
        if args.full:
            batches = iter_batches(samples, args.batch_size)
            print(f"--dry-run 全量：{len(samples)} 条 → {len(batches)} 批（batch_size={args.batch_size}）")
        else:
            user_preview = build_user_prompt(samples, taxonomy, cluster_stats, ACTIVE)
            print(f"--dry-run：不调 API。user prompt 约 {len(user_preview)} 字符。")
        full_flag = " --full" if args.full else ""
        print(f"下一步：python script/llm_iterate.py --schema {ACTIVE.key}{full_flag}")
        return

    if args.validate_only or args.apply:
        if not out_proposal.exists():
            raise SystemExit(f"找不到 {out_proposal}，请先运行不带 --validate-only 的 llm_iterate.py")
        proposal = json.loads(out_proposal.read_text(encoding="utf-8"))
        proposal = enforce_keep_unclass_policy(samples, proposal)
        validated = validate_proposal(
            proposal, tokens_map, labels, taxonomy_words, ACTIVE.rule_categories,
        )
        out_validated.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
        write_report(out_report, cfg=ACTIVE, samples=samples, proposal=proposal, validated=validated)
        print(f"校验结果：{out_validated.relative_to(ROOT)}")
        print(f"报告：{out_report.relative_to(ROOT)}")
        if args.apply:
            suggested = apply_proposal(
                taxonomy, proposal, validated, ACTIVE.rule_categories,
            )
            out_suggested.write_text(json.dumps(suggested, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"建议词表：{out_suggested.relative_to(ROOT)}（请人工复核后再替换 category_taxonomy.json）")
        return

    api_key, base_url, model, timeout, retries = ensure_api_config()
    timeout = effective_timeout(timeout, full_mode=args.full, batch_size=args.batch_size)
    print(f"调用模型：{model} @ {base_url}（timeout={timeout}s，retries={retries}）")

    out_raw_batches = ACTIVE.results_dir / "llm_iterate_raw_batches.jsonl"
    batch_proposals: list[dict] = []
    all_raw: list[dict] = []

    if args.full:
        batches = iter_batches(samples, args.batch_size)
        n_batches = len(batches)
        print(f"全量模式：{len(samples)} 条，分 {n_batches} 批（每批 ≤{args.batch_size} 条）")
        completed_raw = load_completed_raw_batches(out_raw_batches) if args.resume else {}
        if args.resume:
            if completed_raw:
                print(f"续跑：跳过已有 {len(completed_raw)} 批（{out_raw_batches.relative_to(ROOT)}）")
            else:
                print("续跑：未找到已完成批次，从头开始")
        else:
            out_raw_batches.write_text("", encoding="utf-8")
        downgraded = 0
        for batch_idx, batch_samples in enumerate(
            progress_bar(batches, total=n_batches, desc="LLM batches"), 1,
        ):
            if batch_idx in completed_raw:
                raw = completed_raw[batch_idx]
            else:
                bstats = batch_cluster_stats(batch_samples, tokens_map)
                user_prompt = build_user_prompt(
                    batch_samples, taxonomy, bstats, ACTIVE,
                    batch_index=batch_idx, batch_total=n_batches,
                )
                raw = call_chat_api(
                    system=ACTIVE.system_prompt,
                    user=user_prompt,
                    model=model,
                    base_url=base_url,
                    api_key=api_key,
                    timeout=timeout,
                    retries=retries,
                )
                with out_raw_batches.open("a", encoding="utf-8") as fout:
                    fout.write(json.dumps({"batch": batch_idx, "response": raw}, ensure_ascii=False) + "\n")
            all_raw.append({"batch": batch_idx, "response": raw})
            prop = enforce_keep_unclass_policy(batch_samples, extract_json_content(raw))
            downgraded += prop.pop("_meta", {}).get("keep_unclass_downgraded", 0)
            batch_proposals.append(prop)
        out_raw.write_text(json.dumps(all_raw, ensure_ascii=False, indent=2), encoding="utf-8")
        proposal = merge_proposals(batch_proposals, ACTIVE.rule_categories)
    else:
        user_prompt = build_user_prompt(samples, taxonomy, cluster_stats, ACTIVE)
        raw = call_chat_api(
            system=ACTIVE.system_prompt,
            user=user_prompt,
            model=model,
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            retries=retries,
        )
        out_raw.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
        proposal = extract_json_content(raw)
        proposal = enforce_keep_unclass_policy(samples, proposal)
        downgraded = proposal.pop("_meta", {}).get("keep_unclass_downgraded", 0)

    proposal["_meta"] = {
        "scheme": ACTIVE.key,
        "model": model,
        "base_url": base_url,
        "sample_count": len(samples),
        "full_mode": args.full,
        "batch_size": args.batch_size if args.full else None,
        "batch_count": len(batch_proposals) if args.full else 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    if downgraded:
        proposal["_meta"]["keep_unclass_downgraded"] = downgraded
        print(f"  已将 {downgraded} 条「保持未分类」修正为「未分类」（非 short_content）")
    out_proposal.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")

    validated = validate_proposal(
        proposal, tokens_map, labels, taxonomy_words, ACTIVE.rule_categories,
    )
    out_validated.write_text(json.dumps(validated, ensure_ascii=False, indent=2), encoding="utf-8")
    write_report(out_report, cfg=ACTIVE, samples=samples, proposal=proposal, validated=validated)

    print(f"原始响应：{out_raw.relative_to(ROOT)}")
    print(f"结构化建议：{out_proposal.relative_to(ROOT)}")
    print(f"校验结果：{out_validated.relative_to(ROOT)}")
    print(f"报告：{out_report.relative_to(ROOT)}")
    print("\n下一步：")
    print(f"  1. 阅读 {out_report.relative_to(ROOT)}")
    full_flag = " --full" if args.full else ""
    print(f"  2. python script/llm_iterate.py --schema {ACTIVE.key}{full_flag} --validate-only")
    print(f"  3. python script/llm_iterate.py --schema {ACTIVE.key}{full_flag} --apply")
    print(f"  4. 复核 category_taxonomy.suggested.json → 覆盖 category_taxonomy.json")
    print(f"  5. {ACTIVE.classify_cmd}")


if __name__ == "__main__":
    main()
