from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import (
    OfficialPlanAdapter,
    monthly_usd,
    product_window,
    require_complete_prices,
    visible_text,
)


class KiroPlanAdapter(OfficialPlanAdapter):
    source = "kiro_plans"
    source_url = "https://kiro.dev/pricing/"
    minimum_plan_count = 5

    _PRODUCTS = (
        ("free", "Kiro Free", "KIRO FREE", True),
        ("pro", "Kiro Pro", "KIRO PRO", False),
        ("pro-plus", "Kiro Pro+", "KIRO PRO+", False),
        ("pro-max", "Kiro Pro Max", "KIRO PRO MAX", False),
        ("power", "Kiro Power", "KIRO POWER", False),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        labels = tuple(product[2] for product in self._PRODUCTS)
        plans: list[Plan] = []
        for index, (slug, product_name, label, is_free) in enumerate(self._PRODUCTS):
            window = product_window(text, label, labels[index + 1:], width=500)
            if not window:
                continue
            price = monthly_usd(window, free=is_free)
            quota_match = re.search(r"([0-9][0-9,]*)\s+credits?", window, flags=re.I)
            quota = float(quota_match.group(1).replace(",", "")) if quota_match else None
            plans.append(Plan(
                plan_id=f"kiro/kiro/{slug}",
                provider_id="kiro",
                provider_name="Kiro",
                product_name=product_name,
                plan_category="coding_tool",
                billing_type="subscription",
                is_free=is_free,
                price_amount=price,
                monthly_equivalent=price,
                currency="USD",
                billing_cadence="monthly",
                included_quota=quota,
                quota_unit="credits" if quota is not None else None,
                quota_period="monthly" if quota is not None else None,
                purchase_url=self.source_url,
                source_url=self.source_url,
                source_kind="html",
                fetched_at=fetched_at,
                raw={"official_text": window},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
