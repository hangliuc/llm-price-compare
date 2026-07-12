# LLM 价格比价网站 · 设计文档

- 日期：2026-07-12
- 状态：已通过设计评审，待用户复核
- 范围：MVP 阶段

## 1. 背景与目标

### 1.1 背景

在使用 AI Coding、AI 创作或持续运行 Agent 框架（如 OpenClaw）时，Token 消耗极快。用户经常需要抢购大模型 Token、coding plan（如火山引擎、智谱 coding plan 经常售罄），缺乏一个聚合比较各大模型价格的工具。

### 1.2 目标

开发一个针对大模型（LLM）的价格比价网站，帮助用户：

- 比较不同大模型厂商的价格（per-token、coding plan、订阅制）
- 搜索/筛选符合需求的模型
- 通过订阅跳转链接直达厂商购买页
- 提交反馈（价格异常、建议新厂商）

### 1.3 非目标（MVP 阶段不做）

- 库存/售罄状态展示
- 补货提醒/推送
- 用户账号、收藏功能
- 限时促销价跟踪
- 价格历史趋势图（虽然 git history 天然提供数据，但 MVP 不做前端展示）
- 视觉风格定制（后续单独讨论）

## 2. 关键决策汇总

| 维度 | 决策 |
|---|---|
| 数据来源 | 混合模式：热门厂商写适配器定时抓取 + 长尾厂商人工 YAML 补充 |
| MVP 比较维度 | 只比价格（per-token / coding plan / 订阅制） |
| 部署形态 | 静态站点（GitHub Pages/Vercel）+ 自建服务器 cron 抓取 |
| 更新频率 | 每日一更（11:00 北京时间） |
| 厂商范围 | 10 家：6 家适配器 + 4 家 manual |
| 反馈渠道 | GitHub Issues（预填模板） |
| 用户账号 | MVP 不要 |
| 价格换算 | MVP 硬编码汇率，后续接实时汇率 |

## 3. 整体架构

### 3.1 数据流

```
[厂商定价页/API]                       [社区提交 Issue]
       ↓                                      ↓
  Python 适配器                          管理员审核
       ↓                                      ↓
   抓取/校验 ──────→ 合并 ──────→ data/prices.json
          ↑                                  ↓
   自建服务器 cron                     git push 到仓库
   (每日 11:00 北京时间)                    ↓
                                   GitHub Pages / Vercel
                                          ↓
                              Vue 3 SPA 消费 prices.json
```

### 3.2 仓库结构

```
llm-price-compare/
├── scripts/
│   ├── adapters/          # 每家厂商一个适配器
│   │   ├── base.py        # 抽象基类
│   │   ├── openai.py
│   │   ├── anthropic.py
│   │   ├── zhipu.py
│   │   ├── volcengine.py
│   │   ├── deepseek.py
│   │   ├── opencode.py
│   │   └── tests/         # 适配器测试 + fixtures
│   ├── core/
│   │   ├── fetcher.py     # HTTP/browser 抓取封装
│   │   ├── models.py      # 数据模型
│   │   └── validate.py    # 数据校验 + 波动检测
│   └── run_daily.py       # cron 入口
├── data/
│   ├── prices.json        # 抓取产物（被 commit 回仓库）
│   ├── run_status.json    # 本地运行状态（不 commit）
│   └── manual/            # 人工补充的长尾厂商数据
│       ├── google.yaml
│       ├── mistral.yaml
│       ├── qwen.yaml
│       └── moonshot.yaml
├── ui/
│   ├── index.html         # Vue 3 CDN 引入，无 build step
│   ├── app.js
│   └── style.css
├── .github/
│   ├── workflows/
│   │   ├── deploy.yml     # Pages 部署
│   │   └── test.yml       # CI 测试
│   └── ISSUE_TEMPLATE/
│       ├── price-report.yml
│       └── new-provider.yml
└── README.md
```

### 3.3 部署链路

1. 自建服务器 crontab 每日 11:00（北京时间）触发 `python3 scripts/run_daily.py`
2. 脚本抓取 → 校验 → 波动检测 → 写 prices.json
3. 若 prices.json 有变化 → `git commit + git push`
4. push 触发 GitHub Actions deploy.yml → GitHub Pages 重建
5. 失败/异常 → 飞书 webhook 告警

