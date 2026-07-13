# scripts/sources/litellm.py
"""L1 主源：LiteLLM model_prices_and_context_window.json。

特点：
- 静态 JSON 文件，无鉴权，可缓存可 fork。
- 覆盖 9/12 厂商（缺 opencode/zhipu/xiaomi）。
- 价格为 per-token 科学计数法，需 ×1e6 转 per-1M。
- volcengine 价格为 0（社区占位数据），reconcile 层会降权。

数据源：https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json
"""
import logging
from typing import Optional

from scripts.core.fetcher import fetch_json
from scripts.core.models import Product, BillingType
from scripts.sources.base import SourceBase

log = logging.getLogger("sources.litellm")

_LITELLM_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)

# LiteLLM 的 litellm_provider 字段 -> 项目 provider_id
# 多个 litellm_provider 值会归并到同一个 provider_id 下
PROVIDER_MAP: dict[str, list[str]] = {
    "openai": ["openai"],
    "anthropic": ["anthropic"],
    "google": ["gemini", "vertex_ai-language-models", "vertex_ai"],
    "aws": ["bedrock"],
    "deepseek": ["deepseek"],
    "moonshot": ["moonshot"],
    "qwen": ["dashscope"],
    "volcengine": ["volcengine"],
    "minimax": ["minimax"],
    # opencode/zhipu/xiaomi: LiteLLM 未覆盖，走官网 Scraper 或 manual
}

# 反向映射：litellm_provider -> provider_id
_LITELLM_TO_PID: dict[str, str] = {}
for pid, providers in PROVIDER_MAP.items():
    for p in providers:
        _LITELLM_TO_PID[p] = pid


def _normalize_model_id(model_key: str) -> str:
    """清理模型 ID：
    - 去掉 litellm_provider/ 前缀（如 'dashscope/qwen-coder' -> 'qwen-coder'）
    - 去掉日期后缀（如 'claude-haiku-4-5-20251001' -> 'claude-haiku-4-5'）
    """
    mid = model_key.split("/", 1)[-1] if "/" in model_key else model_key
    # 去掉 8 位日期后缀
    import re
    mid = re.sub(r"-(\d{8})$", "", mid)
    return mid


def _to_per_m(per_token_cost: Optional[float]) -> Optional[float]:
    """per-token 科学计数法 -> per-1M-tokens。None 或 0 视为缺失。"""
    if per_token_cost is None or per_token_cost <= 0:
        return None
    return round(per_token_cost * 1_000_000, 6)


class LiteLLMSource(SourceBase):
    source_id = "litellm"
    covers = list(PROVIDER_MAP.keys())

    def fetch_all(self) -> dict[str, list[Product]]:
        log.info("fetching %s", _LITELLM_URL)
        data = fetch_json(_LITELLM_URL, timeout=60)

        # 顶层有 "sample_spec" 等元字段，模型条目是 dict 且含 litellm_provider
        result: dict[str, list[Product]] = {pid: [] for pid in PROVIDER_MAP}

        for model_key, entry in data.items():
            if not isinstance(entry, dict) or "litellm_provider" not in entry:
                continue

            litellm_provider = entry.get("litellm_provider", "")
            pid = _LITELLM_TO_PID.get(litellm_provider)
            if not pid:
                continue

            # 仅保留 chat 模型（排除 image/audio/embedding 等）
            if entry.get("mode") != "chat":
                continue

            input_cost = _to_per_m(entry.get("input_cost_per_token"))
            output_cost = _to_per_m(entry.get("output_cost_per_token"))
            # 价格缺失或为 0 视为无效（volcengine 全 0，会被这里过滤掉）
            if input_cost is None or output_cost is None:
                continue

            model_id = _normalize_model_id(model_key)
            cached_input = _to_per_m(entry.get("cache_read_input_token_cost"))

            prices = {
                "input": input_cost,
                "output": output_cost,
                "currency": "USD",
                "unit": "per_1m_tokens",
            }
            if cached_input is not None:
                prices["cached_input"] = cached_input

            # purchase_url：LiteLLM 不提供，用 provider 官网兜底
            # 由 reconcile 阶段从 manual yaml 或 adapter 静态值补齐
            purchase_url = _fallback_purchase_url(pid)

            product = Product(
                id=f"{model_id}-token",
                model=model_id,
                billing_type=BillingType.PER_TOKEN,
                context_window=entry.get("max_input_tokens") or entry.get("max_tokens"),
                modalities=_extract_modalities(entry),
                prices=prices,
                purchase_url=purchase_url,
            )
            result[pid].append(product)

        # 每个 provider 去重（同 model_id 可能有多条变种）
        for pid in result:
            seen = set()
            deduped = []
            for p in result[pid]:
                if p.id not in seen:
                    seen.add(p.id)
                    deduped.append(p)
            result[pid] = deduped
            log.info("litellm %s: %d products", pid, len(deduped))

        return result


def _extract_modalities(entry: dict) -> list:
    """从 LiteLLM 字段推断 modalities。"""
    mods = ["text"]
    if entry.get("supports_vision"):
        mods.append("vision")
    if entry.get("supports_audio_input") or entry.get("supports_audio_output"):
        mods.append("audio")
    return mods


# provider_id -> 官网 URL，作为 purchase_url 兜底
_FALLBACK_URLS = {
    "openai": "https://platform.openai.com/docs/pricing",
    "anthropic": "https://www.anthropic.com/pricing",
    "google": "https://ai.google.dev/pricing",
    "aws": "https://aws.amazon.com/bedrock/pricing/",
    "deepseek": "https://api-docs.deepseek.com/quick_start/pricing",
    "moonshot": "https://platform.moonshot.cn/docs/pricing",
    "qwen": "https://help.aliyun.com/zh/dashscope/product-overview/billing",
    "volcengine": "https://www.volcengine.com/docs/82379/1099320",
    "minimax": "https://platform.minimaxi.com/document/Price",
}


def _fallback_purchase_url(pid: str) -> str:
    return _FALLBACK_URLS.get(pid, "")
