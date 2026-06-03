# 邮件内容安全 · 第二次作业

## 1. 目录结构

```
.
├── config/                         # 清洗与聚类配置（字典、停用词、字段剥离列表）
│   ├── mars_chars.json
│   ├── phrase_map.json
│   ├── rm_words.json
│   ├── single_en_whitelist.json
│   └── cluster_stopwords.json
├── data/                           # 流水线中间数据（.gitignore，脚本运行时会自动创建）
│   ├── spam_email_data.log
│   ├── cleaned_emails.jsonl
│   ├── min_cleaned_email.jsonl
│   ├── deep_cleaned_email.jsonl
│   ├── concat_email.jsonl
│   ├── tokenized_email.jsonl
│   ├── tfidf/                      # TF-IDF 矩阵、词表、关键词等
│   └── structural_features.jsonl
├── schemes/                        # 两套正式五类方案（规则分类，见 schemes/README.md）
│   ├── scheme1_semantic5/          # 暴力色情 / 广告营销 / 钓鱼 / 学术会议期刊 / 赌博
│   │   ├── category_taxonomy.json
│   │   ├── classify.py
│   │   ├── outputs/                # submit.csv, labels.jsonl, keywords.csv, report.md …
│   │   └── results/                # llm_iterate 迭代产物
│   └── scheme2_balanced5/          # 暴力色情 / 发票营销 / 商业广告 / 钓鱼 / 学术营销
│       ├── category_taxonomy.json
│       ├── classify.py
│       └── outputs/
├── tools/
│   └── kmeans/                     # KMeans 早期探索（不入 schemes 提交）
│       ├── outputs/                # submit.csv, cluster_labels.jsonl, …
│       └── results/                # cluster_metrics.json, …
├── script/                         # 流水线 + 共享 rule_classify 引擎
│   ├── data_explore.py … tokenize_and_tfidf.py
│   ├── structural_features.py
│   ├── rule_classify.py            # 被 schemes/*/classify.py 调用
│   ├── hybrid_classify.py          # 兼容入口 → scheme1
│   ├── cluster_baseline.py         # 产物 → tools/kmeans/
│   ├── kmeans6_compare.py
│   └── llm_iterate.py              # 默认对接 scheme1
├── reports/                        # 实验报告 + 诊断/导出（.gitignore，脚本运行时会自动创建）
│   ├── 实验报告.md
│   ├── _field_stats.md             # data_explore 字段缺失率统计
│   ├── single_en_audit.jsonl       # deep_process --audit-single-en 审计（可选）
│   └── results/                    # export_classified 分类汇总导出
├── excel/                          # jsonl_to_excel 输出（.gitignore，脚本运行时会自动创建）
├── Plan.md
└── README.md
```

## 2. 流水线脚本

### 2.1 `data_explore.py`：原始日志 → 字段统计 + 基础清洗

逐行读 `data/spam_email_data.log`（`<record_id>\t<json>` 格式），输出：`data/cleaned_emails.jsonl`、`reports/_field_stats.md`；加 `--min_analysis` 时额外输出 `data/min_cleaned_email.jsonl`。

```bash
# 默认：JSONL + 字段统计 Markdown
python script/data_explore.py

# 同时输出精简版（剥掉 rm_words.json 列的字段）
python script/data_explore.py --min_analysis config/rm_words.json
```

清洗规则：空白压缩、HTML 实体解码、NFKC 归一、去外层成对引号、`@timestamp` → `timestamp`（ISO 解析失败记 `null`）、缺失语义统一。

### 2.2 `deep_process.py`：深度清洗（占位符化 / 繁简归一 / 单字母剥离）

对 `min_cleaned_email.jsonl` 的 `subject / content / doccontent / fromname` 做语义级归一；其余字段原样保留。

```bash
# 默认：data/min_cleaned_email.jsonl → data/deep_cleaned_email.jsonl
python script/deep_process.py

# 同时把"夹在汉字间的单字母剥离"每一处命中（含上下文）写到审计 JSONL，
# 默认落到 reports/single_en_audit.jsonl，方便人工迭代白名单
python script/deep_process.py --audit-single-en

# 写到自定义路径
python script/deep_process.py --audit-single-en my_audit.jsonl

# 改抽样对照条数（默认 3）
python script/deep_process.py --sample 10
```