> 部署期配置值：GitHub 仓库 owner（下文 `<user>` 占位）与飞书 webhook URL 通过服务器环境变量注入，不在代码中硬编码。

### 3.4 关键设计取舍

1. **单一 JSON 契约**：`data/prices.json` 是适配器输出、人工补充、前端消费三方的唯一契约。
2. **`data/manual/` 是社区补充入口**：管理员审核 Issue 后把数据补到 YAML，merge 时合并进 prices.json。
3. **抓取与构建解耦**：抓取失败不影响上次成功部署的站点，prices.json 只在校验通过后才覆盖。
4. **价格历史白送**：daily commit 的 git log 形成价格历史，MVP 不做前端展示，预留扩展。

## 4. 数据模型

### 4.1 prices.json 顶层结构

```json
{
  "generated_at": "2026-07-12T11:00:00+08:00",
  "providers": [...],
  "provider_status": [...]
}
```

- `generated_at`：本次抓取时间（ISO 8601，带时区），前端显示「最近更新于 X 小时前」。
- `providers`：厂商数组。
- `provider_status`：每个 provider 的抓取状态，用于前端展示与告警。

### 4.2 Provider 结构

```json
{
  "id": "zhipu",
  "name": "智谱",
  "name_en": "Zhipu AI",
  "region": "cn",
  "website": "https://open.bigmodel.cn/",
  "pricing_url": "https://open.bigmodel.cn/pricing",
  "products": [...]
}
```

- `id`：稳定标识符（小写英文），前端路由/书签用。
- `region`：`cn` / `us` / `eu`，用于前端按地区筛选。
- `products`：该厂商的计费产品数组。

### 4.3 Product 结构

统一抽象三种计费模式：

```json
{
  "id": "glm-4-plus-token",
  "model": "GLM-4-Plus",
  "billing_type": "per_token",
  "context_window": 128000,
  "modalities": ["text", "vision"],
  "release_date": "2024-08-01",
  "prices": {
    "input": 0.05,
    "output": 0.05,
    "cached_input": 0.005,
    "currency": "CNY",
    "unit": "per_1m_tokens"
  },
  "purchase_url": "https://open.bigmodel.cn/pricing",
  "notes": null
}
```

三种 `billing_type` 与 prices 字段对应：

| billing_type | 适用场景 | prices 必填字段 |
|---|---|---|
| `per_token` | 按 token 计费的 API（OpenAI/Anthropic/DeepSeek 等） | input, output, currency, unit（cached_input 可选） |
| `subscription` | 月度订阅（ChatGPT Plus、Claude Pro 等） | monthly_price, currency（included_quota、features 可选） |
| `coding_plan` | Coding 套餐（智谱、火山引擎、OpenCode 等） | monthly_price, currency, included_quota, quota_unit, features |

所有 `prices` 都包含 `currency`（CNY/USD）和明确的 `unit`。

### 4.4 provider_status 结构

```json
{
  "provider_id": "volcengine",
  "status": "failed",
  "last_success_at": "2026-07-11T11:00:00+08:00",
  "error": "Headless browser timeout",
  "stale": true
}
```

- `status`：`ok` / `failed` / `no_data`（首次抓取即失败）
- `stale`：true 时前端展示过期提示
- 波动 20%–50% 的警告通过 `status: "ok"` + 额外 `warning` 字段表达（见 4.5）

### 4.5 波动警告标记

provider_status 中可附加波动警告：

```json
{
  "provider_id": "zhipu",
  "status": "ok",
  "last_success_at": "2026-07-12T11:00:00+08:00",
  "warnings": [
    {
      "product_id": "glm-4-plus-token",
      "field": "prices.input",
      "old_value": 0.05,
      "new_value": 0.065,
      "volatility_pct": 30
    }
  ]
}
```

### 4.6 数据校验规则（core/validate.py）

每个 Product 落库前必须通过校验：

