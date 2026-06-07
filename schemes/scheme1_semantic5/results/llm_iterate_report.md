# LLM 词表迭代报告（scheme1）

- 生成时间：2026-06-07 20:28:10
- 审查样本数：39
- 其中 short_content（允许保持未分类）：11
- 保持未分类：3 / 39 条审查

## 模型总结

本轮审查发现未分类中主要漏网为英文色情/交友诱导、商业广告、疑似压缩包下载钓鱼，以及少量学术营销短样本；Crashlytics/监控/日报等技术告警无五类语义，归未分类不扩词。空样本和极短乱码样本谨慎保持或未分类，不写入词表。建议新增高置信、可由 tokens 精确匹配的短语，避免 login/notification/manager 等跨类噪声词。

## 样本审查（节选）

共 39 条审查记录，以下展示前 20 条：

- `rpdQfIeMh6`：未分类 → **未分类** (0.35) — 文本像随机姓名和小说片段，无五类垃圾语义。
- `YHshOloTp4`：未分类 → **未分类** (0.45) — 内容过短，仅有电话、附图、经理等，无法稳定归入五类；不使用保持未分类以控制比例。
- `36hcKpPHD5`：未分类 → **暴力色情** (0.62) — 英文交友/情感诱导模板，带 URL 和邮箱，属于 dating 类色情交友垃圾，但本条 tokens 可用词较弱，谨慎不扩核心词。
- `ikV6948B0x`：未分类 → **暴力色情** (0.78) — 典型英文交友诱导，出现 dude、long term committed relationship 等约会关系话术。
- `SvVNqHwpGb`：未分类 → **未分类** (0.8) — 酒店 CCTV 告警通知，属于技术/监控告警，无五类垃圾语义。
- `ehnEQPBTm0`：未分类 → **暴力色情** (0.55) — 意大利语短句加 URL/邮箱，疑似交友诱导垃圾，但 tokens 缺少稳定色情或商业关键词，暂不扩词。
- `fFBwRo7A4W`：未分类 → **未分类** (0.9) — Crashlytics/Fabric 崩溃告警邮件，无广告、钓鱼、色情、博彩或学术营销语义。
- `siyTxHS0YV`：未分类 → **暴力色情** (0.95) — 明确出现 sexual desire、girl、sexual experiences，属于英文色情/交友诱导。
- `abiWGA0DhR`：未分类 → **暴力色情** (0.9) — 出现 sleeping with more guys、not looking for obligations or commitment，典型无承诺性邀约。
- `YiHPz18j7L`：未分类 → **未分类** (0.9) — Crashlytics/Fabric 崩溃告警邮件，无五类垃圾语义。
- `pQtYvKad53`：未分类 → **未分类** (0.9) — Crashlytics/Fabric 崩溃告警邮件，无五类垃圾语义。
- `h37v0MF6bs`：未分类 → **未分类** (0.5) — 极短乱码加电话，无可稳定归类的五类语义；不扩词。
- `5GWCRJf86c`：未分类 → **暴力色情** (0.6) — 英文交友/约会垃圾模板，adventure 加 URL/邮箱，但词面较泛，谨慎不扩。
- `1akJwgUsM8`：未分类 → **未分类** (0.5) — 极短乱码加电话和姓名，无五类稳定语义；不扩词。
- `AW6xMN8JSF`：未分类 → **未分类** (0.9) — Crashlytics/Fabric 非致命崩溃告警，无五类垃圾语义。
- `sA7Sz3Pqb4`：未分类 → **未分类** (0.82) — 用户复机错误类系统告警，无五类垃圾语义。
- `WHbuD3flRI`：未分类 → **未分类** (0.5) — 随机英文小说片段和原始邮件头，未见五类垃圾语义。
- `qDf9whbNgU`：未分类 → **未分类** (0.5) — 仅电话和随机串，无法归入五类；不扩词。
- `k9vfdUF1Ma`：未分类 → **钓鱼邮件** (0.72) — “领导请阅”加“压缩包下载”符合附件/下载诱导型钓鱼或恶意载荷投递话术。
- `hkcifVzBAQ`：未分类 → **未分类** (0.88) — 服务调用日报/监控统计，无五类垃圾语义。

## 建议词校验

### 暴力色情
- `sexual desire` (en)：语料命中 21，误伤 10，已在词表=False — ⚠️ 需人工判断
- `sexual experiences` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `surrendering sexual desire` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `sleeping more guys` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `long term committed relationship` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `cool relaxed dude` (en)：语料命中 3，误伤 0，已在词表=False — ✅ 建议采纳
- `boner` (en)：语料命中 32，误伤 29，已在词表=False — ⚠️ 需人工判断

### 广告营销
- `加信` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `walking stick` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `telescopic canes` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `ergonomic handle` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `improve posture` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `make purchase` (en)：语料命中 9，误伤 7，已在词表=False — ⚠️ 需人工判断
- `earn more points` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `rewards points` (en)：语料命中 2，误伤 1，已在词表=False — ⚠️ 需人工判断
- `get app` (en)：语料命中 6，误伤 2，已在词表=False — ⚠️ 需人工判断

### 钓鱼邮件
- `领导 请阅` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `压缩包 下载` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断

### 学术会议/期刊营销
- `学术论文` (zh)：语料命中 26，误伤 1，已在词表=False — ✅ 建议采纳
- `成功 检索` (zh)：语料命中 120，误伤 0，已在词表=False — ✅ 建议采纳
- `正刊` (zh)：语料命中 86，误伤 0，已在词表=False — ✅ 建议采纳
- `jcr impact factor` (zh)：语料命中 66，误伤 0，已在词表=False — ✅ 建议采纳
- `nature index` (en)：语料命中 4，误伤 2，已在词表=False — ⚠️ 需人工判断
- `physical sciences` (en)：语料命中 6，误伤 1，已在词表=False — ✅ 建议采纳
- `new research` (en)：语料命中 84，误伤 3，已在词表=False — ✅ 建议采纳
- `nature research` (en)：语料命中 5，误伤 2，已在词表=False — ⚠️ 需人工判断
