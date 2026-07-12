# LLM 价格比价网站 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现一个每日自动抓取 10 家 LLM 厂商定价、静态部署到 GitHub Pages 的比价网站。

**Architecture:** Python 适配器每日 cron 抓取厂商定价页 → 校验/波动检测 → 写 `data/prices.json` → git push 触发 GitHub Pages 重建 → Vue 3 CDN SPA 消费 JSON。失败隔离 + 飞书告警 + 网页 stale 标记。

**Tech Stack:** Python 3.11 (requests, beautifulsoup4, playwright, pyyaml, pytest), Vue 3 (CDN 引入，无 build step), GitHub Actions, GitHub Pages。

## Global Constraints

- Python 版本：3.11+
- 前端：Vue 3 CDN 引入，无 build step，无 npm 依赖
- 数据契约：单一 `data/prices.json`，schema 见 spec 第 4 节
- 厂商范围：6 家适配器（OpenAI、Anthropic、智谱、火山引擎、DeepSeek、OpenCode）+ 4 家 manual（Google、Mistral、阿里通义、月之暗面）
- 更新频率：每日 11:00 北京时间（自建服务器 cron）
- 波动阈值：>20% 警告，>50% 阻断
- 反爬：遇 403/验证码立即标记失败，不重试不破解
- 请求头：`User-Agent: LLM-Price-Bot/1.0 (+https://github.com/<user>/llm-price-compare)`
- 货币：CNY/USD，MVP 硬编码汇率
- 项目根目录：`/Users/shareit/personal/llm-price-compare/`

---

## File Structure

```
llm-price-compare/
├── scripts/
│   ├── adapters/
│   │   ├── __init__.py          # ADAPTERS 注册表
│   │   ├── base.py              # BaseAdapter 抽象基类
│   │   ├── openai.py            # OpenAIAdapter
│   │   ├── anthropic.py         # AnthropicAdapter
│   │   ├── zhipu.py             # ZhipuAdapter
│   │   ├── volcengine.py        # VolcengineAdapter
│   │   ├── deepseek.py          # DeepSeekAdapter
│   │   ├── opencode.py          # OpenCodeAdapter
│   │   └── tests/
│   │       ├── __init__.py
│   │       ├── conftest.py              # mock_http fixture
│   │       ├── test_deepseek.py
│   │       ├── test_openai.py
│   │       ├── test_anthropic.py
│   │       ├── test_opencode.py
│   │       ├── test_zhipu.py            # @pytest.mark.browser
│   │       ├── test_volcengine.py       # @pytest.mark.browser
│   │       └── fixtures/
│   │           ├── deepseek_pricing.html
│   │           ├── deepseek_expected.json
│   │           ├── openai_pricing.html
│   │           ├── openai_expected.json
│   │           ├── anthropic_pricing.html
│   │           ├── anthropic_expected.json
│   │           ├── opencode_pricing.html
│   │           └── opencode_expected.json
│   ├── core/
│   │   ├── __init__.py
│   │   ├── fetcher.py           # HTTP/browser 抓取封装
│   │   ├── models.py            # Product/Provider dataclass
│   │   ├── validate.py          # 字段校验 + 波动检测
│   │   ├── manual.py            # YAML 加载
│   │   ├── alert.py             # 飞书 webhook
│   │   └── status.py            # run_status.json 读写
│   ├── run_daily.py             # cron 入口
│   └── tests/
│       ├── __init__.py
│       ├── test_validate.py
│       ├── test_manual.py
│       ├── test_alert.py
│       └── test_run_daily.py
├── data/
│   ├── prices.json              # 抓取产物（commit 回仓库）
│   ├── run_status.json          # 本地状态（.gitignore）
│   └── manual/
│       ├── google.yaml
│       ├── mistral.yaml
│       ├── qwen.yaml
│       └── moonshot.yaml
├── ui/
│   ├── index.html
│   ├── app.js
│   └── style.css
├── .github/
│   ├── workflows/
│   │   ├── test.yml
│   │   └── deploy.yml
│   └── ISSUE_TEMPLATE/
│       ├── price-report.yml
│       └── new-provider.yml
├── .gitignore
├── requirements.txt
├── pytest.ini
└── README.md
```

**职责说明**：
- `core/models.py`：纯数据结构，无 IO
- `core/validate.py`：纯函数校验逻辑，无 IO
- `core/fetcher.py`：HTTP/browser 抓取封装，被 adapters 复用
- `adapters/*.py`：每家厂商一个，只负责「抓 + 转 Product」
- `run_daily.py`：编排，无业务逻辑
- `core/manual.py`、`core/alert.py`、`core/status.py`：独立 IO 模块，单一职责

---

## Phase 1: 项目骨架与数据模型

### Task 1: 初始化项目结构

**Files:**
- Create: `llm-price-compare/` 目录树
- Create: `llm-price-compare/requirements.txt`
- Create: `llm-price-compare/.gitignore`
- Create: `llm-price-compare/pytest.ini`
- Create: `llm-price-compare/README.md`
- Create: `llm-price-compare/data/prices.json` (空骨架)
- Create: `llm-price-compare/scripts/__init__.py`
- Create: `llm-price-compare/scripts/adapters/__init__.py`
- Create: `llm-price-compare/scripts/adapters/tests/__init__.py`
- Create: `llm-price-compare/scripts/core/__init__.py`
- Create: `llm-price-compare/scripts/tests/__init__.py`

**Interfaces:**
- Produces: 项目目录结构 + 依赖清单 + git 仓库

- [ ] **Step 1: 创建目录树**

```bash
cd /Users/shareit/personal
mkdir -p llm-price-compare/{scripts/{adapters/{tests,fixtures},core,tests},data/manual,ui,.github/{workflows,ISSUE_TEMPLATE}}
cd llm-price-compare
touch scripts/__init__.py scripts/adapters/__init__.py scripts/adapters/tests/__init__.py scripts/core/__init__.py scripts/tests/__init__.py
```

- [ ] **Step 2: 写 requirements.txt**

```
# scripts/core/fetcher.py
requests>=2.31.0
beautifulsoup4>=4.12.0

# scripts/adapters/zhipu.py, volcengine.py (headless browser)
playwright>=1.40.0

# scripts/core/manual.py
pyyaml>=6.0

# 测试
pytest>=7.4.0
pytest-mock>=3.12.0
responses>=0.24.0
```

- [ ] **Step 3: 写 .gitignore**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
data/run_status.json
/var/log/llm-price/
playwright.cfg
```

- [ ] **Step 4: 写 pytest.ini**

```ini
[pytest]
testpaths = scripts
markers =
    browser: marks tests requiring headless browser (deselect with '-m "not browser"')
addopts = -m "not browser"
```

- [ ] **Step 5: 写 data/prices.json 空骨架**

```json
{
  "generated_at": null,
  "providers": [],
  "provider_status": []
}
```

- [ ] **Step 6: 写 README.md（最小骨架）**

```markdown
# LLM 价格比价网站

每日抓取主流大模型厂商定价，提供比价与搜索。

## 开发

```bash
pip install -r requirements.txt
playwright install chromium
pytest scripts/
```

## 部署

详见 `docs/superpowers/specs/2026-07-12-llm-price-compare-design.md`。
```

- [ ] **Step 7: 初始化 git 并首次提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git init
git add .
git commit -m "chore: initialize project structure"
```

---

### Task 2: 数据模型 (core/models.py)

**Files:**
- Create: `llm-price-compare/scripts/core/models.py`
- Test: `llm-price-compare/scripts/tests/test_models.py`

**Interfaces:**
- Produces: `Product`, `Provider`, `ProviderStatus` dataclass；`BillingType` 枚举；函数 `product_to_dict(p: Product) -> dict`、`provider_to_dict(p: Provider) -> dict`

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_models.py
from scripts.core.models import (
    Product, Provider, BillingType, product_to_dict, provider_to_dict
)

def test_product_per_token_to_dict():
    p = Product(
        id="gpt-4o-token",
        model="GPT-4o",
        billing_type=BillingType.PER_TOKEN,
        context_window=128000,
        modalities=["text", "vision"],
        prices={"input": 2.5, "output": 10, "currency": "USD", "unit": "per_1m_tokens"},
        purchase_url="https://openai.com/api/pricing/",
    )
    d = product_to_dict(p)
    assert d["id"] == "gpt-4o-token"
    assert d["billing_type"] == "per_token"
    assert d["prices"]["input"] == 2.5
    assert d["purchase_url"].startswith("https://")

def test_product_coding_plan_to_dict():
    p = Product(
        id="zhipu-coding-plan",
        model=None,
        billing_type=BillingType.CODING_PLAN,
        context_window=None,
        modalities=[],
        prices={
            "monthly_price": 99,
            "currency": "CNY",
            "included_quota": 500,
            "quota_unit": "次",
            "features": ["GLM-4.5"]
        },
        purchase_url="https://open.bigmodel.cn/pricing",
    )
    d = product_to_dict(p)
    assert d["model"] is None
    assert d["billing_type"] == "coding_plan"
    assert d["prices"]["monthly_price"] == 99

def test_provider_to_dict():
    p = Provider(
        id="openai",
        name="OpenAI",
        name_en="OpenAI",
        region="us",
        website="https://openai.com/",
        pricing_url="https://openai.com/api/pricing/",
        products=[],
    )
    d = provider_to_dict(p)
    assert d["id"] == "openai"
    assert d["region"] == "us"
    assert d["products"] == []
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.core.models'`

- [ ] **Step 3: 实现 models.py**

```python
# scripts/core/models.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BillingType(str, Enum):
    PER_TOKEN = "per_token"
    SUBSCRIPTION = "subscription"
    CODING_PLAN = "coding_plan"


@dataclass
class Product:
    id: str
    billing_type: BillingType
    prices: dict
    purchase_url: str
    model: Optional[str] = None
    context_window: Optional[int] = None
    modalities: list = field(default_factory=list)
    release_date: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Provider:
    id: str
    name: str
    name_en: str
    region: str
    website: str
    pricing_url: str
    products: list = field(default_factory=list)


@dataclass
class ProviderStatus:
    provider_id: str
    status: str  # "ok" | "failed" | "no_data"
    last_success_at: Optional[str] = None
    error: Optional[str] = None
    stale: bool = False
    warnings: list = field(default_factory=list)


def product_to_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "model": p.model,
        "billing_type": p.billing_type.value,
        "context_window": p.context_window,
        "modalities": p.modalities,
        "release_date": p.release_date,
        "prices": p.prices,
        "purchase_url": p.purchase_url,
        "notes": p.notes,
    }


def provider_to_dict(p: Provider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "name_en": p.name_en,
        "region": p.region,
        "website": p.website,
        "pricing_url": p.pricing_url,
        "products": [product_to_dict(prod) for prod in p.products],
    }


def provider_status_to_dict(s: ProviderStatus) -> dict:
    return {
        "provider_id": s.provider_id,
        "status": s.status,
        "last_success_at": s.last_success_at,
        "error": s.error,
        "stale": s.stale,
        "warnings": s.warnings,
    }
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_models.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/models.py scripts/tests/test_models.py
git commit -m "feat: add data models for Product/Provider/ProviderStatus"
```

---

### Task 3: 数据校验逻辑 (core/validate.py)

**Files:**
- Create: `llm-price-compare/scripts/core/validate.py`
- Test: `llm-price-compare/scripts/tests/test_validate.py`

**Interfaces:**
- Consumes: `Product`, `BillingType` from `scripts.core.models`
- Produces: `ValidationError` 异常；函数 `validate_product(p: Product) -> None`、`validate_provider(p: Provider) -> None`、`validate_global(data: dict) -> bool`

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_validate.py
import pytest
from scripts.core.models import Product, Provider, BillingType
from scripts.core.validate import validate_product, ValidationError


def _make_per_token_product(**overrides):
    base = dict(
        id="gpt-4o",
        billing_type=BillingType.PER_TOKEN,
        prices={"input": 2.5, "output": 10, "currency": "USD", "unit": "per_1m_tokens"},
        purchase_url="https://openai.com/",
    )
    base.update(overrides)
    return Product(**base)


def test_validate_product_per_token_ok():
    p = _make_per_token_product()
    validate_product(p)  # 不抛异常即通过