1. **必填字段**：`id`, `billing_type`, `prices`, `prices.currency`, `purchase_url`。
2. **billing_type 与 prices 字段匹配**：
   - `per_token` → 必须有 `input`/`output`/`unit`
   - `subscription` → 必须有 `monthly_price`
   - `coding_plan` → 必须有 `monthly_price`/`included_quota`/`quota_unit`
3. **价格非负**：所有数值字段 ≥ 0（免费模型填 0）。
4. **ID 唯一**：同一 provider 内 `product.id` 唯一。
5. **波动检测**（按最大波动字段判定，含等号归属）：
   - ≤ 20%：正常落盘
   - > 20% 且 ≤ 50%：警告但落盘，记入 `warnings`，飞书告警
   - > 50%：阻断该 provider 落盘，沿用上次数据，飞书告警

## 5. 抓取适配器层

### 5.1 适配器基类

```python
# scripts/adapters/base.py
class BaseAdapter:
    provider_id: str          # "zhipu"
    provider_name: str        # "智谱"
    region: str               # "cn"
    website: str
    pricing_url: str

    def fetch(self) -> list[Product]:
        """抓取并返回该厂商的所有 products。失败抛异常。"""
        raise NotImplementedError

    def validate(self, products: list[Product]) -> list[Product]:
        """适配器层面的校验。默认调用 core/validate.py 通用校验。"""
        ...
```

适配器只负责「抓 + 转成 Product 列表」，不负责持久化、不负责合并——单一职责。

### 5.2 抓取策略分层

| 策略 | 适用场景 | 示例厂商 |
|---|---|---|
| HTTP + JSON 解析 | 有公开 API 或定价页是 JSON 渲染 | OpenAI（部分）、DeepSeek |
| HTTP + HTML 解析 | 静态 HTML 定价页 | Anthropic、OpenCode |
| Headless Browser | JS 动态渲染、反爬中等 | 智谱、火山引擎 |

约束：优先用 HTTP，浏览器是兜底；浏览器适配器串行执行，复用 headless 实例，请求间隔 2-3 秒。

### 5.3 MVP 阶段 6 家适配器

| 适配器 | provider_id | 抓取策略 | billing_type | 数据源 |
|---|---|---|---|---|
| OpenAIAdapter | openai | HTTP + HTML/JSON | per_token | openai.com/api/pricing |
| AnthropicAdapter | anthropic | HTTP + HTML | per_token + subscription | docs.anthropic.com |
| ZhipuAdapter | zhipu | Headless Browser | per_token + coding_plan | open.bigmodel.cn/pricing |
| VolcengineAdapter | volcengine | Headless Browser | per_token + coding_plan | volcengine.com/product/ark |
| DeepSeekAdapter | deepseek | HTTP + HTML | per_token | api-docs.deepseek.com |
| OpenCodeAdapter | opencode | HTTP + HTML | coding_plan | opencode.ai/zh/go |

### 5.4 MVP 阶段 4 家 manual

| 厂商 | provider_id | 原因 |
|---|---|---|
| Google Gemini | google | 定价页结构复杂，先 manual |
| Mistral | mistral | 长尾，后续再写 |
| 阿里通义 | qwen | 百炼平台反爬待评估 |
| 月之暗面 | moonshot | 同上 |

manual 数据格式见 `data/manual/*.yaml`，由 `load_manual_providers()` 读取后 merge 进 providers 列表。

### 5.5 适配器注册机制

`scripts/adapters/__init__.py` 维护注册表：

```python
ADAPTERS = [
    OpenAIAdapter(),
    AnthropicAdapter(),
    ZhipuAdapter(),
    VolcengineAdapter(),
    DeepSeekAdapter(),
    OpenCodeAdapter(),
]
```

新增厂商 = 写一个 adapter 文件 + 加一行注册；删除 = 注释一行。

### 5.6 失败可见性（双通道）

**通道 1：网页展示**

前端根据 `provider_status`：
- `ok` → 正常显示
- `failed` + `stale: true` → 行/卡片橙色边框 + tooltip「数据来自 X 小时前，可能过期」
- 波动警告 → 行内橙色提示「近期价格波动较大，请核对」

