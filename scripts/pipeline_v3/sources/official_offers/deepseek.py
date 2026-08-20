"""DeepSeek direct API official CNY offers, including time-of-day prices."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


_AMOUNT = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*元")


class DeepSeekPricingAdapter(OfficialModelOfferAdapter):
    source = "deepseek_official_pricing"
    source_url = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
    minimum_offer_count = 2

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        soup = BeautifulSoup(raw, "html.parser")
        table = soup.find("table")
        if not table:
            raise ValueError(f"{self.source}: pricing table not found")
        rows = [[cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])] for tr in table.find_all("tr")]
        if not rows or rows[0][0] != "模型" or len(rows[0]) < 3:
            raise ValueError(f"{self.source}: model header not found")
        models = [_model_id(value) for value in rows[0][1:]]
        if any(value is None for value in models):
            raise ValueError(f"{self.source}: unsupported model header")
        prices = _price_matrix(rows, len(models))
        offers: list[ModelOffer] = []
        for index, model_id in enumerate(models):
            for condition in ("off_peak", "peak"):
                values = prices.get(condition, {})
                cache_read = values.get("cache_hit", [None] * len(models))[index]
                input_price = values.get("input", [None] * len(models))[index]
                output_price = values.get("output", [None] * len(models))[index]
                if input_price is None or output_price is None:
                    continue
                offers.append(ModelOffer(
                    offer_id=f"deepseek/{model_id}/cn_mainland/official_api/standard/{condition}",
                    modelsdev_provider_id="deepseek",
                    provider_id="deepseek",
                    provider_name="DeepSeek",
                    model_id=model_id,
                    model_name=model_id,
                    region="cn",
                    service_tier="standard",
                    currency="CNY",
                    input_per_1m=input_price,
                    output_per_1m=output_price,
                    cache_read_per_1m=cache_read,
                    context_window=1_000_000,
                    source_url=self.source_url,
                    fetched_at=fetched_at,
                    market="cn_mainland",
                    access_channel="official_api",
                    pricing_condition=condition,
                    source_id=self.source,
                    raw={"pricing_condition": condition, "source_table": rows},
                ))
        if len(offers) < self.minimum_offer_count:
            raise ValueError(f"{self.source}: parsed {len(offers)} offers")
        return offers


def _model_id(value: str) -> str | None:
    match = re.search(r"(deepseek-[a-z0-9._-]+)", value, re.I)
    return match.group(1).lower() if match else None


def _amounts(cells: list[str], count: int) -> list[float] | None:
    values = [float(value) for cell in cells for value in _AMOUNT.findall(cell)]
    return values[:count] if len(values) >= count else None


def _price_matrix(rows: list[list[str]], count: int) -> dict[str, dict[str, list[float]]]:
    result: dict[str, dict[str, list[float]]] = {"off_peak": {}, "peak": {}}
    current_metric = None
    for cells in rows:
        if not cells:
            continue
        label = " ".join(cells[:2])
        if "缓存命中" in label:
            current_metric = "cache_hit"
        elif "缓存未命中" in label:
            current_metric = "input"
        elif "百万tokens输出" in label:
            current_metric = "output"
        if not current_metric:
            continue
        condition = "off_peak" if "空闲时段" in cells else "peak" if "高峰时段" in cells else None
        if condition:
            amounts = _amounts(cells, count)
            if amounts:
                result[condition][current_metric] = amounts
    return result
