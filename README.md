# PPK · Price Per Token

> 选大模型，从定价开始。

聚合 OpenAI、Anthropic、Google、AWS、DeepSeek、Kimi、阿里通义、MiniMax、小米、火山引擎、智谱、OpenCode 等 12 家主流厂商的 LLM 计费数据，覆盖按需计费（per-token）、订阅制、Coding Plan 三种模式。每日 11:00（北京时间）自动抓取，三源交叉验证。

- 线上：http://129.226.94.179:8001/ui/
- GitHub Pages：https://hangliuc.github.io/llm-price-compare/

## 特性

- **三源交叉验证**：LiteLLM JSON（L1）+ OpenRouter API（L2）+ 官网 Scraper（L3），按 product_id 对齐做价格仲裁，输出 confidence 标签
- **12 家厂商、500+ 产品**：含国内/国外主流大模型 API、订阅、Coding 套餐
- **失败可见性**：抓取失败时双通道告警（网页 stale 标记 + 飞书 webhook），数据回退至上次成功版本
- **价格波动保护**：单字段波动 >20% 警告、>50% 阻断落盘
- **静态前端**：Vue 3 CDN 引入，无 build step，GitHub Pages / Nginx 直发
- **可扩展**：新增厂商 = 写一个 adapter 或 manual yaml + 注册一行

## 技术栈

| 层 | 选型 |
|---|---|
| 抓取 | Python 3.11 + requests + BeautifulSoup4 + Playwright |
| 仲裁 | 自研 reconcile.py（5%/20% 阈值投票） |
| 前端 | Vue 3（CDN）+ 原生 CSS，无构建 |
| 部署 | Docker Compose（scraper + nginx），cron 调度 |
| CI | GitHub Actions（test + deploy-pages + deploy-to-server） |
| 告警 | 飞书 webhook |

## 架构

```
┌──────────────────────────────────────────────────────────────┐
│  数据源层                                                     │
│  L1: LiteLLM JSON  ──┐                                       │
│  L2: OpenRouter API ─┼──> 仲裁层 (reconcile.py)              │
│  L3: 官网 Scraper   ─┘       │                               │
│  L4: manual yaml ────────────┤（未覆盖厂商兜底）             │
└──────────────────────────────┼───────────────────────────────┘
                               ▼
                    波动检测 (validate.py)
                    20% 警告 / 50% 阻断
                               │
                               ▼
                    data/prices.json  ──git push──>  GitHub
                               │                       │
                               │                       ├──> GitHub Pages
                               ▼                       └──> 服务器 docker pull
                    前端 fetch 消费                         │
                                                            ▼
                                                  Nginx 容器 (8001)
```

## 目录结构

```
llm-price-compare/
├── scripts/
│   ├── sources/               # 外部数据源采集层
│   │   ├── litellm.py         # L1: LiteLLM JSON
│   │   └── openrouter.py      # L2: OpenRouter API
│   ├── adapters/              # 官网 Scraper (L3)
│   │   ├── openai.py
│   │   ├── anthropic.py
│   │   └── deepseek.py
│   ├── core/
│   │   ├── reconcile.py       # 三源仲裁
│   │   ├── validate.py        # 波动检测 + 全局校验
│   │   ├── alert.py           # 飞书告警
│   │   ├── manual.py          # YAML 加载
│   │   ├── status.py          # run_status.json
│   │   ├── fetcher.py         # HTTP/browser 封装
│   │   └── models.py          # Product/Provider 数据模型
│   ├── run_daily.py           # cron 入口
│   └── tests/                 # pytest 单测
├── data/
│   ├── prices.json            # 数据契约（每日 commit）
│   ├── run_status.json        # 本地运行状态（不 commit）
│   └── manual/                # 人工补充数据
│       ├── google.yaml
│       ├── moonshot.yaml
│       ├── opencode.yaml
│       ├── qwen.yaml
│       ├── volcengine.yaml
│       └── zhipu.yaml
├── ui/
│   ├── index.html             # Vue 3 SPA 入口
│   ├── app.js                 # 路由 + 数据 + 交互
│   ├── style.css
│   └── icons/                 # 12 家厂商 logo + 站点 logo
├── .github/
│   ├── workflows/
│   │   ├── test.yml           # CI 测试（跳过 browser）
│   │   ├── deploy.yml         # GitHub Pages 部署
│   │   └── deploy-to-server.yml  # SSH 触发服务器 docker 重建
│   └── ISSUE_TEMPLATE/        # 反馈模板
├── note/
│   ├── design.md              # 原始设计文档
│   ├── reconcile.md           # 三源仲裁设计（含 mermaid）
│   └── plan.md
├── Dockerfile
├── docker-compose.yml         # scraper + nginx 两个服务
├── entrypoint.sh              # 容器入口（cron 守护 / 手动 run）
├── DEPLOY.md                  # 详细部署指南
└── requirements.txt
```

## 快速开始

### 1. 本地运行测试

```bash
pip install -r requirements.txt
playwright install chromium   # 可选，仅 browser 适配器需要
pytest scripts/ -v -m "not browser"
```

### 2. 本地预览前端

```bash
python3 -m http.server 8000
# 打开 http://localhost:8000/ui/
```

