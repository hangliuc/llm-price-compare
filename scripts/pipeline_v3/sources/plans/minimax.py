from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter, require_complete_prices, visible_text


class MiniMaxPlanAdapter(OfficialPlanAdapter):
    # The official page embeds the current public plan table in its server-side
    # FAQ payload. Browser-visible text can omit that payload after a UI change,
    # while the HTML remains a stable first-party source.
    fetch_mode = "static"
    source = "minimax_plans"
    source_url = "https://platform.minimaxi.com/subscribe/token-plan"
    minimum_plan_count = 3
    _plans = (
        ("plus", "Plus", "MiniMax Token Plan Plus"),
        ("max", "Max", "MiniMax Token Plan Max"),
        ("ultra", "Ultra", "MiniMax Token Plan Ultra"),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        html = raw.decode("utf-8", errors="replace")
        visible = visible_text(raw)
        table_start = visible.find("哪个计划更适合你")
        table_end = visible.find("积分购买", table_start)
        visible_table = visible[table_start:table_end] if table_start >= 0 and table_end > table_start else ""

        # MiniMax currently publishes the three tier prices in a table inside
        # the official `available-plans` FAQ. Keep parsing restricted to that
        # record rather than accepting unrelated marketing prices elsewhere.
        faq_start = html.find('"id":"available-plans"')
        faq = html[faq_start:faq_start + 2400] if faq_start >= 0 else ""
        plans: list[Plan] = []
        for slug, label, product_name in self._plans:
            match = re.search(
                rf"\|\s*{label}\s*\|\s*[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*月",
                faq,
                re.I,
            ) or re.search(
                rf"\b{label}\b\s*[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*月",
                visible_table,
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
                source_url=self.source_url, source_kind="static",
                fetched_at=fetched_at,
                raw={"official_text": match.group(0) if match else (faq or visible_table)},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
