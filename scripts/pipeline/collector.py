from dataclasses import dataclass, field
import logging
from time import monotonic
from typing import Any, Iterable, Optional

from scripts.core.models import Product

log = logging.getLogger("pipeline.collector")


@dataclass
class CollectionResult:
    source_id: str
    status: str
    products: dict[str, list[Product]] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0

    @property
    def product_count(self) -> int:
        return sum(len(items) for items in self.products.values())


def collect_sources(sources: Iterable[Any]) -> list[CollectionResult]:
    """Collect sources independently and preserve failure/empty semantics."""
    results = []
    for source in sources:
        started = monotonic()
        try:
            products = source.fetch_all()
            status = "success" if any(products.values()) else "empty"
            results.append(CollectionResult(
                source_id=source.source_id,
                status=status,
                products=products,
                duration_ms=int((monotonic() - started) * 1000),
            ))
        except Exception as exc:
            log.exception("source %s failed", source.source_id)
            results.append(CollectionResult(
                source_id=source.source_id,
                status="failed",
                error=str(exc),
                duration_ms=int((monotonic() - started) * 1000),
            ))
    return results


def collect_adapters(adapters: Iterable[Any]) -> list[CollectionResult]:
    """Collect each provider adapter as its own observable source."""
    results = []
    for adapter in adapters:
        source_id = f"adapter:{adapter.provider_id}"
        started = monotonic()
        try:
            products = adapter.validate(adapter.fetch())
            results.append(CollectionResult(
                source_id=source_id,
                status="success" if products else "empty",
                products={adapter.provider_id: products},
                duration_ms=int((monotonic() - started) * 1000),
            ))
        except Exception as exc:
            log.exception("adapter %s failed", adapter.provider_id)
            results.append(CollectionResult(
                source_id=source_id,
                status="failed",
                error=str(exc),
                duration_ms=int((monotonic() - started) * 1000),
            ))
    return results
