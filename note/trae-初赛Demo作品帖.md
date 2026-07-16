# TRAE 初赛 Demo 作品帖 · PPK · Price Per Token

> 用于 TRAE AI 创造力大赛初赛提交。提交时把本文正文复制到社区初赛专区发帖框，标题用下文标题，标签选「学习工作」。
>
> 必备要素：体验链接 ✅ / 关键步骤截图 ≥3 张（发帖时手动上传）/ Session ID ≥3 个（双击 TRAE 会话头像复制）

---

**标签：** 学习工作

**标题：** 【学习工作】 PPK （ Price Per Token）—— 致力于做最好的AI大模型价格网站

---

## 正文

### 1. Demo 简介

**一句话介绍：** PPK (Price Per Token) 是一个聚合 12 家主流大模型厂商定价数据的静态网站 + 后端定时抓取系统，帮开发者一站式对比 Token 单价、订阅制与 Coding Plan，每日自动更新。

**产品形态：** 网站（静态前端 + Python 抓取后端）

**线上体验：**
- 主站（自有服务器）：http://129.226.94.179:8001/ui/
- GitHub Pages 备用：https://hangliuc.github.io/llm-price-compare/

**面向用户：**
- AI 应用开发者（独立开发者、创业团队）
- Agent / Workflow 框架使用者（Coze、Dify、AutoGen 等用户）
- 企业技术选型负责人
- AI Coding 重度用户（Claude Code / Cursor / GLM Coding 等）

**核心功能（3 个）：**

1. **三源交叉验证的比价表** — 12 家厂商、475+ 产品，覆盖 per_token / subscription / coding_plan 三种计费方式。每日 11:00 自动抓取，LiteLLM JSON + OpenRouter API + 官网 Scraper 三源仲裁，价格波动 >20% 警告、>50% 阻断落盘，保证数据可信。

2. **三种计费方式独立页 + 厂商卡片视图** — 按需计费页 8 列表格（含缓存命中价、上下文窗口）；Coding Plan / 订阅制页默认卡片视图，一张卡一个厂商含所有套餐，点击套餐展开功能列表；支持表格/卡片切换、CNY/USD 换算、厂商筛选、关键词搜索。

3. **失败可见性 + 数据新鲜度** — 每家厂商独立状态标记（正常 / 失败 / 过期），抓取失败时前端展示「数据来自 X 小时前，可能过期」并回退到上次成功数据；同时通过飞书 webhook 告警，确保问题第一时间可见。

**界面截图：**

（发帖时在此上传首页、按需计费页、Coding Plan 卡片页 三张截图）

---

### 2. Demo 创作思路

**灵感来源：**

自己在跑长任务 Agent 框架时，经常需要在 OpenAI / Anthropic / DeepSeek / 智谱 / 火山等几家之间切换，每次都要重新打开十几个官网定价页核对——有的厂商还经常售罄（如智谱、火山的 Coding Plan）。市面上的价格对比工具要么只覆盖海外厂商，要么数据更新频率低，缺少一个真正面向国内开发者、覆盖订阅制和 Coding Plan 的实时聚合站。

**想解决的问题：**

- **信息分散**：12 家厂商定价页格式各异、单位不一（per-1M / per-token / 月费 / credits），对比一次要开十几个标签页
- **数据过期**：厂商调价频繁，但多数聚合站更新滞后甚至停更
- **缺少国产 Coding Plan**：海外工具不覆盖智谱、火山、Kimi 等国内厂商的编程套餐
- **失败不可见**：用户无法判断聚合站展示的价格是否最新、是否可信

**为什么做这个方向：**

- **真实刚需**：自己每天都在用，是 dogfooding 场景，痛点具体可量化
- **技术挑战适中**：涉及爬虫、数据仲裁、前端展示、定时任务、CI/CD 全链路，能完整展示 TRAE 的工程落地能力
- **可持续迭代**：数据源、厂商、功能都有明确扩展路径（历史趋势、实时汇率、库存预警），不会做完就扔

**关键取舍：**

- **不用 GitHub Actions cron**：实测延迟 10-30 分钟，改用自有服务器 Docker cron 精准触发
- **前端不用框架构建**：Vue 3 CDN 引入，无 build step，GitHub Pages 直发，部署链路最短
- **三源仲裁而非单源**：单源易错（LiteLLM 曾出现 volcengine 价格全 0 的占位数据），三源投票 + 波动阻断才能保证可信

---

### 3. Demo 体验地址

**主站（推荐，每日 11:00 自动更新）：** http://129.226.94.179:8001/ui/

**GitHub Pages 备用：** https://hangliuc.github.io/llm-price-compare/

**项目仓库：** https://github.com/hangliuc/llm-price-compare

