from __future__ import annotations

from datetime import datetime, timezone
from time import monotonic

from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def probe_plan_adapters(adapters: list[OfficialPlanAdapter]) -> dict:
    """Fetch every plan source independently and return a complete health report.

    A failed adapter is isolated so operators can see all broken sources in one
    run. This command never publishes a catalog and therefore cannot overwrite
    the last known good release.
    """

    results: list[dict] = []
    for adapter in adapters:
        started = monotonic()
        fetched = None
        try:
            fetched = adapter.fetch()
            plans = adapter.normalize(fetched.raw, _now_iso())
            if len(plans) < adapter.minimum_plan_count:
                raise ValueError(
                    f"plan count {len(plans)} is below adapter minimum "
                    f"{adapter.minimum_plan_count}"
                )
            results.append({
                "source": adapter.source,
                "source_url": fetched.source_url,
                "status": "healthy",
                "http_status": fetched.http_status,
                "plan_count": len(plans),
                "plans": [item.product_name for item in plans],
                "duration_ms": round((monotonic() - started) * 1000),
            })
        except Exception as exc:
            results.append({
                "source": adapter.source,
                "source_url": adapter.source_url,
                "status": "failed",
                "http_status": fetched.http_status if fetched else None,
                "plan_count": 0,
                "plans": [],
                "duration_ms": round((monotonic() - started) * 1000),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })

    healthy = sum(item["status"] == "healthy" for item in results)
    return {
        "checked_at": _now_iso(),
        "status": "healthy" if healthy == len(results) else "degraded",
        "healthy_sources": healthy,
        "total_sources": len(results),
        "plan_count": sum(item["plan_count"] for item in results),
        "sources": results,
    }


def probe_official_offer_adapters(adapters: list[OfficialModelOfferAdapter]) -> dict:
    """Check market-price adapters without changing the published catalog."""

    results: list[dict] = []
    for adapter in adapters:
        started = monotonic()
        fetched = None
        try:
            fetched = adapter.fetch()
            offers = adapter.normalize(fetched.raw, _now_iso())
            if len(offers) < adapter.minimum_offer_count:
                raise ValueError(
                    f"offer count {len(offers)} is below adapter minimum {adapter.minimum_offer_count}"
                )
            results.append({
                "source": adapter.source,
                "source_url": fetched.source_url,
                "status": "healthy",
                "http_status": fetched.http_status,
                "offer_count": len(offers),
                "markets": sorted({item.market for item in offers}),
                "currencies": sorted({item.currency for item in offers}),
                "duration_ms": round((monotonic() - started) * 1000),
            })
        except Exception as exc:
            results.append({
                "source": adapter.source,
                "source_url": adapter.source_url,
                "status": "failed",
                "http_status": fetched.http_status if fetched else None,
                "offer_count": 0,
                "markets": [],
                "currencies": [],
                "duration_ms": round((monotonic() - started) * 1000),
                "error_type": type(exc).__name__,
                "error": str(exc),
            })
    healthy = sum(item["status"] == "healthy" for item in results)
    return {
        "checked_at": _now_iso(),
        "status": "healthy" if healthy == len(results) else "degraded",
        "healthy_sources": healthy,
        "total_sources": len(results),
        "offer_count": sum(item["offer_count"] for item in results),
        "sources": results,
    }
