"""Official OpenAI commercial-plan adapters.

OpenAI's Help Center articles are used instead of geo-localized pricing pages.
The parsers fail closed when the official wording/prices disappear; they never
substitute a remembered price.
"""

from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter, visible_text


def _plan(*, plan_id: str, product_name: str, fetched_at: str, source_url: str,
          price_amount: float | None, billing_cadence: str = "monthly",
          monthly_equivalent: float | None = None, price_status: str = "priced",
          price_scope: str = "per_account", seat_type: str | None = None,
          minimum_seats: int | None = None, featured_on_home: bool = False,
          features: tuple[str, ...] = (),
          official_text: str = "") -> Plan:
    is_free = price_status == "free"
    return Plan(
        plan_id=plan_id,
        provider_id="openai",
        provider_name="OpenAI",
        product_name=product_name,
        plan_category="general_ai",
        billing_type="subscription",
        is_free=is_free,
        price_amount=price_amount,
        monthly_equivalent=monthly_equivalent if monthly_equivalent is not None else price_amount,
        currency="USD",
        billing_cadence=billing_cadence,
        purchase_url=source_url,
        source_url=source_url,
        source_kind="static",
        fetched_at=fetched_at,
        featured_on_home=featured_on_home,
        features=features,
        market="global",
        seat_type=seat_type,
        minimum_seats=minimum_seats,
        price_status=price_status,
        price_scope=price_scope,
        raw={"official_text": official_text},
    )


def _usd_amounts(text: str) -> set[float]:
    return {float(value) for value in re.findall(r"(?:US)?\$\s*(\d+(?:\.\d+)?)", text, flags=re.I)}


class OpenAIProPlanAdapter(OfficialPlanAdapter):
    source = "openai_chatgpt_pro"
    source_url = "https://help.openai.com/en/articles/9793128"
    minimum_plan_count = 2

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        amounts = _usd_amounts(text)
        folded = text.lower()
        if 100.0 not in amounts or 200.0 not in amounts or "5x" not in folded or "20x" not in folded:
            raise ValueError(f"{self.source}: missing official Pro 5x/20x pricing markers")
        return [
            _plan(plan_id="openai/chatgpt/pro-5x", product_name="ChatGPT Pro 5x",
                  fetched_at=fetched_at, source_url=self.source_url, price_amount=100,
                  features=("5 倍使用配额", "高级推理模型", "更高 Codex 使用量", "高级图像生成", "深度研究"),
                  official_text=text),
            _plan(plan_id="openai/chatgpt/pro-20x", product_name="ChatGPT Pro 20x",
                  fetched_at=fetched_at, source_url=self.source_url, price_amount=200,
                  features=("20 倍使用配额", "高级推理模型", "更高 Codex 使用量", "高级图像生成", "深度研究"),
                  official_text=text),
        ]


class OpenAIBusinessPlanAdapter(OfficialPlanAdapter):
    source = "openai_chatgpt_business"
    source_url = "https://help.openai.com/en/articles/8792536"
    minimum_plan_count = 4

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        amounts = _usd_amounts(text)
        folded = text.lower()
        if 25.0 not in amounts or 20.0 not in amounts or "codex" not in folded or "credit" not in folded:
            raise ValueError(f"{self.source}: missing official Business pricing markers")
        if "enterprise" not in folded or "2" not in text:
            raise ValueError(f"{self.source}: missing Business seat/Enterprise markers")
        return [
            _plan(plan_id="openai/chatgpt/business-monthly", product_name="ChatGPT Business（月付）",
                  fetched_at=fetched_at, source_url=self.source_url, price_amount=25,
                  price_scope="per_user", seat_type="standard_seat", minimum_seats=2,
                  features=("团队工作空间", "统一账单", "管理控制台", "Codex 与 AI Credits"),
                  official_text=text),
            _plan(plan_id="openai/chatgpt/business-annual", product_name="ChatGPT Business（年付）",
                  fetched_at=fetched_at, source_url=self.source_url, price_amount=240,
                  monthly_equivalent=20, billing_cadence="annual", price_scope="per_user",
                  seat_type="standard_seat", minimum_seats=2,
                  features=("团队工作空间", "统一账单", "管理控制台", "Codex 与 AI Credits"), official_text=text),
            _plan(plan_id="openai/chatgpt/business-codex-seat", product_name="ChatGPT Business Codex Seat",
                  fetched_at=fetched_at, source_url=self.source_url, price_amount=None,
                  monthly_equivalent=None, price_status="usage_based", price_scope="usage_based",
                  seat_type="codex_seat", official_text=text),
            _plan(plan_id="openai/chatgpt/enterprise", product_name="ChatGPT Enterprise",
                  fetched_at=fetched_at, source_url=self.source_url, price_amount=None,
                  monthly_equivalent=None, price_status="contact_sales", price_scope="per_seat",
                  seat_type="enterprise_seat", features=("企业级安全与管理", "专属工作空间", "管理员控制台", "企业隐私与合规"), official_text=text),
        ]
