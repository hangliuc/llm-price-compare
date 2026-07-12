# scripts/core/models.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BillingType(str, Enum):
    PER_TOKEN = "per_token"
    SUBSCRIPTION = "subscription"
    CODING_PLAN = "coding_plan"


@dataclass
class Product:
    id: str
    billing_type: BillingType
    prices: dict
    purchase_url: str
    model: Optional[str] = None
    context_window: Optional[int] = None
    modalities: list = field(default_factory=list)
    release_date: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class Provider:
    id: str
    name: str
    name_en: str
    region: str
    website: str
    pricing_url: str
    products: list = field(default_factory=list)


@dataclass
class ProviderStatus:
    provider_id: str
    status: str  # "ok" | "failed" | "no_data"
    last_success_at: Optional[str] = None
    error: Optional[str] = None
    stale: bool = False
    warnings: list = field(default_factory=list)


def product_to_dict(p: Product) -> dict:
    return {
        "id": p.id,
        "model": p.model,
        "billing_type": p.billing_type.value,
        "context_window": p.context_window,
        "modalities": p.modalities,
        "release_date": p.release_date,
        "prices": p.prices,
        "purchase_url": p.purchase_url,
        "notes": p.notes,
    }


def provider_to_dict(p: Provider) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "name_en": p.name_en,
        "region": p.region,
        "website": p.website,
        "pricing_url": p.pricing_url,
        "products": [product_to_dict(prod) for prod in p.products],
    }


def provider_status_to_dict(s: ProviderStatus) -> dict:
    return {
        "provider_id": s.provider_id,
        "status": s.status,
        "last_success_at": s.last_success_at,
        "error": s.error,
        "stale": s.stale,
        "warnings": s.warnings,
    }
