from dataclasses import replace
from datetime import datetime, timezone
from typing import Iterable, Optional

from scripts.core.models import BillingType, Product
from scripts.pipeline_v2.models import Observation


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def product_kind(product: Product) -> str:
    return "model" if product.billing_type == BillingType.PER_TOKEN else "plan"


def product_fields(product: Product) -> dict:
    fields = {
        "name": product.model or product.id,
        "billing_type": product.billing_type.value,
        "purchase_url": product.purchase_url,
        "modalities": list(product.modalities or []),
    }
    if product.context_window is not None:
        fields["context_window"] = product.context_window
    if product.release_date:
        fields["release_date"] = product.release_date
    if product.notes:
        fields["notes"] = product.notes
    if product.plan_category:
        fields["plan_category"] = product.plan_category
    fields["featured_on_home"] = bool(product.featured_on_home)
    for key, value in (product.prices or {}).items():
        if key == "features":
            fields["features"] = value
        elif key in {"included_quota", "quota_unit"}:
            continue
        else:
            fields[f"price.{key}"] = value
    quota = (product.prices or {}).get("included_quota")
    quota_unit = (product.prices or {}).get("quota_unit")
    if quota is not None or quota_unit:
        fields["allowance"] = {"value": quota, "unit": quota_unit or "unknown"}
    return fields


def products_to_observations(source_id: str, source_kind: str, provider_id: str,
                             products: Iterable[Product], observed_at: Optional[str] = None,
                             source_url: str = "", expires_at: str = "") -> list[Observation]:
    timestamp = observed_at or now_iso()
    return [Observation(
        source_id=source_id,
        source_kind=source_kind,
        provider_id=provider_id,
        product_id=product.id,
        product_kind=product_kind(product),
        observed_at=timestamp,
        fields=product_fields(product),
        source_url=source_url or product.purchase_url,
        expires_at=expires_at,
    ) for product in products]


def manual_dict_to_observations(provider: dict, observed_at: Optional[str] = None) -> list[Observation]:
    # A pipeline run is not a manual verification. Missing verification stays
    # empty and is surfaced by the freshness review instead of being refreshed.
    timestamp = str(provider.get("verified_at") or observed_at or "")
    products = []
    directives = {}
    for raw in provider.get("products", []):
        try:
            billing = BillingType(raw["billing_type"])
        except (KeyError, ValueError):
            continue
        products.append(Product(
            id=raw["id"], billing_type=billing, prices=raw.get("prices", {}),
            purchase_url=raw.get("purchase_url", ""), model=raw.get("model"),
            context_window=raw.get("context_window"), modalities=raw.get("modalities", []),
            release_date=raw.get("release_date"), notes=raw.get("notes"),
            plan_category=raw.get("plan_category"),
            featured_on_home=bool(raw.get("featured_on_home", False)),
        ))
        directives[raw["id"]] = tuple(str(item) for item in raw.get("clear_fields", []))
    observations = products_to_observations(
        "manual", "manual_override", provider["id"], products, timestamp,
        provider.get("source_url") or provider.get("pricing_url", ""),
        str(provider.get("expires_at") or ""),
    )
    observations = [replace(item, clear_fields=directives.get(item.product_id, ()))
                    for item in observations]
    for entry in provider.get("retired_products", []):
        product_id = entry if isinstance(entry, str) else entry.get("id")
        if not product_id:
            continue
        product_kind_value = (entry.get("product_kind", "model")
                              if isinstance(entry, dict) else "model")
        observations.append(Observation(
            source_id="manual", source_kind="manual_override",
            provider_id=provider["id"], product_id=str(product_id),
            product_kind=product_kind_value, observed_at=timestamp, fields={},
            source_url=provider.get("source_url") or provider.get("pricing_url", ""),
            expires_at=str(provider.get("expires_at") or ""), retired=True,
        ))
    return observations
