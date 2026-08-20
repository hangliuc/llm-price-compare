from __future__ import annotations

from dataclasses import dataclass
import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import (
    OfficialPlanAdapter,
    monthly_usd,
    require_complete_prices,
    visible_text,
)


@dataclass(frozen=True)
class PlanSpec:
    slug: str
    product_name: str
    label_pattern: str
    plan_category: str
    billing_type: str
    currency: str
    is_free: bool = False
    featured_on_home: bool = False


_CNY_PATTERNS = (
    re.compile(r"[\u00a5￥]\s*([0-9]+(?:\.[0-9]+)?)\s*(?:/\s*月|每月|元\s*/\s*月)", re.I),
    re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*元\s*(?:/\s*月|每月)", re.I),
    re.compile(r"(?:月费|每月)\s*[:：]?\s*[\u00a5￥]?\s*([0-9]+(?:\.[0-9]+)?)\s*元?", re.I),
)


def monthly_price(window: str, currency: str, *, free: bool) -> float | None:
    if free:
        return 0.0
    if currency == "USD":
        return monthly_usd(window)
    if currency == "CNY":
        for pattern in _CNY_PATTERNS:
            match = pattern.search(window)
            if match:
                return float(match.group(1))
        return None
    raise ValueError(f"unsupported declarative plan currency: {currency}")


class DeclarativeHtmlPlanAdapter(OfficialPlanAdapter):
    provider_id: str
    provider_name: str
    product_family: str
    purchase_url: str
    specs: tuple[PlanSpec, ...]
    window_width = 700

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        matches: list[tuple[int, int, PlanSpec]] = []
        for spec in self.specs:
            match = re.search(spec.label_pattern, text, flags=re.I)
            if match:
                matches.append((match.start(), match.end(), spec))
        matches.sort(key=lambda item: item[0])
        plans: list[Plan] = []
        for index, (start, _, spec) in enumerate(matches):
            next_start = matches[index + 1][0] if index + 1 < len(matches) else len(text)
            window = text[start:min(next_start, start + self.window_width)]
            price = monthly_price(window, spec.currency, free=spec.is_free)
            plans.append(Plan(
                plan_id=f"{self.provider_id}/{self.product_family}/{spec.slug}",
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                product_name=spec.product_name,
                plan_category=spec.plan_category,
                billing_type=spec.billing_type,
                is_free=spec.is_free,
                price_amount=price,
                monthly_equivalent=price,
                currency=spec.currency,
                billing_cadence="monthly",
                purchase_url=self.purchase_url,
                source_url=self.source_url,
                source_kind=self.fetch_mode,
                fetched_at=fetched_at,
                featured_on_home=spec.featured_on_home,
                raw={"official_text": window},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
