"""Xiaomi MiMo mainland pay-as-you-go API pricing."""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


_AMOUNT = re.compile(r"(?:¥|Â¥)\s*([0-9]+(?:\.[0-9]+)?)")


class XiaomiMiMoMainlandPricingAdapter(OfficialModelOfferAdapter):
    source = "xiaomi_mimo_mainland_official_pricing"
    source_url = "https://mimo.mi.com/docs/zh-CN/price/pay-as-you-go"
    minimum_offer_count = 2

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        soup = BeautifulSoup(raw, "html.parser")
        heading = next((tag for tag in soup.find_all(["h1", "h2", "h3"]) if "模型国内定价" in tag.get_text(" ", strip=True)), None)
        if not heading:
            raise ValueError(f"{self.source}: mainland pricing heading not found")
        table = heading.find_next("table")
        if not table:
            raise ValueError(f"{self.source}: mainland pricing table not found")
        offers: list[ModelOffer] = []
        for tr in table.find_all("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in tr.find_all(["th", "td"])]
            if len(cells) != 4 or not cells[0].lower().startswith("mimo-"):
                continue
            values = [_amount(cell) for cell in cells[1:]]
            if any(value is None for value in values):
                continue
            model_id = cells[0].strip().lower()
            offers.append(ModelOffer(
                offer_id=f"xiaomi/{model_id}/cn_mainland/official_api/standard",
                modelsdev_provider_id="xiaomi",
                provider_id="xiaomi",
                provider_name="小米 MiMo",
                model_id=model_id,
                model_name=model_id,
                region="cn",
                service_tier="standard",
                currency="CNY",
                input_per_1m=values[1],
                output_per_1m=values[2],
                cache_read_per_1m=values[0],
                context_window=1_000_000,
                source_url=self.source_url,
                fetched_at=fetched_at,
                market="cn_mainland",
                access_channel="official_api",
                pricing_condition="standard",
                source_id=self.source,
                raw={"source_row": cells, "cache_write_note": "限时免费"},
            ))
        if len(offers) < self.minimum_offer_count:
            raise ValueError(f"{self.source}: parsed {len(offers)} mainland offers")
        return offers


def _amount(value: str) -> float | None:
    match = _AMOUNT.search(value)
    return float(match.group(1)) if match else None


__all__ = ["XiaomiMiMoMainlandPricingAdapter"]
