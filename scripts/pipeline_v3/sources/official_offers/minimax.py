"""MiniMax official mainland and international token-API offers.

The two pages are separate commercial markets: the mainland page is CNY and
the international page is USD.  They are parsed independently and never
derived from each other by FX conversion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import unescape
from urllib.parse import unquote

from bs4 import BeautifulSoup
from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


_HTML = re.compile(r"<[^>]+>")
_MODEL = re.compile(r"(?:MiniMax-[A-Za-z0-9.-]+|M2-her)", re.I)
_AMOUNT = re.compile(r"(?:¥|\\\$|\$)\s*([0-9]+(?:\.[0-9]+)?)")
_BARE_AMOUNT = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*$")
_NUMBERS = re.compile(r"[0-9]+(?:\.[0-9]+)?")


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
        "https://platform.minimaxi.com/docs/guides/pricing-paygo",
        "cn_mainland", "CNY", 5,
    ),
    MiniMaxPricingPage(
        "minimax_global_official_pricing",
        "https://platform.minimax.io/docs/guides/pricing-paygo.md",
        "global", "USD", 10,
    ),
)

# Pricing is published on the Open Platform page, while the M3 context limit
# is documented on its official model page. Keep this provenance in the raw
# record instead of deriving a context limit from a pricing tier.
MINIMAX_MODEL_METADATA = {
    "minimax-m3": {
        "context_window": 1_000_000,
        "context_source_url": "https://www.minimax.io/models/text/m3",
    },
}


class MiniMaxPricingAdapter(OfficialModelOfferAdapter):
    def __init__(self, page: MiniMaxPricingPage, *, timeout_seconds: int = 45, fetcher=None):
        super().__init__(timeout_seconds=timeout_seconds, fetcher=fetcher)
        self.page = page
        self.source = page.source
        self.source_url = page.source_url
        self.minimum_offer_count = page.minimum_offer_count

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        text = raw.decode("utf-8", errors="replace")
        offers: list[ModelOffer] = []
        # The live MiniMax pricing page renders its tables as HTML. Keep the
        # Markdown parser below for documentation exports and fixtures, but
        # parse the rendered tables first so current M3 CNY offers are kept.
        for header, rows, tier in _html_price_tables(text):
            column = _column_map(header)
            if not column:
                continue
            for row in rows:
                offer = self._offer_from_row(row, column, tier, fetched_at)
                if offer:
                    offers.append(offer)

        lines = text.splitlines()
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
        unique = {offer.offer_id: offer for offer in offers}
        if len(unique) < self.minimum_offer_count:
            raise ValueError(f"{self.source}: parsed {len(unique)} token-priced offers")
        return list(unique.values())

    def _offer_from_row(self, row, column, tier, fetched_at):
        model_cell = row[column["model"]]
        model_match = _MODEL.search(_plain(model_cell))
        if not model_match:
            return None
        model_name = model_match.group(0)
        model_id = model_name.lower()
        metadata = MINIMAX_MODEL_METADATA.get(model_id, {})
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
            context_window=metadata.get("context_window"),
            source_url=self.source_url,
            fetched_at=fetched_at,
            market=self.page.market,
            access_channel=access_channel,
            pricing_condition=condition,
            source_id=self.source,
            raw={"source_row": row, **metadata},
        )


def _cells(line: str) -> list[str]:
    line = line.strip()
    return [cell.strip() for cell in line.strip("|").split("|")] if line.startswith("|") else []


def _html_price_tables(text: str):
    soup = BeautifulSoup(text, "html.parser")
    for table in soup.find_all("table"):
        header_row = table.find("tr")
        if not header_row:
            continue
        header = [cell.decode_contents().strip() for cell in header_row.find_all(["th", "td"])]
        rows = [
            [cell.decode_contents().strip() for cell in row.find_all(["th", "td"])]
            for row in table.find_all("tr")[1:]
        ]
        yield header, rows, _html_tier(table)


def _html_tier(table) -> str:
    for parent in [table, *table.parents]:
        attributes = " ".join(str(value) for value in parent.attrs.values())
        decoded = unquote(attributes).lower()
        if "priority" in decoded or "优先" in decoded:
            return "priority"
    return "standard"


def _plain(value: str) -> str:
    return unescape(_HTML.sub(" ", value)).replace("**", "").replace("\\", "").strip()


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
    if bare_amount:
        return float(bare_amount.group(1))
    # The current mainland M3 promotion table renders a struck-through list
    # price followed by the live CNY price without a currency symbol.  In a
    # price cell the last number is the displayed, payable price.
    if "~~" in value or "<del" in value.lower():
        numbers = _NUMBERS.findall(_plain(value))
        return float(numbers[-1]) if numbers else None
    return None


def _condition(model_cell: str) -> str:
    lowered = model_cell.lower().replace(" ", "")
    if "≤512k" in lowered:
        return "input_lte_512k"
    if ">512k" in lowered:
        return "input_gt_512k"
    return "standard"


__all__ = ["MINIMAX_PRICING_PAGES", "MiniMaxPricingAdapter", "MiniMaxPricingPage"]
