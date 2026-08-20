import logging
from typing import Optional
from uuid import uuid4

from scripts.adapters import ADAPTERS
from scripts.core.manual import load_manual_providers
from scripts.pipeline_v2.catalog import build_catalog
from scripts.pipeline_v2.changes import detect_changes
from scripts.pipeline_v2.collector import collect_adapters, collect_manual, collect_sources
from scripts.pipeline_v2.config import V2Config
from scripts.pipeline_v2.identity import AliasRegistry, find_identity_reviews
from scripts.pipeline_v2.evidence import persist_evidence
from scripts.pipeline_v2.freshness import apply_freshness
from scripts.pipeline_v2.manual_freshness import inspect_manual_providers
from scripts.pipeline_v2.drift import apply_price_drift_guard
from scripts.pipeline_v2.normalize import now_iso
from scripts.pipeline_v2.publisher import FileLock, atomic_write_json, publish
from scripts.pipeline_v2.alerts import deliver_pipeline_alert
from scripts.pipeline_v2.release_gate import check_release
from scripts.pipeline_v2.reconcile import find_authoritative_conflicts, reconcile
from scripts.pipeline_v2.storage import V2Store
from scripts.pipeline_v2.validate import validate_catalog
from scripts.sources.litellm import LiteLLMSource
from scripts.sources.openrouter import OpenRouterSource

log = logging.getLogger("pipeline_v2.runner")


def _profile_observations(profile: str, observations: list) -> list:
    if profile == "payg":
        return [item for item in observations if item.fields.get("billing_type") == "per_token"]
    if profile == "plans":
        return [item for item in observations if item.fields.get("billing_type") != "per_token"]
    return observations


