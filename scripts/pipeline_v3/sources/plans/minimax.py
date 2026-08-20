from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter, require_complete_prices, visible_text


class MiniMaxPlanAdapter(OfficialPlanAdapter):
    fetch_mode = "browser"
    source = "minimax_plans"
    source_url = "https://platform.minimaxi.com/subscribe/token-plan"
    minimum_plan_count = 3
    _plans = (
        ("plus", "Plus", "MiniMax Token Plan Plus"),
        ("max", "Max", "MiniMax Token Plan Max"),
        ("ultra", "Ultra", "MiniMax Token Plan Ultra"),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        table_start = text.find("哪个计划更适合你")
        table_end = text.find("积分购买", table_start)
        table = text[table_start:table_end] if table_start >= 0 and table_end > table_start else ""
        plans: list[Plan] = []
        for slug, label, product_name in self._plans:
            match = re.search(
                rf"\b{label}\b\s*[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*月",
                table,
                re.I,
            )
            price = float(match.group(1)) if match else None
            plans.append(Plan(
                plan_id=f"minimax/token-plan/{slug}",
                provider_id="minimax", provider_name="MiniMax",
                product_name=product_name, plan_category="developer_api",
                billing_type="coding_plan", is_free=False,
                price_amount=price, monthly_equivalent=price, currency="CNY",
                billing_cadence="monthly", purchase_url=self.source_url,
                source_url=self.source_url, source_kind="browser",
                fetched_at=fetched_at,
                raw={"official_text": match.group(0) if match else table},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
