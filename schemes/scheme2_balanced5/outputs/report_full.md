# 方案2 · 均衡五类（全量归类 · full） 分类报告

- 总样本：**24000**
- 未分类：**0**
- 空样本：**4**
- 本轮强制归类：**393** 条（原「未分类」）

## 类别分布

| cluster_id | 类别 | 数量 | 占比 |
|---:|---|---:|---:|
| 0 | 暴力色情 | 7619 | 31.7% |
| 1 | 发票营销 | 5468 | 22.8% |
| 3 | 钓鱼邮件 | 4618 | 19.2% |
| 4 | 学术营销 | 3785 | 15.8% |
| 2 | 商业广告 | 2506 | 10.4% |
| -1 | 空样本 | 4 | 0.0% |

## 强制归类方法统计

- heuristic_default_zh: 94
- heuristic_ads_en: 61
- heuristic_default_short: 52
- heuristic_academic: 49
- heuristic_default_en: 47
- heuristic_dating_url: 43
- heuristic_ads_zh: 22
- heuristic_url_en: 8
- heuristic_url_mismatch_short: 5
- heuristic_invoice_short: 4
- heuristic_invoice: 2
- heuristic_ed_spam: 2
- heuristic_porn_zh: 2
- heuristic_phish_zh: 1
- heuristic_academic_en: 1

## 规则 Top 命中词

- **暴力色情**：dating(1156)、国产(1077)、av(1018)、罗莉(947)、出兽(735)、无码(527)、城人(522)、少妇(479)、成人(463)、幼女(450)、九电偷(438)、青城 电影 私聊(438)、偷拍(436)、guy(350)、sex(340)
- **发票营销**：开发票(1910)、发票(1116)、普通(1019)、开票(855)、专用发票(822)、代开(521)、验证 付款(481)、普通发票(477)、设计费(467)、服务费(461)、广告费(460)、报消(455)、材料费(453)、劳务费(444)、培训费(438)
- **商业广告**：领取(570)、葡京(443)、bbin(420)、百款(374)、打码(371)、澳门(370)、领取 网址(366)、晋升为 vip(365)、澳门 葡京(357)、有存(348)、任你玩(328)、新老用户(315)、电子游戏(311)、满壹千送(270)、回馈 新老用户(256)
- **钓鱼邮件**：account(637)、登录(399)、登陆(398)、security(376)、confirm(333)、帐户(292)、mailbox(276)、click below(226)、upgrade mail(223)、email server(210)、administrator(205)、verify(203)、subject(201)、update(182)、dhl express(126)
- **学术营销**：research(946)、journal(940)、international(860)、conference(857)、会议(747)、ei(744)、检索(714)、sci(678)、投稿(677)、submit(649)、期刊(628)、papers(599)、science(558)、issn(495)、论文(476)