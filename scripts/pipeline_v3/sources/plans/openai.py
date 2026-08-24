from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter, require_complete_prices, visible_text
from scripts.pipeline_v3.sources.plans.declarative import PlanSpec


class OpenAIPlanAdapter(OfficialPlanAdapter):
    """US-dollar ChatGPT plans from OpenAI's worldwide Go announcement.

    The interactive pricing page localizes prices by requester network region.
    The official worldwide launch announcement states the US prices explicitly,
    making it the canonical source for this USD-only catalogue.
    """

    fetch_mode = "browser"
    source = "openai_chatgpt_plus"
    source_url = "https://openai.com/index/introducing-chatgpt-go/"
    purchase_url = "https://openai.com/chatgpt/pricing/"
    minimum_plan_count = 4
    render_settle_ms = 3500
    browser_locale = "en-US"
    browser_timezone_id = "America/New_York"
    browser_geolocation = (40.7128, -74.0060)
    specs = (
        PlanSpec("plus", "ChatGPT Plus", r"ChatGPT Plus", "general_ai", "subscription", "USD", featured_on_home=True),
    )
    _price_patterns = {
        "go": re.compile(r"ChatGPT\s+Go\s+at\s+\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:USD\s*)?/?\s*month", re.I),
        "plus": re.compile(r"ChatGPT\s+Plus\s+at\s+\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:USD\s*)?/?\s*month", re.I),
        "pro": re.compile(r"ChatGPT\s+Pro\s+at\s+\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:USD\s*)?/?\s*month", re.I),
    }
    _plans = (
        ("free", "ChatGPT Free", 0.0, ("免费使用", "基础聊天与工具访问")),
        ("go", "ChatGPT Go", None, ("消息、文件上传和图像生成额度为免费版的 10 倍", "更长的记忆与上下文")),
        ("plus", "ChatGPT Plus", None, ("高级推理模型", "更高的消息、上传、记忆与上下文额度", "可使用 Codex")),
        ("pro", "ChatGPT Pro", None, ("最强模型的完整访问权限", "最大记忆与上下文", "新功能抢先预览")),
    )

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        plans: list[Plan] = []
        for slug, product_name, fixed_price, features in self._plans:
            if fixed_price is None:
                match = self._price_patterns[slug].search(text)
                if not match:
                    continue
                price = float(match.group(1))
            else:
                price = fixed_price
            plans.append(
                Plan(
                    plan_id=f"openai/chatgpt/{slug}",
                    provider_id="openai",
                    provider_name="OpenAI",
                    product_name=product_name,
                    plan_category="general_ai",
                    billing_type="subscription",
                    is_free=slug == "free",
                    price_amount=price,
                    monthly_equivalent=price,
                    currency="USD",
                    billing_cadence="monthly",
                    purchase_url=self.purchase_url,
                    source_url=self.source_url,
                    source_kind="browser",
                    fetched_at=fetched_at,
                    featured_on_home=slug == "plus",
                    features=features,
                    raw={"official_text": text},
                )
            )
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
