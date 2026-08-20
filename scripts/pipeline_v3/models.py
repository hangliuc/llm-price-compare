from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class ModelOffer:
    offer_id: str
    modelsdev_provider_id: str
    provider_id: str
    provider_name: str
    model_id: str
    model_name: str
    region: str = "global"
    service_tier: str = "standard"
    currency: str = "USD"
    price_unit: str = "per_1m_tokens"
    input_per_1m: Optional[float] = None
    output_per_1m: Optional[float] = None
    cache_read_per_1m: Optional[float] = None
    cache_write_per_1m: Optional[float] = None
    context_window: Optional[int] = None
    max_output_tokens: Optional[int] = None
    modalities: tuple[str, ...] = ()
    knowledge_cutoff: Optional[str] = None
    release_date: Optional[str] = None
    source_url: str = "https://models.dev/api.json"
    source_updated_at: Optional[str] = None
    fetched_at: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["modalities"] = list(self.modalities)
        return data


@dataclass(frozen=True)
class Plan:
    plan_id: str
    provider_id: str
    provider_name: str
    product_name: str
    plan_category: str
    billing_type: str
    is_free: bool
    currency: str
    billing_cadence: str
    source_url: str
    source_kind: str
    fetched_at: str
    price_amount: Optional[float] = None
    monthly_equivalent: Optional[float] = None
    first_period_price: Optional[float] = None
    included_quota: Optional[float] = None
    quota_unit: Optional[str] = None
    quota_period: Optional[str] = None
    features: tuple[str, ...] = ()
    supported_models: tuple[str, ...] = ()
    purchase_url: str = ""
    source_updated_at: Optional[str] = None
    featured_on_home: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["features"] = list(self.features)
        data["supported_models"] = list(self.supported_models)
        return data
