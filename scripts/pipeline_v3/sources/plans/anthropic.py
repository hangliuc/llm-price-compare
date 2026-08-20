from __future__ import annotations

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import (
    OfficialPlanAdapter,
    monthly_usd,
    product_window,
    require_complete_prices,
    visible_text,
)


class AnthropicPlanAdapter(OfficialPlanAdapter):
    source = "anthropic_plans"
    source_url = "https://support.claude.com/en/articles/11049762-choosing-a-claude-plan"
    minimum_plan_count = 3

    _PRODUCTS = (
        ("pro", "Claude Pro", "Pro", True),
        ("max-5x", "Claude Max 5x", "Max 5x", False),
        ("max-20x", "Claude Max 20x", "Max 20x", False),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        table_start = text.find("Plan Price Billing Interval")
        if table_start < 0:
            raise ValueError("anthropic_plans: official comparison table was not found")
        text = text[table_start:]
        labels = tuple(product[2] for product in self._PRODUCTS)
        plans: list[Plan] = []
        for index, (slug, name, label, featured) in enumerate(self._PRODUCTS):
            window = product_window(text, label, labels[index + 1:])
            if not window:
                continue
            price = monthly_usd(window)
            plans.append(Plan(
                plan_id=f"anthropic/claude/{slug}",
                provider_id="anthropic",
                provider_name="Anthropic",
                product_name=name,
                plan_category="general_ai",
                billing_type="subscription",
                is_free=False,
                price_amount=price,
                monthly_equivalent=price,
                currency="USD",
                billing_cadence="monthly",
                purchase_url=self.source_url,
                source_url=self.source_url,
                source_kind="html",
                fetched_at=fetched_at,
                featured_on_home=featured,
                raw={"official_text": window},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
