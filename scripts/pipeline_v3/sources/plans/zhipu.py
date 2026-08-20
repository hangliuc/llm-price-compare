from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter, require_complete_prices, visible_text


class ZhipuPlanAdapter(OfficialPlanAdapter):
    fetch_mode = "browser"
    source = "zhipu_plans"
    source_url = "https://www.bigmodel.cn/glm-coding"
    minimum_plan_count = 3
    _plans = (
        ("lite", "Lite", "GLM Coding Plan Lite", False),
        ("pro", "Pro", "GLM Coding Plan Pro", True),
        ("max", "Max", "GLM Coding Plan Max", False),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        positions = []
        for _, label, _, _ in self._plans:
            match = re.search(rf"\b{re.escape(label)}\b", text, re.I)
            positions.append(match.start() if match else -1)
        plans: list[Plan] = []
        for index, (slug, label, product_name, featured) in enumerate(self._plans):
            start = positions[index]
            next_start = positions[index + 1] if index + 1 < len(positions) else len(text)
            window = text[start:min(next_start, start + 650)] if start >= 0 else ""
            prices = [
                float(value)
                for value in re.findall(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*月", window)
            ]
            # The page shows discounted cadence prices before the standard
            # monthly price. The largest displayed monthly amount is the
            # undiscounted month-to-month price used by the catalog.
            price = max(prices) if prices else None
            plans.append(Plan(
                plan_id=f"zhipu/coding-plan/{slug}",
                provider_id="zhipu", provider_name="智谱",
                product_name=product_name, plan_category="coding_tool",
                billing_type="coding_plan", is_free=False,
                price_amount=price, monthly_equivalent=price, currency="CNY",
                billing_cadence="monthly", purchase_url=self.source_url,
                source_url=self.source_url, source_kind="browser",
                fetched_at=fetched_at, featured_on_home=featured,
                raw={"official_text": window, "displayed_monthly_prices": prices},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