配套字典：`config/mars_chars.json`、`config/phrase_map.json`、`config/single_en_whitelist.json`。

### 2.3 `concat_fields.py`：把多字段拼成单 `text` 字段

下游 jieba / TF-IDF / 聚类只关心一段连续文本。这一步把 `subject / content / doccontent / fromname` 顺序拼成单字段 `text`，跳过空字段，输出 `data/concat_email.jsonl`。

```bash
# 默认：仅保留 record_id + text，单空格分隔
python script/concat_fields.py

# 自定义分隔符 + 保留原始字段做对照
python script/concat_fields.py --sep " | " --keep-fields

# 自定义参与拼接的字段顺序
python script/concat_fields.py --fields subject content
```

控制台会打印 text 长度的分位数（min / p50 / p90 / p99 / max / avg）和各字段非空命中率，便于排查"是不是某个字段全是空"。

### 2.4 `tokenize_and_tfidf.py`：jieba 分词 + TF-IDF 特征生成

读取 `data/concat_email.jsonl`，输出一份分词 JSONL 和一组配套的 TF-IDF 产物，作为 KMeans / 分类模型的统一特征入口。

```bash
# 默认：data/concat_email.jsonl → data/tokenized_email.jsonl + data/tfidf/tfidf_*.{npz,json,jsonl}
python script/tokenize_and_tfidf.py

# 外挂停用词（JSON 字符串列表 或 一行一词的文本文件，会与内置停用词合并）
python script/tokenize_and_tfidf.py --stopwords my_stopwords.json

# 调 TF-IDF 过滤强度（默认 min_df=5, max_df=0.95, max_features=50000）
python script/tokenize_and_tfidf.py --min-df 10 --max-df 0.9 --max-features 30000

# 调每封邮件 / 全局保留的关键词数（默认 20 / 200）
python script/tokenize_and_tfidf.py --top-n-per-doc 30 --global-top-n 500
```

设计要点：

- **占位符整体保留**：`[URL] [EMAIL] [PHONE] [QQ] [WECHAT] [MONEY]` 先用正则切出，再把其余文本交给 `jieba.lcut`，避免方括号被切成噪声 token 而把占位符拆碎。
- **英文统一小写、占位符保大写**：normalize 阶段对纯字母 token 做 `.lower()`，占位符原样保留，可在结果里直接 grep。
- **过滤策略**：去掉空白 / 长度为 1 的孤立字符 / 纯数字 / 停用词；停用词默认是中英文常用虚词的小型集合，可经 `--stopwords` 扩充。
- **TF-IDF 走自定义分词**：`TfidfVectorizer(tokenizer=str.split, token_pattern=None, lowercase=False)`，直接消费已经分好的 token，绕过 sklearn 默认的英文正则，保证 `[EMAIL]` 不会再被切一次。

### 2.5 `structural_features.py`：并行结构特征流（钓鱼信号）

纯文本聚类无法识别「钓鱼」——证据在元数据字段里。本脚本**只读** `cleaned_emails.jsonl`（全字段），用 `record_id` 与文本线对齐。

```bash
python script/structural_features.py            # → data/structural_features.jsonl
```

派生字段：


| 字段                                           | 含义                                    |
| -------------------------------------------- | ------------------------------------- |
| `sender_domain`                              | 真实发件域名                                |
| `display_domain` / `display_domain_mismatch` | 显示名自称域名；与发件域不一致则为伪造嫌疑                 |
| `url_count` / `url_domains`                  | 正文 URL 域名列表                           |
| `url_sender_mismatch`                        | URL 域与发件域不一致（弱信号）                     |
| `url_suspicious`                             | URL 含 login/verify/account 等凭证路径（强信号） |
| `domainrep_max`                              | `domainrep` 多段串的最大信誉分                 |
| `has_attach` / `lang`                        | 是否含附件；zh/en/mixed 启发式语言               |


