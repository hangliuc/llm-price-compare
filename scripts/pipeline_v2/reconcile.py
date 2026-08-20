from collections import defaultdict
import json
from typing import Any, Optional

from scripts.pipeline_v2.models import FieldDecision, Observation, ProductCandidate, ReviewItem


SOURCE_PRIORITY = {
    "official_api": 500,
    "official_document": 450,
    "official_adapter": 400,
    "manual_override": 350,
    "manual": 250,
    "aggregator": 100,
}


def _valid(value: Any) -> bool:
    return value is not None and value != ""


def choose_field(canonical_id: str, field: str, observations: list[Observation],
                 lkg_value: Any = None, lkg_observed_at: str = "") -> Optional[FieldDecision]:
    available = [item for item in observations if _valid(item.fields.get(field))]
    if available:
        ranked = sorted(
            available,
            key=lambda item: (SOURCE_PRIORITY.get(item.source_kind, 0), item.observed_at),
            reverse=True,
        )
        winner = ranked[0]
        same_rank = [item for item in ranked
                     if SOURCE_PRIORITY.get(item.source_kind, 0)
                     == SOURCE_PRIORITY.get(winner.source_kind, 0)]
        if len(same_rank) > 1 and all(item.fields[field] == winner.fields[field]
                                      for item in same_rank):
            reason = f"{winner.source_kind} sources agree"
        else:
            reason = f"highest-priority valid source: {winner.source_kind}"
        return FieldDecision(canonical_id, field, winner.fields[field], winner.source_id,
                             winner.source_kind, reason, winner.observed_at)
    if lkg_value is not None:
        return FieldDecision(canonical_id, field, lkg_value, "last_known_good", "lkg",
                             "no valid new observation; retained previous release",
                             lkg_observed_at)
    return None


def field_is_explicitly_cleared(field: str, observations: list[Observation]) -> bool:
    clearers = [item for item in observations if field in item.clear_fields]
    if not clearers:
        return False
    clear_priority = max(SOURCE_PRIORITY.get(item.source_kind, 0) for item in clearers)
    value_priorities = [SOURCE_PRIORITY.get(item.source_kind, 0)
                        for item in observations if _valid(item.fields.get(field))]
    return clear_priority >= max(value_priorities, default=-1)


def find_authoritative_conflicts(observations: list[Observation]) -> list[ReviewItem]:
    grouped: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    for item in observations:
        if not item.source_kind.startswith("official"):
            continue
        for field, value in item.fields.items():
            if _valid(value):
                grouped[(item.canonical_id, field)].append(item)
    reviews = []
    for (canonical_id, field), items in sorted(grouped.items()):
        values = {json.dumps(item.fields[field], ensure_ascii=False, sort_keys=True)
                  for item in items}
        if len(values) <= 1:
            continue
        reviews.append(ReviewItem(
            canonical_id=canonical_id,
            field=field,
            reason="authoritative sources disagree",
            details={"observations": [{
                "source_id": item.source_id,
                "value": item.fields[field],
                "observed_at": item.observed_at,
            } for item in items]},
        ))
    return reviews


def reconcile(observations: list[Observation], lkg_catalog: Optional[dict] = None,
              blocked_fields: Optional[set[tuple[str, str]]] = None
              ) -> list[ProductCandidate]:
    blocked_fields = blocked_fields or set()
    retired = {item.canonical_id for item in observations if item.retired}
    grouped: dict[str, list[Observation]] = defaultdict(list)
    for item in observations:
        if item.retired or item.canonical_id in retired:
            continue
        grouped[item.canonical_id].append(item)
    lkg_products = catalog_product_map(lkg_catalog)
    candidates = []
    for canonical_id, items in sorted(grouped.items()):
        old = lkg_products.get(canonical_id, {})
        old_fields = old.get("fields", {})
        old_observed_at = (old.get("freshness") or {}).get("latest_observed_at", "")
        fields = sorted(set().union(
            *(item.fields.keys() for item in items),
            *(item.clear_fields for item in items),
            old_fields.keys(),
        ))
        decisions = []
        selected = {}
        stale = []
        for name in fields:
            if field_is_explicitly_cleared(name, items):
                continue
            if (canonical_id, name) in blocked_fields:
                old_value = old_fields.get(name)
                decision = (FieldDecision(
                    canonical_id, name, old_value, "last_known_good", "lkg",
                    "authoritative source conflict; retained previous release",
                    old_observed_at,
                ) if old_value is not None else None)
            else:
                decision = choose_field(canonical_id, name, items, old_fields.get(name),
                                        old_observed_at)
            if decision is None:
                continue
            decisions.append(decision)
            selected[name] = decision.value
            if decision.source_kind == "lkg":
                stale.append(name)
        sample = items[0]
        candidates.append(ProductCandidate(
            canonical_id=canonical_id,
            provider_id=sample.provider_id,
            product_id=sample.product_id,
            product_kind=sample.product_kind,
            fields=selected,
            decisions=decisions,
            status="partial" if stale else "accepted",
            stale_fields=stale,
        ))
    # A source outage must not silently delete products that were present in
    # the last published V2 release.
    for canonical_id, old in sorted(lkg_products.items()):
        if canonical_id in grouped or canonical_id in retired:
            continue
        provider_id, product_id = canonical_id.split("/", 1)
        fields = old["fields"]
        decisions = [FieldDecision(
            canonical_id, name, value, "last_known_good", "lkg",
            "product absent from this run; retained previous release",
            (old.get("freshness") or {}).get("latest_observed_at", ""),
        ) for name, value in fields.items()]
        candidates.append(ProductCandidate(
            canonical_id=canonical_id, provider_id=provider_id,
            product_id=product_id, product_kind=old["product_kind"],
            fields=fields, decisions=decisions, status="partial",
            stale_fields=sorted(fields),
        ))
    return candidates


def catalog_product_map(catalog: Optional[dict]) -> dict[str, dict]:
    result = {}
    release_observed_at = (catalog or {}).get("published_at", "")
    for section in ("models", "plans"):
        for item in (catalog or {}).get(section, []):
            freshness = dict(item.get("freshness", {}))
            if not freshness.get("latest_observed_at"):
                freshness["latest_observed_at"] = release_observed_at
            result[item.get("canonical_id", "")] = {
                "fields": dict(item.get("fields", {})),
                "product_kind": "model" if section == "models" else "plan",
                "freshness": freshness,
            }
    return result