顶部数据新鲜度条：若任何 provider stale，显示「⚠ N 家厂商数据可能过期，详情见标注」。

**通道 2：飞书告警**

通过环境变量 `FEISHU_WEBHOOK_URL` 配置。触发条件：

1. 适配器抓取失败
2. 价格波动 > 20%（含警告档和阻断档）
3. 全局校验失败，未落盘

飞书消息格式示例：

```
[LLM 比价站告警]
类型: 适配器失败
厂商: 火山引擎
错误: Headless browser timeout
上次成功: 2026-07-11 11:00
当前数据已回退至上次成功版本，站点正常显示但标注过期
```

### 5.7 适配器失效感知

适配器静默失效（页面改版但抓到错误数据）比报错更危险。两层防护：

1. **数据合理性校验**（core/validate.py）：
   - 价格相对上次波动 > 20% → 警告/阻断
   - 必填字段为空 → 失败
   - 价格为 0 但 `notes` 未标明"免费" → 警告

2. **适配器自检断言**：每个适配器在 `fetch()` 末尾自检，例如智谱适配器断言「至少抓到 3 个 products」，抓到 0 个主动抛异常。

### 5.8 run_daily.py 调度逻辑

```python
def main():
    old_data = load_prices_json()
    new_providers = []
    provider_status = []
    alerts = []

    for adapter in ADAPTERS:
        try:
            products = adapter.fetch()
            products = adapter.validate(products)

            # 波动检测
            old_provider = find_provider(old_data, adapter.provider_id)
            volatility = check_volatility(old_provider, products)
            if volatility.max_pct > 50:
                alerts.append(("blocked", adapter.provider_id, f"波动 {volatility.max_pct}%"))
                provider_status.append(stale_status(adapter, old_provider))
                new_providers.append(old_provider)
                continue
            elif volatility.max_pct > 20:
                alerts.append(("warning", adapter.provider_id, f"波动 {volatility.max_pct}%"))
                provider_status.append(ok_status_with_warning(adapter, volatility))

            new_providers.append(adapter_to_provider_dict(adapter, products))
            provider_status.append(ok_status(adapter))

        except Exception as e:
            alerts.append(("failed", adapter.provider_id, str(e)))
            old_provider = find_provider(old_data, adapter.provider_id)
            if old_provider:
                new_providers.append(old_provider)
                provider_status.append(failed_status(adapter, old_provider, e))
            else:
                provider_status.append(no_data_status(adapter, e))

    # 合并 manual
    manual_providers = load_manual_providers("data/manual/")
    new_providers.extend(manual_providers)
    for mp in manual_providers:
        provider_status.append(ok_status_for_manual(mp["id"]))

    new_data = {
        "generated_at": now_iso(),
        "providers": new_providers,
        "provider_status": provider_status,
    }

    if validate_global(new_data):
        write_prices_json(new_data)
        update_run_status(success=True)
        if has_changed(old_data, new_data):
            git_commit_push()
        if alerts:
            send_feishu_alerts(alerts)
    else:
        alerts.append(("fatal", "global", "Global validation failed"))
        update_run_status(success=False)
        send_feishu_alerts(alerts)
```

关键设计：
- **失败隔离**：单个适配器失败不影响其他，沿用上次成功数据。
- **全局校验门槛**：全局校验不过不落盘。
- **变化检测**：prices.json 无变化时不 commit。
- **失败告警**：飞书 webhook 推送。

## 6. 前端 UI

### 6.1 技术选型

Vue 3 CDN 引入，无 build step。单页应用，运行时 fetch `data/prices.json`。

### 6.2 页面结构（单页三区）

