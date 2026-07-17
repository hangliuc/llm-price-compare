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

## 2026-07-17 · 统一 per_token purchase_url 为厂商官方定价页

- **commit**: pending（待提交）
- **背景**:
  1. per_token 产品的 `purchase_url` 来自多个数据源，混杂 OpenRouter (`openrouter.ai/<vendor>/<model>`)、LiteLLM（部分厂商官方页）、manual yaml（官方定价页）
  2. 90%+ 的 per_token 产品走 OpenRouter 来源，点击"购买"跳转到 openrouter.ai 的模型详情页，对终端用户无意义——用户想看官方定价、去官方充值，而不是通过 OpenRouter 中转
  3. OpenRouter 对国内厂商（阿里通义/MiniMax/火山引擎等）充值不便，用户体验差
- **决策**:
  1. 在 `run_daily.py` 新增 step 4.5：统一覆盖所有 per_token 产品的 `purchase_url` 为厂商官方 `pricing_url`
  2. 数据来源：manual yaml 的 `pricing_url` + `_PROVIDER_META` 的 `pricing_url` + adapter 的 `pricing_url`，所有 14 个厂商已覆盖
  3. **subscription / coding_plan 保持 manual yaml 的精准购买页不变**（如 `openai.com/chatgpt/business`、`common-buy.aliyun.com/coding-plan`），因为它们的购买页比 `pricing_url` 更精准，直接对应具体套餐
- **被否决方案**:
  - **保留 OpenRouter 链接 + 改文案"通过 OpenRouter"**：OpenRouter 对国内用户充值不便，且暴露数据源给终端用户不专业
  - **取消购买按钮**：失去跳转便利，用户需要自己去搜索厂商定价页
  - **双链接（官方 + OpenRouter）**：UI 复杂度高，按钮区放两个链接拥挤，不符合 MVP 简洁原则
  - **在 reconcile 层处理**：reconcile 的 `_pick_purchase_url` 按 adapter > litellm > openrouter 优先级取值，但 sources-only 厂商（google/aws/moonshot 等）没 adapter，仍会取 OpenRouter 链接。放在 run_daily 统一处理更干净
