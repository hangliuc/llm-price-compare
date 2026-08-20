from datetime import datetime, timezone
from typing import Optional

from scripts.pipeline_v2.manual_freshness import parse_timestamp
from scripts.pipeline_v2.models import Observation, ProductCandidate


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds") if value else None


def apply_freshness(candidates: list[ProductCandidate], observations: list[Observation],
                    now: str, stale_manual_providers: Optional[set[str]] = None
                    ) -> list[ProductCandidate]:
    stale_manual_providers = stale_manual_providers or set()
    current = parse_timestamp(now) or datetime.now(timezone.utc)
    obs_by_product: dict[str, list[Observation]] = {}
    for item in observations:
        obs_by_product.setdefault(item.canonical_id, []).append(item)

    for candidate in candidates:
        items = obs_by_product.get(candidate.canonical_id, [])
        observed = [parse_timestamp(item.observed_at) for item in items]
        observed = [item for item in observed if item]
        lkg_dates = [parse_timestamp(decision.observed_at) for decision in candidate.decisions
                     if decision.source_kind == "lkg"]
        lkg_dates = [item for item in lkg_dates if item]
        manual_items = [item for item in items if item.source_kind == "manual_override"]
        verified = [parse_timestamp(item.observed_at) for item in manual_items]
        verified = [item for item in verified if item]
        expires = [parse_timestamp(item.expires_at) for item in manual_items]
        expires = [item for item in expires if item]
        manual_stale = candidate.provider_id in stale_manual_providers
        if manual_stale:
            manual_fields = {decision.field for decision in candidate.decisions
                             if decision.source_kind == "manual_override"}
            candidate.stale_fields = sorted(set(candidate.stale_fields) | manual_fields)
            critical_manual = any(field.startswith("price.") for field in manual_fields)
            all_manual = bool(candidate.decisions) and all(
                decision.source_kind == "manual_override"
                for decision in candidate.decisions)
            candidate.status = "stale" if critical_manual or all_manual else "partial"
        lkg_age = max(((current - item).total_seconds() / 3600 for item in lkg_dates),
                      default=None)
        candidate.freshness = {
            "latest_observed_at": _iso(max(observed)) if observed else None,
            "oldest_observed_at": _iso(min(observed)) if observed else None,
            "lkg_age_hours": round(lkg_age, 1) if lkg_age is not None else None,
            "manual_verified_at": _iso(max(verified)) if verified else None,
            "manual_expires_at": _iso(min(expires)) if expires else None,
            "manual_stale": manual_stale,
        }
    return candidates
