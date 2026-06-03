# LLM 词表迭代报告（scheme2）

- 生成时间：2026-06-03 18:31:14
- 审查样本数：100
- 其中 short_content（允许保持未分类）：18
- 保持未分类：12 / 100 条审查

## 模型总结

本轮重点将未分类中的英文交友/色情引流、ED药品、产品促销/培训/货代/招聘/金融资讯/电商促销、伪物流/伪支付/邮箱升级钓鱼、学术/会议/课程线索归入五类。仅对极短且 token 不足以稳定判别的占位/乱码样本建议保持未分类；对长文本但无五类语义的技术告警、OA通知、文学乱码、正常业务邮件等标为未分类且不扩词。

## 样本审查（节选）

共 100 条审查记录，以下展示前 20 条：

- `k9vfdUF1Ma`：未分类 → **商业广告** (0.62) — 教师素养、实习管理、实践教学压缩包下载，疑似培训/资料推广。
- `vzBhEs3oyG`：未分类 → **暴力色情** (0.98) — 长腿模特、干时、不要等色情诱导内容。
- `VlLdrgmzWs`：未分类 → **商业广告** (0.7) — 短内容但含王牌销售，偏销售培训/营销。
- `edUV9rRZgl`：未分类 → **未分类** (0.45) — 英文随机拼接/小说片段，无五类明确语义。
- `ozyVeTBjHM`：未分类 → **钓鱼邮件** (0.7) — 附件查阅、meeting notifications 是常见诱导查看附件通知话术。
- `IdMVumEyBr`：未分类 → **未分类** (0.95) — Crashlytics 崩溃告警，非五类营销/钓鱼。
- `3Bzds460SC`：未分类 → **暴力色情** (0.82) — meet me、escape together、URL，典型英文交友引流。
- `WHbuD3flRI`：未分类 → **未分类** (0.52) — 转发小说/乱码片段，无五类明确意图。
- `R7lrO4X0Ca`：未分类 → **钓鱼邮件** (0.74) — 陌生人寻求 business partner 并要求 get back details，疑似诈骗/钓鱼。
- `xtJd9zpTEO`：未分类 → **未分类** (0.52) — 英文小说片段与姓名插入，无五类明确语义。
- `AXv19ZTPIy`：未分类 → **未分类** (0.96) — 应用崩溃堆栈日志，非五类。
- `2Em7FTkKUu`：未分类 → **暴力色情** (0.76) — married、rich、URL 的交友婚恋引流。
- `UquEGaAWQj`：未分类 → **暴力色情** (0.8) — good time、forget decency、URL，交友/色情引流。
- `mY3FoZb7Q0`：未分类 → **钓鱼邮件** (0.88) — RFQ、attached、Google Drive、order procurement，典型伪采购附件钓鱼。
- `bPVmLp6ZlK`：未分类 → **暴力色情** (0.78) — deeply connect with a man 与 URL，交友引流。
- `Fi4HEJmYuU`：未分类 → **未分类** (0.95) — Crashlytics 崩溃告警，非五类。
- `hjxz59WVs7`：未分类 → **商业广告** (0.72) — 基金周观点/市场回顾，投资理财资讯营销。
- `qDf9whbNgU`：未分类 → **保持未分类** (0.99) — short_content=true，只有电话占位符和乱码 token，无法扩词。
- `A2VoTi4Iv7`：未分类 → **暴力色情** (0.72) — beautiful family/dream 加 URL，婚恋交友引流。
- `l9g28bdfk0`：未分类 → **暴力色情** (0.9) — ED、pill、medicine、order，性功能药品营销。

## 建议词校验

