from typing import Optional


PRICE_FIELDS = ("input", "output", "cached_input", "monthly_price", "first_month_price")


def detect_changes(old_data: Optional[dict], new_data: dict) -> list[dict]:
    """Pure dataset diff used before persistence/publish side effects."""
    if not old_data:
        return []
    old_products = {
        (provider["id"], product["id"]): product
        for provider in old_data.get("providers", [])
        for product in provider.get("products", [])
    }
    changes = []
    for provider in new_data.get("providers", []):
        for product in provider.get("products", []):
            old = old_products.get((provider["id"], product["id"]))
            if not old:
                continue
            before_prices, after_prices = old.get("prices") or {}, product.get("prices") or {}
            if before_prices.get("currency") != after_prices.get("currency"):
                continue
            for field_name in PRICE_FIELDS:
                before, after = before_prices.get(field_name), after_prices.get(field_name)
                if before == after:
                    continue
                if before is None or after is None or before == 0:
                    pct = None
                else:
                    pct = round((float(after) - float(before)) / float(before) * 100, 2)
                changes.append({
                    "provider_id": provider["id"],
                    "product_id": product["id"],
                    "billing_type": product.get("billing_type"),
                    "field": field_name,
                    "old_value": before,
                    "new_value": after,
                    "change_pct": pct,
                })
    return changes
