"""KMeans 基线聚类：在 TF-IDF 稀疏矩阵上聚类并导出解释性产物。

输入  : data/tfidf/tfidf_matrix.npz
        data/tfidf/tfidf_record_ids.json
        data/tfidf/tfidf_feature_names.json
        data/concat_email.jsonl          （样本展示用 text）
        data/tokenized_email.jsonl       （识别空样本）
        data/tfidf/tfidf_top_keywords.jsonl    （可选，样本 Top 关键词）

输出  : data/cluster_labels.jsonl
        submit.csv
        cluster_keywords.csv
        cluster_samples.xlsx
        results/cluster_metrics.json     （--scan-k 时生成 / 更新）

用法：
  python script/cluster_baseline.py              # 默认 K=5
  python script/cluster_baseline.py --k 8
  python script/cluster_baseline.py --scan-k --skip-cluster   # 仅扫描 K，写入 metrics
  python script/cluster_baseline.py --scan-k --k 5            # 先扫描再按 K=5 聚类
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

import numpy as np

from project_dirs import DATA_DIR, TFIDF_DIR

ROOT = Path(__file__).resolve().parent.parent
KMEANS_DIR = ROOT / "tools" / "kmeans"
MATRIX_FILE = TFIDF_DIR / "tfidf_matrix.npz"
RECORD_IDS_FILE = TFIDF_DIR / "tfidf_record_ids.json"
FEATURE_NAMES_FILE = TFIDF_DIR / "tfidf_feature_names.json"
CONCAT_FILE = DATA_DIR / "concat_email.jsonl"
TOKENIZED_FILE = DATA_DIR / "tokenized_email.jsonl"
TOP_KEYWORDS_FILE = TFIDF_DIR / "tfidf_top_keywords.jsonl"

LABELS_FILE = KMEANS_DIR / "outputs" / "cluster_labels.jsonl"
SUBMIT_FILE = KMEANS_DIR / "outputs" / "submit.csv"
KEYWORDS_FILE = KMEANS_DIR / "outputs" / "cluster_keywords.csv"
SAMPLES_FILE = KMEANS_DIR / "outputs" / "cluster_samples.xlsx"
METRICS_FILE = KMEANS_DIR / "results" / "cluster_metrics.json"

DEFAULT_K = 5
DEFAULT_SCAN_KS = (8, 10, 12, 15, 18, 20, 25, 30)
EMPTY_CLUSTER_ID = -1


def _import_deps():
    try:
        from scipy.sparse import load_npz  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 scipy，请先安装：pip install scipy") from exc

    try:
        from sklearn.cluster import KMeans, MiniBatchKMeans  # type: ignore
        from sklearn.decomposition import TruncatedSVD  # type: ignore
        from sklearn.metrics import silhouette_score  # type: ignore
        from sklearn.preprocessing import Normalizer  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 scikit-learn，请先安装：pip install scikit-learn") from exc

    return load_npz, KMeans, MiniBatchKMeans, TruncatedSVD, Normalizer, silhouette_score


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_text_map(path: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            rid = str(obj.get("record_id", ""))
            text = obj.get("text", "")
            mapping[rid] = text if isinstance(text, str) else ""
    return mapping


def load_top_keywords(path: Path) -> dict[str, list[str]]:
    mapping: dict[str, list[str]] = {}
    if not path.exists():
        return mapping
    with path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            rid = str(obj.get("record_id", ""))
            kws = obj.get("keywords", [])
            if isinstance(kws, list):
                mapping[rid] = [
                    str(item.get("token", ""))
                    for item in kws[:5]
                    if isinstance(item, dict) and item.get("token")
                ]
    return mapping


def find_empty_row_indices(tokenized_path: Path, record_ids: list[str]) -> set[int]:
    """分词后 tokens 为空的行不参与 KMeans，标记为 cluster -1。"""
    empty_ids: set[str] = set()
    with tokenized_path.open("r", encoding="utf-8") as fin:
        for line in fin:
            if not line.strip():
                continue
            obj = json.loads(line)
            tokens = obj.get("tokens", [])
            if not tokens:
                empty_ids.add(str(obj.get("record_id", "")))
    return {i for i, rid in enumerate(record_ids) if rid in empty_ids}


def scan_k_values(
    X,
    ks: tuple[int, ...],
    *,
    MiniBatchKMeans,
    silhouette_score,
    random_state: int,
) -> list[dict]:
    """用 MiniBatchKMeans 快速扫描多个 K，返回 inertia / silhouette 指标。"""
    metrics: list[dict] = []
    for k in ks:
        model = MiniBatchKMeans(
            n_clusters=k,
            random_state=random_state,
            batch_size=2048,
            n_init=3,
            max_iter=100,
        )
        labels = model.fit_predict(X)
        sil = float(silhouette_score(X, labels, metric="euclidean"))
        metrics.append({
            "k": k,
            "inertia": float(model.inertia_),
            "silhouette": round(sil, 6),
            "cluster_sizes": [int(np.sum(labels == c)) for c in range(k)],
        })
        print(f"  K={k:<3d}  inertia={model.inertia_:.2f}  silhouette={sil:.4f}")
    return metrics


def pick_recommended_k(metrics: list[dict]) -> int:
    """轮廓系数最高且 cluster 大小不太悬殊的 K。"""
    best = max(metrics, key=lambda m: m["silhouette"])
    return int(best["k"])


def cluster_keywords(
    centers: np.ndarray,
    feature_names: list[str],
    *,
    top_n: int,
) -> dict[int, list[tuple[str, float]]]:
    result: dict[int, list[tuple[str, float]]] = {}
    for cid in range(centers.shape[0]):
        center = centers[cid]
        top_idx = np.argsort(center)[-top_n:][::-1]
        result[cid] = [(feature_names[i], float(center[i])) for i in top_idx if center[i] > 0]
    return result


def cluster_keywords_from_members(
    X,
    labels: np.ndarray,
    feature_names: list[str],
    *,
    top_n: int,
) -> dict[int, list[tuple[str, float]]]:
    """在原始 TF-IDF 空间按簇求均值向量，取 Top 词（SVD 聚类后的可解释关键词）。"""
    result: dict[int, list[tuple[str, float]]] = {}
    unique_labels = sorted(set(int(x) for x in labels))
    for cid in unique_labels:
        mask = labels == cid
        if not np.any(mask):
            result[cid] = []
            continue
        mean_vec = X[mask].mean(axis=0)
        mean_dense = np.asarray(mean_vec).ravel()
        top_idx = np.argsort(mean_dense)[-top_n:][::-1]
        result[cid] = [
            (feature_names[i], float(mean_dense[i]))
            for i in top_idx
            if mean_dense[i] > 0
        ]
    return result


def prepare_clustering_matrix(
    X,
    *,
    svd_components: int | None,
    random_state: int,
    TruncatedSVD,
    Normalizer,
):
    """可选 LSA 降维 + L2 归一；返回聚类用矩阵与 SVD 模型（若有）。"""
    if svd_components is None:
        return X, None
    n_features = X.shape[1]
    n_comp = min(svd_components, max(1, n_features - 1))
    svd = TruncatedSVD(n_components=n_comp, random_state=random_state)
    X_reduced = svd.fit_transform(X)
    X_cluster = Normalizer(copy=False).fit_transform(X_reduced)
    return X_cluster, svd


def prefixed_path(base: Path, prefix: str) -> Path:
    """submit.csv + prefix=v2 → submit_v2.csv；data/foo.jsonl → data/foo_v2.jsonl。"""
    if not prefix:
        return base
    return base.with_name(f"{base.stem}_{prefix}{base.suffix}")


def nearest_samples(
    X,
    labels: np.ndarray,
    centers: np.ndarray,
    record_ids: list[str],
    *,
    top_n: int,
) -> dict[int, list[tuple[str, float]]]:
    """每个 cluster 取距中心最近的 top_n 个样本。"""
    from sklearn.metrics.pairwise import euclidean_distances

    result: dict[int, list[tuple[str, float]]] = {}
    for cid in range(centers.shape[0]):
        idx = np.where(labels == cid)[0]
        if len(idx) == 0:
            result[cid] = []
            continue
        sub = X[idx]
        dist = euclidean_distances(sub, centers[cid].reshape(1, -1)).ravel()
        order = np.argsort(dist)[:top_n]
        result[cid] = [(record_ids[idx[i]], float(dist[i])) for i in order]
    return result


def write_labels_jsonl(path: Path, record_ids: list[str], labels: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fout:
        for rid, label in zip(record_ids, labels):
            fout.write(json.dumps({"record_id": rid, "cluster_id": int(label)}, ensure_ascii=False) + "\n")


def write_submit_csv(path: Path, record_ids: list[str], labels: np.ndarray) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(["record_id", "cluster_id"])
        for rid, label in zip(record_ids, labels):
            writer.writerow([rid, int(label)])


def write_keywords_csv(path: Path, kw_by_cluster: dict[int, list[tuple[str, float]]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as fout:
        writer = csv.writer(fout)
        writer.writerow(["cluster_id", "rank", "token", "score"])
        for cid in sorted(kw_by_cluster):
            for rank, (token, score) in enumerate(kw_by_cluster[cid], start=1):
                writer.writerow([cid, rank, token, round(score, 8)])


def write_samples_xlsx(
    path: Path,
    samples_by_cluster: dict[int, list[tuple[str, float]]],
    text_map: dict[str, str],
    kw_preview: dict[str, list[str]],
    *,
    preview_len: int = 200,
) -> None:
    try:
        from openpyxl import Workbook  # type: ignore
    except ImportError as exc:
        raise SystemExit("缺少依赖 openpyxl，请先安装：pip install openpyxl") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook(write_only=True)
    ws = wb.create_sheet("cluster_samples")
    ws.append(["cluster_id", "rank", "record_id", "distance", "text_preview", "top_keywords"])

    for cid in sorted(samples_by_cluster):
        for rank, (rid, dist) in enumerate(samples_by_cluster[cid], start=1):
            text = text_map.get(rid, "")
            preview = text[:preview_len] + ("..." if len(text) > preview_len else "")
            kws = " / ".join(kw_preview.get(rid, []))
            ws.append([cid, rank, rid, round(dist, 6), preview, kws])

    wb.save(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="TF-IDF 矩阵 KMeans 基线聚类。")
    parser.add_argument("--k", type=int, default=DEFAULT_K, help=f"聚类数，默认 {DEFAULT_K}")
    parser.add_argument("--scan-k", action="store_true", help="扫描多个 K 并写入 cluster_metrics.json")
    parser.add_argument(
        "--scan-ks", type=int, nargs="+", default=list(DEFAULT_SCAN_KS),
        help=f"--scan-k 时扫描的 K 列表，默认 {list(DEFAULT_SCAN_KS)}",
    )
    parser.add_argument("--random-state", type=int, default=42, help="随机种子，默认 42")
    parser.add_argument("--samples-per-cluster", type=int, default=10, help="每个 cluster 导出样本数，默认 10")
    parser.add_argument("--keywords-per-cluster", type=int, default=20, help="每个 cluster 导出关键词数，默认 20")
    parser.add_argument("--skip-cluster", action="store_true", help="仅 --scan-k 时使用：扫描后不跑正式聚类")
    parser.add_argument("--matrix", type=Path, default=MATRIX_FILE,
                        help=f"TF-IDF 矩阵，默认 {MATRIX_FILE.name}")
    parser.add_argument("--feature-names", type=Path, default=FEATURE_NAMES_FILE,
                        help=f"特征名 JSON，默认 {FEATURE_NAMES_FILE.name}")
    parser.add_argument("--output-prefix", default="",
                        help="产物文件名前缀，如 v2 → submit_v2.csv")
    parser.add_argument("--svd-components", type=int, default=None,
                        help="TruncatedSVD 降维维数；不设则直接在 TF-IDF 上聚类")
    parser.add_argument("--no-svd", action="store_true", help="显式关闭 SVD（与 --svd-components 互斥）")
    args = parser.parse_args()

    if args.no_svd:
        args.svd_components = None

    load_npz, KMeans, MiniBatchKMeans, TruncatedSVD, Normalizer, silhouette_score = _import_deps()

    labels_file = prefixed_path(LABELS_FILE, args.output_prefix)
    submit_file = prefixed_path(SUBMIT_FILE, args.output_prefix)
    keywords_file = prefixed_path(KEYWORDS_FILE, args.output_prefix)
    samples_file = prefixed_path(SAMPLES_FILE, args.output_prefix)
    metrics_file = prefixed_path(METRICS_FILE, args.output_prefix)

    for path in (args.matrix, RECORD_IDS_FILE, args.feature_names, CONCAT_FILE, TOKENIZED_FILE):
        if not path.exists():
            raise SystemExit(f"找不到输入文件：{path}")

    X = load_npz(args.matrix)
    record_ids = load_json(RECORD_IDS_FILE)
    feature_names = load_json(args.feature_names)

    if X.shape[0] != len(record_ids):
        raise SystemExit(f"矩阵行数 {X.shape[0]} 与 record_ids 长度 {len(record_ids)} 不一致")

    empty_rows = find_empty_row_indices(TOKENIZED_FILE, record_ids)
    valid_mask = np.ones(X.shape[0], dtype=bool)
    valid_mask[list(empty_rows)] = False
    X_valid = X[valid_mask]

    print(f"加载矩阵：{X.shape[0]} x {X.shape[1]}，有效样本 {X_valid.shape[0]}，空样本 {len(empty_rows)}")

    metrics_file.parent.mkdir(parents=True, exist_ok=True)

    X_cluster, svd_model = prepare_clustering_matrix(
        X_valid,
        svd_components=args.svd_components,
        random_state=args.random_state,
        TruncatedSVD=TruncatedSVD,
        Normalizer=Normalizer,
    )
    if svd_model is not None:
        print(f"LSA 降维：{X_valid.shape[1]} → {X_cluster.shape[1]} 维，再 L2 归一")

    if args.scan_k:
        print(f"扫描 K：{args.scan_ks}")
        metrics = scan_k_values(
            X_cluster,
            tuple(args.scan_ks),
            MiniBatchKMeans=MiniBatchKMeans,
            silhouette_score=silhouette_score,
            random_state=args.random_state,
        )
        recommended = pick_recommended_k(metrics)
        payload = {
            "scan_ks": args.scan_ks,
            "metrics": metrics,
            "recommended_k": recommended,
        }
        metrics_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"推荐 K={recommended}（轮廓系数最高）→ {metrics_file}")
        if args.skip_cluster:
            return

    print(f"正式聚类：KMeans，K={args.k}，random_state={args.random_state}")
    model = KMeans(
        n_clusters=args.k,
        random_state=args.random_state,
        n_init=10,
        max_iter=300,
    )
    valid_labels = model.fit_predict(X_cluster)
    sil = float(silhouette_score(X_cluster, valid_labels, metric="euclidean"))

    labels = np.full(X.shape[0], EMPTY_CLUSTER_ID, dtype=int)
    labels[valid_mask] = valid_labels

    sizes = Counter(int(x) for x in labels)
    print(f"  inertia={model.inertia_:.2f}  silhouette={sil:.4f}")
    print("  cluster 大小：")
    for cid in sorted(sizes):
        name = "空集合" if cid == EMPTY_CLUSTER_ID else f"cluster {cid}"
        print(f"    {name:<12s}: {sizes[cid]}")

    kw_by_cluster = cluster_keywords_from_members(
        X_valid, valid_labels, feature_names, top_n=args.keywords_per_cluster,
    )
    samples_by_cluster = nearest_samples(
        X_cluster, valid_labels, model.cluster_centers_,
        [record_ids[i] for i in np.where(valid_mask)[0]],
        top_n=args.samples_per_cluster,
    )

    text_map = load_text_map(CONCAT_FILE)
    kw_preview = load_top_keywords(TOP_KEYWORDS_FILE)

    write_labels_jsonl(labels_file, record_ids, labels)
    write_submit_csv(submit_file, record_ids, labels)
    write_keywords_csv(keywords_file, kw_by_cluster)
    write_samples_xlsx(samples_file, samples_by_cluster, text_map, kw_preview)

    valid_sizes = {str(cid): int(np.sum(valid_labels == cid)) for cid in range(args.k)}
    max_cluster_pct = max(valid_sizes.values()) / X_valid.shape[0] * 100 if valid_sizes else 0.0

    run_metrics = {
        "k": args.k,
        "random_state": args.random_state,
        "matrix": str(args.matrix),
        "svd_components": args.svd_components,
        "output_prefix": args.output_prefix or None,
        "n_samples": int(X.shape[0]),
        "n_valid": int(X_valid.shape[0]),
        "n_empty": len(empty_rows),
        "inertia": float(model.inertia_),
        "silhouette": round(sil, 6),
        "max_cluster_pct": round(max_cluster_pct, 2),
        "cluster_sizes": {str(cid): int(sizes[cid]) for cid in sorted(sizes)},
        "valid_cluster_sizes": valid_sizes,
    }
    if metrics_file.exists() and args.scan_k:
        existing = json.loads(metrics_file.read_text(encoding="utf-8"))
        existing["final_run"] = run_metrics
        metrics_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        metrics_file.write_text(json.dumps({"final_run": run_metrics}, ensure_ascii=False, indent=2), encoding="utf-8")

    rel = lambda p: p.relative_to(ROOT) if p.is_relative_to(ROOT) else p
    print(f"  最大 cluster 占比：{max_cluster_pct:.1f}%")
    print("产物：")
    print(f"  标签 JSONL   : {rel(labels_file)}")
    print(f"  提交 CSV     : {rel(submit_file)}")
    print(f"  关键词 CSV   : {rel(keywords_file)}")
    print(f"  样本 Excel   : {rel(samples_file)}")
    print(f"  指标 JSON    : {rel(metrics_file)}")


if __name__ == "__main__":
    main()
