# LLM 词表迭代报告（scheme1）

- 生成时间：2026-06-03 19:54:53
- 审查样本数：100
- 其中 short_content（允许保持未分类）：21
- 保持未分类：19 / 100 条审查

## 模型总结

本批未分类样本中主要漏网为英文交友/色情约会、中文色情视频、英文ED药品广告、SEO/产品/展会/电商广告、科研培训/建模课程、伪物流钓鱼和少量遗产诈骗。Crashlytics告警、OA/合同/物流内部通知、普通新闻简报、欢迎信、宗教/政治长文等虽为垃圾或探测噪声，但不宜写入五类词表，标为未分类。仅对short_content=true且内容过短样本使用保持未分类。

## 样本审查（节选）

共 100 条审查记录，以下展示前 20 条：

- `bmAMCejRxU`：未分类 → **保持未分类** (0.3) — 短样本且仅随机串、电话占位和不可解释词，无法安全扩词。
- `wxPAOY2Tiy`：未分类 → **暴力色情** (0.78) — 英文约会诱导，邀请年轻男性一起喝酒聚会并带URL，符合dating/色情交友垃圾。
- `qXGmBhxkgb`：未分类 → **暴力色情** (0.8) — cute sporty female、lad、happily ever after等典型交友诱导话术。
- `no36GKmOjw`：未分类 → **暴力色情** (0.86) — voluptuous female等明显色情/交友诱导词。
- `ZGS6zwBVqx`：未分类 → **暴力色情** (0.82) — solitary girl、thrilling things with him为约会色情诱导。
- `ryoJ1s6mnp`：未分类 → **学术会议/期刊营销** (0.62) — 科技服务专递，组织申报技术培训班项目，属于科研培训/学术信息营销边界。
- `Fdh2yYlq0t`：未分类 → **保持未分类** (0.35) — 短样本，仅技术词和姓名，无五类可判定语义。
- `lMe71h4Bji`：未分类 → **暴力色情** (0.74) — 男女伴侣关系、sucked和URL组合，属于英文色情交友诱导。
- `bfFxiewcAN`：未分类 → **暴力色情** (0.79) — relationships、handsome man、date every day等约会垃圾话术。
- `sdUwgoLmRr`：未分类 → **钓鱼邮件** (0.84) — 伪安全告警/黑客勒索，声称入侵系统和账户、感染malware，属于凭据/恐吓型钓鱼诈骗。
- `wMKPXNHa3p`：未分类 → **广告营销** (0.9) — SEO免费审计报告和网站排名推广广告。
- `UmWbQ6917L`：未分类 → **学术会议/期刊营销** (0.58) — 题名式医学研究论文/课题内容，疑似论文营销或学术稿件探测。
- `QjDblqhBFs`：未分类 → **未分类** (0.86) — Crashlytics技术告警，不属于五类垃圾语义。
- `0CeoDSpKiO`：未分类 → **未分类** (0.8) — 企业OA合同下传通知，不属于五类。
- `jBAb9QyfKh`：未分类 → **学术会议/期刊营销** (0.88) — 地下水建模、数值模拟、报到授课、会务，典型科研软件培训班。
- `xXC7POWrl9`：未分类 → **广告营销** (0.9) — 数字营销峰会推广，含立即报名、嘉宾阵容等会展营销。
- `LgwSvnhz3B`：未分类 → **暴力色情** (0.86) — mistress for a guy、live happily等交友色情诱导。
- `9RpQqxtBiI`：未分类 → **广告营销** (0.92) — ED药品促销，含buy immediately、drug shop和折扣码，按商业药品广告归广告营销。
- `Ndm0DgzYfh`：未分类 → **钓鱼邮件** (0.8) — 典型遗产/ dormant accounts 诈骗，冒充机构通知。
- `39yX4LaKcn`：未分类 → **学术会议/期刊营销** (0.72) — 人工智能/PYTHON深度学习附件邀请，符合技术学习/科研培训营销。

## 建议词校验

### 暴力色情
- `妹子 像片` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `男友 报复 分享` (zh)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `女教师 高清 完整版` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `私人 订制` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `音乐系 女教师` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `voluptuous female` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `solitary girl` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `single lassie` (en)：语料命中 4，误伤 0，已在词表=True — ✅ 建议采纳
- `date online` (en)：语料命中 65，误伤 10，已在词表=False — ⚠️ 需人工判断
- `frisky games` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `lights out` (en)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `lonely mistress` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `respectable man` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `appetising mistress` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `mistress ukraine` (en)：语料命中 3，误伤 0，已在词表=True — ✅ 建议采纳
- `hot woman` (en)：语料命中 18，误伤 0，已在词表=True — ✅ 建议采纳
- `woman ukraine` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `seeking mister` (en)：语料命中 4，误伤 0，已在词表=True — ✅ 建议采纳
- `reply my photo` (en)：语料命中 12，误伤 0，已在词表=True — ✅ 建议采纳
- `sporty female` (en)：语料命中 3，误伤 0，已在词表=True — ✅ 建议采纳
- `cute female` (en)：语料命中 6，误伤 0，已在词表=True — ✅ 建议采纳
- `handsome man` (en)：语料命中 16，误伤 0，已在词表=True — ✅ 建议采纳
- `thrilling adventures` (en)：语料命中 4，误伤 0，已在词表=True — ✅ 建议采纳
- `pretty females` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `females close` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `deeply connect` (en)：语料命中 8，误伤 0，已在词表=True — ✅ 建议采纳
- `get married rich famous man` (en)：语料命中 3，误伤 0，已在词表=True — ✅ 建议采纳

