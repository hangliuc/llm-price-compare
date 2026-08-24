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
    # `hl=en-US` only changes language; the default endpoint still derives
    # billing currency from the crawler's IP.  The intl/en_us endpoint is
    # Google's dedicated US storefront and provides the USD catalogue.
    source_url = "https://one.google.com/intl/en_us/about/google-ai-plans/"
    fetch_mode = "browser"
    minimum_plan_count = 3
    render_settle_ms = 3500
    render_ready_headings = ("Google AI Plus", "Google AI Pro", "Google AI Ultra")
    render_scroll_to_bottom = True
    browser_locale = "en-US"
    browser_timezone_id = "America/New_York"
    browser_geolocation = (40.7128, -74.0060)
    _plans = (
        ("plus", "Google AI Plus"),
        ("pro", "Google AI Pro"),
        ("ultra", "Google AI Ultra"),
    )

    @staticmethod
    def _regional_price(window: str) -> tuple[float | None, str | None]:
        patterns = (
            ("USD", re.compile(
                r"(?:From\s+)?\$\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*mo", re.I)),
            ("USD", re.compile(
                r"(?:From\s+)?USD\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*mo", re.I)),
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