### 2.6 `jsonl_to_excel.py`：任意 JSONL → Excel


| 参数                | 默认值                         | 说明             |
| ----------------- | --------------------------- | -------------- |
| `-i` / `--input`  | `data/cleaned_emails.jsonl` | 输入 JSONL       |
| `-o` / `--output` | `excel/<输入同名>.xlsx`         | 不传则按 stem 自动命名 |


```bash
python script/jsonl_to_excel.py
python script/jsonl_to_excel.py -i data/min_cleaned_email.jsonl
python script/jsonl_to_excel.py -i schemes/scheme1_semantic5/outputs/unclassified_concat.jsonl -o excel/unclassified_concat_1.xlsx
```

### 2.7 `cluster_baseline.py`：KMeans 基线聚类（`tools/kmeans/`）

读取 `data/tfidf/tfidf_matrix.npz` 及配套索引文件，在 TF-IDF 稀疏矩阵上做 KMeans 聚类，并导出提交文件与解释性产物。分词后 token 为空的样本（通常 4 条）不参与聚类，标记为 `cluster_id = -1`。

```bash
# 默认 K=5 → submit.csv + cluster_keywords.csv + cluster_samples.xlsx
python script/cluster_baseline.py

# 指定 K
python script/cluster_baseline.py --k 8

# 仅扫描多个 K（MiniBatchKMeans），写入 results/cluster_metrics.json，不跑正式聚类
python script/cluster_baseline.py --scan-k --skip-cluster

# 先扫描再按 K=5 正式聚类（metrics 里同时保留 scan 与 final_run）
python script/cluster_baseline.py --scan-k --k 5

# 自定义扫描范围 / 每 cluster 导出样本数
python script/cluster_baseline.py --scan-k --skip-cluster --scan-ks 5 8 10 12 15
python script/cluster_baseline.py --samples-per-cluster 15 --keywords-per-cluster 30
```


| 参数                       | 默认值                      | 说明                                                           |
| ------------------------ | ------------------------ | ------------------------------------------------------------ |
| `--k`                    | `5`                      | 正式聚类使用的 K                                                    |
| `--scan-k`               | 关                        | 用 MiniBatchKMeans 扫描 `--scan-ks` 中各 K 的 inertia / silhouette |
| `--scan-ks`              | `8 10 12 15 18 20 25 30` | `--scan-k` 时扫描的 K 列表                                         |
| `--skip-cluster`         | 关                        | 与 `--scan-k` 联用：只扫描、不写聚类产物                                   |
| `--random-state`         | `42`                     | 随机种子                                                         |
| `--samples-per-cluster`  | `10`                     | `cluster_samples.xlsx` 每个 cluster 代表样本数                      |
| `--keywords-per-cluster` | `20`                     | `cluster_keywords.csv` 每个 cluster 中心词数                       |


设计要点：

- **空样本隔离**：依据 `tokenized_email.jsonl` 中 `tokens` 为空的记录，赋 `cluster_id = -1`，避免空向量拉偏中心。
- **正式聚类用 KMeans**：24 000 量级下约 20 ~ 30 秒；`--scan-k` 阶段用 MiniBatchKMeans 加速调参。
- **Cluster 关键词**：从 `cluster_centers_` 取权重 Top-N token（比简单词频更准确）。
- **代表样本**：每个 cluster 取距中心欧氏距离最近的 Top-N 封邮件，写入 Excel 便于人工核对语义。

产物（均在 `tools/kmeans/`）：


| 文件                             | 内容                               |
| ------------------------------ | -------------------------------- |
| `outputs/cluster_labels.jsonl` | `{"record_id", "cluster_id"}`    |
| `outputs/submit.csv`           | 提交用：`record_id, cluster_id`      |
| `outputs/cluster_keywords.csv` | `cluster_id, rank, token, score` |
| `outputs/cluster_samples.xlsx` | 每 cluster 代表样本 + text 预览         |
| `results/cluster_metrics.json` | K 扫描 / 正式聚类指标                    |


### 2.8 `kmeans6_compare.py`：K=6 聚类 vs 方案1 规则分类

