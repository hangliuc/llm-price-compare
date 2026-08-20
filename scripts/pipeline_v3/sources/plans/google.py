from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import (
    OfficialPlanAdapter,
    require_complete_prices,
    visible_text,
)


class GooglePlanAdapter(OfficialPlanAdapter):
    source = "google_ai_plans"
    source_url = "https://one.google.com/about/google-ai-plans/?hl=en-US"
    fetch_mode = "browser"
    minimum_plan_count = 3
    _plans = (
        ("plus", "Google AI Plus"),
        ("pro", "Google AI Pro"),
        ("ultra", "Google AI Ultra"),
    )

    @staticmethod
    def _regional_price(window: str) -> tuple[float | None, str | None]:
        patterns = (
            ("SGD", re.compile(
                r"(?:From\s+)?(?:\$\s*)?(?:SGD\s*)?([0-9]+(?:\.[0-9]+)?)\s*SGD\s*/\s*mo",
                re.I,
            )),
            ("SGD", re.compile(
                r"SGD\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*mo", re.I)),
            ("USD", re.compile(
                r"(?:From\s+)?\$\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*mo", re.I)),
        )
        for currency, pattern in patterns:
            match = pattern.search(window)
            if match:
                return float(match.group(1)), currency
        return None, None

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        names = tuple(name for _, name in self._plans)
        plans: list[Plan] = []
        folded = text.casefold()
        heading_pattern = re.compile("|".join(re.escape(name) for name in names), re.I)
        for slug, name in self._plans:
            candidates: list[tuple[str, float, str]] = []
            start = 0
            while (position := folded.find(name.casefold(), start)) >= 0:
                next_heading = heading_pattern.search(text, position + len(name))
                end = min(len(text), position + 1200)
                if next_heading:
                    end = min(end, next_heading.start())
                window = text[position:end]
                price, currency = self._regional_price(window)
                if price is not None and currency:
                    candidates.append((window, price, currency))
                start = position + len(name)
            if not candidates:
                continue
            window, price, currency = candidates[0]
            plans.append(Plan(
                plan_id=f"google/google-ai/{slug}",
                provider_id="google", provider_name="Google", product_name=name,
                plan_category="general_ai", billing_type="subscription",
                is_free=False, price_amount=price, monthly_equivalent=price,
                currency=currency, billing_cadence="monthly",
                purchase_url=self.source_url, source_url=self.source_url,
                source_kind="browser", fetched_at=fetched_at,
                raw={"official_text": window},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
