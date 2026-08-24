"""Official model-offer adapters.

Adapters in this package add verified, market-specific official offers.
For domestic providers, the published catalogue is mainland-only.
"""

from scripts.pipeline_v3.sources.official_offers.deepseek import DeepSeekPricingAdapter
from scripts.pipeline_v3.sources.official_offers.kimi import KIMI_MAINLAND_PRICING_PAGES, KimiPricingAdapter
from scripts.pipeline_v3.sources.official_offers.minimax import MINIMAX_PRICING_PAGES, MiniMaxPricingAdapter
from scripts.pipeline_v3.sources.official_offers.qwen import QwenModelStudioAdapter
from scripts.pipeline_v3.sources.official_offers.xiaomi import XiaomiMiMoMainlandPricingAdapter
from scripts.pipeline_v3.sources.official_offers.zhipu import ZhipuMainlandPricingAdapter


def experimental_official_offer_adapters(timeout_seconds: int = 45):
    """Adapters that have parser coverage but are not release-blocking yet."""

    return [
        QwenModelStudioAdapter(timeout_seconds=timeout_seconds),
        DeepSeekPricingAdapter(timeout_seconds=timeout_seconds),
        ZhipuMainlandPricingAdapter(timeout_seconds=timeout_seconds),
        XiaomiMiMoMainlandPricingAdapter(timeout_seconds=timeout_seconds),
        *(KimiPricingAdapter(page, timeout_seconds=timeout_seconds) for page in KIMI_MAINLAND_PRICING_PAGES),
        *(MiniMaxPricingAdapter(page, timeout_seconds=timeout_seconds) for page in MINIMAX_PRICING_PAGES),
    ]


__all__ = [
    "DeepSeekPricingAdapter", "KIMI_MAINLAND_PRICING_PAGES", "KimiPricingAdapter",
    "MINIMAX_PRICING_PAGES", "MiniMaxPricingAdapter",
    "QwenModelStudioAdapter", "XiaomiMiMoMainlandPricingAdapter",
    "ZhipuMainlandPricingAdapter", "experimental_official_offer_adapters",
]
