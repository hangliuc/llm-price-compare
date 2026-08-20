from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter, require_complete_prices, visible_text


class QwenTokenPlanAdapter(OfficialPlanAdapter):
    source = "qwen_token_plans"
    source_url = "https://www.aliyun.com/benefit/scene/tokenplan"
    fetch_mode = "browser"
    minimum_plan_count = 3
    _plans = (
        ("lite", "Lite版本", "百炼 Token Plan Lite"),
        ("standard", "Standard版本", "百炼 Token Plan Standard"),
        ("pro", "Pro版本", "百炼 Token Plan Pro"),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = re.sub(r"(?<=\d)\s*\.\s*(?=\d)", ".", visible_text(raw))
        positions = [text.find(label) for _, label, _ in self._plans]
        plans: list[Plan] = []
        for index, (slug, _, product_name) in enumerate(self._plans):
            start = positions[index]
            next_start = positions[index + 1] if index + 1 < len(positions) else len(text)
            window = text[start:min(next_start, start + 850)] if start >= 0 else ""
            match = re.search(
                r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*1\s*个?月", window)
            price = float(match.group(1)) if match else None
            plans.append(Plan(
                plan_id=f"qwen/token-plan/{slug}",
                provider_id="qwen", provider_name="阿里通义",
                product_name=product_name, plan_category="developer_api",
                billing_type="coding_plan", is_free=False,
                price_amount=price, monthly_equivalent=price, currency="CNY",
                billing_cadence="monthly", purchase_url=self.source_url,
                source_url=self.source_url, source_kind="browser",
                fetched_at=fetched_at,
                raw={"official_text": window},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)


__all__ = ["QwenTokenPlanAdapter"]
