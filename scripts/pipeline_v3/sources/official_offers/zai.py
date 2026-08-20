"""Z.AI international official API offers in USD.

This source is deliberately independent from the China-mainland BigModel
documentation.  It is a complete official international pricing table, while
the mainland documentation currently exposes prices across separate model
pages rather than one equivalent structured table.  PPK must not fabricate a
mainland price by converting this USD table.
"""

from __future__ import annotations

import re

from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


_MONEY = re.compile(r"\$\s*([0-9]+(?:\.[0-9]+)?)")


class ZaiGlobalPricingAdapter(OfficialModelOfferAdapter):
    source = "zai_global_official_pricing"
    source_url = "https://docs.z.ai/guides/overview/pricing.md"
    minimum_offer_count = 10

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        lines = raw.decode("utf-8", errors="replace").splitlines()
        offers: list[ModelOffer] = []
        index = 0
        while index < len(lines):
            cells = _cells(lines[index])
            if not _is_model_price_header(cells):
                index += 1
                continue
            column = {name.lower(): position for position, name in enumerate(cells)}
            index += 2  # header and Markdown separator
            while index < len(lines):
                row = _cells(lines[index])
                if not row:
                    break
                index += 1
                if len(row) < len(cells) or _is_separator_row(row):
                    continue
                model_name = row[column["model"]].strip()
                input_price = _price(row[column["input"]])
                cache_price = _price(row[column["cached input"]])
                output_price = _price(row[column["output"]])
                # A row with a non-price unit (for example per image) cannot
                # be represented as a per-1M-token offer and is intentionally
                # omitted from this catalog.
                if not model_name or input_price is None or output_price is None:
                    continue
                model_id = model_name.lower()
                offers.append(ModelOffer(
                    offer_id=f"zhipuai/{model_id}/global/official_api/standard",
                    modelsdev_provider_id="zhipuai",
                    provider_id="zhipu",
                    provider_name="智谱",
                    model_id=model_id,
                    model_name=model_name,
                    region="global",
                    service_tier="standard",
                    currency="USD",
                    input_per_1m=input_price,
                    output_per_1m=output_price,
                    cache_read_per_1m=cache_price,
                    source_url=self.source_url,
                    fetched_at=fetched_at,
                    market="global",
                    access_channel="official_api",
                    pricing_condition="standard",
                    source_id=self.source,
                    raw={"source_row": row},
                ))
        if len(offers) < self.minimum_offer_count:
            raise ValueError(f"{self.source}: parsed {len(offers)} token-priced offers")
        return offers


def _cells(line: str) -> list[str]:
    line = line.strip()
    if not line.startswith("|"):
        return []
    return [cell.strip() for cell in line.strip("|").split("|")]


def _is_model_price_header(cells: list[str]) -> bool:
    normalized = {cell.lower() for cell in cells}
    return {"model", "input", "cached input", "output"}.issubset(normalized)


def _is_separator_row(cells: list[str]) -> bool:
    return all(set(cell) <= {":", "-", " "} for cell in cells)


def _price(value: str) -> float | None:
    normalized = value.replace("\\$", "$").strip()
    if normalized.lower() == "free":
        return 0.0
    match = _MONEY.search(normalized)
    return float(match.group(1)) if match else None


__all__ = ["ZaiGlobalPricingAdapter"]
