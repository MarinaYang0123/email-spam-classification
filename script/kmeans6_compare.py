"""全量 KMeans(K=6) 基准 vs 现有混合分类对比。

前提：数据集全部为垃圾邮件，不做「正常邮件」类别。

输入  : data/tfidf/tfidf_cluster_matrix.npz
        data/tfidf/tfidf_cluster_feature_names.json
        data/tfidf/tfidf_record_ids.json
        data/final_labels.jsonl          （hybrid_classify 产物）
        data/concat_email.jsonl

输出  : data/kmeans6_labels.jsonl
        submit_k6.csv
        kmeans6_keywords.csv
        results/kmeans6_vs_hybrid.md
        results/kmeans6_metrics.json
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from project_dirs import DATA_DIR, TFIDF_DIR

ROOT = Path(__file__).resolve().parent.parent
KMEANS_DIR = ROOT / "tools" / "kmeans"
MATRIX_FILE = TFIDF_DIR / "tfidf_cluster_matrix.npz"
FEATURE_NAMES_FILE = TFIDF_DIR / "tfidf_cluster_feature_names.json"
RECORD_IDS_FILE = TFIDF_DIR / "tfidf_record_ids.json"
HYBRID_LABELS_FILE = ROOT / "schemes" / "scheme1_semantic5" / "outputs" / "labels.jsonl"
CONCAT_FILE = DATA_DIR / "concat_email.jsonl"

OUT_LABELS = KMEANS_DIR / "outputs" / "kmeans6_labels.jsonl"
OUT_SUBMIT = KMEANS_DIR / "outputs" / "submit_k6.csv"
OUT_KEYWORDS = KMEANS_DIR / "outputs" / "kmeans6_keywords.csv"
OUT_REPORT = KMEANS_DIR / "results" / "kmeans6_vs_hybrid.md"
OUT_METRICS = KMEANS_DIR / "results" / "kmeans6_metrics.json"

HYBRID_CATS = ("暴力色情", "广告营销", "钓鱼邮件", "赌博博彩", "学术会议/期刊营销", "未分类", "空样本")


def _import_deps():
    try:
        from scipy.sparse import load_npz  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 scipy") from exc
    try:
        from sklearn.cluster import KMeans  # type: ignore
        from sklearn.decomposition import TruncatedSVD  # type: ignore
        from sklearn.metrics import adjusted_rand_score, normalized_mutual_info_score, silhouette_score  # type: ignore
        from sklearn.preprocessing import Normalizer  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 scikit-learn") from exc
    return load_npz, KMeans, TruncatedSVD, Normalizer, silhouette_score, adjusted_rand_score, normalized_mutual_info_score


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_hybrid_labels(path: Path) -> dict[str, str]:
    out = {}
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            out[str(obj["record_id"])] = obj["category"]
    return out


def cluster_keywords(X, labels: np.ndarray, feature_names: list[str], top_n: int) -> dict[int, list[tuple[str, float]]]:
    out: dict[int, list[tuple[str, float]]] = {}
    for cid in sorted(set(int(x) for x in labels)):
        mask = labels == cid
        mean_dense = np.asarray(X[mask].mean(axis=0)).ravel()
        top_idx = np.argsort(mean_dense)[-top_n:][::-1]
        out[cid] = [(feature_names[i], float(mean_dense[i])) for i in top_idx if mean_dense[i] > 0]
    return out


def suggest_semantic_name(keywords: list[tuple[str, float]]) -> str:
    """根据 Top 词启发式命名 KMeans 簇（全为垃圾语义）。"""
    tops = {w for w, _ in keywords[:12]}
    tops_str = " ".join(tops)
    if any(w in tops for w in ("葡京", "bbin", "mg", "pt", "打码", "领彩")):
        return "赌博博彩"
    if any(w in tops for w in ("journal", "conference", "sci", "research", "投稿", "论文", "期刊")):
        return "学术会议/期刊营销"
    if any(w in tops for w in ("发票", "开发票", "代开", "材料费", "服务费")):
        return "广告营销(发票/费用)"
    if any(w in tops for w in ("account", "verify", "login", "password", "mailbox", "登录", "验证")):
        return "钓鱼邮件"
    if any(w in tops for w in ("国产", "无码", "罗莉", "sex", "dating", "porn", "啪啪")):
        return "暴力色情"
    if any(w in tops for w in ("how", "hi", "hey", "profile", "visit")):
        return "英文引流/外链"
    return "待命名簇"


def main() -> None:
    parser = argparse.ArgumentParser(description="KMeans K=6 全量聚类并与 hybrid 分类对比")
    parser.add_argument("--k", type=int, default=6)
    parser.add_argument("--svd-components", type=int, default=100)
    parser.add_argument("--random-state", type=int, default=42)
    parser.add_argument("--top-keywords", type=int, default=20)
    args = parser.parse_args()

    load_npz, KMeans, TruncatedSVD, Normalizer, silhouette_score, ari, nmi = _import_deps()

    for p in (MATRIX_FILE, FEATURE_NAMES_FILE, RECORD_IDS_FILE, HYBRID_LABELS_FILE):
        if not p.exists():
            raise SystemExit(f"缺少 {p}")

    record_ids = load_json(RECORD_IDS_FILE)
    feature_names = load_json(FEATURE_NAMES_FILE)
    X = load_npz(MATRIX_FILE)
    hybrid = load_hybrid_labels(HYBRID_LABELS_FILE)

    n_comp = min(args.svd_components, max(1, X.shape[1] - 1), max(1, X.shape[0] - 1))
    svd = TruncatedSVD(n_components=n_comp, random_state=args.random_state)
    reduced = Normalizer(copy=False).fit_transform(svd.fit_transform(X))

    model = KMeans(n_clusters=args.k, random_state=args.random_state, n_init=10, max_iter=300)
    k_labels = model.fit_predict(reduced)

    sil = float(silhouette_score(reduced, k_labels, sample_size=min(5000, len(k_labels)), random_state=args.random_state))

    # hybrid 标签 → 整数（对比用，未分类/空样本保留）
    hybrid_cat_list = sorted(set(hybrid.get(rid, "未分类") for rid in record_ids))
    h2i = {c: i for i, c in enumerate(hybrid_cat_list)}
    h_int = np.array([h2i[hybrid.get(rid, "未分类")] for rid in record_ids])

    ari_score = float(ari(h_int, k_labels))
    nmi_score = float(nmi(h_int, k_labels))

    kw = cluster_keywords(X, k_labels, feature_names, args.top_keywords)

    # 交叉表：KMeans 簇 × hybrid 类
    crosstab: dict[int, Counter] = {i: Counter() for i in range(args.k)}
    for rid, kl in zip(record_ids, k_labels):
        crosstab[int(kl)][hybrid.get(rid, "未分类")] += 1

    cluster_names = {cid: suggest_semantic_name(kws) for cid, kws in kw.items()}

    # 每个 hybrid 类的主 KMeans 簇（纯度）
    hybrid_to_k: dict[str, dict] = {}
    row_of = {rid: i for i, rid in enumerate(record_ids)}
    for cat in HYBRID_CATS:
        ids = [rid for rid in record_ids if hybrid.get(rid) == cat]
        if not ids:
            continue
        k_dist = Counter(int(k_labels[row_of[rid]]) for rid in ids)
        main_k, main_n = k_dist.most_common(1)[0]
        hybrid_to_k[cat] = {
            "count": len(ids),
            "main_kmeans_cluster": main_k,
            "main_kmeans_name": cluster_names.get(main_k, "?"),
            "purity": round(main_n / len(ids), 3),
            "spread_clusters": len(k_dist),
        }

    # 写 KMeans 产物
    OUT_LABELS.parent.mkdir(parents=True, exist_ok=True)
    with OUT_LABELS.open("w", encoding="utf-8") as fout:
        for rid, kl in zip(record_ids, k_labels):
            cid = int(kl)
            fout.write(json.dumps({
                "record_id": rid,
                "cluster_id": cid,
                "cluster_name": cluster_names.get(cid, f"簇{cid}"),
            }, ensure_ascii=False) + "\n")

    with OUT_SUBMIT.open("w", encoding="utf-8-sig", newline="") as fout:
        w = csv.writer(fout)
        w.writerow(["record_id", "cluster_id", "cluster_name"])
        for rid, kl in zip(record_ids, k_labels):
            cid = int(kl)
            w.writerow([rid, cid, cluster_names.get(cid, f"簇{cid}")])

    with OUT_KEYWORDS.open("w", encoding="utf-8-sig", newline="") as fout:
        w = csv.writer(fout)
        w.writerow(["cluster_id", "cluster_name", "rank", "token", "score"])
        for cid in sorted(kw):
            for rank, (tok, score) in enumerate(kw[cid], 1):
                w.writerow([cid, cluster_names.get(cid, ""), rank, tok, round(score, 6)])

    sizes = Counter(int(x) for x in k_labels)
    lines = [
        "# KMeans-6 全量聚类 vs 混合分类对比",
        "",
        "> 数据集全部为垃圾邮件；KMeans 仅作无监督参照，不引入「正常邮件」类。",
        "",
        f"- K={args.k}，LSA 维数={n_comp}",
        f"- silhouette={sil:.4f}，ARI(vs hybrid)={ari_score:.4f}，NMI={nmi_score:.4f}",
        "",
        "## KMeans 簇分布",
        "",
        "| cluster_id | 启发式命名 | 数量 | 占比 | Top 词 |",
        "|---:|---|---:|---:|---|",
    ]
    total = len(record_ids)
    for cid in sorted(sizes):
        pct = sizes[cid] / total * 100
        top = "、".join(w for w, _ in kw[cid][:10])
        lines.append(f"| {cid} | {cluster_names[cid]} | {sizes[cid]} | {pct:.1f}% | {top} |")

    lines += ["", "## 交叉表：KMeans 簇内 hybrid 类别构成（行=KMeans，列=hybrid 计数 Top3）", ""]
    for cid in sorted(crosstab):
        top3 = crosstab[cid].most_common(3)
        desc = " · ".join(f"{c}({n})" for c, n in top3)
        lines.append(f"- **簇{cid} {cluster_names[cid]}**：{desc}")

    lines += ["", "## hybrid 各类在 KMeans 空间中的集中度", "",
              "| hybrid 类别 | 数量 | 主 KMeans 簇 | 簇内纯度 | 分散到几簇 | 评估 |",
              "|---|---:|---:|---:|---:|---|"]
    for cat in HYBRID_CATS:
        info = hybrid_to_k.get(cat)
        if not info:
            continue
        if info["purity"] >= 0.6 and info["spread_clusters"] <= 2:
            verdict = "✅ 与 KMeans 较一致"
        elif info["purity"] >= 0.4:
            verdict = "⚠️ 部分重叠，可迭代词表"
        else:
            verdict = "❌ 与 KMeans 结构不一致，建议复查"
        lines.append(
            f"| {cat} | {info['count']} | 簇{info['main_kmeans_cluster']}({info['main_kmeans_name']}) | "
            f"{info['purity']*100:.1f}% | {info['spread_clusters']} | {verdict} |"
        )

    lines += ["", "## 结论提示", "",
              "- **ARI/NMI 低不代表 hybrid 错误**：规则类带先验，KMeans 纯文本结构。",
              "- **纯度高**：说明 hybrid 类在文本空间有清晰边界。",
              "- **纯度低 / 分散多簇**：该类可能过宽、过窄或与它类语义重叠（如广告 vs 学术）。",
              "- **未分类**：若大量落入单一 KMeans 簇，说明存在稳定但未命名的垃圾子类。",
              ""]

    OUT_REPORT.parent.mkdir(parents=True, exist_ok=True)
    OUT_REPORT.write_text("\n".join(lines), encoding="utf-8")

    metrics = {
        "k": args.k,
        "svd_components": n_comp,
        "silhouette": sil,
        "ari_vs_hybrid": ari_score,
        "nmi_vs_hybrid": nmi_score,
        "cluster_sizes": {str(k): v for k, v in sorted(sizes.items())},
        "cluster_names": {str(k): v for k, v in cluster_names.items()},
        "hybrid_concentration": hybrid_to_k,
    }
    OUT_METRICS.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"KMeans K={args.k} 完成，silhouette={sil:.4f}")
    print(f"  vs hybrid: ARI={ari_score:.4f}, NMI={nmi_score:.4f}")
    print("  KMeans 分布：")
    for cid in sorted(sizes):
        print(f"    簇{cid} {cluster_names[cid]}: {sizes[cid]} ({sizes[cid]/total*100:.1f}%)")
    print(f"报告：{OUT_REPORT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
