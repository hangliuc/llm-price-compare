from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Mapping

from scripts.pipeline_v3.fetchers import StaticHttpFetcher
from scripts.pipeline_v3.models import ModelOffer


@dataclass(frozen=True)
class OfficialOfferFetch:
    source: str
    source_url: str
    raw: bytes
    http_status: int
    headers: Mapping[str, str]


class OfficialModelOfferAdapter(ABC):
    """A single official pricing source that may publish several markets.

    The parser must attach every returned offer to an explicit market and
    original currency. It is intentionally separate from Models.dev so an
    official local-market record can coexist with a global directory record.
    """

    source: str
    source_url: str
    minimum_offer_count: int = 1

    def __init__(self, *, timeout_seconds: int = 45, fetcher=None):
        self.timeout_seconds = timeout_seconds
        self.fetcher = fetcher or StaticHttpFetcher()

    def fetch(self) -> OfficialOfferFetch:
        response = self.fetcher.fetch(self.source_url, self.timeout_seconds)
        return OfficialOfferFetch(
            source=self.source,
            source_url=self.source_url,
            raw=response.raw,
            http_status=response.http_status,
            headers=response.headers,
        )

    @abstractmethod
    def normalize(self, raw: bytes, fetched_at: str) -> list[ModelOffer]:
        raise NotImplementedError
