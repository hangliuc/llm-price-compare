from __future__ import annotations

from collections import Counter
from typing import Iterable

from scripts.pipeline_v3.models import ModelOffer, Plan


class ValidationError(ValueError):
    pass


def validate_offers(offers: Iterable[ModelOffer], minimum_count: int = 1,
                    previous_count: int | None = None,
                    maximum_drop_ratio: float = 0.20) -> list[ModelOffer]:
    offers = list(offers)
    if len(offers) < minimum_count:
        raise ValidationError(
            f"offer count {len(offers)} is below minimum {minimum_count}")
    duplicates = [key for key, count in Counter(x.offer_id for x in offers).items() if count > 1]
    if duplicates:
        raise ValidationError(f"duplicate offer_id: {duplicates[:5]}")
    for item in offers:
        if not item.provider_id or not item.model_id or not item.model_name:
            raise ValidationError(f"offer identity is incomplete: {item.offer_id}")
        if item.currency not in {"USD", "CNY"}:
            raise ValidationError(f"unsupported currency: {item.currency}")
        if item.input_per_1m is None and item.output_per_1m is None:
            raise ValidationError(f"offer has no input/output price: {item.offer_id}")
        for value in (item.input_per_1m, item.output_per_1m,
                      item.cache_read_per_1m, item.cache_write_per_1m):
            if value is not None and value < 0:
                raise ValidationError(f"negative price: {item.offer_id}")
    if previous_count:
        drop_ratio = max(0, previous_count - len(offers)) / previous_count
        if drop_ratio > maximum_drop_ratio:
            raise ValidationError(
                f"offer count dropped {drop_ratio:.1%}, limit is {maximum_drop_ratio:.1%}")
    return offers


def validate_plans(plans: Iterable[Plan], minimum_count: int = 1,
                   previous_count: int | None = None,
                   maximum_drop_ratio: float = 0.20) -> list[Plan]:
    plans = list(plans)
    if len(plans) < minimum_count:
        raise ValidationError(f"plan count {len(plans)} is below minimum {minimum_count}")
    duplicates = [key for key, count in Counter(x.plan_id for x in plans).items() if count > 1]
    if duplicates:
        raise ValidationError(f"duplicate plan_id: {duplicates[:5]}")
    for item in plans:
        if not item.provider_id or not item.product_name or not item.source_url:
            raise ValidationError(f"plan identity/source is incomplete: {item.plan_id}")
        if item.billing_type not in {"subscription", "coding_plan"}:
            raise ValidationError(f"unsupported billing_type: {item.plan_id}")
        if item.plan_category not in {"general_ai", "coding_tool", "developer_api"}:
            raise ValidationError(f"unsupported plan_category: {item.plan_id}")
        if item.price_amount is not None and item.price_amount < 0:
            raise ValidationError(f"negative plan price: {item.plan_id}")
        if item.is_free and item.price_amount not in (0, 0.0):
            raise ValidationError(f"free plan has non-zero price: {item.plan_id}")
    if previous_count:
        drop_ratio = max(0, previous_count - len(plans)) / previous_count
        if drop_ratio > maximum_drop_ratio:
            raise ValidationError(
                f"plan count dropped {drop_ratio:.1%}, limit is {maximum_drop_ratio:.1%}")
    return plans
