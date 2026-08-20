"""MiniMax official mainland and international token-API offers.

The two pages are separate commercial markets: the mainland page is CNY and
the international page is USD.  They are parsed independently and never
derived from each other by FX conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


_HTML = re.compile(r"<[^>]+>")
_MODEL = re.compile(r"(?:MiniMax-[A-Za-z0-9.-]+|M2-her)", re.I)
_AMOUNT = re.compile(r"(?:¥|\\\$|\$)\s*([0-9]+(?:\.[0-9]+)?)")
_BARE_AMOUNT = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*$")


@dataclass(frozen=True)
class MiniMaxPricingPage:
    source: str
    source_url: str
    market: str
    currency: str
    minimum_offer_count: int


MINIMAX_PRICING_PAGES = (
    MiniMaxPricingPage(
        "minimax_cn_official_pricing",
        "https://platform.minimaxi.com/docs/api-reference/anthropic-api-compatible-cache.md",
        "cn_mainland", "CNY", 5,
    ),
    MiniMaxPricingPage(
        "minimax_global_official_pricing",
        "https://platform.minimax.io/docs/guides/pricing-paygo.md",
        "global", "USD", 10,
    ),
)


class MiniMaxPricingAdapter(OfficialModelOfferAdapter):
    def __init__(self, page: MiniMaxPricingPage, *, timeout_seconds: int = 45, fetcher=None):
        super().__init__(timeout_seconds=timeout_seconds, fetcher=fetcher)
        self.page = page
        self.source = page.source
        self.source_url = page.source_url
        self.minimum_offer_count = page.minimum_offer_count

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        lines = raw.decode("utf-8", errors="replace").splitlines()
        offers: list[ModelOffer] = []
        tier = "standard"
        index = 0
        while index < len(lines):
            line = lines[index]
            if 'title="Priority' in line:
                tier = "priority"
            elif 'title="Standard' in line:
                tier = "standard"
            elif "</Tabs>" in line:
                tier = "standard"
            header = _cells(line)
            column = _column_map(header)
            if not column:
                index += 1
                continue
            index += 2
            while index < len(lines):
                row = _cells(lines[index])
                if not row:
                    break
                index += 1
                if _is_separator(row) or len(row) < len(header):
                    continue
                offer = self._offer_from_row(row, column, tier, fetched_at)
                if offer:
                    offers.append(offer)
        if len(offers) < self.minimum_offer_count:
            raise ValueError(f"{self.source}: parsed {len(offers)} token-priced offers")
        return offers

    def _offer_from_row(self, row, column, tier, fetched_at):
        model_cell = row[column["model"]]
        model_match = _MODEL.search(_plain(model_cell))
        if not model_match:
            return None
        model_name = model_match.group(0)
        model_id = model_name.lower()
        input_price = _price(row[column["input"]])
        output_price = _price(row[column["output"]])
        if input_price is None or output_price is None:
            return None
        cache_read = _price(row[column["cache_read"]]) if "cache_read" in column else None
        cache_write = _price(row[column["cache_write"]]) if "cache_write" in column else None
        condition = _condition(_plain(model_cell))
        access_channel = "official_anthropic_api" if self.page.market == "cn_mainland" else "official_api"
        return ModelOffer(
            offer_id=f"minimax-cn/{model_id}/{self.page.market}/{access_channel}/{tier}/{condition}",
            modelsdev_provider_id="minimax-cn",
            provider_id="minimax",
            provider_name="MiniMax",
            model_id=model_id,
            model_name=model_name,
            region="cn" if self.page.market == "cn_mainland" else "global",
            service_tier=tier,
            currency=self.page.currency,
            input_per_1m=input_price,
            output_per_1m=output_price,
            cache_read_per_1m=cache_read,
            cache_write_per_1m=cache_write,
            source_url=self.source_url,
            fetched_at=fetched_at,
            market=self.page.market,
            access_channel=access_channel,
            pricing_condition=condition,
            source_id=self.source,
            raw={"source_row": row},
        )


def _cells(line: str) -> list[str]:
    line = line.strip()
    return [cell.strip() for cell in line.strip("|").split("|")] if line.startswith("|") else []


def _plain(value: str) -> str:
    return _HTML.sub(" ", value).replace("**", "").replace("\\", "").strip()


def _column_map(header: list[str]) -> dict[str, int]:
    names = [_plain(cell).lower().replace(" ", "") for cell in header]
    result: dict[str, int] = {}
    for index, name in enumerate(names):
        if name in {"model", "模型"}:
            result["model"] = index
        elif name in {"input", "输入价格元/百万tokens"}:
            result["input"] = index
        elif name in {"output", "输出价格元/百万tokens"}:
            result["output"] = index
        elif name in {"promptcachingread", "缓存读取元/百万tokens"}:
            result["cache_read"] = index
        elif name in {"promptcachingwrite", "缓存写入元/百万tokens"}:
            result["cache_write"] = index
    return result if {"model", "input", "output"}.issubset(result) else {}


def _is_separator(cells: list[str]) -> bool:
    return all(set(cell) <= {":", "-", " "} for cell in cells)


def _price(value: str) -> float | None:
    # Discount tables strike through the old price first; the final displayed
    # amount is the current official price.
    values = _AMOUNT.findall(value)
    if values:
        return float(values[-1])
    # 中国大陆官方表在表头统一声明“元/百万 Tokens”，金额单元格只保留数值。
    # 这里只接受纯数字，避免把上下文或配额等其他信息误作价格。
    bare_amount = _BARE_AMOUNT.match(_plain(value))
    return float(bare_amount.group(1)) if bare_amount else None


def _condition(model_cell: str) -> str:
    lowered = model_cell.lower().replace(" ", "")
    if "≤512k" in lowered:
        return "input_lte_512k"
    if ">512k" in lowered:
        return "input_gt_512k"
    return "standard"


__all__ = ["MINIMAX_PRICING_PAGES", "MiniMaxPricingAdapter", "MiniMaxPricingPage"]
