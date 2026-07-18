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


# 追加到 scripts/core/validate.py 末尾
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class VolatilityResult:
    max_pct: float = 0.0
    should_block: bool = False
    warnings: list = field(default_factory=list)


# 参与波动检测的字段
# cached_input 不参与 block 判断：缓存价格通常很低（如 0.02），小绝对值变化会产生
# 大百分比（如 0.02145 → 0.1345 = 527%），容易误 block 正常调价
# 但 cached_input 仍参与 warning（>20% 提醒），只不触发 >50% block
_PRICE_FIELDS = ["input", "output", "cached_input", "monthly_price"]
_PRICE_FIELDS_BLOCK = ["input", "output", "monthly_price"]


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

        # 货币不一致时跳过价差对比（CNY vs USD 会产生假阳性阻塞）
        # 首次从 manual 切换到 reconcile 数据源时，货币可能从 CNY 变为 USD
        old_currency = old_prices.get("currency")
        new_currency = new_prices.get("currency")
        if old_currency and new_currency and old_currency != new_currency:
            continue

        # 所有字段都参与 warning（>20%）
        # 但只有 _PRICE_FIELDS_BLOCK 中的字段参与 block 判断（>50%）
        block_max_pct = 0.0
        for f in _PRICE_FIELDS:
            if f in old_prices and f in new_prices:
                pct = _pct_change(float(old_prices[f]), float(new_prices[f]))
                if pct > result.max_pct:
                    result.max_pct = pct
                if f in _PRICE_FIELDS_BLOCK:
                    if pct > block_max_pct:
                        block_max_pct = pct
                if pct > 20.0:
                    result.warnings.append({
                        "product_id": pid,
                        "field": f"prices.{f}",
                        "old_value": old_prices[f],
                        "new_value": new_prices[f],
                        "volatility_pct": round(pct, 2),
                    })

    if block_max_pct > 50.0:
        result.should_block = True

    return result
