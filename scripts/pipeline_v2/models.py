from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Optional


@dataclass(frozen=True)
class Observation:
    source_id: str
    source_kind: str
    provider_id: str
    product_id: str
    product_kind: str
    observed_at: str
    fields: dict[str, Any]
    source_url: str = ""
    source_product_id: str = ""
    expires_at: str = ""

    @property
    def canonical_id(self) -> str:
        return f"{self.provider_id}/{self.product_id}"


@dataclass(frozen=True)
class FieldDecision:
    canonical_id: str
    field: str
    value: Any
    source_id: str
    source_kind: str
    reason: str
    observed_at: str


@dataclass
class ProductCandidate:
    canonical_id: str
    provider_id: str
    product_id: str
    product_kind: str
    fields: dict[str, Any] = field(default_factory=dict)
    decisions: list[FieldDecision] = field(default_factory=list)
    status: str = "accepted"
    stale_fields: list[str] = field(default_factory=list)
    freshness: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ReviewItem:
    canonical_id: str
    field: str
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


def decimal_or_none(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None