def test_validate_product_missing_id():
    p = _make_per_token_product(id="")
    with pytest.raises(ValidationError, match="id"):
        validate_product(p)


def test_validate_product_missing_input():
    p = _make_per_token_product(prices={"output": 10, "currency": "USD", "unit": "per_1m_tokens"})
    with pytest.raises(ValidationError, match="input"):
        validate_product(p)


def test_validate_product_negative_price():
    p = _make_per_token_product(prices={"input": -1, "output": 10, "currency": "USD", "unit": "per_1m_tokens"})
    with pytest.raises(ValidationError, match="non-negative"):
        validate_product(p)


def test_validate_product_missing_purchase_url():
    p = _make_per_token_product(purchase_url="")
    with pytest.raises(ValidationError, match="purchase_url"):
        validate_product(p)


def test_validate_product_coding_plan_missing_quota():
    p = Product(
        id="plan",
        billing_type=BillingType.CODING_PLAN,
        prices={"monthly_price": 99, "currency": "CNY"},
        purchase_url="https://example.com",
    )
    with pytest.raises(ValidationError, match="included_quota"):
        validate_product(p)


def test_validate_product_subscription_ok():
    p = Product(
        id="plus",
        billing_type=BillingType.SUBSCRIPTION,
        prices={"monthly_price": 20, "currency": "USD"},
        purchase_url="https://example.com",
    )
    validate_product(p)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: 实现 validate.py**

```python
# scripts/core/validate.py
from scripts.core.models import Product, Provider, BillingType


class ValidationError(Exception):
    pass


_PER_TOKEN_REQUIRED = ["input", "output", "unit"]
_SUBSCRIPTION_REQUIRED = ["monthly_price"]
_CODING_PLAN_REQUIRED = ["monthly_price", "included_quota", "quota_unit"]


def _require(condition: bool, msg: str):
    if not condition:
        raise ValidationError(msg)


def _check_non_negative(prices: dict, fields: list):
    for f in fields:
        if f in prices and prices[f] is not None:
            _require(prices[f] >= 0, f"prices.{f} must be non-negative, got {prices[f]}")


def validate_product(p: Product) -> None:
    _require(bool(p.id), "product.id is required")
    _require(bool(p.purchase_url), f"product.purchase_url is required (product={p.id})")
    _require(p.billing_type in BillingType, f"unknown billing_type: {p.billing_type}")

    prices = p.prices or {}
    _require("currency" in prices, f"prices.currency is required (product={p.id})")

    if p.billing_type == BillingType.PER_TOKEN:
        for f in _PER_TOKEN_REQUIRED:
            _require(f in prices, f"per_token product missing prices.{f} (product={p.id})")
        _check_non_negative(prices, ["input", "output", "cached_input"])
    elif p.billing_type == BillingType.SUBSCRIPTION:
        for f in _SUBSCRIPTION_REQUIRED:
            _require(f in prices, f"subscription product missing prices.{f} (product={p.id})")
        _check_non_negative(prices, ["monthly_price"])
    elif p.billing_type == BillingType.CODING_PLAN:
        for f in _CODING_PLAN_REQUIRED:
            _require(f in prices, f"coding_plan product missing prices.{f} (product={p.id})")
        _check_non_negative(prices, ["monthly_price"])


def validate_provider(p: Provider) -> None:
    _require(bool(p.id), "provider.id is required")
    _require(p.region in ("cn", "us", "eu"), f"invalid region: {p.region}")
    _require(bool(p.website), f"provider.website is required (provider={p.id})")
    _require(bool(p.pricing_url), f"provider.pricing_url is required (provider={p.id})")

    ids = [prod.id for prod in p.products]
    dupes = [x for x in set(ids) if ids.count(x) > 1]
    _require(not dupes, f"duplicate product ids in provider {p.id}: {dupes}")

    for prod in p.products:
        validate_product(prod)


def validate_global(data: dict) -> bool:
    try:
        _require("generated_at" in data, "missing generated_at")
        _require("providers" in data, "missing providers")
        _require("provider_status" in data, "missing provider_status")
        _require(isinstance(data["providers"], list), "providers must be list")
        _require(isinstance(data["provider_status"], list), "provider_status must be list")

        provider_ids = [p["id"] for p in data["providers"]]
        dupes = [x for x in set(provider_ids) if provider_ids.count(x) > 1]
        _require(not dupes, f"duplicate provider ids: {dupes}")

        return True
    except (ValidationError, KeyError, TypeError) as e:
        return False
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_validate.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/validate.py scripts/tests/test_validate.py
git commit -m "feat: add product/provider/global validation logic"
```

---

### Task 4: 波动检测 (core/validate.py 扩展)

**Files:**
- Modify: `llm-price-compare/scripts/core/validate.py`
- Test: `llm-price-compare/scripts/tests/test_validate.py`

**Interfaces:**
- Produces: `VolatilityResult` dataclass；函数 `check_volatility(old_provider: Optional[dict], new_products: list[Product]) -> VolatilityResult`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 scripts/tests/test_validate.py
from scripts.core.validate import check_volatility, VolatilityResult


def _old_provider_with_input(price: float):
    return {
        "id": "x",
        "products": [{
            "id": "p1",
            "billing_type": "per_token",
            "prices": {"input": price, "output": 10, "currency": "USD", "unit": "per_1m_tokens"},
        }]
    }


def test_volatility_none_when_no_old():
    new = [_make_per_token_product(id="p1", prices={"input": 5, "output": 10, "currency": "USD", "unit": "per_1m_tokens"})]
    result = check_volatility(None, new)
    assert result.max_pct == 0.0
    assert result.warnings == []


def test_volatility_within_threshold():
    old = _old_provider_with_input(10.0)
    new = [_make_per_token_product(id="p1", prices={"input": 11.0, "output": 10, "currency": "USD", "unit": "per_1m_tokens"})]
    result = check_volatility(old, new)
    assert result.max_pct == 10.0
    assert result.warnings == []


def test_volatility_warning_band():
    old = _old_provider_with_input(10.0)
    new = [_make_per_token_product(id="p1", prices={"input": 13.0, "output": 10, "currency": "USD", "unit": "per_1m_tokens"})]
    result = check_volatility(old, new)
    assert result.max_pct == 30.0
    assert len(result.warnings) == 1
    assert result.warnings[0]["volatility_pct"] == 30.0


def test_volatility_block_band():
    old = _old_provider_with_input(10.0)
    new = [_make_per_token_product(id="p1", prices={"input": 20.0, "output": 10, "currency": "USD", "unit": "per_1m_tokens"})]
    result = check_volatility(old, new)
    assert result.max_pct == 100.0
    assert result.should_block is True
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_validate.py::test_volatility_none_when_no_old -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 实现波动检测**

```python
# 追加到 scripts/core/validate.py 末尾
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VolatilityResult:
    max_pct: float = 0.0
    should_block: bool = False
    warnings: list = field(default_factory=list)


_PRICE_FIELDS = ["input", "output", "cached_input", "monthly_price"]


def _pct_change(old: float, new: float) -> float:
    if old == 0:
        return 0.0 if new == 0 else 100.0
    return abs((new - old) / old) * 100.0


def check_volatility(old_provider: Optional[dict], new_products: list) -> VolatilityResult:
    result = VolatilityResult()
    if not old_provider:
        return result

    old_by_id = {p["id"]: p for p in old_provider.get("products", [])}

    for new_prod in new_products:
        pid = new_prod.id
        old_prod = old_by_id.get(pid)
        if not old_prod:
            continue

        old_prices = old_prod.get("prices", {})
        new_prices = new_prod.prices

        for f in _PRICE_FIELDS:
            if f in old_prices and f in new_prices:
                pct = _pct_change(float(old_prices[f]), float(new_prices[f]))
                if pct > result.max_pct:
                    result.max_pct = pct
                if pct > 20.0:
                    result.warnings.append({
                        "product_id": pid,
                        "field": f"prices.{f}",
                        "old_value": old_prices[f],
                        "new_value": new_prices[f],
                        "volatility_pct": round(pct, 2),
                    })

    if result.max_pct > 50.0:
        result.should_block = True

    return result
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_validate.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/validate.py scripts/tests/test_validate.py
git commit -m "feat: add price volatility detection with 20%/50% thresholds"
```

---

## Phase 2: 核心抓取层

### Task 5: HTTP Fetcher (core/fetcher.py)

**Files:**
- Create: `llm-price-compare/scripts/core/fetcher.py`
- Test: `llm-price-compare/scripts/tests/test_fetcher.py`

**Interfaces:**
- Produces: 函数 `fetch_html(url: str, timeout: int = 10) -> str`、`fetch_json(url: str, timeout: int = 10) -> dict`、`USER_AGENT` 常量

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_fetcher.py
import pytest
from unittest.mock import patch, MagicMock
from scripts.core.fetcher import fetch_html, fetch_json, USER_AGENT