- **影响**:
  - [scripts/run_daily.py](file:///Users/shareit/personal/llm-price-compare/scripts/run_daily.py) 新增 step 4.5
  - 11 个有 per_token 产品的厂商共 565 条产品链接被统一覆盖
  - `data/prices.json` 的 per_token 产品 purchase_url 全部指向厂商官方定价页
  - 前端 UI 无需改动，按钮文案和样式保持不变

---

## 2026-07-16 · 修复 product_id 大小写归一化 + manual 优先覆盖

- **commit**: pending（待提交）
- **背景**:
  1. MiniMax 出现同模型重复：LiteLLM 用 `MiniMax-M3-token`（大写），OpenRouter 用 `minimax-m3-token`（小写），reconcile 按 `p.id` 严格匹配未归一化，导致同模型保留两条
  2. manual 合并逻辑"只补充缺失"导致 manual 的高质量官网 CNY 定价无法覆盖 sources 的低置信度 USD 数据（如同 id 的 minimax-m3-token，sources 版保留，manual 版被跳过）
- **决策**:
  1. `reconcile.py`：`by_id` 构建时对 `p.id` 做 `.lower()` 归一化，LiteLLM/OpenRouter 大小写不一致的同模型对齐到同一 product
  2. `run_daily.py` 步骤 4：manual 合并从"只补充缺失"改为"归一化 id 去重，manual 优先覆盖 sources"。manual 的人工确认数据（官网 CNY）覆盖 sources 低置信度数据（USD），manual 分段产品（id 不同）自动补充
- **被否决方案**:
  - 基于 model 名归一化去重：风险高，不同档位分段产品 model 名不同不会误删，但同模型不同计价方式（如 M1 单条 vs 分段）难以自动判断取舍
  - 在 MiniMax manual yaml 里显式标注"废弃"产品：引入新概念增加复杂度
- **影响**: 修改 `scripts/core/reconcile.py`（by_id 归一化）、`scripts/run_daily.py`（manual 合并逻辑）。MiniMax 从 20 条降到 16 条（消除 4 条大小写重复），全平台总产品数 602→598。M1 单条（sources USD）与分段（manual CNY）共存，属不同计价方式可接受

---

## 2026-07-16 · 数据补全：OpenAI/Google/MiniMax/阿里通义

- **commit**: pending（待提交）
- **背景**:
  1. OpenAI 订阅制只有 Plus/Pro，缺 Free/Business
  2. Google 缺订阅制（Gemini Free/AI Plus/AI Pro/AI Ultra）
  3. MiniMax 只有 3 个 coding_plan，per_token 模型为 0
  4. 阿里通义只有 1 个 per_token（Qwen-Max），缺 Qwen3.7-Max/Plus/Flash/Long 等主力模型
  5. 分段定价模型（如 Qwen3-Max 0-32K/32-128K/128-256K）未拆分
- **决策**:
  1. OpenAI：补全 Free($0)/Business($25)，Enterprise 价格未公开不录
  2. Google：新增 4 个订阅制（Free/$0, AI Plus/$4.99, AI Pro/$19.99, AI Ultra 5x/$249.99），Ultra 20x 价格未公开不录
  3. MiniMax：补全 6 个 per_token（M3/M2.5/M2/M1×3档），M2.7/M2.1 价格未确认不录
  4. 阿里通义：补全 21 个 per_token（按档位拆分）+ Token Plan 团队版(subscription)，Qwen-VL 价格未公开不录，Qwen-Turbo 已下线不录
  5. 修改 run_daily.py manual 合并逻辑：从"跳过所有 per_token"改为"按 product id 去重合并"（sources 已有不覆盖，manual 补充缺失）
  6. 新增 SKIP_PUSH 环境变量开关，支持本地生产数据不推送
  7. 厂商名保持"阿里通义"（_PROVIDER_META 改回）
- **被否决方案**:
  - 厂商名改"阿里云百炼"或"Qwen"：需改前端多处，"阿里通义"是官方中文名
  - 新增 billing_type=token_plan：MiniMax Token Plan 归 coding_plan 避免前端改动
  - 录入无法确认价格的数据并标注"待确认"：保证数据准确，只录确认数据
- **影响**: 更新 `data/manual/{openai,google,minimax,qwen}.yaml`；改造 `scripts/run_daily.py`（合并逻辑+SKIP_PUSH+_products_to_dicts）。产品数 475→602（+127），SQLite 快照 535 条，原始数据 20 条

---

## 2026-07-16 · 引入 SQLite 历史数据层（双写架构）

- **commit**: pending（待提交）
- **背景**:
  1. 现有 prices.json 每次全量覆盖写，无历史快照，无法追溯"某模型上周/上月价格"
  2. 三源仲裁（LiteLLM + OpenRouter + adapter）结果直接落盘，原始数据丢失，仲裁失败时无法回溯是哪个源出错
  3. 波动检测只能和昨天比，无法做长期趋势分析
  4. 用户痛点：某厂商价格不准 + 多源冲突难判断 + 抓取失败率高 + 无法追溯历史
- **决策**:
  1. 采用 SQLite 双写架构：cron 抓取后同时写 SQLite（历史+原始数据）和 prices.json（前端用，保持静态托管不变）
  2. SQLite 文件存 `data/prices.db`，gitignore 排除，服务器本地存储
  3. 三张表：
     - `price_snapshots`：每日最终采用的数据快照，支持历史追溯
     - `raw_fetches`：L1/L2/L3 原始抓取数据留痕，仲裁失败可回溯
     - `price_changes`：自动 diff 今日与昨日，记录字段级变动和百分比
  4. 建表语句集中在 `scripts/core/schema.sql`，支持幂等执行（IF NOT EXISTS），后续新增表（如用户 token 资产）在此追加
  5. DAO 层 `scripts/core/history.py` 封装所有 SQL，后续迁移 MySQL/Postgres 只需改 SQL 方言（? → %s）
  6. 连接 `scripts/core/db.py` 用 WAL 模式，并发读不阻塞写
  7. `run_daily.py` 改造：步骤1写 raw_fetches，步骤2-4写 snapshots，步骤5检测变动并告警（>20% 加入飞书告警）
  8. `scripts/query_history.py` 命令行工具：stats/product/changes/raw/list
  9. 不回填历史数据，从明天首次运行开始积累
- **被否决方案**:
  - 直接上 MySQL/Postgres：数据量小（475 产品 × 365 天 ≈ 17 万条/年），SQLite 足够；引入额外运维成本，不符合 MVP 风格
  - 用 SQLAlchemy ORM：当前代码风格标准库优先（json/logging/subprocess），引入 ORM 风格不一致；DAO 层足够清晰时迁移成本可控
  - 从 git 历史回填 prices.json：费时且收益有限，不回填从新开始更简洁
  - 分两张表（per_token 一张、subscription/coding_plan 一张）：统一一张表按 billing_type 区分字段更简单
- **影响**: 新增 `scripts/core/schema.sql`、`scripts/core/db.py`、`scripts/core/history.py`、`scripts/query_history.py`；改造 `scripts/run_daily.py`（6 步流程）；更新 `.gitignore`。不破坏现有 JSON 契约，前端零改动。后续迁移 MySQL/Postgres 改 DAO 层 SQL 方言即可

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
