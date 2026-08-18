from copy import deepcopy
import logging
from pathlib import Path
from typing import Optional
from uuid import uuid4

from scripts.adapters import ADAPTERS
from scripts.core import history
from scripts.core.manual import load_manual_providers
from scripts.core.reconcile import reconcile_provider
from scripts.pipeline.changes import detect_changes
from scripts.pipeline.alerts import deliver_alerts
from scripts.pipeline.collector import collect_adapters, collect_sources
from scripts.pipeline.config import PipelineConfig
from scripts.pipeline.guardrails import guard_dataset, guard_provider
from scripts.pipeline.normalize import build_provider, merge_manual, normalize_purchase_urls
from scripts.pipeline.publisher import FileLock, atomic_write_json, load_json
from scripts.pipeline.storage import PipelineStore, now_iso
from scripts.sources import SOURCES

log = logging.getLogger("pipeline.runner")


def _provider_map(data: Optional[dict]) -> dict:
    return {p["id"]: p for p in (data or {}).get("providers", [])}


def _last_success(old_data: Optional[dict], provider_id: str) -> Optional[str]:
    for status in (old_data or {}).get("provider_status", []):
        if status.get("provider_id") == provider_id:
            return status.get("last_success_at")
    return None


def _ordered_provider_ids(old_data: Optional[dict], manuals: list,
                          source_maps: dict, adapter_map: dict) -> list:
    ordered = [p["id"] for p in (old_data or {}).get("providers", [])]
    for manual in manuals:
        if manual["id"] not in ordered:
            ordered.append(manual["id"])
    discovered = set(adapter_map)
    for products_by_provider in source_maps.values():
        discovered.update(products_by_provider)
    ordered.extend(sorted(discovered - set(ordered)))
    return ordered


def _bootstrap_lkg(store: PipelineStore, output_path: Path) -> Optional[dict]:
    # The atomically published file is the serving boundary. Prefer it so a
    # previous metadata-write failure cannot make a newer live release vanish.
    return load_json(output_path) or store.load_last_published()


