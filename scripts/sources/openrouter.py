# scripts/sources/openrouter.py
"""L2 交叉源：OpenRouter /api/v1/models。

特点：
- REST API，无鉴权，无明显限流。
- 覆盖 7/12 厂商（缺 aws/opencode/volcengine/zhipu，kimi 在 moonshotai 下）。
- 价格为 per-token 字符串，需 ×1e6 转 per-1M。
- 独有 benchmarks（intelligence/coding/agentic index）+ reasoning 能力位。

数据源：https://openrouter.ai/api/v1/models
"""
import logging
from typing import Optional

from scripts.core.fetcher import fetch_json
from scripts.core.models import Product, BillingType
from scripts.sources.base import SourceBase

log = logging.getLogger("sources.openrouter")

_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"

# OpenRouter 的 id 前缀（provider/...）-> 项目 provider_id
# 注意：~前缀表示 OpenRouter 自有变种，归并到同一 provider
PROVIDER_MAP: dict[str, list[str]] = {
    "openai": ["openai", "~openai"],
    "anthropic": ["anthropic", "~anthropic"],
    "google": ["google", "~google"],
    "deepseek": ["deepseek"],
    "moonshot": ["moonshotai", "~moonshotai"],
    "qwen": ["qwen"],
    "minimax": ["minimax"],
    "xiaomi": ["xiaomi"],
    # aws/opencode/volcengine/zhipu: OpenRouter 未覆盖
}


def _to_per_m(per_token_str: Optional[str]) -> Optional[float]:
    """per-token 字符串 -> per-1M-tokens。空串/0/None 视为缺失。"""
    if not per_token_str:
        return None
    try:
        v = float(per_token_str)
    except (TypeError, ValueError):
        return None
    if v <= 0:
        return None
    return round(v * 1_000_000, 6)


def _to_iso_date(created: Optional[int]) -> Optional[str]:
    """OpenRouter created 时间戳（Unix 秒）-> ISO 日期字符串。"""
    if not created:
        return None
    try:
        from datetime import datetime, timezone
        return datetime.fromtimestamp(int(created), tz=timezone.utc).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError):
        return None


class OpenRouterSource(SourceBase):
    source_id = "openrouter"
    covers = list(PROVIDER_MAP.keys())

    def fetch_all(self) -> dict[str, list[Product]]:
        log.info("fetching %s", _OPENROUTER_URL)
        data = fetch_json(_OPENROUTER_URL, timeout=30)
        models = data.get("data", [])
        log.info("openrouter total models: %d", len(models))

        result: dict[str, list[Product]] = {pid: [] for pid in PROVIDER_MAP}

        for m in models:
            model_id_full = m.get("id", "")
            if "/" not in model_id_full:
                continue

            prefix = model_id_full.split("/", 1)[0].lstrip("~")
            pid = _match_provider(prefix)
            if not pid:
                continue

            # 只要 text 输出模型（排除纯 image/audio 工具）
            arch = m.get("architecture") or {}
            out_mods = arch.get("output_modalities") or []
            if out_mods and "text" not in out_mods:
                continue

            pricing = m.get("pricing") or {}
            input_cost = _to_per_m(pricing.get("prompt"))
            output_cost = _to_per_m(pricing.get("completion"))
            if input_cost is None or output_cost is None:
                continue

            model_id = model_id_full.split("/", 1)[1]
            cached_input = _to_per_m(pricing.get("input_cache_read"))

            prices = {
                "input": input_cost,
                "output": output_cost,
                "currency": "USD",
                "unit": "per_1m_tokens",
            }
            if cached_input is not None:
                prices["cached_input"] = cached_input

            product = Product(
                id=f"{model_id}-token",
                model=model_id,
                billing_type=BillingType.PER_TOKEN,
                context_window=m.get("context_length"),
                modalities=_extract_modalities(arch),
                prices=prices,
                purchase_url=_openrouter_url(model_id_full),
                release_date=_to_iso_date(m.get("created")),
                # OpenRouter 独有的能力元数据，存到 notes 字段（JSON 字符串）
                # 便于 reconcile 阶段取出
                notes=_serialize_metadata(m),
            )
            result[pid].append(product)

        # 去重
        for pid in result:
            seen = set()
            deduped = []
            for p in result[pid]:
                if p.id not in seen:
                    seen.add(p.id)
                    deduped.append(p)
            result[pid] = deduped
            log.info("openrouter %s: %d products", pid, len(deduped))

        return result


def _match_provider(prefix: str) -> Optional[str]:
    """OpenRouter 前缀 -> 项目 provider_id。"""
    for pid, prefixes in PROVIDER_MAP.items():
        if prefix in prefixes or f"~{prefix}" in prefixes:
            return pid
    return None


def _extract_modalities(arch: dict) -> list:
    """从 OpenRouter architecture 字段推断 modalities。"""
    mods = ["text"]
    input_mods = arch.get("input_modalities") or []
    if "image" in input_mods:
        mods.append("vision")
    if "audio" in input_mods:
        mods.append("audio")
    if "file" in input_mods:
        mods.append("file")
    return mods


def _openrouter_url(model_id_full: str) -> str:
    """OpenRouter 模型详情页作为 purchase_url 兜底。"""
    return f"https://openrouter.ai/{model_id_full}"


def _serialize_metadata(m: dict) -> Optional[str]:
    """提取 OpenRouter 独有能力元数据，序列化为 JSON 字符串存到 Product.notes。

    字段：
    - benchmarks: artificial_analysis 评分
    - reasoning: 推理能力位
    - expiration_date: 模型下线时间
    """
    import json
    meta = {}
    benchmarks = (m.get("benchmarks") or {}).get("artificial_analysis")
    if benchmarks:
        meta["benchmarks"] = benchmarks
    reasoning = m.get("reasoning")
    if reasoning and reasoning.get("supported_efforts"):
        meta["reasoning"] = {
            "mandatory": reasoning.get("mandatory", False),
            "supported_efforts": reasoning.get("supported_efforts", []),
            "default_effort": reasoning.get("default_effort"),
        }
    if m.get("expiration_date"):
        meta["expiration_date"] = m["expiration_date"]
    return json.dumps(meta, ensure_ascii=False) if meta else None
