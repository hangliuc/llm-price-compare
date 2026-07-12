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