```
┌─────────────────────────────────────────────┐
│  Header                                      │
│  [Logo] LLM 价格比价  [搜索框] [反馈]        │
├─────────────────────────────────────────────┤
│  筛选区                                      │
│  地区: [全部][国内][国外]                    │
│  计费类型: [全部][Token][订阅][Coding Plan]  │
│  能力: [全部][文本][视觉]                    │
├─────────────────────────────────────────────┤
│  数据新鲜度条                                │
│  最近更新: 2 小时前 · 10 家厂商 · 32 个产品  │
│  (若有失败 provider, 这里显示橙色提示)       │
├─────────────────────────────────────────────┤
│  结果区: 表格 + 卡片视图切换                 │
│  ┌──────────────────────────────────────┐  │
│  │ 厂商 | 模型 | 计费 | 输入价 | 输出价 |→│  │
│  │ 智谱 | GLM-4-Plus | Token | ¥0.05 |... │  │
│  │ [点击行展开详情/购买链接]              │  │
│  └──────────────────────────────────────┘  │
├─────────────────────────────────────────────┤
│  Footer                                      │
│  数据仅供参考 · 价格以厂商为准 · GitHub     │
└─────────────────────────────────────────────┘
```

### 6.3 核心交互

1. **搜索框**：实时模糊搜索厂商名 / 模型名。
2. **筛选器**：地区、计费类型、能力（modalities）三个维度，多选叠加。
3. **排序**：点表头排序（输入价/输出价/上下文窗口/最近更新）。
4. **价格换算**：右上角切换 CNY/USD 显示，MVP 用硬编码汇率。
5. **行展开**：点行展开详情——购买链接、能力、上下文窗口、备注、数据状态。
6. **视图切换**：表格视图 / 卡片视图切换。
7. **反馈按钮**：跳转 GitHub Issues 预填模板。

### 6.4 反馈 Issue 模板

仓库 `.github/ISSUE_TEMPLATE/` 下两个模板：

**price-report.yml（报告价格异常）**

```yaml
name: 价格异常报告
labels: [price-error]
body:
  - type: dropdown
    id: provider
    attributes:
      label: 厂商
      options: [OpenAI, Anthropic, 智谱, 火山引擎, DeepSeek, OpenCode, Google, Mistral, 阿里通义, 月之暗面]
  - type: input
    id: model
    attributes:
      label: 模型/产品
  - type: textarea
    id: correct_price
    attributes:
      label: 正确价格（请附厂商定价页截图或链接）
```

**new-provider.yml（建议新增厂商）**

```yaml
name: 建议新增厂商
labels: [new-provider]
body:
  - type: input
    id: provider_name
    attributes:
      label: 厂商名称
  - type: input
    id: pricing_url
    attributes:
      label: 定价页 URL
```

反馈按钮根据上下文带 query params 跳转：

```
https://github.com/<user>/llm-price-compare/issues/new?
  template=price-report.yml
  &labels=price-error
  &title=[价格异常]+智谱+GLM-4-Plus
```

### 6.5 错误状态展示

- 某 provider `stale: true` → 行/卡片橙色边框 + tooltip
- 顶部数据新鲜度条若任何 provider stale → 显示「⚠ N 家厂商数据可能过期」
- 前端 fetch prices.json 404 → 全屏错误页「数据暂不可用」
- 前端 fetch 超时 → 重试 1 次，仍失败显示缓存数据 + 顶部黄色提示条

### 6.6 性能预算

- prices.json 预估 < 50KB（10 厂商 × 5 产品 ≈ 50 条记录）
- 前端无依赖打包，首屏 < 1s
- 移动端响应式（最小 375px 宽）

## 7. 错误处理矩阵

| 场景 | 处理策略 | 用户感知 | 告警 |
|---|---|---|---|
| 单适配器抓取失败 | 沿用上次数据，标记 `stale: true` | 行/卡片橙色边框 + tooltip | 飞书 |
| 适配器抓到 0 条（页面改版） | 自检断言失败 → 抛异常 → 走失败分支 | 同上 | 飞书 |
| 价格波动 > 50% | 阻断落盘，沿用旧数据 | 同上 | 飞书（阻断档） |
| 价格波动 20%–50% | 落盘但标波动警告 | 行内橙色提示「近期波动较大」 | 飞书（警告档） |
| 全局校验失败 | 不落盘，保留旧 prices.json | 站点无变化 | 飞书（fatal） |
| git push 失败 | 重试 3 次，仍失败告警 | 站点数据不更新 | 飞书 |
| 前端 fetch prices.json 404 | 显示全屏错误页 | 全屏错误 | 无 |
| 前端 fetch 超时 | 重试 1 次，仍失败显示缓存 + 提示 | 顶部黄色提示条 | 无 |
| 飞书 webhook 本身失败 | 记日志，不重试 | 无 | 无 |