@patch("scripts.core.fetcher.requests.get")
def test_fetch_html_returns_text(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = "<html>hello</html>"
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    html = fetch_html("https://example.com/pricing")
    assert html == "<html>hello</html>"
    args, kwargs = mock_get.call_args
    assert kwargs["headers"]["User-Agent"] == USER_AGENT
    assert USER_AGENT.startswith("LLM-Price-Bot")


@patch("scripts.core.fetcher.requests.get")
def test_fetch_json_returns_dict(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"key": "value"}
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    data = fetch_json("https://example.com/api")
    assert data == {"key": "value"}


@patch("scripts.core.fetcher.requests.get")
def test_fetch_html_raises_on_403(mock_get):
    import requests
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.raise_for_status.side_effect = requests.HTTPError("403")
    mock_get.return_value = mock_resp

    with pytest.raises(requests.HTTPError):
        fetch_html("https://example.com/forbidden")
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_fetcher.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 实现 fetcher.py**

```python
# scripts/core/fetcher.py
import requests

USER_AGENT = "LLM-Price-Bot/1.0 (+https://github.com/llm-price-compare/llm-price-compare)"

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_html(url: str, timeout: int = 10) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_json(url: str, timeout: int = 10) -> dict:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_fetcher.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/fetcher.py scripts/tests/test_fetcher.py
git commit -m "feat: add HTTP fetcher with transparent User-Agent"
```

---

### Task 6: 适配器基类 (adapters/base.py)

**Files:**
- Create: `llm-price-compare/scripts/adapters/base.py`

**Interfaces:**
- Produces: `BaseAdapter` 抽象基类，子类需实现 `fetch() -> list[Product]`

- [ ] **Step 1: 实现 base.py**

```python
# scripts/adapters/base.py
from abc import ABC, abstractmethod
from scripts.core.models import Product, Provider
from scripts.core.validate import validate_product, ValidationError


class BaseAdapter(ABC):
    provider_id: str = ""
    provider_name: str = ""
    provider_name_en: str = ""
    region: str = ""
    website: str = ""
    pricing_url: str = ""

    @abstractmethod
    def fetch(self) -> list[Product]:
        """抓取并返回该厂商的所有 products。失败抛异常。"""
        raise NotImplementedError

    def validate(self, products: list[Product]) -> list[Product]:
        """通用校验。子类可覆盖加自检断言。"""
        for p in products:
            validate_product(p)
        return products

    def to_provider(self, products: list[Product]) -> Provider:
        return Provider(
            id=self.provider_id,
            name=self.provider_name,
            name_en=self.provider_name_en,
            region=self.region,
            website=self.website,
            pricing_url=self.pricing_url,
            products=products,
        )

    def assert_min_products(self, products: list[Product], minimum: int = 1):
        """适配器自检：抓到的产品数不能太少（防页面改版静默失效）。"""
        if len(products) < minimum:
            raise RuntimeError(
                f"{self.provider_id}: expected >={minimum} products, got {len(products)} "
                f"(page structure may have changed)"
            )
```

- [ ] **Step 2: 写测试**

```python
# scripts/adapters/tests/test_base.py
import pytest
from scripts.adapters.base import BaseAdapter
from scripts.core.models import Product, BillingType
from scripts.core.validate import ValidationError


class DummyAdapter(BaseAdapter):
    provider_id = "dummy"
    provider_name = "Dummy"
    provider_name_en = "Dummy"
    region = "us"
    website = "https://example.com/"
    pricing_url = "https://example.com/pricing"

    def fetch(self):
        return []


def test_to_provider_constructs_provider():
    a = DummyAdapter()
    p = a.to_provider([])
    assert p.id == "dummy"
    assert p.region == "us"


def test_assert_min_products_passes():
    a = DummyAdapter()
    prods = [Product(id=f"p{i}", billing_type=BillingType.PER_TOKEN,
                     prices={"input": 1, "output": 1, "currency": "USD", "unit": "per_1m_tokens"},
                     purchase_url="https://example.com") for i in range(3)]
    a.assert_min_products(prods, minimum=3)


def test_assert_min_products_raises():
    a = DummyAdapter()
    with pytest.raises(RuntimeError, match="page structure"):
        a.assert_min_products([], minimum=1)
```

- [ ] **Step 3: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_base.py -v`
Expected: PASS (3 tests)

- [ ] **Step 4: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/base.py scripts/adapters/tests/test_base.py
git commit -m "feat: add BaseAdapter abstract class with self-check assertion"
```

---

### Task 7: 第一个适配器 DeepSeek (HTTP+HTML)

**Files:**
- Create: `llm-price-compare/scripts/adapters/deepseek.py`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/deepseek_pricing.html`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/deepseek_expected.json`
- Test: `llm-price-compare/scripts/adapters/tests/test_deepseek.py`

**Interfaces:**
- Consumes: `BaseAdapter`, `fetch_html`, `Product`, `BillingType`
- Produces: `DeepSeekAdapter` 类

**说明**：DeepSeek 定价页 https://api-docs.deepseek.com/quick_start/pricing 是静态 HTML，列出 deepseek-chat 和 deepseek-reasoner 的 input/output 价格（USD per 1M tokens）。

- [ ] **Step 1: 创建 fixture HTML（简化样本）**

```html
<!-- scripts/adapters/tests/fixtures/deepseek_pricing.html -->
<html>
<body>
<table class="pricing">
  <tr><th>Model</th><th>Input ($/1M tokens)</th><th>Output ($/1M tokens)</th></tr>
  <tr><td>deepseek-chat</td><td>0.27</td><td>1.10</td></tr>
  <tr><td>deepseek-reasoner</td><td>0.55</td><td>2.19</td></tr>
</table>
</body>
</html>
```

- [ ] **Step 2: 创建 expected JSON**

```json
[
  {
    "id": "deepseek-chat-token",
    "model": "deepseek-chat",
    "billing_type": "per_token",
    "context_window": 64000,
    "modalities": ["text"],
    "prices": {"input": 0.27, "output": 1.10, "currency": "USD", "unit": "per_1m_tokens"},
    "purchase_url": "https://api-docs.deepseek.com/quick_start/pricing"
  },
  {
    "id": "deepseek-reasoner-token",
    "model": "deepseek-reasoner",
    "billing_type": "per_token",
    "context_window": 64000,
    "modalities": ["text"],
    "prices": {"input": 0.55, "output": 2.19, "currency": "USD", "unit": "per_1m_tokens"},
    "purchase_url": "https://api-docs.deepseek.com/quick_start/pricing"
  }
]
```

- [ ] **Step 3: 写失败测试**

```python
# scripts/adapters/tests/test_deepseek.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.deepseek import DeepSeekAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _load_expected(name: str) -> list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@patch("scripts.adapters.deepseek.fetch_html")
def test_deepseek_parses_pricing_table(mock_fetch):
    mock_fetch.return_value = _load_fixture("deepseek_pricing.html")
    adapter = DeepSeekAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    expected = _load_expected("deepseek_expected.json")
    assert len(products) == len(expected)
    for got, want in zip(products, expected):
        assert got.id == want["id"]
        assert got.model == want["model"]
        assert got.billing_type.value == want["billing_type"]
        assert got.prices["input"] == want["prices"]["input"]
        assert got.prices["output"] == want["prices"]["output"]
        assert got.prices["currency"] == want["prices"]["currency"]
```

- [ ] **Step 4: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_deepseek.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 5: 实现 DeepSeekAdapter**

```python
# scripts/adapters/deepseek.py
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing"
_CONTEXT_WINDOW = {
    "deepseek-chat": 64000,
    "deepseek-reasoner": 64000,
}


class DeepSeekAdapter(BaseAdapter):
    provider_id = "deepseek"
    provider_name = "DeepSeek"
    provider_name_en = "DeepSeek"
    region = "cn"
    website = "https://deepseek.com/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_PRICING_URL)
        soup = BeautifulSoup(html, "html.parser")

        products = []
        table = soup.find("table", class_="pricing") or soup.find("table")
        if not table:
            raise RuntimeError("DeepSeek: pricing table not found")

        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            model = cells[0].get_text(strip=True)
            input_price = float(cells[1].get_text(strip=True).lstrip("$"))
            output_price = float(cells[2].get_text(strip=True).lstrip("$"))

            products.append(Product(
                id=f"{model}-token",
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=_CONTEXT_WINDOW.get(model, 64000),
                modalities=["text"],
                prices={
                    "input": input_price,
                    "output": output_price,
                    "currency": "USD",
                    "unit": "per_1m_tokens",
                },
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_deepseek.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/deepseek.py scripts/adapters/tests/test_deepseek.py scripts/adapters/tests/fixtures/deepseek_*
git commit -m "feat: add DeepSeek adapter with fixture test"
```

---

### Task 8: OpenAI 适配器

**Files:**
- Create: `llm-price-compare/scripts/adapters/openai.py`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/openai_pricing.html`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/openai_expected.json`
- Test: `llm-price-compare/scripts/adapters/tests/test_openai.py`

**说明**：OpenAI 定价页 https://openai.com/api/pricing/ 列出 GPT-4o、GPT-4o-mini、o1 等模型的 input/output/cached_input 价格。

- [ ] **Step 1: 创建 fixture HTML（简化样本）**

```html
<!-- scripts/adapters/tests/fixtures/openai_pricing.html -->
<html>
<body>
<div class="pricing-table">
  <div class="model-row" data-model="gpt-4o">
    <span class="name">GPT-4o</span>
    <span class="input">$2.50</span>
    <span class="output">$10.00</span>
    <span class="cached">$1.25</span>
  </div>
  <div class="model-row" data-model="gpt-4o-mini">
    <span class="name">GPT-4o mini</span>
    <span class="input">$0.15</span>
    <span class="output">$0.60</span>
    <span class="cached">$0.075</span>
  </div>
</div>
</body>
</html>
```

- [ ] **Step 2: 创建 expected JSON**

```json
[
  {
    "id": "gpt-4o-token",
    "model": "GPT-4o",
    "billing_type": "per_token",
    "prices": {"input": 2.50, "output": 10.00, "cached_input": 1.25, "currency": "USD", "unit": "per_1m_tokens"},
    "purchase_url": "https://openai.com/api/pricing/"
  },
  {
    "id": "gpt-4o-mini-token",
    "model": "GPT-4o mini",
    "billing_type": "per_token",
    "prices": {"input": 0.15, "output": 0.60, "cached_input": 0.075, "currency": "USD", "unit": "per_1m_tokens"},
    "purchase_url": "https://openai.com/api/pricing/"
  }
]
```

- [ ] **Step 3: 写失败测试**

```python
# scripts/adapters/tests/test_openai.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.openai import OpenAIAdapter

FIXTURES = Path(__file__).parent / "fixtures"


@patch("scripts.adapters.openai.fetch_html")
def test_openai_parses_models(mock_fetch):
    mock_fetch.return_value = (FIXTURES / "openai_pricing.html").read_text(encoding="utf-8")
    adapter = OpenAIAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    expected = json.loads((FIXTURES / "openai_expected.json").read_text(encoding="utf-8"))
    assert len(products) == len(expected)
    for got, want in zip(products, expected):
        assert got.id == want["id"]
        assert got.prices["cached_input"] == want["prices"]["cached_input"]
```

- [ ] **Step 4: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_openai.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 5: 实现 OpenAIAdapter**

```python
# scripts/adapters/openai.py
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://openai.com/api/pricing/"

# 真实页面结构可能变化，这里按 fixture 设计解析逻辑
# 实际实现时需打开 https://openai.com/api/pricing/ 调整选择器
_MODEL_CONTEXT = {
    "GPT-4o": 128000,
    "GPT-4o mini": 128000,
}


def _parse_price(text: str) -> float:
    return float(text.strip().lstrip("$").replace(",", ""))


class OpenAIAdapter(BaseAdapter):
    provider_id = "openai"
    provider_name = "OpenAI"
    provider_name_en = "OpenAI"
    region = "us"
    website = "https://openai.com/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_PRICING_URL)
        soup = BeautifulSoup(html, "html.parser")

        products = []
        rows = soup.select(".model-row")
        for row in rows:
            name_el = row.select_one(".name")
            if not name_el:
                continue
            model = name_el.get_text(strip=True)
            input_el = row.select_one(".input")
            output_el = row.select_one(".output")
            cached_el = row.select_one(".cached")

            if not input_el or not output_el:
                continue

            prices = {
                "input": _parse_price(input_el.get_text()),
                "output": _parse_price(output_el.get_text()),
                "currency": "USD",
                "unit": "per_1m_tokens",
            }
            if cached_el:
                prices["cached_input"] = _parse_price(cached_el.get_text())

            products.append(Product(
                id=f"{model.lower().replace(' ', '-')}-token",
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=_MODEL_CONTEXT.get(model, 128000),
                modalities=["text", "vision"],
                prices=prices,
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_openai.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/openai.py scripts/adapters/tests/test_openai.py scripts/adapters/tests/fixtures/openai_*
git commit -m "feat: add OpenAI adapter with cached_input support"
```

---

### Task 9: Anthropic 适配器 (per_token + subscription)

**Files:**
- Create: `llm-price-compare/scripts/adapters/anthropic.py`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/anthropic_pricing.html`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/anthropic_expected.json`
- Test: `llm-price-compare/scripts/adapters/tests/test_anthropic.py`

**说明**：Anthropic 同时提供 API（per-token）和 Claude Pro 订阅（$20/月），用于验证 `billing_type` 多类型适配器。

- [ ] **Step 1: 创建 fixture HTML**

```html
<!-- scripts/adapters/tests/fixtures/anthropic_pricing.html -->
<html>
<body>
<h2>API Pricing</h2>
<table class="api-pricing">
  <tr><th>Model</th><th>Input</th><th>Output</th></tr>
  <tr><td>Claude 3.5 Sonnet</td><td>$3.00</td><td>$15.00</td></tr>
  <tr><td>Claude 3 Opus</td><td>$15.00</td><td>$75.00</td></tr>
</table>
<h2>Subscription</h2>
<div class="subscription">
  <span class="plan-name">Claude Pro</span>
  <span class="price">$20/month</span>
  <ul class="features"><li>5x more usage</li><li>Priority access</li></ul>
</div>
</body>
</html>
```

- [ ] **Step 2: 创建 expected JSON**

```json
[
  {
    "id": "claude-3-5-sonnet-token",
    "model": "Claude 3.5 Sonnet",
    "billing_type": "per_token",
    "prices": {"input": 3.00, "output": 15.00, "currency": "USD", "unit": "per_1m_tokens"},
    "purchase_url": "https://docs.anthropic.com/en/docs/about-claude/pricing"
  },
  {
    "id": "claude-pro-subscription",
    "model": null,
    "billing_type": "subscription",
    "prices": {"monthly_price": 20, "currency": "USD", "features": ["5x more usage", "Priority access"]},
    "purchase_url": "https://claude.ai/pricing"
  }
]
```

- [ ] **Step 3: 写失败测试**

```python
# scripts/adapters/tests/test_anthropic.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.anthropic import AnthropicAdapter
from scripts.core.models import BillingType

FIXTURES = Path(__file__).parent / "fixtures"


@patch("scripts.adapters.anthropic.fetch_html")
def test_anthropic_parses_api_and_subscription(mock_fetch):
    mock_fetch.return_value = (FIXTURES / "anthropic_pricing.html").read_text(encoding="utf-8")
    adapter = AnthropicAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    # 至少有一个 per_token 和一个 subscription
    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types
    assert BillingType.SUBSCRIPTION in types

    # 找到 subscription，验证 monthly_price
    sub = next(p for p in products if p.billing_type == BillingType.SUBSCRIPTION)
    assert sub.prices["monthly_price"] == 20
    assert "features" in sub.prices
```

- [ ] **Step 4: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_anthropic.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 5: 实现 AnthropicAdapter**

```python
# scripts/adapters/anthropic.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_API_URL = "https://docs.anthropic.com/en/docs/about-claude/pricing"
_SUB_URL = "https://claude.ai/pricing"


def _parse_price(text: str) -> float:
    return float(text.strip().lstrip("$").replace(",", "").replace("/month", ""))


class AnthropicAdapter(BaseAdapter):
    provider_id = "anthropic"
    provider_name = "Anthropic"
    provider_name_en = "Anthropic"
    region = "us"
    website = "https://anthropic.com/"
    pricing_url = _API_URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_API_URL)
        soup = BeautifulSoup(html, "html.parser")
        products = []

        # API pricing table
        api_table = soup.find("table", class_="api-pricing") or soup.find("table")
        if api_table:
            for row in api_table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                model = cells[0].get_text(strip=True)
                products.append(Product(
                    id=f"{model.lower().replace(' ', '-').replace('.', '-')}-token",
                    model=model,
                    billing_type=BillingType.PER_TOKEN,
                    context_window=200000,
                    modalities=["text", "vision"],
                    prices={
                        "input": _parse_price(cells[1].get_text()),
                        "output": _parse_price(cells[2].get_text()),
                        "currency": "USD",
                        "unit": "per_1m_tokens",
                    },
                    purchase_url=_API_URL,
                ))

        # Subscription block
        sub = soup.select_one(".subscription")
        if sub:
            name_el = sub.select_one(".plan-name")
            price_el = sub.select_one(".price")
            features = [li.get_text(strip=True) for li in sub.select(".features li")]
            if name_el and price_el:
                products.append(Product(
                    id=f"{name_el.get_text(strip=True).lower().replace(' ', '-')}-subscription",
                    model=None,
                    billing_type=BillingType.SUBSCRIPTION,
                    prices={
                        "monthly_price": _parse_price(price_el.get_text()),
                        "currency": "USD",
                        "features": features,
                    },
                    purchase_url=_SUB_URL,
                ))

        self.assert_min_products(products, minimum=2)
        return products
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_anthropic.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/anthropic.py scripts/adapters/tests/test_anthropic.py scripts/adapters/tests/fixtures/anthropic_*
git commit -m "feat: add Anthropic adapter (per_token + subscription)"
```

---

### Task 10: OpenCode 适配器 (coding_plan)

**Files:**
- Create: `llm-price-compare/scripts/adapters/opencode.py`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/opencode_pricing.html`
- Create: `llm-price-compare/scripts/adapters/tests/fixtures/opencode_expected.json`
- Test: `llm-price-compare/scripts/adapters/tests/test_opencode.py`

**说明**：OpenCode (https://opencode.ai/zh/go) 是 coding plan，验证 `billing_type: coding_plan` 适配器实现。

- [ ] **Step 1: 创建 fixture HTML**

```html
<!-- scripts/adapters/tests/fixtures/opencode_pricing.html -->
<html>
<body>
<div class="pricing-card">
  <h3 class="plan-name">OpenCode Pro</h3>
  <div class="price">¥99/月</div>
  <div class="quota">包含 500 次调用</div>
  <ul class="features">
    <li>支持 GPT-4o</li>
    <li>支持 Claude 3.5</li>
  </ul>
  <a class="buy-link" href="https://opencode.ai/zh/go/buy">立即购买</a>
</div>
</body>
</html>
```

- [ ] **Step 2: 创建 expected JSON**

```json
[
  {
    "id": "opencode-pro-plan",
    "model": null,
    "billing_type": "coding_plan",
    "prices": {
      "monthly_price": 99,
      "currency": "CNY",
      "included_quota": 500,
      "quota_unit": "次",
      "features": ["支持 GPT-4o", "支持 Claude 3.5"]
    },
    "purchase_url": "https://opencode.ai/zh/go/buy"
  }
]
```

- [ ] **Step 3: 写失败测试**

```python
# scripts/adapters/tests/test_opencode.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.opencode import OpenCodeAdapter
from scripts.core.models import BillingType

FIXTURES = Path(__file__).parent / "fixtures"


@patch("scripts.adapters.opencode.fetch_html")
def test_opencode_parses_coding_plan(mock_fetch):
    mock_fetch.return_value = (FIXTURES / "opencode_pricing.html").read_text(encoding="utf-8")
    adapter = OpenCodeAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=1)

    p = products[0]
    assert p.billing_type == BillingType.CODING_PLAN
    assert p.prices["monthly_price"] == 99
    assert p.prices["currency"] == "CNY"
    assert p.prices["included_quota"] == 500
    assert p.prices["quota_unit"] == "次"
    assert len(p.prices["features"]) == 2
