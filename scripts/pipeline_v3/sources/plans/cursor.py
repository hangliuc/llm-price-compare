from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import (
    OfficialPlanAdapter,
    require_complete_prices,
    visible_text,
)


class CursorPlanAdapter(OfficialPlanAdapter):
    source = "cursor_plans"
    source_url = "https://cursor.com/docs/models-and-pricing"
    minimum_plan_count = 3

    _PRODUCTS = (
        ("pro", "Cursor Pro", r"\bPro\b(?!\s*(?:Plus|\+))", False, True),
        ("pro-plus", "Cursor Pro+", r"\bPro\s*(?:Plus\b|\+)", False, False),
        ("ultra", "Cursor Ultra", r"\bUltra\b", False, False),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        full_text = visible_text(raw)
        text = full_text
        # Cursor localizes this page.  Anchor on the plan table itself rather
        # than on the English prose surrounding it.
        table_match = re.search(r"(?:Plan|方案)\s+(?:Price|价格)", text, flags=re.I)
        if table_match:
            text = text[table_match.start():table_match.start() + 900]
        else:
            # Retain compatibility with the previous English table markup.
            table_start = text.find("Start (India only)")
            table_end = text.find("Since different models", table_start)
            if table_start < 0 or table_end < 0:
                raise ValueError("cursor_plans: official plan table was not found")
            text = text[table_start:table_end]
        plans: list[Plan] = []
        for slug, product_name, label_pattern, is_free, featured in self._PRODUCTS:
            match = re.search(
                rf"{label_pattern}\s+(?:US)?\$\s*([0-9]+(?:\.[0-9]+)?)\s*/\s*(?:mo(?:nth)?|月)",
                text,
                flags=re.I,
            )
            if not match:
                continue
            # Keep the complete official pricing/features page for feature
            # extraction; the price regex still anchors on the plan table.
            window = full_text
            price = 0.0 if is_free else float(match.group(1))
            plans.append(Plan(
                plan_id=f"cursor/cursor/{slug}",
                provider_id="cursor",
                provider_name="Cursor",
                product_name=product_name,
                plan_category="coding_tool",
                billing_type="subscription",
                is_free=is_free,
                price_amount=price,
                monthly_equivalent=price,
                currency="USD",
                billing_cadence="monthly",
                purchase_url="https://cursor.com/pricing",
                source_url=self.source_url,
                source_kind="html",
                fetched_at=fetched_at,
                featured_on_home=featured,
                raw={"official_text": window},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)


class CursorHobbyPlanAdapter(OfficialPlanAdapter):
    source = "cursor_hobby_plan"
    source_url = "https://cursor.com/pricing"
    minimum_plan_count = 1

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        match = re.search(r"\bHobby\b.{0,120}\bFree\b", text, flags=re.I)
        if not match:
            raise ValueError("cursor_hobby_plan: Hobby Free marker was not found")
        return [Plan(
            plan_id="cursor/cursor/hobby", provider_id="cursor", provider_name="Cursor",
            product_name="Cursor Hobby", plan_category="coding_tool",
            billing_type="subscription", is_free=True, price_amount=0,
            monthly_equivalent=0, currency="USD", billing_cadence="monthly",
            purchase_url=self.source_url, source_url=self.source_url,
            source_kind="html", fetched_at=fetched_at,
            raw={"official_text": text},
        )]


class CursorTeamsPlanAdapter(OfficialPlanAdapter):
    source = "cursor_teams_plan"
    source_url = "https://cursor.com/docs/models-and-pricing"
    minimum_plan_count = 2

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        plans = []
        for slug, label in (("teams-standard", "Standard"), ("teams-premium", "Premium")):
            match = re.search(
                rf"{label}\s*\(\s*\$([0-9.]+)\s*/\s*(?:user|用户)\s*/\s*(?:mo|月)\s*\)",
                text,
                flags=re.I,
            )
            if not match:
                continue
            price = float(match.group(1))
            plans.append(Plan(
                plan_id=f"cursor/cursor/{slug}", provider_id="cursor", provider_name="Cursor",
                product_name=f"Cursor Teams {label}", plan_category="coding_tool",
                billing_type="subscription", is_free=False, price_amount=price,
                monthly_equivalent=price, currency="USD", billing_cadence="monthly",
                purchase_url="https://cursor.com/pricing", source_url=self.source_url,
                source_kind="html", fetched_at=fetched_at,
                raw={"official_text": text},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
