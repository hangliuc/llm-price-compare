from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.errors


def validate_catalog(catalog: dict) -> ValidationResult:
    result = ValidationResult()
    if catalog.get("schema_version") != "2.0":
        result.errors.append("schema_version must be 2.0")
    provider_ids = {item.get("id") for item in catalog.get("providers", [])}
    seen = set()
    for section in ("models", "plans"):
        for item in catalog.get(section, []):
            cid = item.get("canonical_id")
            if not cid or cid in seen:
                result.errors.append(f"missing or duplicate canonical_id: {cid}")
            seen.add(cid)
            if item.get("provider_id") not in provider_ids:
                result.errors.append(f"unknown provider for {cid}")
            fields = item.get("fields", {})
            freshness = item.get("freshness")
            if not isinstance(freshness, dict):
                result.errors.append(f"missing freshness: {cid}")
            else:
                required_freshness = {
                    "latest_observed_at", "oldest_observed_at", "lkg_age_hours",
                    "manual_verified_at", "manual_expires_at", "manual_stale",
                }
                missing_freshness = required_freshness - freshness.keys()
                if missing_freshness:
                    result.errors.append(
                        f"incomplete freshness for {cid}: {sorted(missing_freshness)}")
            if not fields.get("name"):
                result.errors.append(f"missing name: {cid}")
            price_fields = [key for key in fields if key.startswith("price.") and key not in
                            {"price.currency", "price.unit"}]
            for key in price_fields:
                try:
                    if Decimal(str(fields[key])) < 0:
                        result.errors.append(f"negative {key}: {cid}")
                except (InvalidOperation, TypeError):
                    result.errors.append(f"invalid {key}: {cid}")
            if section == "models" and not {"price.input", "price.output"}.issubset(fields):
                result.errors.append(f"model must have input and output price: {cid}")
            if price_fields and not fields.get("price.currency"):
                result.errors.append(f"priced product has no currency: {cid}")
            if price_fields and not fields.get("price.unit") and section == "models":
                result.errors.append(f"priced model has no unit: {cid}")
            if section == "plans" and fields.get("price.monthly_price") is None:
                result.errors.append(f"plan has no monthly price: {cid}")
    if not catalog.get("models") and not catalog.get("plans"):
        result.errors.append("catalog has no products")
    return result