def run_pipeline(config: Optional[PipelineConfig] = None,
                 sources=None, adapters=None, send_alerts: bool = True) -> int:
    config = config or PipelineConfig.from_env()
    sources = SOURCES if sources is None else sources
    adapters = ADAPTERS if adapters is None else adapters
    run_id = uuid4().hex
    alerts = []
    summary = {"run_id": run_id, "providers": {}, "sources": {}}

    with FileLock(config.lock_path):
        store = PipelineStore(config.db_path)
        store.start_run(run_id)
        old_data = _bootstrap_lkg(store, config.output_path)
        try:
            manuals = load_manual_providers(str(config.manual_dir))
            manual_map = {provider["id"]: provider for provider in manuals}
            source_results = collect_sources(sources)
            adapter_results = collect_adapters(adapters)
            for result in source_results + adapter_results:
                store.record_collection(run_id, result)
                summary["sources"][result.source_id] = result.status
                if result.status == "failed":
                    alerts.append(("failed", result.source_id, result.error or "fetch failed"))

            collection_results = source_results + adapter_results
            if collection_results and not any(
                result.status == "success" for result in collection_results
            ):
                raise RuntimeError(
                    "all automatic sources failed or returned empty; preserving last published dataset"
                )

            source_maps = {result.source_id: result.products for result in source_results}
            adapter_map = {}
            for result in adapter_results:
                adapter_map.update(result.products)
            old_providers = _provider_map(old_data)
            providers, statuses = [], []

            for provider_id in _ordered_provider_ids(old_data, manuals, source_maps, adapter_map):
                old_provider = old_providers.get(provider_id)
                manual = manual_map.get(provider_id)
                litellm = source_maps.get("litellm", {}).get(provider_id, [])
                openrouter = source_maps.get("openrouter", {}).get(provider_id, [])
                adapter_products = adapter_map.get(provider_id, [])
                candidate, confidence = None, "manual"
                sources_used, warnings = [], []

                if litellm or openrouter or adapter_products:
                    result = reconcile_provider(provider_id, litellm, openrouter, adapter_products)
                    reconciled = result.products
                    if provider_id == "aws":
                        reconciled = [p for p in reconciled if p.id.startswith("us-east-1/") or "/" not in p.id]
                        for product in reconciled:
                            product.notes = "us-east-1 区域价格，其他区域可能不同"
                    if reconciled:
                        candidate = build_provider(provider_id, reconciled, manual)
                        confidence, sources_used = result.confidence, result.sources_used
                        warnings.extend(result.warnings)
                if manual:
                    candidate = merge_manual(candidate, manual)
                    if "manual" not in sources_used:
                        sources_used.append("manual")
                if candidate:
                    normalize_purchase_urls(candidate)

                if not candidate:
                    errors = ["all sources unavailable and no manual data"]
                else:
                    guard = guard_provider(candidate, old_provider, config.provider_min_ratio)
                    errors = guard.errors
                    warnings.extend(guard.warnings)

                if errors:
                    error = "; ".join(errors)
                    if old_provider:
                        accepted = deepcopy(old_provider)
                        providers.append(accepted)
                        status = {
                            "provider_id": provider_id, "status": "failed",
                            "last_success_at": _last_success(old_data, provider_id),
                            "stale": True, "error": error, "warnings": warnings,
                            "confidence": "lkg", "sources": ["last_known_good"],
                        }
                        store.record_provider(run_id, provider_id, "fallback_lkg",
                                              len(accepted.get("products", [])), True, warnings, error)
                        summary["providers"][provider_id] = "fallback_lkg"
                        alerts.append(("blocked", provider_id, error))
                    else:
                        store.record_provider(run_id, provider_id, "rejected", 0, True, warnings, error)
                        summary["providers"][provider_id] = "rejected"
                        alerts.append(("failed", provider_id, error))
                        continue
                else:
                    providers.append(candidate)
                    status = {
                        "provider_id": provider_id, "status": "ok",
                        "last_success_at": now_iso(), "stale": False,
                        "warnings": warnings, "confidence": confidence,
                        "sources": sources_used,
                    }
                    store.record_provider(run_id, provider_id, "accepted",
                                          len(candidate.get("products", [])), False, warnings)
                    summary["providers"][provider_id] = "accepted"
                statuses.append(status)

            candidate_data = {
                "generated_at": now_iso(),
                "providers": providers,
                "provider_status": statuses,
            }
            dataset_guard = guard_dataset(candidate_data, old_data, config.dataset_min_ratio,
                                           config.min_providers, config.min_products)
            if not dataset_guard.accepted:
                raise RuntimeError("dataset validation failed: " + "; ".join(dataset_guard.errors))

            changes = detect_changes(old_data, candidate_data)
            summary.update(
                provider_count=len(providers),
                product_count=sum(len(p.get("products", [])) for p in providers),
                change_count=len(changes),
            )
            store.stage_release(run_id, candidate_data)
            atomic_write_json(config.output_path, candidate_data)
            post_publish_errors = []
            try:
                store.mark_release_published(run_id)
                store.record_changes(run_id, changes)
            except Exception as exc:
                log.exception("published run metadata failed run=%s", run_id)
                post_publish_errors.append(f"release metadata: {exc}")

            # Compatibility history is secondary: it must never invalidate an
            # already atomically published release.
            for provider in providers:
                try:
                    provider_status = next(s for s in statuses if s["provider_id"] == provider["id"])
                    history.write_provider_snapshots(
                        store.conn, provider["id"], provider.get("products", []),
                        confidence=provider_status.get("confidence", ""),
                        sources_used=provider_status.get("sources", []),
                    )
                except Exception as exc:
                    log.exception("compatibility history failed provider=%s", provider["id"])
                    post_publish_errors.append(f"history {provider['id']}: {exc}")

            published_status = "published_with_warnings" if post_publish_errors else "published"
            if post_publish_errors:
                summary["post_publish_errors"] = post_publish_errors
                alerts.extend(("warning", "post_publish", error) for error in post_publish_errors)
            status_data = {
                "run_id": run_id, "last_run_at": now_iso(), "last_success_at": now_iso(),
                "status": published_status, "published": True, "summary": summary,
            }
            try:
                atomic_write_json(config.status_path, status_data)
            except Exception as exc:
                log.exception("run status file failed after publish run=%s", run_id)
                summary.setdefault("post_publish_errors", []).append(f"status file: {exc}")
            store.finish_run(run_id, published_status, summary, published=True)
            if send_alerts and alerts:
                delivery = deliver_alerts(alerts)
                try:
                    store.record_alert(run_id, delivery)
                except Exception:
                    log.exception("recording alert result failed after publish run=%s", run_id)
                if delivery.status == "failed":
                    log.error("alert delivery failed after publish run=%s error=%s",
                              run_id, delivery.error)
            log.info("pipeline published run=%s providers=%d products=%d",
                     run_id, summary["provider_count"], summary["product_count"])
            return 0
        except Exception as exc:
            log.exception("pipeline run %s failed", run_id)
            summary["error"] = str(exc)
            store.finish_run(run_id, "failed", summary, error=str(exc))
            previous_status = load_json(config.status_path) or {}
            atomic_write_json(config.status_path, {
                "run_id": run_id, "last_run_at": now_iso(),
                "last_success_at": previous_status.get("last_success_at"),
                "status": "failed", "published": False, "error": str(exc),
                "summary": summary,
            })
            alerts.append(("fatal", "global", str(exc)))
            if send_alerts:
                delivery = deliver_alerts(alerts)
                try:
                    store.record_alert(run_id, delivery)
                except Exception:
                    log.exception("recording alert result failed run=%s", run_id)
            return 1
        finally:
            store.close()
