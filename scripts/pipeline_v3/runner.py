from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import uuid

from scripts.pipeline_v3.catalog import build_catalog
from scripts.pipeline_v3.comparison import apply_comparison_values
from scripts.pipeline_v3.config import V3Config
from scripts.pipeline_v3.fx import DailyFxSource
from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.publisher import FileLock, publish_release
from scripts.pipeline_v3.sources.models_dev import DOMESTIC_PROVIDER_IDS, ModelsDevSource
from scripts.pipeline_v3.sources.official_offers.base import OfficialModelOfferAdapter
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter
from scripts.pipeline_v3.storage import V3Store, canonical_json, checksum
from scripts.pipeline_v3.validate import validate_offers, validate_plans


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def scoped_previous_offer_count(previous_count: int | None,
                                previous_offers) -> int | None:
    """Keep the offer-drop guard meaningful across the domestic-source cutover.

    Historical releases could include global offers for Chinese providers. They
    are no longer part of the catalogue contract and must not force a fallback
    to precisely those stale records when the new scoped catalogue is smaller.
    """
    if not previous_count or not previous_offers:
        return previous_count
    retained = [offer for offer in previous_offers if not (
        offer.provider_id in DOMESTIC_PROVIDER_IDS
        and (offer.market not in {"cn_mainland", "cn_beijing"} or offer.currency != "CNY")
    )]
    return len(retained)