```

- [ ] **Step 4: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_opencode.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 5: 实现 OpenCodeAdapter**

```python
# scripts/adapters/opencode.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_URL = "https://opencode.ai/zh/go"


def _parse_cny(text: str) -> float:
    """解析 '¥99/月' → 99.0"""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


def _parse_quota(text: str) -> tuple:
    """解析 '包含 500 次调用' → (500, '次')"""
    m = re.search(r"(\d+)\s*(次|token|tokens)", text)
    if m:
        return int(m.group(1)), m.group(2)
    return 0, ""


class OpenCodeAdapter(BaseAdapter):
    provider_id = "opencode"
    provider_name = "OpenCode"
    provider_name_en = "OpenCode"
    region = "us"
    website = "https://opencode.ai/"
    pricing_url = _URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_URL)
        soup = BeautifulSoup(html, "html.parser")
        products = []

        cards = soup.select(".pricing-card")
        for card in cards:
            name_el = card.select_one(".plan-name")
            price_el = card.select_one(".price")
            quota_el = card.select_one(".quota")
            buy_el = card.select_one(".buy-link")
            features = [li.get_text(strip=True) for li in card.select(".features li")]

            if not name_el or not price_el:
                continue

            quota, quota_unit = (0, "")
            if quota_el:
                quota, quota_unit = _parse_quota(quota_el.get_text())

            purchase_url = buy_el["href"] if buy_el and buy_el.has_attr("href") else _URL

            products.append(Product(
                id=f"{name_el.get_text(strip=True).lower().replace(' ', '-')}-plan",
                model=None,
                billing_type=BillingType.CODING_PLAN,
                prices={
                    "monthly_price": _parse_cny(price_el.get_text()),
                    "currency": "CNY",
                    "included_quota": quota,
                    "quota_unit": quota_unit,
                    "features": features,
                },
                purchase_url=purchase_url,
            ))

        self.assert_min_products(products, minimum=1)
        return products
```

- [ ] **Step 6: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_opencode.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/opencode.py scripts/adapters/tests/test_opencode.py scripts/adapters/tests/fixtures/opencode_*
git commit -m "feat: add OpenCode adapter (coding_plan billing type)"
```

---

## Phase 3: 浏览器适配器

### Task 11: Browser Fetcher (core/fetcher.py 扩展)

**Files:**
- Modify: `llm-price-compare/scripts/core/fetcher.py`
- Test: `llm-price-compare/scripts/tests/test_fetcher.py`

**Interfaces:**
- Produces: 函数 `fetch_html_browser(url: str, wait_selector: str = None, timeout: int = 15) -> str`

- [ ] **Step 1: 写失败测试（mock playwright）**

```python
# 追加到 scripts/tests/test_fetcher.py
from unittest.mock import patch, MagicMock
from scripts.core.fetcher import fetch_html_browser


@patch("scripts.core.fetcher.sync_playwright")
def test_fetch_html_browser_returns_html(mock_pw):
    # 构造 mock 链：sync_playwright().start().browser.new_page().content()
    mock_context = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_page.content.return_value = "<html>dynamic</html>"
    mock_browser.new_page.return_value = mock_page
    mock_context.chromium.launch.return_value = mock_browser
    mock_pw.return_value.start.return_value = mock_context

    html = fetch_html_browser("https://example.com", wait_selector=".price")
    assert html == "<html>dynamic</html>"
    mock_page.goto.assert_called_once_with("https://example.com")
    mock_page.wait_for_selector.assert_called_once_with(".price", timeout=15000)
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_fetcher.py::test_fetch_html_browser_returns_html -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 扩展 fetcher.py**

```python
# 追加到 scripts/core/fetcher.py
from playwright.sync_api import sync_playwright


def fetch_html_browser(url: str, wait_selector: str = None, timeout: int = 15) -> str:
    """用 headless Chromium 抓取动态渲染的页面。"""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({"User-Agent": USER_AGENT})
        page.goto(url, timeout=timeout * 1000)
        if wait_selector:
            page.wait_for_selector(wait_selector, timeout=timeout * 1000)
        html = page.content()
        browser.close()
        return html
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_fetcher.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/fetcher.py scripts/tests/test_fetcher.py
git commit -m "feat: add headless browser fetcher using playwright"
```

---

### Task 12: 智谱适配器 (per_token + coding_plan)

**Files:**
- Create: `llm-price-compare/scripts/adapters/zhipu.py`
- Test: `llm-price-compare/scripts/adapters/tests/test_zhipu.py`

**说明**：智谱定价页 https://open.bigmodel.cn/pricing 是 JS 动态渲染，需 headless browser。同时包含 per_token 和 coding plan。测试用 `@pytest.mark.browser` 标记，CI 中跳过。

- [ ] **Step 1: 写测试（mock browser）**

```python
# scripts/adapters/tests/test_zhipu.py
import pytest
from unittest.mock import patch
from scripts.adapters.zhipu import ZhipuAdapter
from scripts.core.models import BillingType

_FAKE_HTML = """
<html><body>
<div class="model-list">
  <div class="model-item">
    <span class="name">GLM-4-Plus</span>
    <span class="input">¥0.05</span>
    <span class="output">¥0.05</span>
  </div>
</div>
<div class="plan-list">
  <div class="plan-item">
    <span class="plan-name">智谱 Coding Plan</span>
    <span class="plan-price">¥99/月</span>
    <span class="plan-quota">500 次</span>
  </div>
</div>
</body></html>
"""


@patch("scripts.adapters.zhipu.fetch_html_browser")
def test_zhipu_parses_token_and_plan(mock_fetch):
    mock_fetch.return_value = _FAKE_HTML
    adapter = ZhipuAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types
    assert BillingType.CODING_PLAN in types

    plan = next(p for p in products if p.billing_type == BillingType.CODING_PLAN)
    assert plan.prices["currency"] == "CNY"
    assert plan.prices["included_quota"] == 500


@pytest.mark.browser
def test_zhipu_live_fetch():
    """真实抓取测试，仅本地手动跑，CI 跳过。"""
    adapter = ZhipuAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    assert len(products) >= 2
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_zhipu.py::test_zhipu_parses_token_and_plan -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 实现 ZhipuAdapter**

