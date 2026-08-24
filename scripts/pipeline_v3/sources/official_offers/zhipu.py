"""Zhipu BigModel mainland API pricing.

The public pricing route is a Vue shell.  Its official pricing payload is
bundled in the page's versioned first-party application script, so the adapter
discovers that script from the public pricing page on every refresh rather
than depending on an undocumented API.
"""

from __future__ import annotations

import re
from urllib.parse import urljoin

from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter, OfficialOfferFetch


_SCRIPT = re.compile(r'<script[^>]+src=["\']([^"\']*app\.[^"\']+\.js)["\']', re.I)
_MODEL = re.compile(
    r'name:"(?P<name>GLM-[^",]+)"[^{}]{0,500}?upDownText:\["(?P<context>[^"]+)"\]'
    r'[^{}]{0,500}?inPrice:\["(?P<input>[0-9.]+)[^"]*"\]'
    r'[^{}]{0,500}?outPrice:\["(?P<output>[0-9.]+)[^"]*"\]'
    r'[^{}]{0,500}?hit:\["(?P<cache>[0-9.]+)[^"]*"\]',
    re.I,
)


class ZhipuMainlandPricingAdapter(OfficialModelOfferAdapter):
    source = "zhipu_mainland_official_pricing"
    source_url = "https://bigmodel.cn/pricing"
    minimum_offer_count = 2

    def fetch(self) -> OfficialOfferFetch:
        page = self.fetcher.fetch(self.source_url, self.timeout_seconds)
        match = _SCRIPT.search(page.raw.decode("utf-8", errors="replace"))
        if not match:
            raise ValueError(f"{self.source}: application script not found")
        script_url = urljoin(self.source_url, match.group(1))
        script = self.fetcher.fetch(script_url, self.timeout_seconds)
        # The raw snapshot is the exact official bundle containing the table;
        # offers still link visitors to the human-readable pricing route.
        return OfficialOfferFetch(self.source, script_url, script.raw, script.http_status, script.headers)

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        text = raw.decode("utf-8", errors="replace")
        offers: list[ModelOffer] = []
        for match in _MODEL.finditer(text):
            name = match.group("name")
            context = _context_tokens(match.group("context"))
            if context is None:
                continue
            model_id = name.lower()
            offers.append(ModelOffer(
                offer_id=f"zhipu/{model_id}/cn_mainland/official_api/standard",
                modelsdev_provider_id="zhipuai",
                provider_id="zhipu",
                provider_name="智谱",
                model_id=model_id,
                model_name=name,
                region="cn",
                service_tier="standard",
                currency="CNY",
                input_per_1m=float(match.group("input")),
                output_per_1m=float(match.group("output")),
                cache_read_per_1m=float(match.group("cache")),
                context_window=context,
                source_url=self.source_url,
                fetched_at=fetched_at,
                market="cn_mainland",
                access_channel="official_api",
                pricing_condition="standard",
                source_id=self.source,
                raw={"context_label": match.group("context"), "source": "official_pricing_bundle"},
            ))
        unique = {offer.offer_id: offer for offer in offers}
        if len(unique) < self.minimum_offer_count:
            raise ValueError(f"{self.source}: parsed {len(unique)} token-priced offers")
        return list(unique.values())


def _context_tokens(value: str) -> int | None:
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)([KkMm])", value.strip())
    if not match:
        return None
    return int(float(match.group(1)) * (1_000_000 if match.group(2).lower() == "m" else 1_000))


__all__ = ["ZhipuMainlandPricingAdapter"]
