from __future__ import annotations

import re

from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter, require_complete_prices, visible_text
from scripts.pipeline_v3.sources.plans.declarative import PlanSpec


class OpenAIPlanAdapter(OfficialPlanAdapter):
    fetch_mode = "browser"
    source = "openai_chatgpt_plus"
    source_url = "https://openai.com/chatgpt/pricing/"
    minimum_plan_count = 1
    # chatgpt.com renders the lower tiers lazily.  Do not snapshot the page
    # until all personal pricing-card headings are visible; a one-card result
    # would otherwise overwrite the published catalogue with only Free.
    render_settle_ms = 5000
    render_ready_headings = ("Free", "Go", "Plus", "Pro")
    render_scroll_to_bottom = True
    # ChatGPT returns localized billing currencies.  Fix this source to the
    # US English storefront so VPN/server region does not turn the catalogue
    # into SGD (or another local currency).
    browser_locale = "en-US"
    specs = (PlanSpec("plus", "ChatGPT Plus", r"(?:ChatGPT\s+)?Plus\b", "general_ai", "subscription", "USD", featured_on_home=True),)
    _plans = (("free", "ChatGPT Free", "Free"), ("go", "ChatGPT Go", "Go"), ("plus", "ChatGPT Plus", "Plus"), ("pro", "ChatGPT Pro", "Pro"))
    _price_pattern = re.compile(
        r"(?:起价\s*)?(?:SGD|USD|\$)\s*([0-9]+(?:\.[0-9]+)?)\s*/?\s*(?:月|mo(?:nth)?)",
        re.I,
    )

    @staticmethod
    def _plan_window(text: str, label: str) -> str:
        """Find a pricing-card occurrence, not a menu or comparison-table label."""
        aliases = ("Free", "免费版") if label == "Free" else (label,)
        plan_labels = tuple(
            alias
            for _, _, plan_label in OpenAIPlanAdapter._plans
            for alias in (("Free", "免费版") if plan_label == "Free" else (plan_label,))
        )
        for alias in aliases:
            pattern = re.escape(alias) if alias == "免费版" else rf"\b{re.escape(alias)}\b"
            for match in re.finditer(pattern, text, flags=re.I):
                window = text[match.start():match.start() + 1800]
                price_match = OpenAIPlanAdapter._price_pattern.search(window)
                if not price_match:
                    continue
            # Header/navigation text contains all plan names before the Free
            # card.  It must not be associated with the first price that
            # happens to follow it (SGD 0), otherwise every paid tier becomes
            # zero-priced.  A genuine card reaches its own price before any
            # other card heading.
                before_price = window[:price_match.start()]
                other_labels = (name for name in plan_labels if name not in aliases)
                if any(
                    re.search(
                        re.escape(other) if other == "免费版" else rf"\b{re.escape(other)}\b",
                        before_price,
                        flags=re.I,
                    )
                    for other in other_labels
                ):
                    continue
                return window
        return ""

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        features = {
            "Free": ("GPT-5.6 Luna 文本聊天", "带上传功能的消息数量受限", "图像生成受限", "语音聊天数量受限", "有限使用深度研究", "记忆与上下文支持受限", "Codex 的有限使用"),
            "Go": ("包含工具调用的消息数量更多", "更高的上传额度", "更高的图片生成额度", "语音聊天数量更多", "更长的记忆"),
            "Plus": ("GPT-5.6 的高级推理模型", "更高的消息与上传配额", "更复杂、更精准的图像生成", "增强版深度研究", "记忆与上下文支持更强", "项目、计划任务和自定义 GPT", "更高的 Codex 使用量", "抢先体验新功能"),
            "Pro": ("5 倍或 20 倍的使用配额", "GPT-5.6 Sol Pro 专业推理", "Codex 最大任务量", "无限制且更快速的图像生成", "最高级别的深度研究", "最大记忆与上下文支持", "更高的项目、任务和自定义 GPT 配额", "新功能的研究预览"),
        }
        plans = []
        for slug, product_name, label in self._plans:
            window = self._plan_window(text, label)
            if not window: continue
            price_match = self._price_pattern.search(window)
            is_free = label == "Free"
            if not price_match and not is_free: continue
            price = 0.0 if is_free else float(price_match.group(1))
            currency = "SGD" if price_match and "SGD" in price_match.group(0).upper() else "USD"
            plans.append(Plan(plan_id=f"openai/chatgpt/{slug}", provider_id="openai", provider_name="OpenAI", product_name=product_name, plan_category="general_ai", billing_type="subscription", is_free=is_free, price_amount=price, monthly_equivalent=price, currency=currency, billing_cadence="monthly", purchase_url=self.source_url, source_url=self.source_url, source_kind="browser", fetched_at=fetched_at, featured_on_home=slug == "plus", features=tuple(x for x in features[label] if x in window), raw={"official_text": window}))
        # Help Center fixtures intentionally expose Plus only. A real pricing
        # page must yield all personal cards, otherwise retain last-known-good
        # plans rather than publishing a destructive partial result.
        expected = 4 if "Free" in text or "免费版" in text else self.minimum_plan_count
        return require_complete_prices(plans, expected, self.source)
