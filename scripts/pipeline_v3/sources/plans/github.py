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


def _github_features(window: str, plan_name: str) -> tuple[str, ...]:
    """Parse the individual-plan card contents shown under the red-marked area."""
    labels = {
        "Copilot Free": (
            (r"([\d,]+) completions? per month", lambda m: f"代码补全：每月 {m.group(1)} 次"),
            (r"Access to Haiku 4\.5, GPT-5 mini, and more", lambda _: "模型访问：Haiku 4.5、GPT-5 mini 等"),
            (r"Copilot CLI", lambda _: "Copilot CLI"),
            (r"Community Support", lambda _: "社区支持"),
        ),
        "Copilot Pro": (
            (r"Access to Cloud agent and code review", lambda _: "云端 Agent 与代码审查"),
            (r"Unlimited code completion and next edit suggestions", lambda _: "无限代码补全与下一步编辑建议"),
            (r"Access to 3rd party agents \(Claude Code and Codex\)", lambda _: "第三方 Agent：Claude Code 与 Codex"),
            (r"Model selection", lambda _: "模型选择"),
            (r"\$15 monthly total credits for Pro", lambda _: "每月 15 美元 GitHub AI Credits"),
        ),
        "Copilot Pro+": (
            (r"Access to premium models, including Opus", lambda _: "高级模型访问：包括 Opus"),
            (r"Audit logs", lambda _: "审计日志"),
            (r"4x\+ included usage than Pro", lambda _: "包含用量达到 Pro 的 4 倍以上"),
            (r"\$70 monthly total credits for Pro\+", lambda _: "每月 70 美元 GitHub AI Credits"),
        ),
        "Copilot Max": (
            (r"Priority access to new models and features", lambda _: "优先体验新模型和新功能"),
            (r"([\d.]+)x\+ included usage than Pro\+", lambda m: f"包含用量达到 Pro+ 的 {m.group(1)} 倍以上"),
            (r"\$200 monthly total credits for Max", lambda _: "每月 200 美元 GitHub AI Credits"),
        ),
    }
    result = []
    for pattern, builder in labels.get(plan_name, ()):
        match = re.search(pattern, window, flags=re.I)
        if match:
            value = builder(match)
            if value not in result:
                result.append(value)
    return tuple(result)


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
                features=_github_features(window, name),
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
                rf"{re.escape(name)}\s+at\s+(\$\s*[0-9.]+\s+USD\s+per\s+user\s+per\s+month),\s+includes\s+([^.]*)\.",
                text,
                flags=re.I,
            )
            if not match:
                continue
            price = monthly_usd(match.group(1))
            benefits = match.group(2)
            features = []
            credits = re.search(r"([\d,]+)\s+AI credits", benefits, flags=re.I)
            if credits:
                features.append(f"每用户包含 {credits.group(1)} AI Credits")
            if re.search(r"broad model catalog", benefits, flags=re.I):
                features.append("广泛的模型目录")
            if re.search(r"priority access to new models and features", benefits, flags=re.I):
                features.append("优先体验新模型和新功能")
            plans.append(Plan(
                plan_id=f"githubcopilot/copilot/{slug}", provider_id="githubcopilot",
                provider_name="GitHub Copilot", product_name=name,
                plan_category="coding_tool", billing_type="subscription", is_free=False,
                price_amount=price, monthly_equivalent=price, currency="USD",
                billing_cadence="monthly", purchase_url=self.source_url,
                source_url=self.source_url, source_kind="html", fetched_at=fetched_at,
                features=tuple(features),
                raw={"official_text": match.group(0)},
            ))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
