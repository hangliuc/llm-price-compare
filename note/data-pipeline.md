# 数据获取与存储方式

> 本文档描述 PPK (Price Per Token) 站点从外部数据源采集到大模型价格、到最终在前端展示的完整数据链路：**采集源 → 仲裁 → 校验 → 落盘 → 推送 → 静态站点**。
>
> 所有采集/合并/校验逻辑都集中在 `scripts/`，最终数据契约是 `data/prices.json`，前端只读这一份 JSON。

---

## 一、整体架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                         外部数据源                                   │
│   L1: LiteLLM JSON    L2: OpenRouter API    L3: 官网 Scraper        │
│   (静态 JSON)         (REST API)           (adapters)               │
└──────────┬──────────────────┬──────────────────┬───────────────────┘
           │                  │                  │
           └──────────┬───────┴──────────┬───────┘
                      ▼                  ▼
            ┌──────────────────────────────────────┐
            │  scripts/core/reconcile.py           │
            │  三源仲裁（按 product_id 对齐价差投票）│
            └─────────────────┬────────────────────┘
                              ▼
            ┌──────────────────────────────────────┐
            │  scripts/core/validate.py            │
            │  波动检测 20% 警告 / 50% 阻断          │
            └─────────────────┬────────────────────┘
                              ▼
            ┌──────────────────────────────────────┐
            │  scripts/core/manual.py              │
            │  合并 manual yaml（订阅/Coding Plan） │
            └─────────────────┬────────────────────┘
                              ▼
            ┌──────────────────────────────────────┐
            │  data/prices.json  +  run_status.json │
            │  （唯一数据契约，前端只读这份 JSON）   │
            └─────────────────┬────────────────────┘
                              ▼
                ┌──────────────────────────┐
                │  git commit + push        │
                │  GitHub Actions 触发      │
                │  → GitHub Pages 部署      │
                └──────────────────────────┘
```

**关键原则**：
- 单一数据契约 `data/prices.json`，scraper 与 frontend 完全解耦
- 三源交叉验证，单源失败不阻塞
- 价格异常波动 >50% 阻断落盘，保留上次成功数据
- 每家厂商独立状态标记，失败时前端展示「数据过期」

---

## 二、数据获取（四种来源）

### L1：LiteLLM JSON（per_token 主源）

**文件**：[scripts/sources/litellm.py](file:///Users/shareit/personal/llm-price-compare/scripts/sources/litellm.py)

**数据源 URL**：`https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`

**特点**：
- 静态 JSON 文件，无鉴权，可缓存可 fork
- 覆盖 9/12 厂商（缺 opencode/zhipu/xiaomi）
- 价格为 per-token 科学计数法，需 ×1e6 转 per-1M
- 已知问题：volcengine 价格全为 0（社区占位数据），源层已过滤

**字段映射**：
| LiteLLM 字段 | 项目字段 | 说明 |
|---|---|---|
| `input_cost_per_token` | `prices.input` | ×1e6 转 per-1M |
| `output_cost_per_token` | `prices.output` | ×1e6 转 per-1M |
| `cache_read_input_token_cost` | `prices.cached_input` | ×1e6，可选 |
| `max_input_tokens` / `max_tokens` | `context_window` | 优先取前者 |
| `supports_vision` | `modalities` 含 `vision` | |
| `supports_audio_input/output` | `modalities` 含 `audio` | |
| `litellm_provider` | `provider_id` | 通过 PROVIDER_MAP 归并 |

**Provider 映射**（`litellm_provider` → 项目 `provider_id`）：
```
openai -> openai
anthropic -> anthropic
gemini / vertex_ai-language-models / vertex_ai -> google
bedrock -> aws
deepseek -> deepseek
moonshot -> moonshot
dashscope -> qwen
volcengine -> volcengine
minimax -> minimax
```

**过滤规则**：
- 仅保留 `mode == "chat"` 模型
- `input` 或 `output` 缺失/为 0 的条目丢弃
- 同 `model_id` 去重（取首条）
- model_id 标准化：去掉 `provider/` 前缀、去掉 8 位日期后缀

---

### L2：OpenRouter API（交叉源 + 能力元数据）

**文件**：[scripts/sources/openrouter.py](file:///Users/shareit/personal/llm-price-compare/scripts/sources/openrouter.py)

**数据源 URL**：`https://openrouter.ai/api/v1/models`