## 8. 测试策略

### 8.1 适配器测试（最关键）

```
scripts/adapters/tests/
├── test_openai.py
├── test_anthropic.py
├── test_zhipu.py
├── test_volcengine.py
├── test_deepseek.py
├── test_opencode.py
└── fixtures/
    ├── openai_pricing.html
    ├── openai_expected.json
    └── ...
```

- 每个 adapter 配套 fixture（HTML 快照 + 期望 JSON）
- 测试时 `fetch()` 用 `mock_http(fixture_html)` 替代真实请求
- 断言解析结果与 `expected.json` 一致
- 厂商改版 → fixture 失效 → 测试红 → 更新 fixture

### 8.2 校验逻辑测试

`core/validate.py` 纯函数测试：
- 波动检测：构造新旧数据，验证 20%/50% 阈值判定
- 字段校验：构造缺失字段/负值/类型错误数据，验证抛错
- 合并逻辑：manual YAML + adapter 输出合并正确

### 8.3 调度流程测试

`run_daily.py`：
- 单适配器失败不影响其他
- 全局校验失败不落盘
- 无变化不 commit

### 8.4 前端测试

MVP 阶段轻量：
- 手动测试清单（搜索、筛选、排序、视图切换、反馈跳转）
- 不引入单测框架

### 8.5 CI

`.github/workflows/test.yml`：

```yaml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.11" }
      - run: pip install -r requirements.txt
      - run: pytest scripts/
```

约束：headless browser 适配器测试在 CI 中跳过（`@pytest.mark.browser` 标记），CI 只跑 HTTP 适配器 + 校验逻辑。

## 9. 可观测性

### 9.1 日志

`run_daily.py` 输出结构化日志到 `/var/log/llm-price/`，按日轮转，保留 30 天：

```
2026-07-12T11:00:01+08:00 INFO  run_daily started
2026-07-12T11:00:03+08:00 INFO  openai fetched 8 products
2026-07-12T11:00:15+08:00 ERROR volcengine failed: Headless browser timeout
2026-07-12T11:00:16+08:00 WARN  volcengine fallback to last success (2026-07-11T11:00:00+08:00)
2026-07-12T11:00:20+08:00 INFO  zhipu volatility 35% on glm-4-plus.input, warning but landed
2026-07-12T11:00:25+08:00 INFO  run_daily finished, 9 ok, 1 failed, 1 warning, pushed
```

### 9.2 运行状态文件

`data/run_status.json`（本地，不 commit）：

```json
{
  "last_run_at": "2026-07-12T11:00:25+08:00",
  "last_success_at": "2026-07-12T11:00:25+08:00",
  "consecutive_failures": 0,
  "last_push_at": "2026-07-12T11:00:25+08:00",
  "providers_summary": {
    "openai": "ok",
    "volcengine": "failed"
  }
}
```

便于在服务器上 `cat data/run_status.json` 快速查看。

## 10. 安全与合规

1. **不存储用户数据**：MVP 无账号、无 cookie、无分析脚本。
2. **适配器请求头**：`User-Agent: LLM-Price-Bot/1.0 (+https://github.com/<user>/llm-price-compare)`，透明标识。
3. **请求频率**：单厂商单次抓取，无并发；浏览器适配器串行执行，间隔 2-3 秒。
4. **免责声明**：页脚固定显示「数据仅供参考，价格以厂商官方为准」。
5. **不绕过反爬**：遇 403/验证码立即标记失败，走失败隔离流程，不重试不破解。

## 11. 后续迭代方向（非 MVP）

- 库存/售罄状态展示
- 补货提醒/推送
- 用户账号、收藏功能
- 限时促销价跟踪
- 价格历史趋势图（基于 git history）
- 实时汇率 API
- 视觉风格定制
- 健康检查端点（接入 Uptime Kuma）
- manual 厂商逐步替换为适配器
