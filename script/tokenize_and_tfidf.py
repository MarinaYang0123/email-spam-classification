"""jieba 分词 + TF-IDF 特征生成。

输入  : data/concat_email.jsonl      （record_id + text）
输出  : data/tokenized_email.jsonl   （record_id + tokens）
        data/tfidf/tfidf_matrix.npz        （TF-IDF 稀疏矩阵，行顺序对应 record_id）
        data/tfidf/tfidf_vocab.json        （token -> 列索引）
        data/tfidf/tfidf_feature_names.json（列索引 -> token）
        data/tfidf/tfidf_record_ids.json   （行索引 -> record_id）
        data/tfidf/tfidf_top_keywords.jsonl（每封邮件的 Top-N TF-IDF 关键词）
        data/tfidf/tfidf_global_top.json   （全局平均 TF-IDF Top-N）

设计要点：
  * 占位符 [URL]/[EMAIL]/[PHONE]/[QQ]/[WECHAT]/[MONEY] 先用正则切出，
    再对其余文本做 jieba，避免方括号被拆成噪声 token。
  * 英文统一小写；占位符保持大写，作为联系方式/链接/金额的结构特征。
  * TF-IDF 直接消费已经分好的 tokens，绕过 sklearn 默认 token_pattern。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path

from project_dirs import DATA_DIR, TFIDF_DIR, ensure_dir

ROOT = Path(__file__).resolve().parent.parent
INPUT_FILE = DATA_DIR / "concat_email.jsonl"
TOKENIZED_FILE = DATA_DIR / "tokenized_email.jsonl"
TFIDF_MATRIX_FILE = TFIDF_DIR / "tfidf_matrix.npz"
TFIDF_VOCAB_FILE = TFIDF_DIR / "tfidf_vocab.json"
TFIDF_FEATURE_NAMES_FILE = TFIDF_DIR / "tfidf_feature_names.json"
TFIDF_RECORD_IDS_FILE = TFIDF_DIR / "tfidf_record_ids.json"
TFIDF_TOP_KEYWORDS_FILE = TFIDF_DIR / "tfidf_top_keywords.jsonl"
TFIDF_GLOBAL_TOP_FILE = TFIDF_DIR / "tfidf_global_top.json"
CLUSTER_STOPWORDS_FILE = ROOT / "config" / "cluster_stopwords.json"
TFIDF_CLUSTER_MATRIX_FILE = TFIDF_DIR / "tfidf_cluster_matrix.npz"
TFIDF_CLUSTER_VOCAB_FILE = TFIDF_DIR / "tfidf_cluster_vocab.json"
TFIDF_CLUSTER_FEATURE_NAMES_FILE = TFIDF_DIR / "tfidf_cluster_feature_names.json"
TFIDF_CLUSTER_TOP_KEYWORDS_FILE = TFIDF_DIR / "tfidf_cluster_top_keywords.jsonl"
TFIDF_CLUSTER_GLOBAL_TOP_FILE = TFIDF_DIR / "tfidf_cluster_global_top.json"

PLACEHOLDERS = ("[URL]", "[EMAIL]", "[PHONE]", "[QQ]", "[WECHAT]", "[MONEY]")
PLACEHOLDER_RE = re.compile(r"\[(?:URL|EMAIL|PHONE|QQ|WECHAT|MONEY)\]")
ASCII_ALPHA_RE = re.compile(r"^[A-Za-z]+$")
CHINESE_RE = re.compile(r"[\u4e00-\u9fff]")

# 小型通用停用词表；高频词还会由 TF-IDF 的 max_df 继续过滤。
DEFAULT_STOPWORDS = {
    "的", "了", "和", "是", "在", "我", "有", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
    "看", "好", "自己", "这", "那", "为", "与", "及", "或", "等", "中", "对", "可",
    "并", "被", "将", "已", "从", "请", "您", "您好", "谢谢", "我们", "你们", "他们",
    "the", "and", "for", "you", "your", "with", "this", "that", "from", "are", "was",
    "were", "have", "has", "had", "not", "but", "can", "will", "our", "all", "any",
    "to", "of", "in", "be", "by", "on", "as", "at", "or", "if", "it", "its", "is",
    "am", "an", "a", "we", "us", "he", "she", "they", "them", "his", "her", "their",
    "there", "here", "then", "than", "into", "out", "up", "down", "over", "under",
    "these", "those", "been", "being", "do", "does", "did", "so", "no", "yes",
    "please", "dear", "regards", "thanks",
}


def _import_runtime_deps():
    """把重依赖放到运行时导入，缺包时给出清晰提示。"""
    try:
        import jieba  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 jieba，请先安装：pip install jieba") from exc

    try:
        from scipy.sparse import save_npz  # type: ignore
        from sklearn.feature_extraction.text import TfidfVectorizer  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 scikit-learn 或 scipy，请先安装：pip install scikit-learn scipy") from exc

    return jieba, TfidfVectorizer, save_npz


def load_stopwords(path: Path | None) -> set[str]:
    """读取可选停用词文件；支持 JSON 列表或一行一个词的文本文件。"""
    words = set(DEFAULT_STOPWORDS)
    if path is None:
        return words
    if not path.exists():
        raise SystemExit(f"找不到停用词文件：{path}")

    if path.suffix.lower() == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
            raise SystemExit(f"{path} 应为字符串 JSON 列表")
        words.update(x.strip() for x in raw if x.strip())
    else:
        with path.open("r", encoding="utf-8") as fin:
            words.update(line.strip() for line in fin if line.strip())
    return words


def normalize_token(token: str) -> str:
    """规约单个 token：占位符原样保留，英文小写，其余 strip。"""
    token = token.strip()
    if token in PLACEHOLDERS:
        return token
    if ASCII_ALPHA_RE.fullmatch(token):
        return token.lower()
    return token


def keep_token(token: str, stopwords: set[str]) -> bool:
    """过滤空白、停用词、孤立单字符和明显无信息的 token。"""
    if not token or token.isspace():
        return False
    if token in PLACEHOLDERS:
        return True
    if token in stopwords:
        return False
    if len(token) == 1:
        return False
    if token.isdigit():
        return False
    if ASCII_ALPHA_RE.fullmatch(token) and len(token) < 2:
        return False
    if not CHINESE_RE.search(token) and not ASCII_ALPHA_RE.fullmatch(token):
        return False
    return True


def tokenize_text(text: str, jieba_module, stopwords: set[str]) -> list[str]:
    """先保留占位符，再对普通片段做 jieba 分词。"""
    tokens: list[str] = []
    last_end = 0

    for match in PLACEHOLDER_RE.finditer(text):
        if match.start() > last_end:
            tokens.extend(jieba_module.lcut(text[last_end:match.start()]))
        tokens.append(match.group(0))
        last_end = match.end()

    if last_end < len(text):
        tokens.extend(jieba_module.lcut(text[last_end:]))

    normalized = (normalize_token(t) for t in tokens)
    return [t for t in normalized if keep_token(t, stopwords)]


def iter_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as fin:
        for line_no, line in enumerate(fin, start=1):
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"{path} 第 {line_no} 行不是合法 JSON：{exc}") from exc


def write_json(path: Path, obj) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def serializable_vocab(vocab: dict[str, int]) -> dict[str, int]:
    """sklearn 可能返回 numpy.int64；写 JSON 前转成普通 int。"""
    return {token: int(idx) for token, idx in vocab.items()}


def build_tokenized_file(
    *,
    input_path: Path,
    output_path: Path,
    jieba_module,
    stopwords: set[str],
) -> tuple[list[str], list[str], Counter]:
    """生成分词 JSONL，并返回 record_ids 与空格拼接后的文档。"""
    ensure_dir(output_path.parent)

    record_ids: list[str] = []
    docs: list[str] = []
    stats: Counter = Counter()

    with output_path.open("w", encoding="utf-8") as fout:
        for obj in iter_jsonl(input_path):
            record_id = str(obj.get("record_id", ""))
            text = obj.get("text", "")
            if not isinstance(text, str):
                text = ""

            tokens = tokenize_text(text, jieba_module, stopwords)
            record_ids.append(record_id)
            docs.append(" ".join(tokens))

            stats["records"] += 1
            stats["tokens"] += len(tokens)
            if not tokens:
                stats["empty_after_tokenize"] += 1
            for token in tokens:
                if token in PLACEHOLDERS:
                    stats[token] += 1

            fout.write(json.dumps(
                {"record_id": record_id, "tokens": tokens},
                ensure_ascii=False,
            ) + "\n")

    return record_ids, docs, stats


def load_tokenized_docs(
    path: Path,
    *,
    filter_tokens: set[str],
) -> tuple[list[str], list[str], Counter]:
    """从已有 tokenized JSONL 读入，过滤聚类停用词后拼成 TF-IDF 文档。"""
    record_ids: list[str] = []
    docs: list[str] = []
    stats: Counter = Counter()

    for obj in iter_jsonl(path):
        record_id = str(obj.get("record_id", ""))
        raw_tokens = obj.get("tokens", [])
        if not isinstance(raw_tokens, list):
            raw_tokens = []
        tokens = [t for t in raw_tokens if isinstance(t, str) and t not in filter_tokens]
        record_ids.append(record_id)
        docs.append(" ".join(tokens))
        stats["records"] += 1
        stats["tokens"] += len(tokens)
        if not tokens:
            stats["empty_after_tokenize"] += 1

    return record_ids, docs, stats


def top_terms_for_row(row, feature_names: list[str], top_n: int) -> list[dict]:
    """取单行稀疏向量中权重最高的 top_n 个词。"""
    if row.nnz == 0:
        return []
    pairs = zip(row.indices, row.data)
    top = sorted(pairs, key=lambda x: x[1], reverse=True)[:top_n]
    return [{"token": feature_names[idx], "score": round(float(score), 8)} for idx, score in top]


def save_top_keywords(
    *,
    path: Path,
    matrix,
    feature_names: list[str],
    record_ids: list[str],
    top_n: int,
) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fout:
        for row_idx, record_id in enumerate(record_ids):
            row = matrix.getrow(row_idx)
            fout.write(json.dumps({
                "record_id": record_id,
                "keywords": top_terms_for_row(row, feature_names, top_n),
            }, ensure_ascii=False) + "\n")


def placeholder_rank(global_scores: list[tuple[str, float]]) -> dict[str, dict]:
    """统计占位符在全局平均 TF-IDF 中的名次。"""
    ranks: dict[str, dict] = {}
    for idx, (token, score) in enumerate(global_scores, start=1):
        if token in PLACEHOLDERS:
            ranks[token] = {"rank": idx, "score": round(float(score), 8)}
    for token in PLACEHOLDERS:
        ranks.setdefault(token, {"rank": None, "score": 0.0})
    return ranks


def main() -> None:
    parser = argparse.ArgumentParser(description="对 concat_email.jsonl 做 jieba 分词并生成 TF-IDF 特征。")
    parser.add_argument("--input", type=Path, default=INPUT_FILE,
                        help=f"输入 JSONL，默认 {INPUT_FILE.relative_to(ROOT)}")
    parser.add_argument("--tokenized-output", type=Path, default=TOKENIZED_FILE,
                        help=f"分词 JSONL 输出，默认 {TOKENIZED_FILE.relative_to(ROOT)}")
    parser.add_argument("--matrix-output", type=Path, default=TFIDF_MATRIX_FILE,
                        help=f"TF-IDF 矩阵输出，默认 {TFIDF_MATRIX_FILE.relative_to(ROOT)}")
    parser.add_argument("--vocab-output", type=Path, default=TFIDF_VOCAB_FILE,
                        help=f"词表输出，默认 {TFIDF_VOCAB_FILE.relative_to(ROOT)}")
    parser.add_argument("--feature-names-output", type=Path, default=TFIDF_FEATURE_NAMES_FILE,
                        help=f"特征名输出，默认 {TFIDF_FEATURE_NAMES_FILE.relative_to(ROOT)}")
    parser.add_argument("--record-ids-output", type=Path, default=TFIDF_RECORD_IDS_FILE,
                        help=f"record_id 输出，默认 {TFIDF_RECORD_IDS_FILE.relative_to(ROOT)}")
    parser.add_argument("--top-keywords-output", type=Path, default=TFIDF_TOP_KEYWORDS_FILE,
                        help=f"单邮件关键词输出，默认 {TFIDF_TOP_KEYWORDS_FILE.relative_to(ROOT)}")
    parser.add_argument("--global-top-output", type=Path, default=TFIDF_GLOBAL_TOP_FILE,
                        help=f"全局关键词输出，默认 {TFIDF_GLOBAL_TOP_FILE.relative_to(ROOT)}")
    parser.add_argument("--stopwords", type=Path, default=None,
                        help="可选停用词文件：JSON 字符串列表，或一行一个词的文本文件")
    parser.add_argument("--min-df", type=int, default=5,
                        help="低于该文档频次的词过滤掉，默认 5")
    parser.add_argument("--max-df", type=float, default=0.95,
                        help="高于该文档比例的词过滤掉，默认 0.95")
    parser.add_argument("--max-features", type=int, default=50000,
                        help="最多保留特征数，默认 50000")
    parser.add_argument("--top-n-per-doc", type=int, default=20,
                        help="每封邮件保存的关键词数，默认 20")
    parser.add_argument("--global-top-n", type=int, default=200,
                        help="保存的全局平均 TF-IDF 关键词数，默认 200")
    parser.add_argument(
        "--for-clustering", action="store_true",
        help="生成聚类专用 TF-IDF：复用 tokenized_email.jsonl，过滤 cluster_stopwords，"
             "max_df=0.25，sublinear_tf=True，输出 tfidf_cluster_* 产物",
    )
    parser.add_argument("--sublinear-tf", action="store_true",
                        help="TfidfVectorizer(sublinear_tf=True)；--for-clustering 时默认开启")
    args = parser.parse_args()

    if args.for_clustering:
        args.max_df = 0.25
        args.sublinear_tf = True
        args.matrix_output = TFIDF_CLUSTER_MATRIX_FILE
        args.vocab_output = TFIDF_CLUSTER_VOCAB_FILE
        args.feature_names_output = TFIDF_CLUSTER_FEATURE_NAMES_FILE
        args.top_keywords_output = TFIDF_CLUSTER_TOP_KEYWORDS_FILE
        args.global_top_output = TFIDF_CLUSTER_GLOBAL_TOP_FILE
        if args.stopwords is None:
            args.stopwords = CLUSTER_STOPWORDS_FILE

    if not args.input.exists():
        raise SystemExit(f"找不到输入文件：{args.input}")

    ensure_dir(DATA_DIR)
    ensure_dir(TFIDF_DIR)

    jieba_module, TfidfVectorizer, save_npz = _import_runtime_deps()

    cluster_filter: set[str] = set()
    if args.for_clustering:
        cluster_filter = load_stopwords(CLUSTER_STOPWORDS_FILE)
        if not TOKENIZED_FILE.exists():
            raise SystemExit(
                f"--for-clustering 需要已有分词文件 {TOKENIZED_FILE}，请先运行默认 tokenize_and_tfidf.py"
            )
        record_ids, docs, stats = load_tokenized_docs(TOKENIZED_FILE, filter_tokens=cluster_filter)
        print(f"聚类模式：复用 {TOKENIZED_FILE.name}，过滤 {len(cluster_filter)} 个聚类停用词")
    else:
        for word in PLACEHOLDERS:
            jieba_module.add_word(word, freq=10_000_000)
        stopwords = load_stopwords(args.stopwords)
        record_ids, docs, stats = build_tokenized_file(
            input_path=args.input,
            output_path=args.tokenized_output,
            jieba_module=jieba_module,
            stopwords=stopwords,
        )

    vectorizer = TfidfVectorizer(
        tokenizer=str.split,
        token_pattern=None,
        lowercase=False,
        min_df=args.min_df,
        max_df=args.max_df,
        max_features=args.max_features,
        sublinear_tf=args.sublinear_tf,
        norm="l2",
    )
    matrix = vectorizer.fit_transform(docs)
    feature_names = vectorizer.get_feature_names_out().tolist()

    ensure_dir(args.matrix_output.parent)
    save_npz(args.matrix_output, matrix)
    write_json(args.vocab_output, serializable_vocab(vectorizer.vocabulary_))
    write_json(args.feature_names_output, feature_names)
    write_json(args.record_ids_output, record_ids)

    save_top_keywords(
        path=args.top_keywords_output,
        matrix=matrix,
        feature_names=feature_names,
        record_ids=record_ids,
        top_n=args.top_n_per_doc,
    )

    global_mean = matrix.mean(axis=0).A1
    global_scores = sorted(
        zip(feature_names, global_mean),
        key=lambda x: x[1],
        reverse=True,
    )
    global_top = {
        "top_keywords": [
            {"token": token, "score": round(float(score), 8)}
            for token, score in global_scores[:args.global_top_n]
        ],
        "placeholder_ranks": placeholder_rank(global_scores),
    }
    write_json(args.global_top_output, global_top)

    n_docs, n_features = matrix.shape
    density = matrix.nnz / (n_docs * n_features) if n_docs and n_features else 0.0
    print(f"分词完成：{stats['records']} 条 → {args.tokenized_output if not args.for_clustering else TOKENIZED_FILE.name + ' (复用)'}")
    print(f"  token 总数：{stats['tokens']}；分词后为空：{stats['empty_after_tokenize']}")
    if not args.for_clustering:
        print("  占位符 token 次数：")
        for token in PLACEHOLDERS:
            print(f"    {token:<8s}: {stats[token]}")
    print(f"TF-IDF 完成：矩阵 {n_docs} x {n_features}，非零元素 {matrix.nnz}，密度 {density:.6f}"
          f"{'  sublinear_tf=True' if args.sublinear_tf else ''}"
          f"{'  max_df=0.25' if args.for_clustering else ''}")
    print(f"  矩阵：{args.matrix_output}")
    print(f"  词表：{args.vocab_output}")
    print(f"  每封邮件关键词：{args.top_keywords_output}")
    print(f"  全局关键词：{args.global_top_output}")
    if not args.for_clustering:
        print("  占位符全局平均 TF-IDF 排名：")
        for token, item in global_top["placeholder_ranks"].items():
            print(f"    {token:<8s}: rank={item['rank']} score={item['score']}")


if __name__ == "__main__":
    main()
