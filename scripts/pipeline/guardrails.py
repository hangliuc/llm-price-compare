from dataclasses import dataclass, field
from typing import Optional


PLAN_CATEGORIES = {"general_ai", "coding_tool", "developer_api"}


@dataclass
class GuardResult:
    accepted: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_product(product: dict) -> list[str]:
    errors = []
    pid = product.get("id") or "<missing>"
    billing = product.get("billing_type")
    prices = product.get("prices") or {}
    if not product.get("id"):
        errors.append("product id is required")
    if billing not in {"per_token", "subscription", "coding_plan"}:
        errors.append(f"{pid}: invalid billing_type")
    if not product.get("purchase_url"):
        errors.append(f"{pid}: purchase_url is required")
    if not prices.get("currency"):
        errors.append(f"{pid}: currency is required")
    required = {
        "per_token": ("input", "output", "unit"),
        "subscription": ("monthly_price",),
        "coding_plan": ("monthly_price", "included_quota", "quota_unit"),
    }.get(billing, ())
    for field_name in required:
        if field_name not in prices or prices[field_name] is None:
            errors.append(f"{pid}: prices.{field_name} is required")
    for field_name in ("input", "output", "cached_input", "monthly_price", "first_month_price"):
        value = prices.get(field_name)
        if value is not None and (not isinstance(value, (int, float)) or value < 0):
            errors.append(f"{pid}: prices.{field_name} must be non-negative")
    if billing in {"subscription", "coding_plan"}:
        if product.get("plan_category") not in PLAN_CATEGORIES:
            errors.append(f"{pid}: plan_category is required")
        if not isinstance(product.get("featured_on_home"), bool):
            errors.append(f"{pid}: featured_on_home must be boolean")
    return errors


def validate_provider(provider: dict) -> list[str]:
    errors = []
    pid = provider.get("id") or "<missing>"
    for field_name in ("id", "name", "website", "pricing_url"):
        if not provider.get(field_name):
            errors.append(f"{pid}: provider.{field_name} is required")
    products = provider.get("products")
    if not isinstance(products, list) or not products:
        errors.append(f"{pid}: provider has no products")
        return errors
    ids = [p.get("id") for p in products]
    if len(ids) != len(set(ids)):
        errors.append(f"{pid}: duplicate product ids")
    for product in products:
        errors.extend(validate_product(product))
    return errors


def _price_guard(old_provider: dict, candidate: dict) -> tuple[list[str], list[str]]:
    errors, warnings = [], []
    old_products = {p.get("id"): p for p in old_provider.get("products", [])}
    for product in candidate.get("products", []):
        old = old_products.get(product.get("id"))
        if not old:
            continue
        old_prices, prices = old.get("prices") or {}, product.get("prices") or {}
        if old_prices.get("currency") != prices.get("currency"):
            continue
        for field_name in ("input", "output", "cached_input", "monthly_price"):
            before, after = old_prices.get(field_name), prices.get(field_name)
            if before is None or after is None or before == 0:
                continue
            pct = abs((float(after) - float(before)) / float(before)) * 100
            if pct > 20:
                warnings.append(f"{product['id']}.{field_name} changed {pct:.1f}%")
            if field_name != "cached_input" and pct > 50:
                errors.append(f"{product['id']}.{field_name} changed {pct:.1f}%")
    return errors, warnings


def guard_provider(candidate: dict, old_provider: Optional[dict], min_ratio: float) -> GuardResult:
    errors = validate_provider(candidate)
    warnings = []
    if old_provider:
        old_count = len(old_provider.get("products", []))
        new_count = len(candidate.get("products", []))
        if old_count >= 5 and new_count <= old_count * min_ratio:
            errors.append(f"product count dropped {old_count} -> {new_count}")
        price_errors, price_warnings = _price_guard(old_provider, candidate)
        errors.extend(price_errors)
        warnings.extend(price_warnings)
    return GuardResult(not errors, errors, warnings)


def guard_dataset(candidate: dict, old_data: Optional[dict], min_ratio: float,
                  min_providers: int, min_products: int) -> GuardResult:
    errors = []
    providers = candidate.get("providers") or []
    provider_ids = [p.get("id") for p in providers]
    product_count = sum(len(p.get("products", [])) for p in providers)
    if len(providers) < min_providers:
        errors.append(f"provider count below minimum: {len(providers)} < {min_providers}")
    if product_count < min_products:
        errors.append(f"product count below minimum: {product_count} < {min_products}")
    if len(provider_ids) != len(set(provider_ids)):
        errors.append("duplicate provider ids")
    if old_data:
        old_providers = old_data.get("providers") or []
        old_products = sum(len(p.get("products", [])) for p in old_providers)
        if len(providers) < len(old_providers) * min_ratio:
            errors.append("global provider count dropped unexpectedly")
        if product_count < old_products * min_ratio:
            errors.append("global product count dropped unexpectedly")
    return GuardResult(not errors, errors)
