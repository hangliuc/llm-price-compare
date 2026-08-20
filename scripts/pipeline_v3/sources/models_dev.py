from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

import requests

from scripts.pipeline_v3.models import ModelOffer


@dataclass(frozen=True)
class ProviderMapping:
    provider_id: str
    provider_name: str
    region: str


PROVIDER_MAPPINGS: dict[str, ProviderMapping] = {
    "anthropic": ProviderMapping("anthropic", "Anthropic", "us"),
    "amazon-bedrock": ProviderMapping("aws", "AWS", "us"),
    "deepseek": ProviderMapping("deepseek", "DeepSeek", "cn"),
    "google": ProviderMapping("google", "Google", "us"),
    "minimax-cn": ProviderMapping("minimax", "MiniMax", "cn"),
    "moonshotai-cn": ProviderMapping("moonshot", "Kimi", "cn"),
    "openai": ProviderMapping("openai", "OpenAI", "us"),
    "alibaba-cn": ProviderMapping("qwen", "阿里通义", "cn"),
    "xiaomi": ProviderMapping("xiaomi", "小米", "cn"),
    "zhipuai": ProviderMapping("zhipu", "智谱", "cn"),
}


class ModelsDevSource:
    source_id = "models_dev"

    def __init__(self, url: str, timeout: int = 45, session=None):
        self.url = url
        self.timeout = timeout
        self.session = session or requests.Session()

    def fetch(self) -> tuple[bytes, dict[str, Any]]:
        response = self.session.get(
            self.url,
            timeout=self.timeout,
            headers={"Accept": "application/json", "User-Agent": "PPK/3 data-pipeline"},
        )
        response.raise_for_status()
        raw = response.content
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Models.dev response must be an object")
        return raw, payload

    def normalize(self, payload: dict[str, Any], fetched_at: str | None = None) -> list[ModelOffer]:
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        offers: list[ModelOffer] = []
        for source_provider_id, mapping in PROVIDER_MAPPINGS.items():
            provider = payload.get(source_provider_id)
            if not isinstance(provider, dict):
                continue
            models = provider.get("models", {})
            if not isinstance(models, dict):
                continue
            for source_model_id, model in models.items():
                if not isinstance(model, dict):
                    continue
                cost = model.get("cost") or {}
                input_price = _number(cost.get("input"))
                output_price = _number(cost.get("output"))
                if input_price is None and output_price is None:
                    continue
                limits = model.get("limit") or {}
                modalities = model.get("modalities") or {}
                input_modalities = modalities.get("input") or []
                output_modalities = modalities.get("output") or []
                all_modalities = tuple(dict.fromkeys([*input_modalities, *output_modalities]))
                service_tier = _service_tier(source_model_id, model)
                offer_id = "/".join((
                    source_provider_id,
                    str(source_model_id).strip("/"),
                    mapping.region if mapping.region == "cn" else "global",
                    service_tier,
                ))
                offers.append(ModelOffer(
                    offer_id=offer_id,
                    modelsdev_provider_id=source_provider_id,
                    provider_id=mapping.provider_id,
                    provider_name=mapping.provider_name,
                    model_id=str(model.get("id") or source_model_id),
                    model_name=str(model.get("name") or source_model_id),
                    region=mapping.region if mapping.region == "cn" else "global",
                    service_tier=service_tier,
                    input_per_1m=input_price,
                    output_per_1m=output_price,
                    cache_read_per_1m=_number(cost.get("cache_read")),
                    cache_write_per_1m=_number(cost.get("cache_write")),
                    context_window=_integer(limits.get("context")),
                    max_output_tokens=_integer(limits.get("output")),
                    modalities=all_modalities,
                    knowledge_cutoff=model.get("knowledge"),
                    release_date=model.get("release_date"),
                    source_url=provider.get("doc") or self.url,
                    source_updated_at=model.get("last_updated"),
                    fetched_at=fetched_at,
                    raw=model,
                ))
        return offers


def _service_tier(model_id: str, model: dict[str, Any]) -> str:
    value = f"{model_id} {model.get('name', '')}".lower()
    for tier in ("batch", "flex"):
        if tier in value:
            return tier
    return "standard"


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int | None:
    number = _number(value)
    return int(number) if number is not None else None
