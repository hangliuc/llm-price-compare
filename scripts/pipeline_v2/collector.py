from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Iterable, Optional

from scripts.pipeline_v2.models import Observation
from scripts.pipeline_v2.normalize import (manual_dict_to_observations, now_iso,
                                           products_to_observations)


@dataclass
class SourceBatch:
    source_id: str
    source_kind: str
    status: str
    observations: list[Observation] = field(default_factory=list)
    duration_ms: int = 0
    error: Optional[str] = None
    evidence_payload: Any = None
    evidence_kind: str = "normalized_snapshot"
    evidence_content_type: str = "application/json"


def collect_sources(sources: Iterable[Any]) -> list[SourceBatch]:
    batches = []
    for source in sources:
        started = monotonic()
        try:
            result = source.fetch_all()
            observations = [item for provider_id, products in result.items()
                            for item in products_to_observations(
                                source.source_id, "aggregator", provider_id, products)]
            batches.append(SourceBatch(
                source.source_id, "aggregator", "success" if observations else "empty",
                observations, int((monotonic() - started) * 1000),
                evidence_payload=getattr(
                    source, "last_evidence", [item.__dict__ for item in observations]),
                evidence_kind=("raw_response" if hasattr(source, "last_evidence")
                               else "normalized_snapshot"),
            ))
        except Exception as exc:
            batches.append(SourceBatch(
                source.source_id, "aggregator", "failed", [],
                int((monotonic() - started) * 1000), str(exc),
            ))
    return batches


def collect_adapters(adapters: Iterable[Any]) -> list[SourceBatch]:
    batches = []
    for adapter in adapters:
        source_id = f"official:{adapter.provider_id}"
        started = monotonic()
        try:
            products = adapter.validate(adapter.fetch())
            observations = products_to_observations(
                source_id, "official_adapter", adapter.provider_id, products)
            batches.append(SourceBatch(
                source_id, "official_adapter", "success" if observations else "empty",
                observations, int((monotonic() - started) * 1000),
                evidence_payload=[item.__dict__ for item in observations],
            ))
        except Exception as exc:
            batches.append(SourceBatch(
                source_id, "official_adapter", "failed", [],
                int((monotonic() - started) * 1000), str(exc),
            ))
    return batches


def collect_manual(providers: list[dict]) -> SourceBatch:
    started = monotonic()
    observations = [item for provider in providers
                    for item in manual_dict_to_observations(provider)]
    return SourceBatch("manual", "manual", "success" if observations else "empty",
                       observations, int((monotonic() - started) * 1000),
                       evidence_payload=providers, evidence_kind="manual_snapshot")
