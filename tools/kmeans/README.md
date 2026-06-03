# KMeans 工具（早期探索）

无监督聚类仅作调参、对照与特征探索，**不属于** `schemes/scheme1` 或 `schemes/scheme2` 的提交标签。

## 脚本

从仓库根目录执行（脚本在 `script/`，产物写入本目录）：

```bash
python script/cluster_baseline.py --k 5
python script/kmeans6_compare.py
```

## 产物

- `outputs/` — `submit.csv`、`cluster_labels.jsonl`、`cluster_keywords.csv` 等
- `results/` — `cluster_metrics.json`、与 hybrid 对照报告等
