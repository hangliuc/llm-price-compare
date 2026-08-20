from decimal import Decimal, InvalidOperation
from typing import Optional

from scripts.pipeline_v2.models import FieldDecision, ProductCandidate, ReviewItem
from scripts.pipeline_v2.reconcile import catalog_product_map


PRICE_FIELDS = {"price.input", "price.output", "price.cached_input", "price.monthly_price",
                "price.first_month_price"}


def _decimal(value) -> Optional[Decimal]:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def apply_price_drift_guard(candidates: list[ProductCandidate], previous: Optional[dict],
                            warning_pct: Decimal = Decimal("20"),
                            block_pct: Decimal = Decimal("50"),
                            accepted_baselines: Optional[dict] = None,
                            ) -> tuple[list[ProductCandidate], list[ReviewItem], list[str]]:
    old_products = catalog_product_map(previous)
    accepted_baselines = accepted_baselines or {}
    reviews, warnings = [], []
    for candidate in candidates:
        old_product = old_products.get(candidate.canonical_id, {})
        old_fields = old_product.get("fields", {})
        old_observed_at = (old_product.get("freshness") or {}).get(
            "latest_observed_at", "")
        if not old_fields:
            continue
        same_currency = candidate.fields.get("price.currency") == old_fields.get("price.currency")
        same_unit = candidate.fields.get("price.unit") == old_fields.get("price.unit")
        if not (same_currency and same_unit):
            continue
        for field in PRICE_FIELDS:
            old_value = _decimal(old_fields.get(field))
            new_value = _decimal(candidate.fields.get(field))
            if old_value is None or new_value is None or old_value == 0:
                continue
            change_pct = abs((new_value - old_value) / old_value * 100)
            approved = accepted_baselines.get((candidate.canonical_id, field))
            if approved:
                approved_value = _decimal(approved.get("value"))
                approved_context = (
                    approved_value == new_value
                    and approved.get("currency") == candidate.fields.get("price.currency")
                    and approved.get("unit") == candidate.fields.get("price.unit")
                )
                if approved_context:
                    continue
            if change_pct > block_pct:
                candidate.fields[field] = old_fields[field]
                candidate.decisions = [item for item in candidate.decisions if item.field != field]
                candidate.decisions.append(FieldDecision(
                    candidate.canonical_id, field, old_fields[field], "last_known_good", "lkg",
                    f"blocked {change_pct:.2f}% price change pending review",
                    old_observed_at,
                ))
                candidate.status = "partial"
                if field not in candidate.stale_fields:
                    candidate.stale_fields.append(field)
                reviews.append(ReviewItem(
                    canonical_id=candidate.canonical_id,
                    field=field,
                    reason="price change exceeds automatic publish threshold",
                    details={"old": old_fields[field], "candidate": float(new_value),
                             "change_pct": float(change_pct),
                             "currency": candidate.fields.get("price.currency"),
                             "unit": candidate.fields.get("price.unit")},
                ))
            elif change_pct > warning_pct:
                warnings.append(
                    f"{candidate.canonical_id} {field} changed {change_pct:.2f}%"
                )
    return candidates, reviews, warnings
