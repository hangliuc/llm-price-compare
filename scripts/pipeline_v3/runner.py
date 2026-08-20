from __future__ import annotations

from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import uuid

from scripts.pipeline_v3.catalog import build_catalog
from scripts.pipeline_v3.config import V3Config
from scripts.pipeline_v3.models import Plan
from scripts.pipeline_v3.publisher import FileLock, publish_release
from scripts.pipeline_v3.sources.models_dev import ModelsDevSource
from scripts.pipeline_v3.sources.plans.base import OfficialPlanAdapter
from scripts.pipeline_v3.storage import V3Store, canonical_json, checksum
from scripts.pipeline_v3.validate import validate_offers, validate_plans


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_pipeline(config: V3Config, *, dry_run: bool = False,
                 models_dev_file: Path | None = None,
                 plans: list[Plan] | None = None,
                 plan_adapters: list[OfficialPlanAdapter] | None = None) -> dict:
    run_id = uuid.uuid4().hex
    release_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + f"-{run_id[:8]}"
    snapshot_id = f"snapshot-{run_id}"
    started_at = now_iso()
    if plans is not None and plan_adapters:
        raise ValueError("pass plans or plan_adapters, not both")
    plans = list(plans or [])
    store = V3Store(config.db_path)
    profile = "full" if (plans or plan_adapters) else "catalog"
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
            plan_source_status: dict[str, dict] = {}
            if plan_adapters:
                for adapter in plan_adapters:
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
            previous = store.latest_published_counts()
            offers = validate_offers(
                source.normalize(payload, fetched_at),
                minimum_count=config.minimum_offer_count,
                previous_count=previous[0] if previous else None,
                maximum_drop_ratio=config.maximum_drop_ratio,
            )
            if plans:
                plans = validate_plans(
                    plans,
                    minimum_count=config.minimum_plan_count if plan_adapters else 1,
                    previous_count=previous[1] if previous else None,
                    maximum_drop_ratio=config.maximum_drop_ratio,
                )
            published_at = now_iso()
            catalog = build_catalog(release_id, published_at, offers, plans)
            store.save_catalog_snapshot(
                snapshot_id=snapshot_id,
                run_id=run_id,
                created_at=published_at,
                catalog=catalog,
                offers=offers,
                plans=plans,
            )
            status = {
                "schema_version": "3.0",
                "release_id": release_id,
                "status": "candidate" if dry_run else "healthy",
                "published_at": None if dry_run else published_at,
                "sources": {
                    "models_dev": {"status": "healthy", "fetched_at": fetched_at},
                    "plan_adapters": {
                        "status": "healthy" if plan_adapters else ("injected" if plans else "not_run"),
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
