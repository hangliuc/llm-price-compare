from dataclasses import dataclass, field
from typing import Optional

from scripts.pipeline_v2.validate import validate_catalog


@dataclass
class ReleaseGateResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.errors


def check_release(catalog: dict, previous: Optional[dict] = None,
                  minimum_providers: int = 1,
                  maximum_product_drop_ratio: float = 0.30) -> ReleaseGateResult:
    """Final checks for the complete artifact consumed by the UI."""
    validation = validate_catalog(catalog)
    result = ReleaseGateResult(list(validation.errors), list(validation.warnings))
    providers = catalog.get("providers", [])
    products = catalog.get("models", []) + catalog.get("plans", [])
    if len(providers) < minimum_providers:
        result.errors.append(
            f"provider count {len(providers)} is below minimum {minimum_providers}"
        )
    if not products:
        result.errors.append("UI contract requires at least one product")
    for product in products:
        fields = product.get("fields", {})
        if not product.get("canonical_id") or not fields.get("name"):
            result.errors.append("UI contract requires stable IDs and product names")
            break
    if previous:
        old_count = len(previous.get("models", [])) + len(previous.get("plans", []))
        if old_count:
            drop = (old_count - len(products)) / old_count
            if drop > maximum_product_drop_ratio:
                result.errors.append(
                    f"product count dropped {drop:.1%}, limit is "
                    f"{maximum_product_drop_ratio:.1%}"
                )
    return result
