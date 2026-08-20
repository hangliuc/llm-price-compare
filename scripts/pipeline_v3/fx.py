"""Daily FX snapshot support for V3.1 comparison values.

Official prices are never rewritten.  This module produces one immutable CNY
reference snapshot per release, used only to derive comparison/sort values.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from typing import Any

import requests


@dataclass(frozen=True)
class FxSnapshot:
    snapshot_id: str
    base_currency: str
    rates_to_cny: dict[str, float]
    source_url: str
    published_date: str
    fetched_at: str
    raw: bytes

    def rate_to_cny(self, currency: str) -> float | None:
        if currency == "CNY":
            return 1.0
        rate = self.rates_to_cny.get(currency.upper())
        return float(rate) if rate is not None and rate > 0 else None

    def to_catalog_dict(self) -> dict[str, Any]:
        return {
            "fx_snapshot_id": self.snapshot_id,
            "base_currency": "CNY",
            "rates_to_cny": self.rates_to_cny,
            "source_url": self.source_url,
            "published_date": self.published_date,
            "fetched_at": self.fetched_at,
        }


class DailyFxSource:
    """Fetch one public daily rate table and normalize it to CNY rates.

    The configured endpoint is expected to return the Frankfurter shape:
    ``{"base":"EUR", "date":"YYYY-MM-DD", "rates":{"USD":...}}``.
    It is deliberately a single source: PPK does not reconcile FX feeds.
    """

    source_id = "daily_fx"

    def __init__(self, url: str, timeout: int = 45, session=None):
        self.url = url
        self.timeout = timeout
        self.session = session or requests.Session()

    def fetch(self) -> tuple[bytes, dict[str, Any]]:
        response = self.session.get(
            self.url,
            timeout=self.timeout,
            headers={"Accept": "application/json", "User-Agent": "PPK/3.1 data-pipeline"},
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("daily FX response must be an object")
        return response.content, payload

    def normalize(self, raw: bytes, payload: dict[str, Any], snapshot_id: str,
                  fetched_at: str | None = None) -> FxSnapshot:
        fetched_at = fetched_at or datetime.now(timezone.utc).isoformat()
        base = str(payload.get("base") or "").upper()
        published_date = str(payload.get("date") or "")
        rates = payload.get("rates")
        if not base or not published_date or not isinstance(rates, dict):
            raise ValueError("daily FX response is missing base, date, or rates")
        normalized = {str(key).upper(): _number(value) for key, value in rates.items()}
        normalized[base] = 1.0
        cny_per_base = normalized.get("CNY")
        if cny_per_base is None or cny_per_base <= 0:
            raise ValueError("daily FX response does not include a valid CNY rate")
        rates_to_cny = {
            currency: cny_per_base / value
            for currency, value in normalized.items()
            if value is not None and value > 0
        }
        rates_to_cny["CNY"] = 1.0
        return FxSnapshot(
            snapshot_id=snapshot_id,
            base_currency="CNY",
            rates_to_cny=rates_to_cny,
            source_url=self.url,
            published_date=published_date,
            fetched_at=fetched_at,
            raw=raw or json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        )


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