**特点**：
- REST API，无鉴权，无明显限流
- 覆盖 7/12 厂商（缺 aws/opencode/volcengine/zhipu）
- 价格为 per-token 字符串，需 ×1e6 转 per-1M
- 独有字段：`benchmarks`（artificial_analysis 评分）、`reasoning`（推理能力位）、`expiration_date`

**Provider 映射**（OpenRouter `id` 前缀 → 项目 `provider_id`）：
```
openai / ~openai       -> openai
anthropic / ~anthropic -> anthropic
google / ~google       -> google
deepseek               -> deepseek
moonshotai             -> moonshot
qwen                   -> qwen
minimax                -> minimax
xiaomi                 -> xiaomi
```

**过滤规则**：
- `id` 必须含 `/`
- `architecture.output_modalities` 不含 `text` 的丢弃（纯图像/音频工具排除）
- `input` 或 `output` 缺失/为 0 的丢弃
- 同 `model_id` 去重

**独有元数据**（序列化为 JSON 存入 `Product.notes`）：
```python
{
  "benchmarks": {...},          # artificial_analysis 评分
  "reasoning": {
    "mandatory": bool,
    "supported_efforts": [...],
    "default_effort": "..."
  },
  "expiration_date": "2026-12-31"
}
```

---

### L3：官网 Scraper（adapters，兜底 + 订阅/Coding Plan 唯一来源）

