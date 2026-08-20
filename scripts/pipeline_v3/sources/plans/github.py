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


class GitHubCopilotPlanAdapter(OfficialPlanAdapter):
    source = "github_copilot_plans"
    source_url = "https://github.com/features/copilot/plans"
    minimum_plan_count = 4

    _PRODUCTS = (
        ("copilot-free", "Copilot Free", False),
        ("copilot-pro", "Copilot Pro", False),
        ("copilot-pro-plus", "Copilot Pro+", False),
        ("copilot-max", "Copilot Max", False),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        start = text.find("Pricing plans For individuals")
        end = text.find("GitHub Copilot is available", start)
        if start < 0 or end < 0:
            raise ValueError("github_copilot_plans: individual pricing section was not found")
        text = text[start:end]
        labels = ("Free", "Pro", "Pro+", "Max")
        plans: list[Plan] = []
        for index, (slug, name, featured) in enumerate(self._PRODUCTS):
            window = product_window(text, labels[index], labels[index + 1:])
            if not window:
                continue
            is_free = name == "Copilot Free"
            price = monthly_usd(window, free=is_free)
            plans.append(Plan(
                plan_id=f"githubcopilot/copilot/{slug.removeprefix('copilot-')}",
                provider_id="githubcopilot",
                provider_name="GitHub Copilot",
                product_name=name,
                plan_category="coding_tool",
                billing_type="subscription",
                is_free=is_free,
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


class GitHubCopilotOrganizationPlanAdapter(OfficialPlanAdapter):
    source = "github_copilot_organization_plans"
    source_url = "https://docs.github.com/en/enterprise-cloud@latest/copilot/concepts/billing/organizations-and-enterprises"
    minimum_plan_count = 2

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        products = (("business", "Copilot Business"), ("enterprise", "Copilot Enterprise"))
        plans = []
        for slug, name in products:
            match = re.search(
                rf"{re.escape(name)}\s+at\s+(\$\s*[0-9.]+\s+USD\s+per\s+user\s+per\s+month)",
                text,
                flags=re.I,
            )
            if not match:
                continue
            price = monthly_usd(match.group(1))
            plans.append(Plan(
                plan_id=f"githubcopilot/copilot/{slug}", provider_id="githubcopilot",
                provider_name="GitHub Copilot", product_name=name,
                plan_category="coding_tool", billing_type="subscription", is_free=False,
                price_amount=price, monthly_equivalent=price, currency="USD",
                billing_cadence="monthly", purchase_url=self.source_url,
                source_url=self.source_url, source_kind="html", fetched_at=fetched_at,
                raw={"official_text": match.group(0)},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