**建议体验路径：**

1. 打开首页，查看 Hero 区厂商环形布局 + 三种计费方式卡片
2. 点「按需计费」→ 体验 8 列表格、筛选标签、点击行展开详情
3. 点「Coding Plan」→ 默认卡片视图，一张卡一个厂商，点击套餐展开功能列表
4. 点「订阅制」→ 查看 OpenAI/Anthropic/Cursor/GitHub Copilot 套餐对比
5. 点「厂商总览」→ 查看 12 家厂商的抓取状态与产品数

---

### 4. TRAE 实践过程

整个项目从 0 到 MVP 上线，再到 UI 多轮打磨，全部在 TRAE IDE 中完成。下面按时间线展开关键步骤。

#### 阶段一：需求拆解与架构设计（2026-07-12）

用 TRAE 的 `brainstorming` skill 梳理需求边界，用 `writing-plans` skill 生成 24 个 task 的实现计划。明确了三源交叉验证、波动阻断、失败可见性三大核心机制。

**关键 Prompt：**

> 我要做一个聚合主流大模型厂商定价的网站。要求：
> 1. 数据每日自动更新，价格波动 >50% 阻断落盘
> 2. 三源交叉验证：LiteLLM JSON + OpenRouter API + 官网 Scraper
> 3. 失败时双通道告警：网页 stale 标记 + 飞书 webhook
> 4. 前端 Vue 3 CDN，无 build step
> 5. Docker 部署，cron 调度
>
> 请帮我拆解任务并生成实现计划。

**截图 1：** TRAE 生成 24 task 实现计划（发帖时上传）

**Session ID：** `6a535a403cbbd94a61218f10`

#### 阶段二：Subagent 驱动开发 MVP（2026-07-12）

把 24 个 task 派发给独立 subagent 执行，TDD 流程：先写测试 → 实现 → 验证。41 个测试全部通过，6 个 adapter fixture 验证了解析逻辑。

**关键技术决策：**

- **数据契约**：单一 `prices.json` 作为 scraper 与 frontend 的唯一契约，完全解耦
- **仲裁层**：自研 `reconcile.py`，按 product_id 对齐三源价格，5%/20% 阈值投票
- **波动检测**：与上次数据对比，单字段 >20% 加入 warnings，整体 >50% 阻断
- **失败隔离**：单源失败不阻塞，单厂商失败保留旧数据并标记 stale

**截图 2：** TRAE Subagent 并发执行 24 task 的过程（发帖时上传）

**Session ID：** `6a535a403cbbd94a61218f10`

#### 阶段三：Docker 化 + 自动部署（2026-07-12 至 07-13）

用 TRAE 生成 Dockerfile（python:3.11-slim + cron + Playwright）+ docker-compose.yml + GitHub Actions（deploy-to-server.yml + deploy.yml）。容器内 cron 每日 11:00 触发 `run_daily.py`，数据变化时自动 git commit + push，触发 GitHub Pages 重建。

**踩过的坑：**

- GitHub Actions cron 延迟 10-30 分钟 → 改用自有服务器 cron
- 容器内 git push 权限 → 用 Personal Access Token 配置 GIT_REMOTE_URL
- Playwright 在 slim 镜像里跑不起来 → Dockerfile 补装 Chromium 依赖

**截图 3：** Docker 容器日志 + 飞书告警截图（发帖时上传）

**Session ID：** `6a535a403cbbd94a61218f10`

#### 阶段四：前端 UI 多轮打磨（2026-07-13 至 07-14）

这是 TRAE 发挥最多的阶段。用 `agent-browser` skill 做可视化验证（截图、DOM 检查、事件模拟），通过多轮对话迭代优化：

**迭代 1：按需计费页 8 列改造**
- 新增「缓存命中价格」「上下文窗口」「类型」三列
- 价格加 /1M 单位，删除冗余「计费」列
- 用 colgroup 明确列宽比例，解决「模型和类型间隔太大」

**迭代 2：筛选标签重构**
- 删除地区标签，新增厂商标签
- 能力标签与类型对齐（text/vision/audio/file）
- 修复 toggleFilter bug：旧代码把 provider 值错误写入 modality 数组

**迭代 3：智谱数据同步**
- 从 6 条 GLM-4 更新到 16 条 GLM-5/4.x 全系列
- 发现浏览器缓存 prices.json → 关闭重开解决

**迭代 4：Coding Plan / 订阅制页改造**
- 新增 18 款 Coding Plan + 9 款订阅制数据（10 个 manual yaml）
- 默认卡片视图：一张卡一个厂商含所有套餐，点击展开功能列表
- 修复表格空白 bug：模板调用了未定义的 `formatMonthly` / `formatQuota` 函数
- 重写标题文案：从「核心定位 / 计费方式 / 使用方式 / 代表产品 / 付费对象」五维度区分两种计费