```python
# scripts/adapters/zhipu.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html_browser
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://open.bigmodel.cn/pricing"


def _parse_cny(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


def _parse_quota(text: str) -> tuple:
    m = re.search(r"(\d+)\s*(次|token)", text)
    return (int(m.group(1)), m.group(2)) if m else (0, "")


class ZhipuAdapter(BaseAdapter):
    provider_id = "zhipu"
    provider_name = "智谱"
    provider_name_en = "Zhipu AI"
    region = "cn"
    website = "https://open.bigmodel.cn/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        html = fetch_html_browser(_PRICING_URL, wait_selector=".model-list, .plan-list")
        soup = BeautifulSoup(html, "html.parser")
        products = []

        # per-token models
        for item in soup.select(".model-item"):
            name_el = item.select_one(".name")
            input_el = item.select_one(".input")
            output_el = item.select_one(".output")
            if not (name_el and input_el and output_el):
                continue
            model = name_el.get_text(strip=True)
            products.append(Product(
                id=f"{model.lower().replace(' ', '-')}-token",
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=128000,
                modalities=["text", "vision"],
                prices={
                    "input": _parse_cny(input_el.get_text()),
                    "output": _parse_cny(output_el.get_text()),
                    "currency": "CNY",
                    "unit": "per_1m_tokens",
                },
                purchase_url=_PRICING_URL,
            ))

        # coding plan
        for item in soup.select(".plan-item"):
            name_el = item.select_one(".plan-name")
            price_el = item.select_one(".plan-price")
            quota_el = item.select_one(".plan-quota")
            if not (name_el and price_el):
                continue
            quota, quota_unit = _parse_quota(quota_el.get_text()) if quota_el else (0, "")
            products.append(Product(
                id=f"{name_el.get_text(strip=True).lower().replace(' ', '-')}-plan",
                model=None,
                billing_type=BillingType.CODING_PLAN,
                prices={
                    "monthly_price": _parse_cny(price_el.get_text()),
                    "currency": "CNY",
                    "included_quota": quota,
                    "quota_unit": quota_unit,
                    "features": [],
                },
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_zhipu.py::test_zhipu_parses_token_and_plan -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/zhipu.py scripts/adapters/tests/test_zhipu.py
git commit -m "feat: add Zhipu adapter (per_token + coding_plan via headless browser)"
```

---

### Task 13: 火山引擎适配器

**Files:**
- Create: `llm-price-compare/scripts/adapters/volcengine.py`
- Test: `llm-price-compare/scripts/adapters/tests/test_volcengine.py`

**说明**：火山引擎 https://www.volcengine.com/product/ark 同样 JS 动态渲染，结构类似智谱。实现模式复用 ZhipuAdapter。

- [ ] **Step 1: 写测试（mock browser）**

```python
# scripts/adapters/tests/test_volcengine.py
import pytest
from unittest.mock import patch
from scripts.adapters.volcengine import VolcengineAdapter
from scripts.core.models import BillingType

_FAKE_HTML = """
<html><body>
<div class="ark-models">
  <div class="model">
    <span class="name">Doubao-pro-32k</span>
    <span class="input">¥0.008</span>
    <span class="output">¥0.02</span>
  </div>
</div>
<div class="ark-plans">
  <div class="plan">
    <span class="plan-name">火山 Coding Plan</span>
    <span class="plan-price">¥199/月</span>
    <span class="plan-quota">1000 次</span>
  </div>
</div>
</body></html>
"""


@patch("scripts.adapters.volcengine.fetch_html_browser")
def test_volcengine_parses_token_and_plan(mock_fetch):
    mock_fetch.return_value = _FAKE_HTML
    adapter = VolcengineAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types
    assert BillingType.CODING_PLAN in types

    plan = next(p for p in products if p.billing_type == BillingType.CODING_PLAN)
    assert plan.prices["monthly_price"] == 199
    assert plan.prices["included_quota"] == 1000


@pytest.mark.browser
def test_volcengine_live_fetch():
    adapter = VolcengineAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    assert len(products) >= 2
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_volcengine.py::test_volcengine_parses_token_and_plan -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 实现 VolcengineAdapter**

```python
# scripts/adapters/volcengine.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html_browser
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://www.volcengine.com/product/ark"


