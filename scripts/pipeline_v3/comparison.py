"""Derive reproducible CNY comparison values without mutating official prices."""

from __future__ import annotations

from dataclasses import replace
from typing import Iterable

from scripts.pipeline_v3.fx import FxSnapshot
from scripts.pipeline_v3.models import ModelOffer, Plan


def apply_comparison_values(offers: Iterable[ModelOffer], plans: Iterable[Plan],
                            fx: FxSnapshot) -> tuple[list[ModelOffer], list[Plan]]:
    return (
        [_offer_with_comparison(item, fx) for item in offers],
        [_plan_with_comparison(item, fx) for item in plans],
    )


def _offer_with_comparison(item: ModelOffer, fx: FxSnapshot) -> ModelOffer:
    rate = fx.rate_to_cny(item.currency)
    values = {
        "comparison_input_per_1m": _convert(item.input_per_1m, rate),
        "comparison_output_per_1m": _convert(item.output_per_1m, rate),
        "comparison_cache_read_per_1m": _convert(item.cache_read_per_1m, rate),
        "comparison_cache_write_per_1m": _convert(item.cache_write_per_1m, rate),
    }
    return replace(
        item,
        comparison_currency="CNY",
        comparison_fx_rate=rate,
        comparison_fx_date=fx.published_date if rate is not None else None,
        **values,
    )


def _plan_with_comparison(item: Plan, fx: FxSnapshot) -> Plan:
    rate = fx.rate_to_cny(item.currency)
    # Free is a real zero. Usage/contact-sales products deliberately keep no
    # comparison price so they cannot participate in monthly-price ordering.
    source_amount = item.monthly_equivalent
    if source_amount is None and item.billing_cadence == "monthly":
        source_amount = item.price_amount
    if item.price_status not in {"priced", "free"}:
        source_amount = None
    return replace(
        item,
        comparison_currency="CNY" if rate is not None else None,
        comparison_fx_rate=rate,
        comparison_fx_date=fx.published_date if rate is not None else None,
        comparison_monthly_amount=_convert(source_amount, rate),
    )


def _convert(value: float | None, rate: float | None) -> float | None:
    if value is None or rate is None:
        return None
    return float(value) * float(rate)