### 暴力色情
- `大长` (zh)：语料命中 33，误伤 0，已在词表=False — ✅ 建议采纳
- `干时` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `毛少` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `肥厚` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `幼师` (zh)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `巨奶` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `合集` (zh)：语料命中 3，误伤 2，已在词表=False — ⚠️ 需人工判断
- `娇羞` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `可人` (zh)：语料命中 2，误伤 1，已在词表=False — ⚠️ 需人工判断
- `sexual urges` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `erectile dysfunction` (en)：语料命中 78，误伤 45，已在词表=False — ⚠️ 需人工判断
- `sexual desire` (en)：语料命中 21，误伤 11，已在词表=False — ⚠️ 需人工判断
- `ed` (en)：语料命中 109，误伤 64，已在词表=False — ⚠️ 需人工判断
- `pill` (en)：语料命中 75，误伤 44，已在词表=False — ⚠️ 需人工判断
- `sleeping guys` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `seventh heaven` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `lose control` (en)：语料命中 31，误伤 0，已在词表=False — ✅ 建议采纳
- `hot emotions` (en)：语料命中 6，误伤 1，已在词表=False — ✅ 建议采纳
- `solitary girl` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `find each other online` (en)：语料命中 6，误伤 0，已在词表=False — ✅ 建议采纳
- `woman ukraine` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `reply photo` (en)：语料命中 14，误伤 1，已在词表=False — ✅ 建议采纳
- `get married` (en)：语料命中 35，误伤 1，已在词表=False — ✅ 建议采纳
- `beautiful family` (en)：语料命中 3，误伤 0，已在词表=False — ✅ 建议采纳
- `cowboy` (en)：语料命中 50，误伤 1，已在词表=False — ✅ 建议采纳
- `dependable` (en)：语料命中 32，误伤 1，已在词表=False — ✅ 建议采纳
- `provaci` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断

### 发票营销
- `普墂` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `增直税发墂` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `做帐报` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `帐报` (zh)：语料命中 4，误伤 0，已在词表=True — ✅ 建议采纳
- `消用` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断

### 商业广告
- `销售` (zh)：语料命中 65，误伤 9，已在词表=False — ✅ 建议采纳
- `王牌销售` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `数据中心` (zh)：语料命中 2，误伤 1，已在词表=False — ⚠️ 需人工判断
- `国际机票` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `航旅` (zh)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `先飞后付款` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `采购谈判` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `谈判技巧` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `谈判策略` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `肖售目` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `工业称重` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `在线免费下载` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `人工智能` (zh)：语料命中 165，误伤 125，已在词表=False — ⚠️ 需人工判断
- `深度学习` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `tensorflow` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `配对人选` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `履历` (zh)：语料命中 2，误伤 1，已在词表=False — ⚠️ 需人工判断
- `基金周观点` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `市场回顾` (zh)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `discounts` (en)：语料命中 12，误伤 5，已在词表=False — ⚠️ 需人工判断
- `free products` (en)：语料命中 8，误伤 5，已在词表=False — ⚠️ 需人工判断
- `claim discounts` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `outdoor spotlight` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `rgbw` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `led` (en)：语料命中 97，误伤 20，已在词表=False — ⚠️ 需人工判断
- `specifications` (en)：语料命中 21，误伤 2，已在词表=False — ✅ 建议采纳
- `fiber laser cutting machine` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `touch sensor` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `customization` (en)：语料命中 6，误伤 5，已在词表=False — ⚠️ 需人工判断
- `gift shop` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `back stock` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `bid now` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `auction` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `connectivity solutions` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `tradeshows` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `product solutions` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `mining newsletter` (en)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `veterans discounts` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断

### 钓鱼邮件
- `附件 查阅` (zh)：语料命中 75，误伤 46，已在词表=False — ⚠️ 需人工判断
- `查阅 附件` (zh)：语料命中 75，误伤 46，已在词表=False — ⚠️ 需人工判断
- `request quotation` (en)：语料命中 21，误伤 12，已在词表=False — ⚠️ 需人工判断
- `attached rfq` (en)：语料命中 14，误伤 12，已在词表=False — ⚠️ 需人工判断
- `google drive` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `order procurement` (en)：语料命中 3，误伤 0，已在词表=True — ✅ 建议采纳
- `business partner get back details` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `unclaimed estates` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `forgotten funds` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `dormant accounts` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `payment successful` (en)：语料命中 3，误伤 0，已在词表=False — ✅ 建议采纳
- `transaction authorized` (en)：语料命中 3，误伤 0，已在词表=False — ✅ 建议采纳
- `maersk notification` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `download shipping document` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `shipping document` (en)：语料命中 7，误伤 2，已在词表=False — ⚠️ 需人工判断
- `buraya tikla` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `posta hesabiniz` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `kilitli` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `meeting notifications` (en)：语料命中 7，误伤 0，已在词表=True — ✅ 建议采纳

### 学术营销
- `线性代数` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `矩阵` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `机器 学习` (zh)：语料命中 111，误伤 9，已在词表=False — ✅ 建议采纳
- `故障诊断` (zh)：语料命中 8，误伤 0，已在词表=False — ✅ 建议采纳
- `icitee invitation` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `agricultural information technology` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `entrepreneurship academy` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `seminar room` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `petit institute` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `biotech building` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