**目录**：[scripts/adapters/](file:///Users/shareit/personal/llm-price-compare/scripts/adapters/)

**当前注册的 adapters**（见 [scripts/adapters/__init__.py](file:///Users/shareit/personal/llm-price-compare/scripts/adapters/__init__.py)）：
- `OpenAIAdapter` — `https://platform.openai.com/docs/pricing`（备用 `openai.com/api/pricing/`）
- `AnthropicAdapter` — `https://www.anthropic.com/pricing`
- `DeepSeekAdapter` — `https://api-docs.deepseek.com/quick_start/pricing`

**已停用改为 manual 维护**（页面结构不稳定或需登录）：
- OpenCode / 智谱 / 火山引擎

**Adapter 基类**：[scripts/adapters/base.py](file:///Users/shareit/personal/llm-price-compare/scripts/adapters/base.py)
- `fetch()` 抓取并返回 `list[Product]`，失败抛异常
- `validate()` 调用 `validate_product` 做字段校验
- `assert_min_products()` 自检：防止页面改版静默失效（默认 ≥1）

**抓取工具**：[scripts/core/fetcher.py](file:///Users/shareit/personal/llm-price-compare/scripts/core/fetcher.py)
- `fetch_html(url)` — requests + 真实浏览器 UA
- `fetch_json(url)` — requests JSON
- `fetch_html_browser(url, wait_selector)` — Playwright headless Chromium，用于动态渲染页面（SPA）

**UA 策略**：使用真实 Chrome UA，避免被 Cloudflare/WAF 拦截 bot UA。

---

### Manual YAML（人工补充数据）

**目录**：[data/manual/](file:///Users/shareit/personal/llm-price-compare/data/manual/)

**用途**：
1. 补充 sources 与 adapter 都未覆盖的厂商（opencode、githubcopilot、cursor、xiaomi 等）
2. 维护页面结构不稳定/需登录的厂商（zhipu、volcengine）
3. **唯一来源** for `subscription` 和 `coding_plan` 类型产品

**当前 manual 文件**：
| 文件 | provider_id | 产品数 | 类型 |
|---|---|---|---|
| `zhipu.yaml` | zhipu | 16 per_token + 3 coding_plan | 全量替换 |
| `volcengine.yaml` | volcengine | 9 per_token + 2 coding_plan | 全量替换 |
| `qwen.yaml` | qwen | 1 per_token + 1 coding_plan | 追加 coding_plan |
| `moonshot.yaml` | moonshot | 1 per_token + 4 coding_plan | 追加 coding_plan |
| `minimax.yaml` | minimax | 3 coding_plan | 全量 |
| `xiaomi.yaml` | xiaomi | 4 coding_plan | 全量 |
| `opencode.yaml` | opencode | 1 coding_plan | 全量 |
| `githubcopilot.yaml` | githubcopilot | 2 subscription | 全量 |
| `cursor.yaml` | cursor | 2 subscription | 全量 |
| `openai.yaml` | openai | 2 subscription | 仅追加 subscription |
| `anthropic.yaml` | anthropic | 3 subscription | 仅追加 subscription |
| `google.yaml` | google | 1 per_token | 仅追加（sources-only 厂商） |

**合并策略**（详见下文「四、数据处理流水线」）：
- **纯 manual 厂商**（不在 sources & 无 adapter）：完整保留 manual 数据
- **reconcile 处理过的厂商**：跳过 manual 的 `per_token`，仅追加 `subscription`/`coding_plan`
- **sources-only 厂商**（google/aws 等）：追加 manual 中的非 per_token 产品

---

## 三、数据存储

### 3.1 主数据契约：`data/prices.json`

**文件**：[data/prices.json](file:///Users/shareit/personal/llm-price-compare/data/prices.json)

**Schema**：
```json
{
  "generated_at": "2026-07-14T21:10:19+08:00",
  "providers": [
    {
      "id": "openai",
      "name": "OpenAI",
      "name_en": "OpenAI",
      "region": "us",              // cn | us | eu
      "website": "https://openai.com/",
      "pricing_url": "https://platform.openai.com/docs/pricing",
      "products": [
        {
          "id": "chat-latest-token",
          "model": "chat-latest",
          "billing_type": "per_token",   // per_token | subscription | coding_plan
          "context_window": 128000,
          "modalities": ["text", "vision"],
          "release_date": null,           // ISO 日期字符串，可为 null
          "prices": { ... },              // 见下文三种类型
          "purchase_url": "https://platform.openai.com/docs/pricing",
          "notes": null                   // OpenRouter 能力元数据 JSON 字符串
        }
      ]
    }
  ],
  "provider_status": [
    {
      "provider_id": "openai",
      "status": "ok",                     // ok | failed
      "last_success_at": "2026-07-14T21:10:19+08:00",
      "error": null,
      "stale": false,                     // true 表示数据可能过期
      "warnings": [],                     // 波动告警列表
      "confidence": "high",               // high | medium | low | manual
      "sources": ["litellm", "openrouter", "adapter"]
    }
  ]
}
```

**三种 `prices` 子结构**：

#### per_token
```json
{
  "input": 5.0,                // per 1M tokens
  "output": 30.0,
  "cached_input": 0.5,         // 可选，缓存读取价
  "currency": "USD",           // USD | CNY
  "unit": "per_1m_tokens"
}
```

#### subscription（产品订阅，面向终端用户）
```json
{
  "monthly_price": 20,         // 月费
  "currency": "USD",
  "features": [                 // 套餐功能列表
    "不限量补全和聊天",
    "支持 GPT-5、Claude Sonnet 5"
  ]
}
```

#### coding_plan（API 额度套餐，面向开发者）
```json
{
  "monthly_price": 49,
  "currency": "CNY",
  "included_quota": 80,
  "quota_unit": "prompts_per_5h",   // prompts_per_5h | calls_per_month | base
  "first_month_price": 9.9,         // 可选，活动首月价
  "features": [...]
}
```

**关键约束**（见 [scripts/core/validate.py](file:///Users/shareit/personal/llm-price-compare/scripts/core/validate.py)）：
- 所有产品必须有 `id` 和 `purchase_url`
- `prices.currency` 必填
- per_token 必须有 `input`/`output`/`unit`
- subscription 必须有 `monthly_price`
- coding_plan 必须有 `monthly_price`/`included_quota`/`quota_unit`
- 同一 provider 内 product id 不能重复
- 同一 prices.json 内 provider id 不能重复

---

### 3.2 运行状态：`data/run_status.json`

**文件**：`data/run_status.json`（由 [scripts/core/status.py](file:///Users/shareit/personal/llm-price-compare/scripts/core/status.py) 维护）

**Schema**：
```json
{
  "last_run_at": "2026-07-14T11:00:00+08:00",
  "last_success_at": "2026-07-14T11:00:00+08:00",
  "consecutive_failures": 0,
  "last_push_at": "2026-07-14T11:00:00+08:00",
  "providers_summary": {
    "openai": "ok",
    "anthropic": "ok",
    "volcengine": "blocked",
    "zhipu": "ok"
  }
}
```

用途：监控 cron 任务健康度，连续失败可在告警中体现。

---

### 3.3 Manual YAML Schema

**目录**：`data/manual/*.yaml`

每个 yaml 文件就是一个 provider 的完整定义：

```yaml
id: zhipu                          # 与 prices.json 中 provider.id 对应
name: 智谱
name_en: Zhipu AI
region: cn                         # cn | us | eu
website: https://open.bigmodel.cn/
pricing_url: https://open.bigmodel.cn/pricing
products:
  - id: glm-5.2-token
    model: GLM-5.2
    billing_type: per_token        # per_token | subscription | coding_plan
    context_window: 1048576
    modalities: [text]
    release_date: "2026-06-01"     # 可选
    prices:
      input: 8.0
      output: 28.0
      cached_input: 2.0            # 可选
      currency: CNY
      unit: per_1m_tokens
    purchase_url: https://open.bigmodel.cn/pricing
  # ... 更多产品
```

**加载逻辑**：[scripts/core/manual.py](file:///Users/shareit/personal/llm-price-compare/scripts/core/manual.py)
- 扫描目录下所有 `*.yaml`，按文件名排序加载
- `yaml.safe_load` 解析，只接受顶层是 dict 且含 `id` 字段的

---

## 四、数据处理流水线（run_daily.py）

**入口**：[scripts/run_daily.py](file:///Users/shareit/personal/llm-price-compare/scripts/run_daily.py)

**调度**：每日北京时间 11:00，由 Docker 容器内 cron 触发（见 [Dockerfile](file:///Users/shareit/personal/llm-price-compare/Dockerfile)）。

### Step 1：采集外部数据源
```python
sources_data = fetch_all_sources()
# 返回 {"litellm": {pid: [Product]}, "openrouter": {pid: [Product]}}
```
单源失败不阻塞，记日志后该源值为 `{}`。

### Step 2：处理有 adapter 的厂商（三源仲裁 L1+L2+L3）
对每个注册的 adapter：
1. L3 抓取官网价格 → `adapter_products`
2. 取 L1 `litellm_products` + L2 `openrouter_products`
3. 调用 `reconcile_provider()` 三源仲裁
4. 波动检测：与上次 `prices.json` 中该 provider 数据对比
   - >50%：阻断，保留旧数据，标记 `stale=true`
   - 20%-50%：警告但更新
5. 成功：写入 `new_providers`，status 含 `confidence` 和 `sources_used`
6. 失败：保留旧 provider 数据，status `stale=true`，记飞书告警

### Step 3：处理 sources-only 厂商（双源仲裁 L1+L2）
对在 L1∪L2 中但无 adapter 的厂商：
1. L1 + L2 双源仲裁（无 L3）
2. 若两源都空（如 volcengine 价格全 0）：交给 manual 兜底
3. 若仲裁后 0 产品：交给 manual 兜底
4. 其余流程同 Step 2

### Step 4：合并 Manual YAML
```python
manual_providers = load_manual_providers("data/manual")
```

对每个 manual provider：
- **已被 reconcile 处理**：跳过 manual 的 `per_token` 产品，仅追加 `subscription`/`coding_plan` 到对应 provider
- **reconcile 失败但 manual 有该 provider**：完整保留 manual 全部产品
- **未被 reconcile 处理**（opencode/zhipu/volcengine 等）：完整保留 manual 全部产品，并补充 status（`confidence: "manual"`, `sources: ["manual"]`）

### Step 5：写盘 + 告警
1. `validate_global(new_data)` 全局校验
2. `write_prices_json(new_data)` 落盘
3. 若数据有变化：`git_commit_push()` 自动提交并推送
4. `update_run_status()` 更新运行状态
5. `send_feishu_alerts(alerts)` 发送飞书告警（失败/警告/阻断/fatal）

---

## 五、三源仲裁规则（reconcile.py）

**文件**：[scripts/core/reconcile.py](file:///Users/shareit/personal/llm-price-compare/scripts/core/reconcile.py)

**仲裁单位**：按 `product_id` 维度对齐，对每个价格字段（`input`/`output`/`cached_input`）独立投票。

**价差阈值**：
- `< 5%`：视为一致
- `5% - 20%`：偏离，warning
- `> 20%`：显著偏离

**仲裁规则**：

| 源数量 | 价差 | 采信策略 | confidence |
|---|---|---|---|
| 3 源 | 全部 <5% | 主源（litellm > adapter > openrouter） | high |
| 3 源 | 5%-20% | 主源，warning | medium |
| 3 源 | >20%，有 2 源一致 | 一致两源均值 | medium |
| 3 源 | >20%，三源互差 | 中位数 | low |
| 2 源 | <5% | 主源 | medium |
| 2 源 | 5%-20% | 主源，warning | medium |
| 2 源 | >20%，有 adapter | 官网（adapter 最权威） | medium |
| 2 源 | >20%，无 adapter | 主源，warning | low |
| 1 源 | — | 该源 | low |
| 0 源 | — | 跳过（run_daily 回退旧数据） | — |

**特殊规则**：
- LiteLLM 价格 = 0：源层已过滤（视为缺失）
- Scraper 失败：不影响 L1/L2 仲裁
- `context_window` 取众数
- `modalities` 取并集
- `release_date` 优先级：openrouter > adapter > litellm
- `purchase_url` 优先级：adapter > litellm > openrouter
- `notes`（能力元数据）优先取 OpenRouter 的

详细设计见 [note/reconcile.md](file:///Users/shareit/personal/llm-price-compare/note/reconcile.md)。

---

## 六、波动检测（validate.py）

**文件**：[scripts/core/validate.py](file:///Users/shareit/personal/llm-price-compare/scripts/core/validate.py#L83-L138)

**输入**：上次 `prices.json` 中该 provider 的产品 + 本次 reconcile 后的新产品。

**对比字段**：`input` / `output` / `cached_input` / `monthly_price`

**规则**：
- 同 `product_id` 对比
- 货币不一致时跳过（CNY vs USD 会产生假阳性阻塞）
- 单字段变化 >20%：加入 `warnings`
- 所有字段最大变化 >50%：`should_block = true`

**阻断处理**（run_daily.py Step 2）：
```python
if volatility.should_block:
    # 保留上次成功数据
    new_providers.append(old_provider)
    # status 标记 failed + stale
    # 飞书告警
    continue
```

---

## 七、失败处理与回退

### 单源失败
- L1/L2 单源失败：`fetch_all_sources()` 捕获异常，该源值为 `{}`，不阻塞其他源
- L3 adapter 失败：Step 2 捕获异常，保留旧 provider 数据，标记 `stale=true`

### Provider 级失败
- 抓取失败：保留上次成功数据，`stale=true`，飞书告警
- 波动阻断：保留上次成功数据，`stale=true`，飞书告警
- Manual 兜底：sources 双源都空或 reconcile 返回 0 产品时，使用 manual 全量数据

### 全局失败
- `validate_global()` 失败：**不落盘**，保留旧 prices.json，发送 fatal 飞书告警
- `consecutive_failures` 累加，可在 run_status.json 监控

### 前端可见性
- 每家厂商独立 `provider_status`，前端展示「正常」/「数据过期」/「抓取失败」
- 单条产品 `stale=true` 时详情区显示「数据来自 X 小时前，可能过期」

---

## 八、部署架构

### 8.1 Scraper 服务（用户自有服务器）

**Docker Compose**：[docker-compose.yml](file:///Users/shareit/personal/llm-price-compare/docker-compose.yml)

```yaml
services:
  scraper:
    build: .
    container_name: llm-price-scraper
    restart: unless-stopped
    environment:
      - TZ=Asia/Shanghai
      - FEISHU_WEBHOOK_URL=${FEISHU_WEBHOOK_URL:-}
      - GIT_USER_NAME=${GIT_USER_NAME:-llm-price-bot}
      - GIT_USER_EMAIL=${GIT_USER_EMAIL:-bot@llm-price-compare}
      - GIT_REMOTE_URL=${GIT_REMOTE_URL:-}
    volumes:
      - ./logs:/var/log/llm-price
```

**容器内 cron**（[Dockerfile](file:///Users/shareit/personal/llm-price-compare/Dockerfile#L24-L28)）：
```
0 11 * * * cd /app && /usr/local/bin/python3 scripts/run_daily.py >> /var/log/llm-price/cron.log 2>&1
```

**入口脚本**：[entrypoint.sh](file:///Users/shareit/personal/llm-price-compare/entrypoint.sh)
- 容器首次启动时若 `.git` 不存在，从 `GIT_REMOTE_URL` 拉取初始化
- 支持 `docker exec llm-price-scraper run` 手动触发一次抓取
- 默认启动 cron 守护

**为什么用用户自有服务器**：GitHub Actions cron 有显著延迟（实测 10-30 分钟），且无法稳定访问部分国内厂商官网。用户服务器部署 Docker 后 cron 精准触发。

### 8.2 Web 服务（GitHub Pages 静态部署）

**Workflow**：[.github/workflows/deploy.yml](file:///Users/shareit/personal/llm-price-compare/.github/workflows/deploy.yml)

**触发条件**：push 到 master 分支且改动 `ui/**` 或 `data/prices.json`

**构建过程**：
1. checkout 代码
2. `ui/` 目录作为站点根
3. 复制 `data/prices.json` 到 `_site/data/`
4. 上传 artifact，部署到 GitHub Pages

**前端**：[ui/](file:///Users/shareit/personal/llm-price-compare/ui/) Vue 3 CDN，无构建步骤
- `index.html` 入口
- `app.js` Vue 应用（fetch `data/prices.json` 渲染）
- `style.css` 样式
- `icons/` 厂商图标

### 8.3 数据流闭环

```
用户服务器 cron (11:00)
    ↓
Docker scraper 容器执行 run_daily.py
    ↓
生成 data/prices.json + git commit
    ↓
git push 到 GitHub master 分支
    ↓
GitHub Actions 触发 deploy.yml
    ↓
GitHub Pages 重新部署静态站点
    ↓
用户访问网站看到最新价格
```

---

## 九、目录索引

```
llm-price-compare/
├── data/
│   ├── prices.json              # 主数据契约（前端唯一数据源）
│   ├── run_status.json          # cron 运行状态
│   └── manual/                  # 人工补充 yaml
│       ├── anthropic.yaml       # 订阅制（Claude Pro/Max）
│       ├── cursor.yaml          # 订阅制
│       ├── githubcopilot.yaml   # 订阅制
│       ├── google.yaml          # per_token 兜底
│       ├── minimax.yaml         # coding_plan
│       ├── moonshot.yaml        # per_token + coding_plan
│       ├── openai.yaml          # 订阅制（ChatGPT Plus/Pro）
│       ├── opencode.yaml        # coding_plan
│       ├── qwen.yaml            # per_token + coding_plan
│       ├── volcengine.yaml      # per_token + coding_plan
│       ├── xiaomi.yaml          # coding_plan
│       └── zhipu.yaml           # per_token + coding_plan
├── scripts/
│   ├── run_daily.py             # 每日抓取入口
│   ├── adapters/                # L3 官网 Scraper
│   │   ├── __init__.py          # 注册 OpenAI/Anthropic/DeepSeek
│   │   ├── base.py              # BaseAdapter 抽象类
│   │   ├── openai.py
│   │   ├── anthropic.py
│   │   └── deepseek.py
│   ├── sources/                 # L1 + L2 外部数据源
│   │   ├── __init__.py          # fetch_all_sources()
│   │   ├── base.py
│   │   ├── litellm.py           # L1 主源
│   │   └── openrouter.py        # L2 交叉源
│   └── core/
│       ├── manual.py            # manual yaml 加载
│       ├── reconcile.py         # 三源仲裁
│       ├── validate.py          # 字段校验 + 波动检测
│       ├── fetcher.py           # HTTP / Playwright 抓取工具
│       ├── status.py            # run_status.json 维护
│       ├── alert.py             # 飞书告警
│       └── models.py            # Product/Provider/ProviderStatus 数据类
├── ui/                          # Vue 3 前端（静态）
│   ├── index.html
│   ├── app.js
│   ├── style.css
│   └── icons/
├── note/                        # 设计文档
│   ├── data-pipeline.md         # 本文档
│   ├── reconcile.md             # 三源仲裁详细设计
│   ├── design.md
│   ├── plan.md
│   └── session-log.md
├── .github/workflows/
│   ├── deploy.yml               # GitHub Pages 部署
│   └── deploy-to-server.yml
├── Dockerfile                   # scraper 容器（cron + Playwright）
├── docker-compose.yml           # scraper + web 服务
├── entrypoint.sh                # 容器入口（git init + cron 守护）
└── requirements.txt
```

---

## 十、添加新厂商 Checklist

1. **判断数据来源**：
   - 官网有结构化定价页且稳定 → 写 adapter 放 `scripts/adapters/`，注册到 `__init__.py`
   - 页面不稳定/需登录 → 写 manual yaml 放 `data/manual/`

2. **manual yaml 模板**：
   ```yaml
   id: newprovider
   name: 新厂商
   name_en: NewProvider
   region: cn
   website: https://...
   pricing_url: https://...
   products:
     - id: model-name-token
       model: Model Name
       billing_type: per_token
       context_window: 128000
       modalities: [text]
       prices:
         input: 1.0
         output: 2.0
         currency: CNY
         unit: per_1m_tokens
       purchase_url: https://...
   ```

3. **前端配置**（[ui/app.js](file:///Users/shareit/personal/llm-price-compare/ui/app.js)）：
   - `ICON_FILES` 添加图标文件名映射
   - `PROVIDER_COLORS` 添加品牌色（图标加载失败兜底）
   - `PROVIDER_META` 添加厂商元数据（name/name_en/region）
   - 把图标 svg/png 放到 `ui/icons/`

4. **若 sources 已覆盖**：确认 [litellm.py](file:///Users/shareit/personal/llm-price-compare/scripts/sources/litellm.py) 或 [openrouter.py](file:///Users/shareit/personal/llm-price-compare/scripts/sources/openrouter.py) 的 `PROVIDER_MAP` 包含该厂商；若没有，手动添加映射

5. **验证**：
   - 本地 `python3 scripts/run_daily.py` 手动跑一次
   - 检查 `data/prices.json` 是否含新厂商
   - 前端 `python3 -m http.server 8010 --directory ui` 验证渲染
