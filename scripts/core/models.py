# scripts/core/models.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class BillingType(str, Enum):
    PER_TOKEN = "per_token"
    SUBSCRIPTION = "subscription"
    CODING_PLAN = "coding_plan"


PLAN_CATEGORIES = {"general_ai", "coding_tool", "developer_api"}


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
    plan_category: Optional[str] = None
    featured_on_home: bool = False


@dataclass
class Provider:
    id: str
    name: str
    name_en: str
    region: str
    website: str
    pricing_url: str
    products: list = field(default_factory=list)
