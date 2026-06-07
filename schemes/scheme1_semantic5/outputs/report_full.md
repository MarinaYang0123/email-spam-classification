# 方案1 · 语义五类（全量归类 · full） 分类报告

- 总样本：**24000**
- 未分类：**0**
- 空样本：**4**
- 本轮强制归类：**701** 条（原「未分类」）

## 类别分布

| cluster_id | 类别 | 数量 | 占比 |
|---:|---|---:|---:|
| 0 | 暴力色情 | 7843 | 32.7% |
| 1 | 广告营销 | 7101 | 29.6% |
| 2 | 钓鱼邮件 | 4413 | 18.4% |
| 4 | 学术会议/期刊营销 | 3825 | 15.9% |
| 3 | 赌博博彩 | 814 | 3.4% |
| -1 | 空样本 | 4 | 0.0% |

## 强制归类方法统计

- heuristic_default_zh: 195
- heuristic_dating_url: 119
- heuristic_ads_en: 67
- heuristic_academic: 67
- heuristic_default_en: 60
- heuristic_default_short: 58
- rule_any: 44
- heuristic_ads_zh: 29
- heuristic_url_en: 15
- heuristic_url_mismatch_short: 10
- heuristic_porn_zh: 7
- heuristic_gambling: 7
- heuristic_invoice: 5
- heuristic_phish_zh: 4
- heuristic_phish_en: 4
- heuristic_invoice_short: 4
- heuristic_ed_spam: 4
- heuristic_academic_en: 2

## 规则 Top 命中词

- **暴力色情**：dating(1176)、国产(1077)、av(1019)、罗莉(947)、出兽(735)、无码(550)、城人(522)、成人(486)、少妇(479)、幼女(450)、九电偷(438)、青城 电影 私聊(438)、偷拍(436)、sex(361)、guy(352)
- **广告营销**：开发票(1910)、发票(1117)、普通(1018)、开票(855)、专用发票(822)、代开(526)、普通发票(477)、设计费(467)、服务费(461)、广告费(460)、报消(455)、材料费(452)、劳务费(444)、培训费(437)、增值(384)
- **钓鱼邮件**：account(605)、登陆(397)、登录(394)、security(370)、confirm(334)、帐户(292)、mailbox(276)、upgrade mail(223)、click below(222)、email server(210)、administrator(205)、verify(203)、subject(199)、update(181)、dhl express(124)
- **赌博博彩**：特邀(537)、领取(492)、葡京(443)、次次(437)、bbin(419)、mg(419)、pt(412)、上限(378)、晋级(375)、百款(374)、打码(371)、领彩(154)、企鹅(154)、百家乐(73)、彩金(34)
- **学术会议/期刊营销**：research(938)、journal(937)、international(859)、conference(853)、会议(750)、ei(743)、检索(720)、sci(678)、投稿(677)、submit(649)、期刊(628)、papers(599)、science(558)、issn(492)、论文(480)