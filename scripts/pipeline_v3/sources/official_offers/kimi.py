"""Kimi mainland official API offers from the provider's Markdown docs.

Kimi publishes the commercial table directly in its documentation as a
machine-readable ``DocTable`` declaration. Each document is a separate
official source snapshot so a changed or unavailable model page is visible in
the run status instead of being inferred from another model's price.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


_ROWS = re.compile(r"rows=\{\s*(\[\s*\[.*?\]\s*,?\s*\])\s*\}", re.S)
_AMOUNT = re.compile(r"¥\s*([0-9]+(?:\.[0-9]+)?)")
_CONTEXT = re.compile(r"([0-9][0-9,]*)\s*tokens", re.I)


@dataclass(frozen=True)
class KimiPricingPage:
    source: str
    source_url: str


KIMI_MAINLAND_PRICING_PAGES = (
    KimiPricingPage("kimi_official_k3", "https://platform.kimi.com/docs/pricing/chat-k3.md"),
    KimiPricingPage("kimi_official_k27_code", "https://platform.kimi.com/docs/pricing/chat-k27-code.md"),
    KimiPricingPage("kimi_official_k26", "https://platform.kimi.com/docs/pricing/chat-k26.md"),
    KimiPricingPage("kimi_official_k25", "https://platform.kimi.com/docs/pricing/chat-k25.md"),
)


class KimiPricingAdapter(OfficialModelOfferAdapter):
    """Parse one official Kimi mainland pricing document.

    Offers carry ``market=cn_mainland`` and must never be used to derive a
    price for Kimi's separate international service.
    """

    minimum_offer_count = 1

    def __init__(self, page: KimiPricingPage, *, timeout_seconds: int = 45, fetcher=None):
        super().__init__(timeout_seconds=timeout_seconds, fetcher=fetcher)
        self.source = page.source
        self.source_url = page.source_url

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        rows = _extract_rows(raw.decode("utf-8", errors="replace"))
        offers: list[ModelOffer] = []
        for row in rows:
            if len(row) != 6 or row[1].lower().replace(" ", "") != "1mtokens":
                continue
            model_id = row[0].strip().lower()
            amounts = [float(value) for value in _AMOUNT.findall(" ".join(row[2:5]))]
            context_match = _CONTEXT.search(row[5])
            if not model_id or len(amounts) != 3 or not context_match:
                continue
            cache_read, input_price, output_price = amounts
            offers.append(ModelOffer(
                offer_id=f"moonshot/{model_id}/cn_mainland/official_api/standard",
                modelsdev_provider_id="moonshot",
                provider_id="moonshot",
                provider_name="Kimi",
                model_id=model_id,
                model_name=model_id,
                region="cn",
                service_tier="standard",
                currency="CNY",
                input_per_1m=input_price,
                output_per_1m=output_price,
                cache_read_per_1m=cache_read,
                context_window=int(context_match.group(1).replace(",", "")),
                source_url=self.source_url,
                fetched_at=fetched_at,
                market="cn_mainland",
                access_channel="official_api",
                pricing_condition="standard",
                source_id=self.source,
                raw={"source_row": row},
            ))
        if len(offers) < self.minimum_offer_count:
            raise ValueError(f"{self.source}: pricing rows not found")
        return offers


def _extract_rows(text: str) -> list[list[str]]:
    """Return literal DocTable rows without executing the documentation JSX."""

    match = _ROWS.search(text)
    if not match:
        raise ValueError("Kimi official pricing rows not found")
    try:
        rows = json.loads(re.sub(r",\s*\]$", "]", match.group(1)))
    except json.JSONDecodeError as exc:
        raise ValueError("Kimi official pricing rows are not valid JSON") from exc
    if not isinstance(rows, list) or not all(isinstance(row, list) for row in rows):
        raise ValueError("Kimi official pricing rows have an unexpected shape")
    return [[str(value) for value in row] for row in rows]


__all__ = ["KIMI_MAINLAND_PRICING_PAGES", "KimiPricingAdapter", "KimiPricingPage"]
