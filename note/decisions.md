# 关键决策记录 (Decisions)

> 记录设计与技术决策的「为什么」，与 commit message（「改了什么」）互补。
> 每次关键 commit 同步追加一条记录，最新在上。

## 记录模板

```
### YYYY-MM-DD · 决策标题
- **commit**: `<hash>` `<type>(<scope>): <subject>`
- **背景**: 遇到什么问题/动机
- **决策**: 做了什么取舍
- **被否决方案**: 考虑过但没采用的方案及原因
- **影响**: 涉及的文件/模块或后续约束
```

---

## 2026-07-16 · 厂商总览页与首页厂商模块重构 + 字体合规

- **commit**: `5e6d8e3` `feat(ui): 厂商详情页 tab 切换、总览页与首页模块重构`
- **背景**:
  1. 厂商总览页（/providers）大卡片过于拥挤，难以快速定位厂商，且"数据正常"提示干扰浏览
  2. 首页"主流大模型厂商"模块排版拥挤，缺乏章节感，与首页其他模块视觉节奏不协调
  3. billing/* 页面 `.freshness b`（包裹日期和产品数，属数据层）未用 mono 字体，违反字体系统三层角色分工
- **决策**:
  1. 厂商总览页：紧凑横向卡片（图标+名称+产品数+官网）+ 地区分组（国内/国外）+ 搜索框；移除"数据正常"提示
  2. 首页厂商模块：回归 `.section` 排版保持一致性；卡片用渐变背景+hover 顶部强调色条；产品数用 Geist Mono 600（数据层合规）；最后一张为"厂商总览"入口卡片（虚线边框+右箭头 SVG，hover 旋转 -45°）
  3. 字体合规：`.freshness b` 补上 `font-family: var(--font-mono)`，weight 600→500
- **被否决方案**:
  - 首页厂商模块用左栏 sticky 标题 + 右栏网格的不对称分栏：与首页其他模块（.section）排版不一致
  - 入口卡片用 `+` 字符或 `···` 带方框图标：视觉过重，不如简约 SVG 箭头
  - 厂商卡片显示计费方式 chips 和地区标签：信息过载，核心需求是快速识别厂商
- **影响**: `ui/index.html`（厂商总览页模板+首页厂商模块+缓存 v18→v27）、`ui/style.css`（PROVIDERS SECTION 区块+freshness b 修正+缓存 v21→v27）、`ui/app.js`（providerList 增 billingTypes+billingLabelShort，v18→v19）。后续新增厂商自动出现在首页网格，无需改模板

## 2026-07-16 · 厂商详情页 tab 切换 + 货币自动适配

- **commit**: `5e6d8e3` `feat(ui): 厂商详情页 tab 切换、总览页与首页模块重构`
- **背景**: 三个问题
  1. 厂商详情页强制用 per_token 表格渲染所有产品，导致 subscription/coding_plan 产品字段不匹配（Cursor/Copilot 显示空白）
  2. 混合计费方式厂商（如 OpenAI 139 per_token + 2 subscription），用户需滚动很久才能看到订阅制
  3. 货币无自动适配，国内厂商也默认显示 USD
- **决策**:
  1. 厂商详情页改为计费方式 tab 切换：per_token / subscription / coding_plan 各为一个 tab，只显示该厂商有的计费方式，默认选中第一个。单一计费方式时不显示 tab，只显示标题。per_token tab 用表格，subscription/coding_plan tab 用卡片
  2. 货币自动适配：watch currentProvider，cn→CNY，us/eu→USD。用户仍可手动切换
  3. watch providerBillingTabs 自动设置默认 tab（解决 currentProvider 变化时 filteredRows 未更新的时序问题）
- **被否决方案**:
  - 分区展示（滚动浏览所有计费方式）：OpenAI 139 款 per_token 表格太长，订阅制被压到底部体验差
  - sticky 快速跳转锚点：保留分区但加锚点导航，仍需滚动，不如 tab 切换直接
  - watch currentProvider 同时设置 tab 和货币：filteredRows 在 watch 触发时还未更新，providerBillingTabs 为空，导致 tab 设置失败
- **影响**: `ui/app.js`（新增 providerBillingTabs/providerBillingTab/providerCurrentRows + 两个 watch）、`ui/index.html`（厂商详情页模板改造为 tab 切换）、`ui/style.css`（新增 tab 样式）。后续新增计费方式需在 providerBillingTabs order 数组中添加

## 2026-07-16 · 字体系统统一为三层角色分工

- **commit**: `fb3f3f7` `refactor(ui): 统一字体系统为三层角色分工`
- **背景**: 网站字体混乱，40 处 font-family 声明缺乏清晰角色分工。核心问题不是字体种类多，而是没有规则：
  - italic 滥用：衬线斜体同时扮演「品牌签名/关键词强调/序号装饰/英文 label」4 种角色
  - mono 滥用：等宽字体同时扮演「英文标签/数字/模型名/箭头符号」4 种角色
  - weight 不统一：同样 13px 文字出现 400/500/600 三种
  - letter-spacing 随意：11 种值（-0.04em ~ 0.08em）无规律
- **决策**: 建立三层角色分工系统
  - **Instrument Serif（展示层）**：仅用于页面大标题、关键数字、序号装饰。weight 统一 400。italic 仅用于关键词强调（hero-title em / section-title em / about-page h2 em），禁止用于序号、label、品牌副标题
  - **Geist（界面层）**：所有 UI 文字、正文、标签、按钮、卡片标题。weight 递进规则：400 正文 / 500 次级 / 600 强调标签 / 700 品牌。letter-spacing 按字号功能分 5 档：uppercase 标签 0.06em / ≥30px 衬线 -0.02em / 20-29px -0.015em / 14-19px -0.01em / ≤13px 正文 0
  - **Geist Mono（数据层）**：仅限数据与代码——价格、Token 数、模型 ID、上下文长度。必备 `font-variant-numeric: tabular-nums`。收窄到 3 种角色（num / card-prices / plan-item-price / card-model / card-ctx / plan-item-quota / currency-toggle）
  - 4 个衬线大标题加 `text-wrap: balance` 防孤行（Vercel Web Interface Guidelines 建议）
- **被否决方案**:
  - 引入新字体（如 Inter/Söhne 替换 Geist）：当前 3 字体已够，问题在角色分工不清而非字体选择本身
  - 全部统一为单一字体族：会丢失「编辑式科技产品」的衬线/无衬线对比特色，与项目定位冲突
  - 改用 CHANGELOG.md 记录变动：CHANGELOG 偏「发布了什么」适合有版本号项目，本项目是 cron 每日持续部署，无版本号语义；且易与 commit message 重复
- **影响**: `ui/style.css`（11 处字体声明修改）、`ui/index.html`（缓存 v17→v18）。后续新增 UI 模块需遵循三层角色规则；新增 commit 需同步追加本文件记录