探索用：在 `data/tfidf/tfidf_cluster_matrix.npz` 上跑 KMeans(K=6)，与 `scheme1` 的 `labels.jsonl` 对比 ARI/NMI，产物写入 `tools/kmeans/`。

```bash
python script/kmeans6_compare.py
python script/kmeans6_compare.py --k 6 --svd-components 100
```

### 2.9 规则五类分类（`rule_classify.py` + `schemes/`）

两套方案共用 `script/rule_classify.py`（词表匹配 + 钓鱼结构信号），**默认不使用 KMeans**。

**方案1**（`schemes/scheme1_semantic5/`）：暴力色情、广告营销、钓鱼邮件、学术会议/期刊营销、赌博博彩。

```bash
python schemes/scheme1_semantic5/classify.py
```

**方案2**（`schemes/scheme2_balanced5/`）：暴力色情、发票营销、商业广告、钓鱼邮件、学术营销（词表由方案1 拆分「广告营销」并迭代维护，见 `category_taxonomy.json`）。

```bash
python schemes/scheme2_balanced5/classify.py
```


| 方案  | 提交文件                                           |
| --- | ---------------------------------------------- |
| 方案1 | `schemes/scheme1_semantic5/outputs/submit.csv` |
| 方案2 | `schemes/scheme2_balanced5/outputs/submit.csv` |


每套 `outputs/` 含 `labels.jsonl`、`submit.csv`、`keywords.csv`、`samples.xlsx`、`report.md`。

**共享引擎 `script/rule_classify.py`**

**方案入口**：`schemes/scheme1_semantic5/classify.py`、`scheme2_balanced5/classify.py` 仅构造 `SchemeConfig` 并调用 `run_scheme`。

### 2.10 `hybrid_classify.py`：兼容入口

`runpy` 转发到 `schemes/scheme1_semantic5/classify.py`，旧命令仍可用。

### 2.11 `llm_iterate.py`：LLM 引导词表迭代（可选）

**定位**：开发期 copilot，审查未分类/探测类漏网样本 → 产出**五类**词表扩充建议（含赌博博彩、学术会议/期刊营销，并区分广告营销）→ 语料校验。

```bash
# 0) 先跑 classify.py 得到 labels.jsonl
python schemes/scheme1_semantic5/classify.py

# 1) 只抽样，不调 API
python script/llm_iterate.py --dry-run
python script/llm_iterate.py --scheme scheme2 --dry-run

# 2) 配置 API Key 后调用模型
python script/llm_iterate.py
python script/llm_iterate.py --scheme scheme2

# 3) 仅校验已有 proposal（2会自动校验并输出报告llm_iterate_report.md）
python script/llm_iterate.py --validate-only

# 4) 将校验通过的词写入建议词表
python script/llm_iterate.py --apply

# 5) 人工复核 category_taxonomy.suggested.json → 合并进 category_taxonomy.json → 重跑 classify
python schemes/scheme1_semantic5/classify.py
```


| 参数                        | 默认        | 说明                                           |
| ------------------------- | --------- | -------------------------------------------- |
| `--scheme`                | `scheme1` | `scheme1` / `scheme2`，决定词表与 results 目录       |
| `--dry-run`               | —         | 只写 `llm_iterate_samples.jsonl`，不调 API        |
| `--categories`            | 自动        | 有「探测类*」则抽探测类；否则「未分类+空样本」                     |
| `--per-category`          | 25        | 每类抽样数                                        |
| `--boundary-per-category` | 5         | 额外抽边界对照类（scheme 相关）                          |
| `--validate-only`         | —         | 语料覆盖率 / 误伤率校验                                |
| `--apply`                 | —         | 写 `category_taxonomy.suggested.json`（不覆盖原词表） |


产物（在对应 `schemes/*/results/`）：


| 文件                                 | 内容                                              |
| ---------------------------------- | ----------------------------------------------- |
| `llm_iterate_samples.jsonl`        | 发给模型的样本包                                        |
| `llm_iterate_proposal.json`        | add_keywords / reject_keywords / sample_reviews |
| `llm_iterate_validated.json`       | 每词命中数、误伤数、是否 recommend                          |
| `llm_iterate_report.md`            | 人读摘要                                            |
| `category_taxonomy.suggested.json` | `--apply` 后的建议词表                                |