def run_pipeline(config: Optional[V2Config] = None, profile: str = "full-verify",
                 dry_run: bool = False, sources=None, adapters=None) -> int:
    if profile not in {"payg", "plans", "full-verify"}:
        raise ValueError(f"unsupported profile: {profile}")
    config = config or V2Config.from_env()
    sources = ([LiteLLMSource(preserve_versions=True), OpenRouterSource()]
               if sources is None else sources)
    adapters = ADAPTERS if adapters is None else adapters
    run_id = uuid4().hex
    started_at = now_iso()

    with FileLock(config.lock_path):
        store = V2Store(config.db_path)
        store.start_run(run_id, profile, started_at)
        try:
            manuals = load_manual_providers(str(config.manual_dir))
            metadata = {item["id"]: item for item in manuals}
            manual_reviews, stale_manual_providers = inspect_manual_providers(
                manuals, started_at)
            batches = collect_sources(sources) + collect_adapters(adapters)
            batches.append(collect_manual(manuals))
            for batch in batches:
                store.record_source(run_id, batch.source_id, batch.status,
                                    len(batch.observations), batch.duration_ms, batch.error)
                if batch.evidence_payload is not None:
                    evidence = persist_evidence(
                        config.evidence_dir or config.runtime_dir / "raw",
                        batch.source_id, batch.evidence_payload, batch.evidence_kind,
                        batch.evidence_content_type)
                    store.record_evidence(run_id, evidence, started_at)

            automatic = [batch for batch in batches if batch.source_kind != "manual"]
            if profile in {"payg", "full-verify"} and automatic and not any(
                    batch.status == "success" for batch in automatic):
                raise RuntimeError("all automatic sources failed or returned empty")

            observations = _profile_observations(
                profile, [item for batch in batches for item in batch.observations])
            if not observations:
                raise RuntimeError(f"profile {profile} produced no observations")
            registry = AliasRegistry.load(config.alias_path)
            observations = [registry.resolve(item) for item in observations]
            identity_reviews = find_identity_reviews(observations, registry)
            store.record_observations(run_id, observations)
            store.record_identity_reviews(run_id, identity_reviews, now_iso())
            new_manual_review_count = store.record_review_items(
                run_id, manual_reviews, now_iso())
            previous = store.last_catalog()
            source_conflicts = find_authoritative_conflicts(observations)
            store.record_review_items(run_id, source_conflicts, now_iso())
            blocked_fields = {(item.canonical_id, item.field) for item in source_conflicts}
            candidates = reconcile(observations, previous, blocked_fields)
            candidates, drift_reviews, drift_warnings = apply_price_drift_guard(
                candidates, previous, accepted_baselines=store.accepted_baselines())
            candidates = apply_freshness(
                candidates, observations, started_at, stale_manual_providers)
            store.record_review_items(run_id, drift_reviews, now_iso())
            decisions = [decision for item in candidates for decision in item.decisions]
            store.record_decisions(run_id, decisions)
            release_id = f"{started_at.replace(':', '').replace('-', '')}-{run_id[:8]}"
            catalog = build_catalog(release_id, started_at, candidates, metadata)
            validation = validate_catalog(catalog)
            if not validation.accepted:
                raise RuntimeError("catalog validation failed: " + "; ".join(validation.errors))
            gate = check_release(catalog, previous)
            if not gate.accepted:
                raise RuntimeError("release gate failed: " + "; ".join(gate.errors))
            changes = detect_changes(previous, catalog)
            lkg_ages = [item.freshness.get("lkg_age_hours") for item in candidates
                        if item.freshness.get("lkg_age_hours") is not None]
            summary = {
                "profile": profile,
                "provider_count": len(catalog["providers"]),
                "model_count": len(catalog["models"]),
                "plan_count": len(catalog["plans"]),
                "change_count": len(changes),
                "identity_review_count": len(identity_reviews),
                "data_review_count": len(drift_reviews),
                "source_conflict_count": len(source_conflicts),
                "manual_review_count": len(manual_reviews),
                "manual_stale_count": sum(
                    1 for item in candidates if item.freshness.get("manual_stale")),
                "manual_stale_product_count": sum(
                    1 for item in candidates if item.freshness.get("manual_stale")),
                "partial_product_count": sum(
                    1 for item in candidates if item.status == "partial"),
                "stale_product_count": sum(
                    1 for item in candidates if item.status == "stale"),
                "lkg_field_count": sum(
                    1 for item in candidates for decision in item.decisions
                    if decision.source_kind == "lkg"),
                "max_lkg_age_hours": max(lkg_ages) if lkg_ages else None,
                "evidence_count": sum(
                    1 for batch in batches if batch.evidence_payload is not None),
                "warning_count": len(drift_warnings),
                "release_warning_count": len(gate.warnings),
                "source_status": {batch.source_id: batch.status for batch in batches},
                "dry_run": dry_run,
            }
            if dry_run:
                store.finish_run(run_id, now_iso(), "dry_run", summary)
                return 0

            digest = store.stage_release(release_id, run_id, catalog, started_at)
            status = {
                "schema_version": "2.0", "release_id": release_id,
                "published_at": started_at, "status": "healthy",
                "checksum": digest, "summary": summary,
                "sources": [{
                    "source_id": batch.source_id,
                    "status": batch.status,
                    "product_count": len(batch.observations),
                    "duration_ms": batch.duration_ms,
                    "error": batch.error,
                } for batch in batches],
            }
            releases_dir = config.releases_dir or config.runtime_dir / "releases"
            publish(config.catalog_path, config.status_path, catalog, status, releases_dir)
            published_at = now_iso()
            store.mark_release_current(release_id, published_at)
            store.record_changes(release_id, changes, now_iso())
            store.finish_run(run_id, now_iso(), "published", summary)
            if profile == "full-verify" and new_manual_review_count:
                message = f"{new_manual_review_count} manual sources require verification"
                delivery_status, delivery_error = deliver_pipeline_alert(
                    "P2", "manual_freshness_review", message)
                store.record_alert(
                    run_id, "P2", "manual_freshness_review", message,
                    {"provider_ids": sorted(stale_manual_providers)}, now_iso(),
                    delivery_status, delivery_error,
                )
            run_status_path = config.run_status_path or config.runtime_dir / "public" / "run_status.json"
            atomic_write_json(run_status_path, {
                "schema_version": "2.0", "run_id": run_id, "profile": profile,
                "status": "published", "finished_at": now_iso(),
                "release_id": release_id, "summary": summary,
            })
            return 0
        except Exception as exc:
            log.exception("V2 pipeline failed run=%s", run_id)
            store.finish_run(run_id, now_iso(), "failed", {}, str(exc))
            delivery_status, delivery_error = deliver_pipeline_alert(
                "P0", "pipeline_run_failed", str(exc))
            store.record_alert(
                run_id, "P0", "pipeline_run_failed", str(exc),
                {"profile": profile}, now_iso(), delivery_status, delivery_error,
            )
            run_status_path = config.run_status_path or config.runtime_dir / "public" / "run_status.json"
            atomic_write_json(run_status_path, {
                "schema_version": "2.0", "run_id": run_id, "profile": profile,
                "status": "failed", "finished_at": now_iso(), "error": str(exc),
                "last_published_release": (store.last_catalog() or {}).get("release_id"),
                "alert_delivery": delivery_status,
            })
            return 1
        finally:
            store.close()