def _parse_cny(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


def _parse_quota(text: str) -> tuple:
    m = re.search(r"(\d+)\s*(次|token)", text)
    return (int(m.group(1)), m.group(2)) if m else (0, "")


class VolcengineAdapter(BaseAdapter):
    provider_id = "volcengine"
    provider_name = "火山引擎"
    provider_name_en = "Volcengine"
    region = "cn"
    website = "https://www.volcengine.com/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        html = fetch_html_browser(_PRICING_URL, wait_selector=".ark-models, .ark-plans")
        soup = BeautifulSoup(html, "html.parser")
        products = []

        for item in soup.select(".model"):
            name_el = item.select_one(".name")
            input_el = item.select_one(".input")
            output_el = item.select_one(".output")
            if not (name_el and input_el and output_el):
                continue
            model = name_el.get_text(strip=True)
            products.append(Product(
                id=f"{model.lower().replace(' ', '-')}-token",
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=32000,
                modalities=["text"],
                prices={
                    "input": _parse_cny(input_el.get_text()),
                    "output": _parse_cny(output_el.get_text()),
                    "currency": "CNY",
                    "unit": "per_1m_tokens",
                },
                purchase_url=_PRICING_URL,
            ))

        for item in soup.select(".plan"):
            name_el = item.select_one(".plan-name")
            price_el = item.select_one(".plan-price")
            quota_el = item.select_one(".plan-quota")
            if not (name_el and price_el):
                continue
            quota, quota_unit = _parse_quota(quota_el.get_text()) if quota_el else (0, "")
            products.append(Product(
                id=f"{name_el.get_text(strip=True).lower().replace(' ', '-')}-plan",
                model=None,
                billing_type=BillingType.CODING_PLAN,
                prices={
                    "monthly_price": _parse_cny(price_el.get_text()),
                    "currency": "CNY",
                    "included_quota": quota,
                    "quota_unit": quota_unit,
                    "features": [],
                },
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/adapters/tests/test_volcengine.py::test_volcengine_parses_token_and_plan -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/volcengine.py scripts/adapters/tests/test_volcengine.py
git commit -m "feat: add Volcengine adapter (per_token + coding_plan)"
```

---

### Task 14: 适配器注册表 (adapters/__init__.py)

**Files:**
- Modify: `llm-price-compare/scripts/adapters/__init__.py`

**Interfaces:**
- Produces: `ADAPTERS` 列表常量

- [ ] **Step 1: 写注册表**

```python
# scripts/adapters/__init__.py
from scripts.adapters.base import BaseAdapter
from scripts.adapters.openai import OpenAIAdapter
from scripts.adapters.anthropic import AnthropicAdapter
from scripts.adapters.deepseek import DeepSeekAdapter
from scripts.adapters.opencode import OpenCodeAdapter
from scripts.adapters.zhipu import ZhipuAdapter
from scripts.adapters.volcengine import VolcengineAdapter

ADAPTERS: list[BaseAdapter] = [
    OpenAIAdapter(),
    AnthropicAdapter(),
    DeepSeekAdapter(),
    OpenCodeAdapter(),
    ZhipuAdapter(),
    VolcengineAdapter(),
]
```

- [ ] **Step 2: 验证导入无误**

Run: `cd /Users/shareit/personal/llm-price-compare && python -c "from scripts.adapters import ADAPTERS; print(len(ADAPTERS))"`
Expected: `6`

- [ ] **Step 3: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/adapters/__init__.py
git commit -m "feat: register all 6 adapters in ADAPTERS list"
```

---

## Phase 4: 调度与告警

### Task 15: Manual YAML 加载器 (core/manual.py)

**Files:**
- Create: `llm-price-compare/scripts/core/manual.py`
- Create: `llm-price-compare/data/manual/google.yaml`
- Create: `llm-price-compare/data/manual/mistral.yaml`
- Create: `llm-price-compare/data/manual/qwen.yaml`
- Create: `llm-price-compare/data/manual/moonshot.yaml`
- Test: `llm-price-compare/scripts/tests/test_manual.py`

**Interfaces:**
- Produces: 函数 `load_manual_providers(dir_path: str) -> list[dict]`

- [ ] **Step 1: 创建 4 个 manual YAML**

```yaml
# data/manual/google.yaml
id: google
name: Google
name_en: Google
region: us
website: https://ai.google.dev/
pricing_url: https://ai.google.dev/pricing
products:
  - id: gemini-1.5-pro-token
    model: Gemini 1.5 Pro
    billing_type: per_token
    context_window: 2000000
    modalities: [text, vision, audio]
    prices:
      input: 1.25
      output: 5.0
      currency: USD
      unit: per_1m_tokens
    purchase_url: https://ai.google.dev/pricing
```

```yaml
# data/manual/mistral.yaml
id: mistral
name: Mistral AI
name_en: Mistral AI
region: eu
website: https://mistral.ai/
pricing_url: https://mistral.ai/pricing
products:
  - id: mistral-large-token
    model: Mistral Large
    billing_type: per_token
    context_window: 128000
    modalities: [text]
    prices:
      input: 2.0
      output: 6.0
      currency: USD
      unit: per_1m_tokens
    purchase_url: https://mistral.ai/pricing
```

```yaml
# data/manual/qwen.yaml
id: qwen
name: 阿里通义
name_en: Alibaba Qwen
region: cn
website: https:// bailian.aliyun.com/
pricing_url: https://help.aliyun.com/zh/model-studio/billing
products:
  - id: qwen-max-token
    model: Qwen-Max
    billing_type: per_token
    context_window: 32000
    modalities: [text]
    prices:
      input: 0.04
      output: 0.12
      currency: CNY
      unit: per_1m_tokens
    purchase_url: https://help.aliyun.com/zh/model-studio/billing
```

```yaml
# data/manual/moonshot.yaml
id: moonshot
name: 月之暗面
name_en: Moonshot AI
region: cn
website: https://platform.moonshot.cn/
pricing_url: https://platform.moonshot.cn/pricing
products:
  - id: moonshot-v1-8k-token
    model: Moonshot-v1-8k
    billing_type: per_token
    context_window: 8000
    modalities: [text]
    prices:
      input: 12.0
      output: 12.0
      currency: CNY
      unit: per_1m_tokens
    purchase_url: https://platform.moonshot.cn/pricing
```

- [ ] **Step 2: 写失败测试**

```python
# scripts/tests/test_manual.py
import tempfile
import os
from pathlib import Path
from scripts.core.manual import load_manual_providers


def test_load_manual_providers_returns_list():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.yaml").write_text("""
id: a
name: A
name_en: A
region: us
website: https://a.com/
pricing_url: https://a.com/p
products:
  - id: a-1
    billing_type: per_token
    prices: {input: 1, output: 2, currency: USD, unit: per_1m_tokens}
    purchase_url: https://a.com/buy
""", encoding="utf-8")
        (Path(d) / "b.yaml").write_text("""
id: b
name: B
name_en: B
region: cn
website: https://b.com/
pricing_url: https://b.com/p
products: []
""", encoding="utf-8")
        providers = load_manual_providers(d)
        assert len(providers) == 2
        ids = [p["id"] for p in providers]
        assert "a" in ids and "b" in ids
        a = next(p for p in providers if p["id"] == "a")
        assert len(a["products"]) == 1
        assert a["products"][0]["prices"]["input"] == 1


def test_load_manual_providers_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        providers = load_manual_providers(d)
        assert providers == []
```

- [ ] **Step 3: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_manual.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 4: 实现 manual.py**

```python
# scripts/core/manual.py
import os
from pathlib import Path
import yaml


def load_manual_providers(dir_path: str) -> list:
    """加载目录下所有 *.yaml 文件，返回 provider dict 列表。"""
    providers = []
    p = Path(dir_path)
    if not p.exists():
        return providers

    for f in sorted(p.glob("*.yaml")):
        with open(f, "r", encoding="utf-8") as fp:
            data = yaml.safe_load(fp)
        if data and isinstance(data, dict) and "id" in data:
            providers.append(data)

    return providers
```

- [ ] **Step 5: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_manual.py -v`
Expected: PASS (2 tests)

- [ ] **Step 6: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/manual.py scripts/tests/test_manual.py data/manual/
git commit -m "feat: add manual YAML loader and 4 provider YAMLs (Google/Mistral/Qwen/Moonshot)"
```

---

### Task 16: 飞书告警模块 (core/alert.py)

**Files:**
- Create: `llm-price-compare/scripts/core/alert.py`
- Test: `llm-price-compare/scripts/tests/test_alert.py`

**Interfaces:**
- Produces: 函数 `send_feishu_alerts(alerts: list, webhook_url: str = None) -> bool`

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_alert.py
from unittest.mock import patch, MagicMock
from scripts.core.alert import send_feishu_alerts, format_alert_message


def test_format_alert_message_failed():
    msg = format_alert_message(("failed", "volcengine", "timeout"))
    assert "适配器失败" in msg
    assert "volcengine" in msg
    assert "timeout" in msg


def test_format_alert_message_warning():
    msg = format_alert_message(("warning", "zhipu", "波动 30%"))
    assert "价格波动" in msg
    assert "30%" in msg


def test_format_alert_message_blocked():
    msg = format_alert_message(("blocked", "openai", "波动 80%"))
    assert "阻断" in msg


@patch("scripts.core.alert.requests.post")
def test_send_feishu_alerts_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": 0}
    mock_post.return_value = mock_resp

    alerts = [("failed", "volcengine", "timeout")]
    ok = send_feishu_alerts(alerts, webhook_url="https://open.feishu.cn/openapis/bot/v2/hook/xxx")
    assert ok is True
    mock_post.assert_called_once()


@patch("scripts.core.alert.requests.post")
def test_send_feishu_alerts_no_webhook_returns_false(mock_post):
    import os
    # 确保环境变量未设置
    with patch.dict(os.environ, {}, clear=True):
        ok = send_feishu_alerts([("failed", "x", "y")], webhook_url=None)
        assert ok is False
        mock_post.assert_not_called()


@patch("scripts.core.alert.requests.post")
def test_send_feishu_alerts_empty_list_returns_true(mock_post):
    ok = send_feishu_alerts([], webhook_url="https://example.com")
    assert ok is True
    mock_post.assert_not_called()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_alert.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 实现 alert.py**

```python
# scripts/core/alert.py
import os
import requests

_ALERT_TEMPLATES = {
    "failed": "[{i}] 类型: 适配器失败\n厂商: {p}\n错误: {msg}",
    "warning": "[{i}] 类型: 价格波动警告\n厂商: {p}\n详情: {msg}",
    "blocked": "[{i}] 类型: 价格波动阻断\n厂商: {p}\n详情: {msg}\n该 provider 已回退至上次成功数据",
    "fatal": "[{i}] 类型: 全局校验失败\n详情: {msg}\n本次未落盘，站点保留旧数据",
}


def format_alert_message(alert: tuple) -> str:
    kind, provider, msg = alert
    template = _ALERT_TEMPLATES.get(kind, "[{i}] 未知告警类型: {kind}\n{msg}")
    return template.format(i="{i}", kind=kind, p=provider, msg=msg)


def send_feishu_alerts(alerts: list, webhook_url: str = None) -> bool:
    """发送飞书告警。webhook_url 未配置时跳过并返回 False。"""
    if not alerts:
        return True

    url = webhook_url or os.environ.get("FEISHU_WEBHOOK_URL")
    if not url:
        return False

    lines = ["[LLM 比价站告警]"]
    for i, alert in enumerate(alerts, 1):
        kind, provider, msg = alert
        template = _ALERT_TEMPLATES.get(kind, "[{i}] 未知告警类型: {kind}\n{msg}")
        lines.append(template.format(i=i, kind=kind, p=provider, msg=msg))
        lines.append("")

    text = "\n".join(lines)
    payload = {"msg_type": "text", "content": {"text": text}}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        return False
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_alert.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/alert.py scripts/tests/test_alert.py
git commit -m "feat: add Feishu webhook alert module"
```

---

### Task 17: 状态文件模块 (core/status.py)

**Files:**
- Create: `llm-price-compare/scripts/core/status.py`
- Test: `llm-price-compare/scripts/tests/test_status.py`

**Interfaces:**
- Produces: 函数 `update_run_status(success: bool, providers_summary: dict, path: str = None) -> None`

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_status.py
import json
import tempfile
import os
from pathlib import Path
from scripts.core.status import update_run_status, load_run_status


def test_update_run_status_writes_file():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run_status.json")
        update_run_status(success=True, providers_summary={"openai": "ok"}, path=path)
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        assert data["consecutive_failures"] == 0
        assert data["providers_summary"]["openai"] == "ok"
        assert "last_run_at" in data
        assert "last_success_at" in data


def test_update_run_status_increments_failures():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run_status.json")
        # 首次失败
        update_run_status(success=False, providers_summary={"x": "failed"}, path=path)
        # 第二次失败
        update_run_status(success=False, providers_summary={"x": "failed"}, path=path)
        data = load_run_status(path)
        assert data["consecutive_failures"] == 2


def test_update_run_status_resets_on_success():
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run_status.json")
        update_run_status(success=False, providers_summary={}, path=path)
        update_run_status(success=True, providers_summary={}, path=path)
        data = load_run_status(path)
        assert data["consecutive_failures"] == 0
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_status.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 实现 status.py**

```python
# scripts/core/status.py
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_DEFAULT_PATH = "data/run_status.json"
_CN_TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def load_run_status(path: str = None) -> dict:
    p = Path(path or _DEFAULT_PATH)
    if not p.exists():
        return {"consecutive_failures": 0, "providers_summary": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def update_run_status(success: bool, providers_summary: dict, path: str = None) -> None:
    p = Path(path or _DEFAULT_PATH)
    old = load_run_status(str(p))
    now = _now_iso()

    new = {
        "last_run_at": now,
        "last_success_at": now if success else old.get("last_success_at"),
        "consecutive_failures": 0 if success else old.get("consecutive_failures", 0) + 1,
        "last_push_at": now if success else old.get("last_push_at"),
        "providers_summary": providers_summary,
    }

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_status.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/core/status.py scripts/tests/test_status.py
git commit -m "feat: add run_status.json tracking module"
```

---

### Task 18: run_daily.py 调度器

**Files:**
- Create: `llm-price-compare/scripts/run_daily.py`
- Test: `llm-price-compare/scripts/tests/test_run_daily.py`

**Interfaces:**
- Consumes: `ADAPTERS`, `load_manual_providers`, `check_volatility`, `validate_global`, `send_feishu_alerts`, `update_run_status`
- Produces: 函数 `main() -> int`（返回 0 成功，1 失败）

- [ ] **Step 1: 写失败测试**

```python
# scripts/tests/test_run_daily.py
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.core.models import Product, BillingType


def _make_adapter(provider_id: str, products: list = None, raises: Exception = None):
    a = MagicMock()
    a.provider_id = provider_id
    if raises:
        a.fetch.side_effect = raises
    else:
        a.fetch.return_value = products or []
        a.validate.return_value = products or []
    a.to_provider.return_value = {
        "id": provider_id,
        "name": provider_id,
        "name_en": provider_id,
        "region": "cn",
        "website": "https://example.com/",
        "pricing_url": "https://example.com/p",
        "products": [],
    }
    return a


@patch("scripts.run_daily.ADAPTERS", [])
@patch("scripts.run_daily.load_manual_providers")
@patch("scripts.run_daily.write_prices_json")
@patch("scripts.run_daily.git_commit_push")
def test_run_daily_empty_adapters(mock_git, mock_write, mock_manual):
    mock_manual.return_value = []
    from scripts.run_daily import main
    rc = main()
    assert rc == 0
    mock_write.assert_called_once()


@patch("scripts.run_daily.ADAPTERS", [])
@patch("scripts.run_daily.load_manual_providers")
@patch("scripts.run_daily.send_feishu_alerts")
@patch("scripts.run_daily.write_prices_json")
@patch("scripts.run_daily.git_commit_push")
def test_run_daily_adapter_failure_does_not_block(mock_git, mock_write, mock_alert, mock_manual):
    """单适配器失败不影响其他。"""
    bad_adapter = _make_adapter("bad", raises=RuntimeError("boom"))
    good_adapter = _make_adapter("good", products=[
        Product(id="p1", billing_type=BillingType.PER_TOKEN,
                prices={"input": 1, "output": 1, "currency": "USD", "unit": "per_1m_tokens"},
                purchase_url="https://example.com")
    ])

    with patch("scripts.run_daily.ADAPTERS", [bad_adapter, good_adapter]):
        from scripts.run_daily import main
        rc = main()

    assert rc == 0
    mock_write.assert_called_once()
    # 应该有告警
    assert mock_alert.called


@patch("scripts.run_daily.ADAPTERS", [])
@patch("scripts.run_daily.load_manual_providers")
@patch("scripts.run_daily.has_changed", return_value=False)
@patch("scripts.run_daily.git_commit_push")
def test_run_daily_no_change_no_commit(mock_git, mock_changed, mock_manual):
    mock_manual.return_value = []
    from scripts.run_daily import main
    rc = main()
    assert rc == 0
    mock_git.assert_not_called()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_run_daily.py -v`
Expected: FAIL with `ImportError`

- [ ] **Step 3: 实现 run_daily.py**

```python
# scripts/run_daily.py
"""每日抓取入口：python3 scripts/run_daily.py"""
import json
import logging
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

from scripts.adapters import ADAPTERS
from scripts.core.manual import load_manual_providers
from scripts.core.models import provider_to_dict, provider_status_to_dict, ProviderStatus
from scripts.core.validate import check_volatility, validate_global
from scripts.core.alert import send_feishu_alerts
from scripts.core.status import update_run_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("run_daily")

_PRICES_PATH = Path("data/prices.json")
_MANUAL_DIR = Path("data/manual")
_CN_TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def load_prices_json() -> dict:
    if not _PRICES_PATH.exists():
        return {"providers": [], "provider_status": []}
    return json.loads(_PRICES_PATH.read_text(encoding="utf-8"))


def write_prices_json(data: dict) -> None:
    _PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PRICES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_provider(data: dict, provider_id: str) -> dict:
    for p in data.get("providers", []):
        if p.get("id") == provider_id:
            return p
    return None


def has_changed(old: dict, new: dict) -> bool:
    return json.dumps(old, sort_keys=True) != json.dumps(new, sort_keys=True)


def git_commit_push() -> bool:
    try:
        subprocess.run(["git", "add", str(_PRICES_PATH)], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore(data): update prices {_now_iso()}", "--", str(_PRICES_PATH)],
            check=True,
        )
        subprocess.run(["git", "push"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"git push failed: {e}")
        return False


def main() -> int:
    log.info("run_daily started")
    old_data = load_prices_json()
    new_providers = []
    provider_status = []
    alerts = []
    summary = {}

    for adapter in ADAPTERS:
        pid = adapter.provider_id
        try:
            products = adapter.fetch()
            products = adapter.validate(products)

            old_provider = find_provider(old_data, pid)
            volatility = check_volatility(old_provider, products)

            if volatility.should_block:
                alerts.append(("blocked", pid, f"波动 {volatility.max_pct}%"))
                if old_provider:
                    new_providers.append(old_provider)
                status = ProviderStatus(
                    provider_id=pid,
                    status="failed",
                    last_success_at=_find_last_success(old_data, pid),
                    error=f"volatility blocked: {volatility.max_pct}%",
                    stale=True,
                )
                provider_status.append(provider_status_to_dict(status))
                summary[pid] = "blocked"
                continue

            if volatility.warnings:
                alerts.append(("warning", pid, f"波动 {volatility.max_pct}%"))

            new_providers.append(adapter.to_provider(products))
            status = ProviderStatus(
                provider_id=pid,
                status="ok",
                last_success_at=_now_iso(),
                warnings=volatility.warnings,
            )
            provider_status.append(provider_status_to_dict(status))
            summary[pid] = "ok"

        except Exception as e:
            log.error(f"{pid} failed: {e}")
            alerts.append(("failed", pid, str(e)))
            old_provider = find_provider(old_data, pid)
            if old_provider:
                new_providers.append(old_provider)
            status = ProviderStatus(
                provider_id=pid,
                status="failed",
                last_success_at=_find_last_success(old_data, pid),
                error=str(e),
                stale=True,
            )
            provider_status.append(provider_status_to_dict(status))
            summary[pid] = "failed"

    # 合并 manual
    manual_providers = load_manual_providers(str(_MANUAL_DIR))
    new_providers.extend(manual_providers)
    for mp in manual_providers:
        pid = mp["id"]
        provider_status.append({
            "provider_id": pid,
            "status": "ok",
            "last_success_at": _now_iso(),
            "stale": False,
            "warnings": [],
        })
        summary[pid] = "ok"

    new_data = {
        "generated_at": _now_iso(),
        "providers": new_providers,
        "provider_status": provider_status,
    }

    if validate_global(new_data):
        write_prices_json(new_data)
        if has_changed(old_data, new_data):
            git_commit_push()
        update_run_status(success=True, providers_summary=summary)
        if alerts:
            send_feishu_alerts(alerts)
        log.info(f"run_daily finished, {len(summary)} providers, {len(alerts)} alerts")
        return 0
    else:
        alerts.append(("fatal", "global", "Global validation failed"))
        update_run_status(success=False, providers_summary=summary)
        send_feishu_alerts(alerts)
        log.error("run_daily failed: global validation failed")
        return 1


def _find_last_success(old_data: dict, pid: str) -> str:
    for s in old_data.get("provider_status", []):
        if s.get("provider_id") == pid:
            return s.get("last_success_at")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行测试验证通过**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/tests/test_run_daily.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add scripts/run_daily.py scripts/tests/test_run_daily.py
git commit -m "feat: add daily scheduler with failure isolation and alerts"
```

---

## Phase 5: 前端

### Task 19: 前端骨架与数据加载

**Files:**
- Create: `llm-price-compare/ui/index.html`
- Create: `llm-price-compare/ui/app.js`
- Create: `llm-price-compare/ui/style.css`

**说明**：Vue 3 CDN 引入，无 build step。先实现数据加载 + 基础骨架，后续 task 加交互。

- [ ] **Step 1: 写 index.html**

```html
<!-- ui/index.html -->
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM 价格比价</title>
  <link rel="stylesheet" href="style.css">
  <script src="https://unpkg.com/vue@3/dist/vue.global.prod.js"></script>
</head>
<body>
  <div id="app">
    <header class="header">
      <div class="brand">LLM 价格比价</div>
      <input class="search" v-model="searchQuery" placeholder="搜索厂商/模型..." />
      <a class="feedback-btn" :href="feedbackUrl" target="_blank">反馈</a>
    </header>

    <section class="filters">
      <div class="filter-group">
        <span class="filter-label">地区</span>
        <button v-for="r in regions" :key="r" @click="toggleFilter('region', r)"
          :class="['chip', {active: filters.region.includes(r)}]">{{ r === 'cn' ? '国内' : (r === 'us' ? '美国' : '欧洲') }}</button>
      </div>
      <div class="filter-group">
        <span class="filter-label">计费</span>
        <button v-for="b in billingTypes" :key="b" @click="toggleFilter('billing', b)"
          :class="['chip', {active: filters.billing.includes(b)}]">{{ billingLabel(b) }}</button>
      </div>
      <div class="filter-group">
        <span class="filter-label">能力</span>
        <button v-for="m in modalities" :key="m" @click="toggleFilter('modality', m)"
          :class="['chip', {active: filters.modality.includes(m)}]">{{ m }}</button>
      </div>
    </section>

    <section class="freshness" v-if="data">
      <span>最近更新: {{ freshnessText }}</span>
      <span>·</span>
      <span>{{ data.providers.length }} 家厂商</span>
      <span>·</span>
      <span>{{ totalProducts }} 个产品</span>
      <span class="stale-warning" v-if="staleCount > 0">⚠ {{ staleCount }} 家厂商数据可能过期</span>
    </section>

    <section class="result" v-if="data">
      <div class="view-toggle">
        <button :class="{active: view === 'table'}" @click="view = 'table'">表格</button>
        <button :class="{active: view === 'card'}" @click="view = 'card'">卡片</button>
        <div class="currency-toggle">
          <button :class="{active: displayCurrency === 'CNY'}" @click="displayCurrency = 'CNY'">¥</button>
          <button :class="{active: displayCurrency === 'USD'}" @click="displayCurrency = 'USD'">$</button>
        </div>
      </div>

      <table class="price-table" v-show="view === 'table'">
        <thead>
          <tr>
            <th @click="sortBy('providerName')">厂商</th>
            <th @click="sortBy('model')">模型</th>
            <th @click="sortBy('billing_type')">计费</th>
            <th @click="sortBy('inputPrice')">输入价</th>
            <th @click="sortBy('outputPrice')">输出价</th>
            <th>购买</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.id" @click="toggleExpand(row.id)"
            :class="{stale: row.stale, expanded: expanded === row.id}">
            <td>{{ row.providerName }}</td>
            <td>{{ row.model || '—' }}</td>
            <td>{{ billingLabel(row.billing_type) }}</td>
            <td>{{ formatPrice(row, 'input') }}</td>
            <td>{{ formatPrice(row, 'output') }}</td>
            <td><a :href="row.purchase_url" target="_blank" @click.stop>购买</a></td>
          </tr>
          <tr v-if="expanded" class="detail-row">
            <td colspan="6">
              <div class="detail">
                <p>上下文窗口: {{ currentRow.context_window || '—' }}</p>
                <p>能力: {{ (currentRow.modalities || []).join(', ') || '—' }}</p>
                <p v-if="currentRow.notes">备注: {{ currentRow.notes }}</p>
                <p v-if="currentRow.stale" class="stale-detail">⚠ 数据来自 {{ staleHours(currentRow) }} 小时前，可能过期</p>
              </div>
            </td>
          </tr>
        </tbody>
      </table>

      <div class="card-grid" v-show="view === 'card'">
        <div v-for="row in filteredRows" :key="row.id" class="card" :class="{stale: row.stale}">
          <div class="card-header">
            <span class="card-provider">{{ row.providerName }}</span>
            <span class="card-billing">{{ billingLabel(row.billing_type) }}</span>
          </div>
          <div class="card-model">{{ row.model || '—' }}</div>
          <div class="card-prices">
            <div v-if="row.prices.input">输入: {{ formatPrice(row, 'input') }}</div>
            <div v-if="row.prices.output">输出: {{ formatPrice(row, 'output') }}</div>
            <div v-if="row.prices.monthly_price">月费: {{ formatPrice(row, 'monthly_price') }}</div>
          </div>
          <a class="card-buy" :href="row.purchase_url" target="_blank">购买</a>
        </div>
      </div>
    </section>

    <section class="error" v-if="error">
      <p>数据暂不可用：{{ error }}</p>
    </section>

    <footer class="footer">
      数据仅供参考 · 价格以厂商官方为准 ·
      <a href="https://github.com/llm-price-compare/llm-price-compare" target="_blank">GitHub</a>
    </footer>
  </div>

  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: 写 app.js（基础版）**

```javascript
// ui/app.js
const { createApp, ref, computed, onMounted } = Vue;

const USD_TO_CNY = 7.2;  // MVP 硬编码汇率

createApp({
  setup() {
    const data = ref(null);
    const error = ref(null);
    const searchQuery = ref("");
    const view = ref("table");
    const displayCurrency = ref("CNY");
    const expanded = ref(null);
    const sortKey = ref("inputPrice");
    const sortAsc = ref(true);
    const filters = ref({
      region: [],
      billing: [],
      modality: [],
    });

    const regions = ["cn", "us", "eu"];
    const billingTypes = ["per_token", "subscription", "coding_plan"];
    const modalities = ["text", "vision", "audio"];

    const providerStatusMap = computed(() => {
      const m = {};
      if (!data.value) return m;
      for (const s of data.value.provider_status || []) {
        m[s.provider_id] = s;
      }
      return m;
    });

    const allRows = computed(() => {
      if (!data.value) return [];
      const rows = [];
      for (const p of data.value.providers) {
        const status = providerStatusMap.value[p.id] || {};
        for (const prod of p.products) {
          rows.push({
            id: `${p.id}:${prod.id}`,
            providerId: p.id,
            providerName: p.name,
            region: p.region,
            stale: status.stale === true,
            status,
            ...prod,
          });
        }
      }
      return rows;
    });

    const filteredRows = computed(() => {
      let rows = allRows.value;
      const q = searchQuery.value.trim().toLowerCase();
      if (q) {
        rows = rows.filter(r =>
          r.providerName.toLowerCase().includes(q) ||
          (r.model || "").toLowerCase().includes(q)
        );
      }
      if (filters.value.region.length) {
        rows = rows.filter(r => filters.value.region.includes(r.region));
      }
      if (filters.value.billing.length) {
        rows = rows.filter(r => filters.value.billing.includes(r.billing_type));
      }
      if (filters.value.modality.length) {
        rows = rows.filter(r =>
          (r.modalities || []).some(m => filters.value.modality.includes(m))
        );
      }
      // sort
      rows = [...rows].sort((a, b) => {
        let va = sortValue(a, sortKey.value);
        let vb = sortValue(b, sortKey.value);
        if (va == null) va = Infinity;
        if (vb == null) vb = Infinity;
        if (typeof va === "string") {
          return sortAsc.value ? va.localeCompare(vb) : vb.localeCompare(va);
        }
        return sortAsc.value ? va - vb : vb - va;
      });
      return rows;
    });

    function sortValue(row, key) {
      if (key === "providerName") return row.providerName;
      if (key === "model") return row.model || "";
      if (key === "billing_type") return row.billing_type;
      if (key === "inputPrice") return row.prices?.input;
      if (key === "outputPrice") return row.prices?.output;
      return null;
    }

    const currentRow = computed(() => {
      if (!expanded.value) return null;
      return allRows.value.find(r => r.id === expanded.value);
    });

    const totalProducts = computed(() => allRows.value.length);
    const staleCount = computed(() => {
      if (!data.value) return 0;
      return (data.value.provider_status || []).filter(s => s.stale).length;
    });

    const freshnessText = computed(() => {
      if (!data.value?.generated_at) return "未知";
      const then = new Date(data.value.generated_at);
      const now = new Date();
      const hours = Math.floor((now - then) / 3600000);
      if (hours < 1) return "刚刚";
      if (hours < 24) return `${hours} 小时前`;
      return `${Math.floor(hours / 24)} 天前`;
    });

    const feedbackUrl = computed(() => {
      const base = "https://github.com/llm-price-compare/llm-price-compare/issues/new";
      const params = new URLSearchParams({
        template: "price-report.yml",
        labels: "price-error",
      });
      return `${base}?${params.toString()}`;
    });

    function toggleFilter(kind, value) {
      const arr = filters.value[kind === "region" ? "region" : (kind === "billing" ? "billing" : "modality")];
      const i = arr.indexOf(value);
      if (i >= 0) arr.splice(i, 1);
      else arr.push(value);
    }

    function sortBy(key) {
      if (sortKey.value === key) sortAsc.value = !sortAsc.value;
      else { sortKey.value = key; sortAsc.value = true; }
    }

    function toggleExpand(id) {
      expanded.value = expanded.value === id ? null : id;
    }

    function billingLabel(b) {
      return { per_token: "Token", subscription: "订阅", coding_plan: "Coding Plan" }[b] || b;
    }

    function formatPrice(row, field) {
      const v = row.prices?.[field];
      if (v == null) return "—";
      const cur = row.prices.currency;
      if (cur === displayCurrency.value) {
        return displayCurrency.value === "CNY" ? `¥${v}` : `$${v}`;
      }
      // 换算
      if (cur === "USD" && displayCurrency.value === "CNY") {
        return `¥${(v * USD_TO_CNY).toFixed(2)}`;
      }
      if (cur === "CNY" && displayCurrency.value === "USD") {
        return `$${(v / USD_TO_CNY).toFixed(2)}`;
      }
      return v;
    }

    function staleHours(row) {
      const last = row.status?.last_success_at;
      if (!last) return "?";
      const hours = Math.floor((Date.now() - new Date(last)) / 3600000);
      return hours;
    }

    async function loadData() {
      try {
        const resp = await fetch("data/prices.json", { cache: "no-cache" });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        data.value = await resp.json();
      } catch (e) {
        error.value = e.message;
      }
    }

    onMounted(loadData);

    return {
      data, error, searchQuery, view, displayCurrency, expanded,
      sortKey, sortAsc, filters, regions, billingTypes, modalities,
      filteredRows, currentRow, totalProducts, staleCount, freshnessText,
      feedbackUrl, toggleFilter, sortBy, toggleExpand, billingLabel,
      formatPrice, staleHours,
    };
  },
}).mount("#app");
```

- [ ] **Step 3: 写 style.css（基础骨架，视觉后续讨论）**

```css
/* ui/style.css */
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif; color: #1a1a1a; background: #fafafa; }

#app { max-width: 1200px; margin: 0 auto; padding: 16px; }

.header { display: flex; align-items: center; gap: 16px; padding: 12px 0; border-bottom: 1px solid #e5e5e5; }
.brand { font-size: 20px; font-weight: 600; }
.search { flex: 1; padding: 8px 12px; border: 1px solid #d5d5d5; border-radius: 6px; font-size: 14px; }
.feedback-btn { padding: 8px 16px; background: #1a1a1a; color: #fff; text-decoration: none; border-radius: 6px; font-size: 14px; }

.filters { padding: 12px 0; border-bottom: 1px solid #e5e5e5; }
.filter-group { display: inline-flex; align-items: center; gap: 8px; margin-right: 24px; }
.filter-label { font-size: 13px; color: #666; }
.chip { padding: 4px 12px; border: 1px solid #d5d5d5; background: #fff; border-radius: 16px; cursor: pointer; font-size: 13px; }
.chip.active { background: #1a1a1a; color: #fff; border-color: #1a1a1a; }

.freshness { padding: 8px 0; font-size: 13px; color: #666; display: flex; gap: 8px; align-items: center; }
.stale-warning { color: #d97706; font-weight: 500; }

.result { padding: 16px 0; }
.view-toggle { display: flex; justify-content: space-between; margin-bottom: 12px; }
.view-toggle button { padding: 6px 12px; border: 1px solid #d5d5d5; background: #fff; cursor: pointer; }
.view-toggle button.active { background: #1a1a1a; color: #fff; }
.currency-toggle { display: inline-flex; }

.price-table { width: 100%; border-collapse: collapse; font-size: 14px; }
.price-table th, .price-table td { padding: 10px 8px; text-align: left; border-bottom: 1px solid #eee; }
.price-table th { cursor: pointer; color: #666; font-weight: 500; }
.price-table tr { cursor: pointer; }
.price-table tr.stale { background: #fff7ed; }
.price-table tr.expanded { background: #f5f5f5; }
.detail-row td { padding: 12px 8px; background: #fafafa; }
.detail p { margin: 4px 0; font-size: 13px; }
.stale-detail { color: #d97706; }

.card-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 12px; }
.card { padding: 16px; border: 1px solid #e5e5e5; border-radius: 8px; background: #fff; }
.card.stale { border-color: #d97706; background: #fff7ed; }
.card-header { display: flex; justify-content: space-between; margin-bottom: 8px; }
.card-provider { font-weight: 500; }
.card-billing { font-size: 12px; color: #666; }
.card-model { margin-bottom: 8px; color: #333; }
.card-prices { font-size: 13px; color: #666; }
.card-prices div { margin: 2px 0; }
.card-buy { display: inline-block; margin-top: 8px; padding: 4px 12px; background: #1a1a1a; color: #fff; text-decoration: none; border-radius: 4px; font-size: 13px; }

.error { padding: 32px; text-align: center; color: #991b1b; }

.footer { padding: 16px 0; border-top: 1px solid #e5e5e5; font-size: 12px; color: #666; text-align: center; }
.footer a { color: #666; }
```

- [ ] **Step 4: 本地验证**

Run: `cd /Users/shareit/personal/llm-price-compare && python3 -m http.server 8000`
打开浏览器访问 `http://localhost:8000/ui/`，应看到空数据页面（无报错）。

- [ ] **Step 5: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add ui/
git commit -m "feat: add Vue 3 SPA frontend with table/card views and filters"
```

---

### Task 20: GitHub Issue 模板

**Files:**
- Create: `llm-price-compare/.github/ISSUE_TEMPLATE/price-report.yml`
- Create: `llm-price-compare/.github/ISSUE_TEMPLATE/new-provider.yml`

- [ ] **Step 1: 写 price-report.yml**

```yaml
# .github/ISSUE_TEMPLATE/price-report.yml
name: 价格异常报告
description: 报告某厂商/模型的价格错误
labels: [price-error]
body:
  - type: dropdown
    id: provider
    attributes:
      label: 厂商
      options:
        - OpenAI
        - Anthropic
        - 智谱
        - 火山引擎
        - DeepSeek
        - OpenCode
        - Google
        - Mistral
        - 阿里通义
        - 月之暗面
        - 其他
    validations:
      required: true
  - type: input
    id: model
    attributes:
      label: 模型/产品
      placeholder: 如 GLM-4-Plus
    validations:
      required: true
  - type: textarea
    id: correct_price
    attributes:
      label: 正确价格
      description: 请附厂商定价页截图或链接
    validations:
      required: true
```

- [ ] **Step 2: 写 new-provider.yml**

```yaml
# .github/ISSUE_TEMPLATE/new-provider.yml
name: 建议新增厂商
description: 建议添加一家新的 LLM 厂商
labels: [new-provider]
body:
  - type: input
    id: provider_name
    attributes:
      label: 厂商名称
    validations:
      required: true
  - type: input
    id: pricing_url
    attributes:
      label: 定价页 URL
    validations:
      required: true
  - type: textarea
    id: notes
    attributes:
      label: 补充说明
```

- [ ] **Step 3: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add .github/ISSUE_TEMPLATE/
git commit -m "feat: add GitHub Issue templates for price reports and new providers"
```

---

## Phase 6: CI 与部署

### Task 21: GitHub Actions CI (test.yml)

**Files:**
- Create: `llm-price-compare/.github/workflows/test.yml`

- [ ] **Step 1: 写 test.yml**

```yaml
# .github/workflows/test.yml
name: Test

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Run tests (skip browser)
        run: |
          pytest scripts/ -v -m "not browser"
```

- [ ] **Step 2: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add .github/workflows/test.yml
git commit -m "ci: add test workflow (skip browser tests)"
```

---

### Task 22: GitHub Pages 部署 (deploy.yml)

**Files:**
- Create: `llm-price-compare/.github/workflows/deploy.yml`

**说明**：当 `data/prices.json` 被 push 时，自动重建 GitHub Pages。

- [ ] **Step 1: 写 deploy.yml**

```yaml
# .github/workflows/deploy.yml
name: Deploy to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - "ui/**"
      - "data/prices.json"

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: "pages"
  cancel-in-progress: true

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - name: Setup Pages
        uses: actions/configure-pages@v4
      - name: Build
        run: |
          # ui/ 作为站点根目录，data/ 保留相对路径
          mkdir -p _site
          cp -r ui/* _site/
          mkdir -p _site/data
          cp data/prices.json _site/data/
      - name: Upload artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: _site
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v4
```

- [ ] **Step 2: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add .github/workflows/deploy.yml
git commit -m "ci: add GitHub Pages deploy workflow"
```

---

### Task 23: 服务器 cron 部署文档

**Files:**
- Create: `llm-price-compare/DEPLOY.md`

- [ ] **Step 1: 写 DEPLOY.md**

```markdown
# 部署指南

## 服务器端配置（cron 抓取）

### 1. 克隆仓库

```bash
cd /opt
git clone https://github.com/llm-price-compare/llm-price-compare.git
cd llm-price-compare
```

### 2. 安装依赖

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 3. 配置环境变量

在 `~/.bashrc` 或 `/etc/llm-price.env` 中：

```bash
export FEISHU_WEBHOOK_URL="https://open.feishu.cn/openapis/bot/v2/hook/xxx"
```

### 4. 配置 git push 权限

```bash
# 用 deploy key 或 personal access token
git remote set-url origin https://<token>@github.com/llm-price-compare/llm-price-compare.git
```

### 5. 配置 crontab

```bash
crontab -e
```

加入：

```
# 每日 11:00 北京时间抓取 LLM 价格
0 11 * * * cd /opt/llm-price-compare && /opt/llm-price-compare/.venv/bin/python3 scripts/run_daily.py >> /var/log/llm-price/$(date +\%Y\%m\%d).log 2>&1
```

### 6. 创建日志目录

```bash
sudo mkdir -p /var/log/llm-price
sudo chown $(whoami) /var/log/llm-price
```

### 7. 手动测试

```bash
cd /opt/llm-price-compare
source .venv/bin/activate
python3 scripts/run_daily.py
cat data/run_status.json
```

## GitHub Pages 配置

1. 仓库 Settings → Pages → Source: GitHub Actions
2. push 后 deploy.yml 自动部署
3. 访问 `https://llm-price-compare.github.io/llm-price-compare/`

## 故障排查

- **抓取失败**：检查 `/var/log/llm-price/` 日志
- **数据未更新**：检查 `git push` 是否成功（看 `data/run_status.json` 的 `last_push_at`）
- **飞书告警未收到**：检查 `FEISHU_WEBHOOK_URL` 环境变量
```

- [ ] **Step 2: 提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git add DEPLOY.md
git commit -m "docs: add server deployment guide with cron configuration"
```

---

### Task 24: 端到端验证

**Files:** 无新建，运行现有测试 + 手动验证

- [ ] **Step 1: 运行全量测试**

Run: `cd /Users/shareit/personal/llm-price-compare && python -m pytest scripts/ -v -m "not browser"`
Expected: 所有测试 PASS

- [ ] **Step 2: 手动跑一次 run_daily.py（mock 模式或真实模式）**

```bash
cd /Users/shareit/personal/llm-price-compare
source .venv/bin/activate  # 如果有
python3 scripts/run_daily.py
cat data/run_status.json
cat data/prices.json | python3 -m json.tool | head -30
```

Expected: `run_status.json` 中 `consecutive_failures: 0`，`prices.json` 包含 manual 厂商数据。

- [ ] **Step 3: 本地启动前端验证**

```bash
cd /Users/shareit/personal/llm-price-compare
python3 -m http.server 8000
```

打开浏览器 `http://localhost:8000/ui/`：
- 看到 manual 厂商（Google/Mistral/阿里通义/月之暗面）数据
- 筛选、搜索、排序、视图切换功能正常
- 反馈按钮跳转 GitHub Issues

- [ ] **Step 4: 修复发现的问题（如有）**

如有问题，回到对应 task 修复并重新提交。

- [ ] **Step 5: 最终提交**

```bash
cd /Users/shareit/personal/llm-price-compare
git log --oneline
git status
```

Expected: 工作区干净，所有 task 提交可见。

---

## Self-Review

### Spec Coverage Check

| Spec 章节 | 覆盖 Task |
|---|---|
| 3. 整体架构 | Task 1, 14, 18, 22, 23 |
| 4. 数据模型 | Task 2 |
| 4.6 数据校验规则 | Task 3 |
| 4.5 波动警告 | Task 4 |
| 5.1 适配器基类 | Task 6 |
| 5.3 6 家适配器 | Task 7-10 (HTTP), 11-13 (browser), 14 (注册) |
| 5.4 4 家 manual | Task 15 |
| 5.6 失败可见性（双通道） | Task 16 (飞书), 19 (网页) |
| 5.8 run_daily.py 调度 | Task 18 |
| 6. 前端 UI | Task 19 |
| 6.4 反馈 Issue 模板 | Task 20 |
| 7. 错误处理矩阵 | Task 3, 4, 16, 18, 19 |
| 8. 测试策略 | 每个 Task 内 TDD + Task 21 (CI) |
| 9. 可观测性 | Task 17 (run_status.json), 18 (日志), 23 (日志轮转) |
| 10. 安全与合规 | Task 5 (UA), 19 (免责声明), 各适配器 (不绕反爬) |
| 3.3 部署链路 | Task 22 (Pages), 23 (cron) |

**Gap**: 9.1 日志按日轮转保留 30 天——这属于系统运维配置（logrotate），未在代码层实现，DEPLOY.md 已提示日志路径，运维侧用 logrotate 配置即可。可接受。

### Placeholder Scan

无 TBD/TODO。所有代码步骤含完整代码块。fixture 文件含具体内容。

### Type Consistency

- `Product.billing_type` 在 models.py (Task 2) 定义为 `BillingType` 枚举，所有 adapter (Task 7-13) 使用一致。
- `check_volatility` (Task 4) 返回 `VolatilityResult`，run_daily.py (Task 18) 使用 `.should_block` 和 `.warnings` 字段一致。
- `ProviderStatus` (Task 2) 字段与 `provider_status_to_dict` 输出、run_daily.py 构造、前端 app.js 读取（`s.stale`、`s.last_success_at`）一致。
- `send_feishu_alerts` (Task 16) 接收 `list[tuple]`，run_daily.py (Task 18) 传入 `("failed", pid, str(e))` 等三元组，一致。

无类型不一致问题。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-12-llm-price-compare-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session, batch execution with checkpoints

Which approach?