**关键 Prompt 示例：**

> Coding Plan、订阅制两个页面有 bug 不显示内容。另外做以下改造：
> 1. 厂商和类型标签有点多余，只保留已有厂商标签
> 2. 默认显示卡片，一张卡片一个厂商包含所有套餐，卡片样式你来设计
> 3. 修改标题说明，从核心定位、计费方式、使用方式、代表产品、付费对象出发

TRAE 一次性完成：新增 `groupedRows` computed、改造卡片 HTML、写 CSS、修复 `formatMonthly`/`formatQuota`、更新标题文案，再用 `agent-browser` 验证渲染。

**截图 4：** Coding Plan 卡片视图渲染效果（发帖时上传）

**Session ID：** `6a535a403cbbd94a61218f10`

#### 阶段五：数据流水线文档（2026-07-14）

用 TRAE 生成 `note/data-pipeline.md`，系统梳理数据获取与存储方式：整体架构图、四种数据来源（L1 LiteLLM / L2 OpenRouter / L3 Scraper / Manual YAML）、三种存储 schema、run_daily.py 五步流水线、三源仲裁规则表、波动检测、失败回退、部署架构、添加新厂商 Checklist。

---

### 5. 经验总结与开发心得

**TRAE 用得最爽的几点：**

1. **Subagent 并发执行**：24 个 task 派发独立 subagent，TDD 流程，主上下文不被海量中间结果污染
2. **agent-browser 可视化验证**：UI 改造后直接截图 + eval 检查 DOM，不用手动开浏览器反复刷新
3. **skill 体系**：brainstorming 梳理需求、writing-plans 生成计划、agent-browser 验证 UI，每个环节有专用工具
4. **多轮对话迭代**：UI 打磨是反复调整的过程，TRAE 能记住上下文，不用每次重新解释项目结构

**踩过的坑与解决：**

- **浏览器缓存**：更新 prices.json 后前端显示旧数据，版本号 `style.css?v=N` + `app.js?v=N` 控制缓存破坏
- **Vue 渲染失败静默**：模板调用未定义函数会导致整个页面空白，没有错误提示，需逐个排查
- **LiteLLM 占位数据**：volcengine 价格全为 0，源层加过滤逻辑
- **GitHub Actions cron 延迟**：改用自有服务器 Docker cron

**项目数据：**

- 44 次提交、12 家厂商、475+ 产品
- 三源交叉验证 + 波动阻断 + 失败回退
- 每日 11:00 自动更新，已稳定运行

---

### 6. 报名帖链接

已通过的报名帖：https://forum.trae.cn/t/topic/22549（注：发帖时替换为实际报名帖链接）

---

## 提交前自查清单

- [ ] 标签选「学习工作」
- [ ] 标题格式：`【学习工作】 PPK （ Price Per Token）—— 致力于做最好的AI大模型价格网站`
- [ ] 正文含 4 个必备部分 ✅（Demo 简介 / 创作思路 / 体验地址 / TRAE 实践过程）
- [ ] 附体验链接 ✅（主站 + GitHub Pages）
- [ ] 关键步骤截图 ≥ 3 张（发帖时手动上传到对应位置）
- [ ] Session ID ≥ 3 个 ✅（均为 `6a535a403cbbd94a61218f10`，双击 TRAE 会话头像复制）
- [ ] 附报名帖链接（发帖时填实际链接）
- [ ] 提交前自己点一遍体验链接，确认可访问
- [ ] TRAE 中国版与社区同一手机号

## 截图拍摄建议（发帖时操作）

需要上传的 4 张截图：

1. **TRAE 生成 24 task 实现计划** — 打开 TRAE IDE 对应会话，截图 task 列表
2. **Subagent 并发执行过程** — 截图 TRAE 中多个 subagent 并发执行的界面
3. **Docker 容器日志 + 飞书告警** — 终端 `docker logs llm-price-scraper` + 飞书群告警截图
4. **Coding Plan 卡片视图** — 浏览器打开 http://129.226.94.179:8001/ui/#/billing/coding_plan 截图

## 相关链接

- 初赛参赛指南：https://forum.trae.cn/t/topic/22549
- 保姆级教程：https://forum.trae.cn/t/topic/22569
- 赛事细则：https://bytedance.larkoffice.com/wiki/DScwwZPzsikvNzk5slJc2kgpnie
- 官网领奖入口：https://www.trae.cn/ai-creativity/result
- 项目线上：http://129.226.94.179:8001/ui/
- GitHub Pages：https://hangliuc.github.io/llm-price-compare/
- 项目仓库：https://github.com/hangliuc/llm-price-compare
