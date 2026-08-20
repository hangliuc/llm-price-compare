"""Alibaba Model Studio official, market-specific Qwen offers.

The public Model Studio page currently presents separate tables for Beijing,
Singapore, Virginia, Frankfurt and Tokyo. The page can contain multiple input
token brackets for a model, so each bracket is emitted as a distinct offer;
they are never averaged or collapsed.
"""

from __future__ import annotations

import re

from bs4 import BeautifulSoup

from scripts.pipeline_v3.models import ModelOffer
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


_MARKETS = {
    "华北 2（北京）": "cn_beijing",
    "美国（弗吉尼亚）": "us_virginia",
    "新加坡": "sg_international",
    "德国（法兰克福）": "de_frankfurt",
    "日本（东京）": "jp_tokyo",
}
_MODEL_ID = re.compile(r"\b(qwen[a-z0-9._-]*)\b", re.I)
_AMOUNT = re.compile(r"(?:原价\s*)?([0-9]+(?:\.[0-9]+)?)\s*元")


class QwenModelStudioAdapter(OfficialModelOfferAdapter):
    source = "qwen_model_studio"
    source_url = "https://help.aliyun.com/zh/model-studio/model-pricing"
    minimum_offer_count = 2

    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        soup = BeautifulSoup(raw, "html.parser")
        offers: list[ModelOffer] = []
        for table in soup.find_all("table"):
            market = _table_market(table)
            if not market:
                continue
            headers = " ".join(table.stripped_strings)
            if "输入单价" not in headers or "输出单价" not in headers:
                continue
            for row in table.find_all("tr"):
                cells = [cell.get_text(" ", strip=True) for cell in row.find_all(["th", "td"])]
                if len(cells) < 5:
                    continue
                model_match = _MODEL_ID.search(cells[0])
                if not model_match:
                    continue
                condition = _condition(cells)
                input_price, output_price = _prices(cells)
                if input_price is None or output_price is None:
                    continue
                model_id = model_match.group(1)
                offer_id = "/".join((
                    "qwen", model_id, market, "official_api", "standard", condition,
                ))
                offers.append(ModelOffer(
                    offer_id=offer_id,
                    modelsdev_provider_id="alibaba-cn",
                    provider_id="qwen",
                    provider_name="阿里通义",
                    model_id=model_id,
                    model_name=model_id,
                    region="cn",
                    service_tier="standard",
                    currency="CNY",
                    input_per_1m=input_price,
                    output_per_1m=output_price,
                    source_url=self.source_url,
                    fetched_at=fetched_at,
                    market=market,
                    access_channel="official_api",
                    pricing_condition=condition,
                    source_id=self.source,
                    raw={
                        "table_market": market,
                        "cells": cells,
                        "pricing_condition": condition,
                    },
                ))
        unique = {offer.offer_id: offer for offer in offers}
        if len(unique) < self.minimum_offer_count:
            raise ValueError(
                f"{self.source}: parsed {len(unique)} official offers; expected at least {self.minimum_offer_count}"
            )
        return list(unique.values())


def _table_market(table) -> str | None:
    for heading in table.find_all_previous(["h1", "h2", "h3", "h4", "h5", "h6"]):
        label = heading.get_text(" ", strip=True)
        if label in _MARKETS:
            return _MARKETS[label]
    return None


def _condition(cells: list[str]) -> str:
    for cell in cells:
        compact = cell.replace(" ", "")
        if "无阶梯计价" in compact:
            return "standard"
        match = re.search(r"(?:0<)?Token≤([0-9]+(?:\.\d+)?)([KkMm])", compact)
        if match:
            return f"input_lte_{match.group(1).lower()}{match.group(2).lower()}"
    return "standard"


def _prices(cells: list[str]) -> tuple[float | None, float | None]:
    # The first price cells after the token-range column are the documented
    # input/output base prices. Promotional wording may also be present; the
    # page itself labels the first amount as 原价, which is the source's price.
    amounts: list[float] = []
    for cell in cells:
        amounts.extend(float(value) for value in _AMOUNT.findall(cell))
    if len(amounts) < 2:
        return None, None
    return amounts[0], amounts[1]