### 广告营销
- `高价 回收` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `电缆 缆盘` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `回收公司` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `数字 营销 峰会` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `立即 报名` (zh)：语料命中 4，误伤 0，已在词表=True — ✅ 建议采纳
- `微电极 测试` (zh)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `微电极 测试 分析 系统` (zh)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `细胞 计数` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `赛默 飞世尔` (zh)：语料命中 3，误伤 1，已在词表=True — ✅ 建议采纳
- `商业用途` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `注册 抢红包` (zh)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `free audit report` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `website ranking` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `targeted keyword` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `analysis report` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `digital strategist` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `erectile dysfunction` (en)：语料命中 78，误伤 29，已在词表=False — ⚠️ 需人工判断
- `drug shop` (en)：语料命中 16，误伤 4，已在词表=False — ⚠️ 需人工判断
- `herbal pills` (en)：语料命中 10，误伤 3，已在词表=False — ⚠️ 需人工判断
- `order now` (en)：语料命中 73，误伤 29，已在词表=False — ⚠️ 需人工判断
- `cure ed` (en)：语料命中 22，误伤 11，已在词表=False — ⚠️ 需人工判断
- `private price` (en)：语料命中 9，误伤 3，已在词表=False — ⚠️ 需人工判断
- `xilinx stock` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `electronic distributor` (en)：语料命中 2，误伤 0，已在词表=False — ⚠️ 需人工判断
- `hot offers` (en)：语料命中 4，误伤 2，已在词表=False — ⚠️ 需人工判断
- `product news` (en)：语料命中 3，误伤 3，已在词表=False — ⚠️ 需人工判断
- `cellular routers` (en)：语料命中 1，误伤 1，已在词表=False — ⚠️ 需人工判断
- `cellular rtus` (en)：语料命中 1，误伤 1，已在词表=False — ⚠️ 需人工判断
- `hpc cloud` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `live demos` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `cloud os` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `bonus bucks` (en)：语料命中 1，误伤 1，已在词表=False — ⚠️ 需人工判断
- `imax movies` (en)：语料命中 1，误伤 1，已在词表=False — ⚠️ 需人工判断
- `jack wolfskin` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `reverse aging` (en)：语料命中 1，误伤 1，已在词表=False — ⚠️ 需人工判断
- `sponsored` (en)：语料命中 16，误伤 14，已在词表=False — ⚠️ 需人工判断

### 钓鱼邮件
- `security alert` (en)：语料命中 68，误伤 0，已在词表=True — ✅ 建议采纳
- `sign details` (en)：语料命中 12，误伤 0，已在词表=True — ✅ 建议采纳
- `hacked os` (en)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `full access` (en)：语料命中 61，误伤 47，已在词表=False — ⚠️ 需人工判断
- `infected malware` (en)：语料命中 32，误伤 22，已在词表=False — ⚠️ 需人工判断
- `unclaimed estates` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `forgotten funds` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `abandoned shares` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `dormant accounts` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `air logistics` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `goods shipped` (en)：语料命中 7，误伤 0，已在词表=True — ✅ 建议采纳
- `in transit` (en)：语料命中 0，误伤 0，已在词表=False — ⚠️ 需人工判断
- `follow attachment` (en)：语料命中 50，误伤 49，已在词表=False — ⚠️ 需人工判断
- `cargotrans pdf` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `maersk tracker` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `want look page` (en)：语料命中 5，误伤 2，已在词表=False — ⚠️ 需人工判断

### 学术会议/期刊营销
- `科技 服务 信息 专递` (zh)：语料命中 7，误伤 0，已在词表=True — ✅ 建议采纳
- `技术 培训班 项目` (zh)：语料命中 8，误伤 0，已在词表=True — ✅ 建议采纳
- `地下水 建模` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `数值 模拟` (zh)：语料命中 2，误伤 1，已在词表=False — ⚠️ 需人工判断
- `上机操作` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `人工智能 python 深度 学习` (zh)：语料命中 15，误伤 0，已在词表=True — ✅ 建议采纳
- `人工智能 python 学习 邀请` (zh)：语料命中 10，误伤 0，已在词表=True — ✅ 建议采纳
- `有限元 分析 研究` (zh)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
- `tough petrasim` (en)：语料命中 1，误伤 0，已在词表=False — ⚠️ 需人工判断
