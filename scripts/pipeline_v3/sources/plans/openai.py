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
    specs = (PlanSpec("plus", "ChatGPT Plus", r"(?:ChatGPT\s+)?Plus\b", "general_ai", "subscription", "USD", featured_on_home=True),)
    _plans = (("free", "ChatGPT Free", "免费版"), ("go", "ChatGPT Go", "Go"), ("plus", "ChatGPT Plus", "Plus"), ("pro", "ChatGPT Pro", "Pro"))

    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        text = visible_text(raw)
        features = {
            "免费版": ("GPT-5.6 Luna 文本聊天", "带上传功能的消息数量受限", "图像生成受限", "语音聊天数量受限", "有限使用深度研究", "记忆与上下文支持受限", "Codex 的有限使用"),
            "Go": ("包含工具调用的消息数量更多", "更高的上传额度", "更高的图片生成额度", "语音聊天数量更多", "更长的记忆"),
            "Plus": ("GPT-5.6 的高级推理模型", "更高的消息与上传配额", "更复杂、更精准的图像生成", "增强版深度研究", "记忆与上下文支持更强", "项目、计划任务和自定义 GPT", "更高的 Codex 使用量", "抢先体验新功能"),
            "Pro": ("5 倍或 20 倍的使用配额", "GPT-5.6 Sol Pro 专业推理", "Codex 最大任务量", "无限制且更快速的图像生成", "最高级别的深度研究", "最大记忆与上下文支持", "更高的项目、任务和自定义 GPT 配额", "新功能的研究预览"),
        }
        plans = []
        for slug, product_name, label in self._plans:
            anchors = {"免费版": "免费版 日常任务", "Go": "Go 扩展访问权限", "Plus": "Plus 以更先进", "Pro": "Pro 大幅提升"}
            start = text.find(anchors[label])
            if start < 0 and label == "Plus":
                start = text.find("Plus")
            if start < 0: continue
            window = text[start:start + 1800]
            price_match = re.search(r"(?:SGD|USD|\$)\s*([0-9]+(?:\.[0-9]+)?)\s*/?\s*(?:月|mo(?:nth)?)", window, re.I)
            is_free = label == "免费版"
            if not price_match and not is_free: continue
            price = 0.0 if is_free else float(price_match.group(1))
            currency = "SGD" if price_match and "SGD" in price_match.group(0).upper() else "USD"
            plans.append(Plan(plan_id=f"openai/chatgpt/{slug}", provider_id="openai", provider_name="OpenAI", product_name=product_name, plan_category="general_ai", billing_type="subscription", is_free=is_free, price_amount=price, monthly_equivalent=price, currency=currency, billing_cadence="monthly", purchase_url=self.source_url, source_url=self.source_url, source_kind="browser", fetched_at=fetched_at, featured_on_home=slug == "plus", features=tuple(x for x in features[label] if x in window), raw={"official_text": window}))
        return require_complete_prices(plans, self.minimum_plan_count, self.source)