### 3. 手动跑一次抓取

```bash
python3 scripts/run_daily.py
# 查看 results
cat data/prices.json | python3 -m json.tool | head -30
cat data/run_status.json
```

> 真实厂商抓取可能因页面改版/反爬失败，属正常现象。manual 厂商数据一定会加载。

## 部署

详见 [DEPLOY.md](DEPLOY.md)。简要：

1. **服务器**：`git clone` 仓库 → `cp .env.example .env` 填配置 → `docker compose up -d --build`
2. **GitHub Secrets**：配置 `SERVER_HOST` / `SERVER_USER` / `SERVER_SSH_KEY`，master 分支 push 时自动 SSH 到服务器执行 `git pull && docker compose up -d --build`
3. **GitHub Pages**：仓库 Settings → Pages → Source 选 `GitHub Actions`，`ui/` 或 `data/prices.json` 变更时自动部署

`.env` 关键变量：

```env
FEISHU_WEBHOOK_URL=               # 飞书告警 webhook（可选）
GIT_REMOTE_URL=https://<token>@github.com/hangliuc/llm-price-compare.git
GIT_USER_NAME=llm-price-bot
GIT_USER_EMAIL=bot@llm-price-compare
```

## 三源仲裁规则

| 场景 | 仲裁策略 | confidence |
|---|---|---|
| 3 源都有，价差 <5% | 采信主源 L1 | high |
| 3 源都有，1 源偏离 >20% | 采信另两源均值 | medium + warning |
| 3 源互差 >20% 无一致对 | 采信中位数 | low + warning |
| 2 源都有，价差 <5% | 采信主源 | medium |
| 2 源都有，价差 >20% 有官网 | 采信官网 L3 | medium + warning |
| 1 源 | 采信该源 | low |
| 0 源 | 跳过，回退 manual | — |

优先级：`litellm > adapter > openrouter`（采信主源时）；`adapter > litellm > openrouter`（purchase_url）。

详细设计见 [note/reconcile.md](note/reconcile.md)。

## 数据契约

`data/prices.json` 是抓取层、manual 层、前端三方的唯一契约：

```json
{
  "generated_at": "2026-07-13T11:00:00+08:00",
  "providers": [
    {
      "id": "openai",
      "name": "OpenAI",
      "name_en": "OpenAI",
      "region": "us",
      "website": "https://openai.com",
      "pricing_url": "https://openai.com/api/pricing",
      "products": [
        {
          "id": "gpt-4o-token",
          "model": "gpt-4o",
          "billing_type": "per_token",
          "context_window": 128000,
          "modalities": ["text", "vision"],
          "release_date": "2024-05-13",
          "prices": {
            "input": 2.5,
            "output": 10,
            "cached_input": 1.25,
            "currency": "USD",
            "unit": "per_1m_tokens"
          },
          "purchase_url": "https://platform.openai.com",
          "notes": null
        }
      ]
    }
  ],
  "provider_status": [
    {
      "provider_id": "openai",
      "status": "ok",
      "last_success_at": "2026-07-13T11:00:00+08:00",
      "stale": false,
      "warnings": [],
      "confidence": "high",
      "sources": ["litellm", "openrouter", "adapter"]
    }
  ]
}
```

三种 `billing_type`：

| 类型 | prices 必填字段 | 示例 |
|---|---|---|
| `per_token` | input / output / currency / unit | OpenAI/Anthropic/DeepSeek API |
| `subscription` | monthly_price / currency | ChatGPT Plus / Claude Pro |
| `coding_plan` | monthly_price / currency / included_quota / quota_unit | 智谱 / 火山 / OpenCode |

## 厂商覆盖

| 厂商 | provider_id | LiteLLM | OpenRouter | Scraper | manual |
|---|---|---|---|---|---|
| OpenAI | openai | ✅ | ✅ | ✅ | — |
| Anthropic | anthropic | ✅ | ✅ | ✅ | — |
| Google | google | ✅ | ✅ | — | ✅ |
| AWS | aws | ✅ | — | — | — |
| DeepSeek | deepseek | ✅ | ✅ | ✅ | — |
| Kimi (Moonshot) | moonshot | ✅ | ✅ | — | ✅ |
| 阿里通义 | qwen | ✅ | ✅ | — | ✅ |
| MiniMax | minimax | ✅ | ✅ | — | — |
| 小米 | xiaomi | — | ✅ | — | — |
| 火山引擎 | volcengine | ⚠️ 价格 0 | — | — | ✅ |
| 智谱 | zhipu | — | — | — | ✅ |
| OpenCode | opencode | — | — | — | ✅ |

## 反馈

- 报告价格异常 / 建议新增厂商：[GitHub Issues](https://github.com/hangliuc/llm-price-compare/issues/new/choose)，提供预填模板
- 页脚「反馈」按钮会带上下文（厂商、模型）自动跳转

## 设计文档

- [note/design.md](note/design.md) — 原始 MVP 设计
- [note/reconcile.md](note/reconcile.md) — 三源交叉验证仲裁设计（含 mermaid 流程图）
- [DEPLOY.md](DEPLOY.md) — 详细部署指南

## License

MIT