def run_pipeline(config: V3Config, *, dry_run: bool = False,
                 models_dev_file: Path | None = None,
                 fx_file: Path | None = None,
                 plans: list[Plan] | None = None,
                 plan_adapters: list[OfficialPlanAdapter] | None = None,
                 official_offer_adapters: list[OfficialModelOfferAdapter] | None = None) -> dict:
    run_id = uuid.uuid4().hex
    release_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{run_id[:8]}"
    snapshot_id = f"snapshot-{run_id}"
    started_at = now_iso()
    if plans is not None and plan_adapters:
        raise ValueError("pass plans or plan_adapters, not both")
    plans = list(plans or [])
    store = V3Store(config.db_path)
    profile = "full" if (plans or plan_adapters or official_offer_adapters) else "catalog"
    store.start_run(run_id, started_at, profile)
    try:
        with FileLock(config.lock_path):
            source = ModelsDevSource(config.models_dev_url, config.timeout_seconds)
            if models_dev_file:
                raw = models_dev_file.read_bytes()
                payload = json.loads(raw)
                source_url = str(models_dev_file)
            else:
                raw, payload = source.fetch()
                source_url = config.models_dev_url
            fetched_at = now_iso()
            raw_path = config.raw_dir / run_id / "models-dev.json.gz"
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            with gzip.open(raw_path, "wb") as handle:
                handle.write(raw)
            store.save_source_snapshot(
                snapshot_id=f"source-{run_id}-models-dev",
                run_id=run_id,
                source="models_dev",
                fetched_at=fetched_at,
                source_url=source_url,
                http_status=200,
                raw_path=str(raw_path),
                raw=raw,
            )
            # A fresh, persisted daily FX snapshot is mandatory for each
            # release. It is only used to create CNY comparison values; the
            # original official prices below remain unchanged.
            fx_source = DailyFxSource(config.fx_url, config.timeout_seconds)
            if fx_file:
                fx_raw = fx_file.read_bytes()
                fx_payload = json.loads(fx_raw)
                fx_source_url = str(fx_file)
                fx_source = DailyFxSource(fx_source_url, config.timeout_seconds)
            else:
                fx_raw, fx_payload = fx_source.fetch()
                fx_source_url = config.fx_url
            fx_fetched_at = now_iso()
            fx_snapshot = fx_source.normalize(
                fx_raw, fx_payload, f"fx-{run_id}", fx_fetched_at)
            fx_raw_path = config.raw_dir / run_id / "daily-fx.json.gz"
            with gzip.open(fx_raw_path, "wb") as handle:
                handle.write(fx_raw)
            store.save_source_snapshot(
                snapshot_id=f"source-{run_id}-daily-fx",
                run_id=run_id,
                source="daily_fx",
                fetched_at=fx_fetched_at,
                source_url=fx_source_url,
                http_status=200,
                raw_path=str(fx_raw_path),
                raw=fx_raw,
            )
            store.save_fx_snapshot(run_id=run_id, snapshot=fx_snapshot)
            plan_source_status: dict[str, dict] = {}
            official_offer_status: dict[str, dict] = {}
            official_offers = []
            if official_offer_adapters:
                for adapter in official_offer_adapters:
                    result = adapter.fetch()
                    adapter_fetched_at = now_iso()
                    adapter_raw_path = config.raw_dir / run_id / f"{adapter.source}.html.gz"
                    adapter_raw_path.parent.mkdir(parents=True, exist_ok=True)
                    with gzip.open(adapter_raw_path, "wb") as handle:
                        handle.write(result.raw)
                    store.save_source_snapshot(
                        snapshot_id=f"source-{run_id}-{adapter.source}",
                        run_id=run_id,
                        source=adapter.source,
                        fetched_at=adapter_fetched_at,
                        source_url=result.source_url,
                        http_status=result.http_status,
                        raw_path=str(adapter_raw_path),
                        raw=result.raw,
                        etag=result.headers.get("ETag"),
                        last_modified=result.headers.get("Last-Modified"),
                    )
                    adapter_offers = adapter.normalize(result.raw, adapter_fetched_at)
                    if len(adapter_offers) < adapter.minimum_offer_count:
                        raise ValueError(
                            f"{adapter.source}: offer count {len(adapter_offers)} is below "
                            f"adapter minimum {adapter.minimum_offer_count}"
                        )
                    official_offers.extend(adapter_offers)
                    official_offer_status[adapter.source] = {
                        "status": "healthy",
                        "fetched_at": adapter_fetched_at,
                        "count": len(adapter_offers),
                    }
            if plan_adapters:
                for adapter in plan_adapters:
                    try:
                        result = adapter.fetch()
                        adapter_fetched_at = now_iso()
                        adapter_raw_path = config.raw_dir / run_id / f"{adapter.source}.html.gz"
                        adapter_raw_path.parent.mkdir(parents=True, exist_ok=True)
                        with gzip.open(adapter_raw_path, "wb") as handle:
                            handle.write(result.raw)
                        store.save_source_snapshot(
                            snapshot_id=f"source-{run_id}-{adapter.source}",
                            run_id=run_id,
                            source=adapter.source,
                            fetched_at=adapter_fetched_at,
                            source_url=result.source_url,
                            http_status=result.http_status,
                            raw_path=str(adapter_raw_path),
                            raw=result.raw,
                            etag=result.headers.get("ETag"),
                            last_modified=result.headers.get("Last-Modified"),
                        )
                        adapter_plans = adapter.normalize(result.raw, adapter_fetched_at)
                        if len(adapter_plans) < adapter.minimum_plan_count:
                            raise ValueError(
                                f"{adapter.source}: plan count {len(adapter_plans)} is below "
                                f"adapter minimum {adapter.minimum_plan_count}"
                            )
                        plans.extend(adapter_plans)
                        plan_source_status[adapter.source] = {
                            "status": "healthy",
                            "fetched_at": adapter_fetched_at,
                            "count": len(adapter_plans),
                        }
                    except Exception as exc:
                        retained = store.latest_published_plans_for_source(adapter.source_url)
                        if not retained:
                            retained = store.published_catalog_plans_for_source(
                                config.catalog_path, adapter.source_url)
                        if len(retained) < adapter.minimum_plan_count:
                            raise
                        plans.extend(retained)
                        plan_source_status[adapter.source] = {
                            "status": "stale",
                            "count": len(retained),
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                            "retained_from": "last_known_good",
                        }
            previous = store.latest_published_counts()
            previous_offers = store.published_catalog_offers(config.catalog_path)
            previous_offer_count = scoped_previous_offer_count(
                previous[0] if previous else None, previous_offers)
            candidate_offers = [*source.normalize(payload, fetched_at), *official_offers]
            try:
                offers = validate_offers(
                    candidate_offers,
                    minimum_count=config.minimum_offer_count,
                    previous_count=previous_offer_count,
                    maximum_drop_ratio=config.maximum_drop_ratio,
                )
                offer_source_status = {"status": "healthy", "count": len(offers)}
            except Exception as exc:
                # A transient Models.dev regression must not block official
                # subscription-plan publication. Keep the last known-good
                # offers and publish the successfully refreshed plans.
                retained_offers = store.published_catalog_offers(config.catalog_path)
                if len(retained_offers) < config.minimum_offer_count:
                    raise
                offers = retained_offers
                offer_source_status = {
                    "status": "stale", "count": len(offers),
                    "error_type": type(exc).__name__, "error": str(exc),
                    "retained_from": "last_known_good",
                }
            if plans:
                plans = validate_plans(
                    plans,
                    minimum_count=config.minimum_plan_count if plan_adapters else 1,
                    previous_count=previous[1] if previous else None,
                    maximum_drop_ratio=config.maximum_drop_ratio,
                )
            offers, plans = apply_comparison_values(offers, plans, fx_snapshot)
            published_at = now_iso()
            catalog = build_catalog(
                release_id, published_at, offers, plans,
                fx_snapshot=fx_snapshot.to_catalog_dict(),
            )
            store.save_catalog_snapshot(
                snapshot_id=snapshot_id,
                run_id=run_id,
                created_at=published_at,
                catalog=catalog,
                offers=offers,
                plans=plans,
            )
            status = {
                "schema_version": catalog["schema_version"],
                "release_id": release_id,
                "status": "candidate" if dry_run else "healthy",
                "published_at": None if dry_run else published_at,
                "sources": {
                    "models_dev": {**offer_source_status, "fetched_at": fetched_at},
                    "daily_fx": {
                        "status": "healthy",
                        "fetched_at": fx_fetched_at,
                        "reference_date": fx_snapshot.published_date,
                        "comparison_currency": "CNY",
                    },
                    "official_market_adapters": {
                        "status": "healthy" if official_offer_adapters else "not_run",
                        "count": len(official_offers),
                        "sources": official_offer_status,
                    },
                    "plan_adapters": {
                        "status": (
                            "degraded" if any(item["status"] == "stale" for item in plan_source_status.values())
                            else "healthy"
                        ) if plan_adapters else ("injected" if plans else "not_run"),
                        "count": len(plans),
                        "sources": plan_source_status,
                    },
                },
                "summary": catalog["summary"],
            }
            if dry_run:
                store.finish_run(
                    run_id, now_iso(), "succeeded", len(offers), len(plans),
                    summary=catalog["summary"],
                )
            else:
                release_catalog, release_status = publish_release(
                    config.catalog_path, config.status_path, config.releases_dir,
                    release_id, catalog, status,
                )
                store.save_release(
                    release_id, snapshot_id, published_at, published_at,
                    checksum(canonical_json(catalog)), str(release_catalog), str(release_status),
                )
                store.finish_run(
                    run_id, now_iso(), "published", len(offers), len(plans),
                    release_id=release_id, summary=catalog["summary"],
                )
            return status
    except Exception as exc:
        store.finish_run(
            run_id, now_iso(), "failed", error_code=type(exc).__name__,
            error_message=str(exc),
        )
        raise
    finally:
        store.close()
