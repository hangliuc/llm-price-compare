from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from html.parser import HTMLParser
import re
from typing import Mapping

from scripts.pipeline_v3.fetchers import BrowserFetcher, StaticHttpFetcher
from scripts.pipeline_v3.models import Plan


@dataclass(frozen=True)
class PlanFetch:
    source: str
    source_url: str
    raw: bytes
    http_status: int
    headers: Mapping[str, str]


class OfficialPlanAdapter(ABC):
    source: str
    source_url: str
    minimum_plan_count: int = 1
    fetch_mode: str = "static"
    wait_selector: str | None = None

    def __init__(self, *, timeout_seconds: int = 45, fetcher=None):
        self.timeout_seconds = timeout_seconds
        self.fetcher = fetcher or (
            BrowserFetcher(self.wait_selector)
            if self.fetch_mode == "browser"
            else StaticHttpFetcher()
        )

    def fetch(self) -> PlanFetch:
        response = self.fetcher.fetch(self.source_url, self.timeout_seconds)
        return PlanFetch(
            source=self.source,
            source_url=self.source_url,
            raw=response.raw,
            http_status=response.http_status,
            headers=response.headers,
        )

    @abstractmethod
    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        raise NotImplementedError


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth and data.strip():
            self.parts.append(data.strip())


def visible_text(raw: bytes) -> str:
    parser = _VisibleTextParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def product_window(text: str, name: str, next_names: tuple[str, ...], width: int = 900) -> str:
    """Return text near a product heading without crossing the next heading."""

    start = text.casefold().find(name.casefold())
    if start < 0:
        return ""
    end = min(len(text), start + width)
    folded = text.casefold()
    for next_name in next_names:
        candidate = folded.find(next_name.casefold(), start + len(name))
        if candidate >= 0:
            end = min(end, candidate)
    return text[start:end]


_MONTHLY_PRICE_PATTERNS = (
    re.compile(r"(?:之后\s*)?每月\s*(?:US)?\$?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:美元|USD)", re.I),
    re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:美元|USD)\s*(?:/\s*月|每月)", re.I),
    re.compile(r"(?:US)?\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:USD\s*)?(?:/\s*(?:user\s*/\s*)?|per\s+(?:user\s*(?:/|per)\s*)?)mo(?:nth)?", re.I),
    re.compile(r"(?:monthly|month)\s*(?:price)?\s*[:\-]?\s*(?:US)?\$\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    re.compile(r"(?:US)?\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:monthly|a month)", re.I),
)


def monthly_usd(window: str, *, free: bool = False) -> float | None:
    if free:
        return 0.0
    for pattern in _MONTHLY_PRICE_PATTERNS:
        match = pattern.search(window)
        if match:
            return float(match.group(1))
    return None


def require_complete_prices(plans: list[Plan], expected_count: int, source: str) -> list[Plan]:
    if len(plans) != expected_count:
        raise ValueError(
            f"{source}: parsed {len(plans)} plans; expected {expected_count}; official page likely changed"
        )
    missing = [item.product_name for item in plans if item.price_amount is None]
    if missing:
        raise ValueError(f"{source}: missing official monthly price for {', '.join(missing)}")
    return plans