### 2.12 `export_unclassified_full.py`：导出未分类邮件

按 `labels.jsonl` 或 `submit.csv` 筛出「未分类」等目标类别，从 `cleaned_emails.jsonl` 或 `concat_email.jsonl` 导出全字段/拼接文本到各方案 `outputs/`。

```bash
python script/export_unclassified_full.py
python script/export_unclassified_full.py --scheme scheme1 --source cleaned
python script/export_unclassified_full.py --scheme all --source concat --categories 未分类
```

### 2.13 `export_classified.py`：导出两套方案分类汇总

从 `cleaned_emails.jsonl` 取原始全字段，合并各方案 `labels.jsonl` 的 `category` / `cluster_id`，**按类别聚合排序**后写入 `reports/results/`。两套方案各一份，文件名含 scheme 区分。

```bash
# 默认：jsonl → reports/results/scheme1_semantic5_classified.jsonl 等
python script/export_classified.py

# 同时生成 CSV 类别统计（每方案一份 *_summary.csv）
python script/export_classified.py --summary

# 仅生成总结，不写明细
python script/export_classified.py --summary-only

# CSV / Excel 明细
python script/export_classified.py --format csv
python script/export_classified.py --format xlsx

# 仅导出某一方案
python script/export_classified.py --scheme scheme2
python script/export_classified.py --scheme scheme2 --summary-only
```


| 参数                | 默认                          | 说明                                                                   |
| ----------------- | --------------------------- | -------------------------------------------------------------------- |
| `--scheme`        | `all`                       | `scheme1` / `scheme2` / `all`                                        |
| `--format` / `-f` | `jsonl`                     | 明细格式：`jsonl` / `csv` / `xlsx`（xlsx 需 openpyxl）                       |
| `--summary`       | 关                           | 额外写 `{slug}_summary.csv`（rank / cluster_id / category / count / pct） |
| `--summary-only`  | 关                           | 只写 CSV 总结，跳过 classified 明细                                           |
| `--cleaned`       | `data/cleaned_emails.jsonl` | 原始清洗 JSONL                                                           |
| `--output-dir`    | `reports/results`           | 输出目录                                                                 |


### 2.14 辅助脚本（人工审计 / 一次性分析）


| 脚本                                | 用途                                                    |
| --------------------------------- | ----------------------------------------------------- |
| `script/_audit_summary.py`        | 统计 `reports/single_en_audit.jsonl` 高频字母段与右邻汉字，辅助维护白名单 |
| `script/_analyze_unclassified.py` | 对未分类样本做占位符/关键词命中的一次性探查（非流水线步骤）                        |


#### API Key 安全导入

**项目根目录** `.env` **文件**

```powershell
Copy-Item .env.example .env
# 用编辑器打开 .env，填入 OPENAI_API_KEY=sk-...
# .env 已在 .gitignore，不会被 git add
```

## 3. 一条龙跑通全流程

```bash
# 1) 字段统计 + 基础清洗 + 精简版（这一步同时产生三份产物）
python script/data_explore.py --min_analysis config/rm_words.json

# 2) 深度清洗（开审计便于后续维护白名单）
python script/deep_process.py --audit-single-en

# 3) 字段拼接 → 单字段 text
python script/concat_fields.py

# 4) jieba 分词 + TF-IDF → 通用特征；再生成聚类专用特征
python script/tokenize_and_tfidf.py
python script/tokenize_and_tfidf.py --for-clustering

# 5) KMeans 基线聚类（可选，用于对照）
python script/cluster_baseline.py

# 6) 并行结构特征流（钓鱼/风控信号，只读全字段）
python script/structural_features.py

# 7) 方案1 规则五类（或方案2，见 schemes/README.md）
python schemes/scheme1_semantic5/classify.py
# python schemes/scheme2_balanced5/classify.py

# 8) 任一阶段需要 Excel 时按需调用
python script/jsonl_to_excel.py -i data/deep_cleaned_email.jsonl
```

