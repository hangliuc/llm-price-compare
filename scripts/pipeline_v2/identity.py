from dataclasses import dataclass, replace
import re
from pathlib import Path
from typing import Optional

import yaml

from scripts.pipeline_v2.models import Observation


@dataclass(frozen=True)
class IdentityReview:
    provider_id: str
    product_ids: tuple[str, ...]
    display_name: str
    reason: str


class AliasRegistry:
    """Explicit source aliases plus conservative ID normalization.

    The fallback only lowercases and trims IDs. It deliberately does not strip
    dates, preview markers, regions, tiers or channel suffixes.
    """

    def __init__(self, aliases: Optional[dict[tuple[str, str, str], str]] = None,
                 distinct_groups: Optional[set[tuple[str, frozenset[str]]]] = None):
        self.aliases = aliases or {}
        self.distinct_groups = distinct_groups or set()

    @classmethod
    def load(cls, path: Path) -> "AliasRegistry":
        if not path.exists():
            return cls()
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        aliases = {}
        for entry in data.get("aliases", []):
            target = entry["canonical_id"]
            target_provider, target_product = target.split("/", 1)
            for source in entry.get("sources", []):
                key = (source["source_id"], source.get("provider_id", target_provider),
                       source["product_id"])
                aliases[key] = target_product
        distinct_groups = set()
        for entry in data.get("distinct", []):
            distinct_groups.add((entry["provider_id"], frozenset(entry["product_ids"])))
        return cls(aliases, distinct_groups)

    @staticmethod
    def safe_product_id(product_id: str) -> str:
        value = re.sub(r"\s+", "-", product_id.strip()).lower()
        return re.sub(r"-{2,}", "-", value)

    def resolve(self, item: Observation) -> Observation:
        source_product_id = item.source_product_id or item.product_id
        key = (item.source_id, item.provider_id, source_product_id)
        product_id = self.aliases.get(key, self.safe_product_id(source_product_id))
        return replace(item, product_id=product_id, source_product_id=source_product_id)

    def is_confirmed_distinct(self, provider_id: str, product_ids: tuple[str, ...]) -> bool:
        return (provider_id, frozenset(product_ids)) in self.distinct_groups


def find_identity_reviews(observations: list[Observation],
                          registry: Optional[AliasRegistry] = None) -> list[IdentityReview]:
    """Find same-provider/same-name records that still resolve to different IDs."""
    grouped: dict[tuple[str, str], list[Observation]] = {}
    for item in observations:
        name = str(item.fields.get("name") or "").strip().casefold()
        if name:
            grouped.setdefault((item.provider_id, name), []).append(item)
    reviews = []
    for (provider_id, normalized_name), items in sorted(grouped.items()):
        product_ids = tuple(sorted({item.product_id for item in items}))
        source_ids = {item.source_id for item in items}
        confirmed_distinct = registry and registry.is_confirmed_distinct(provider_id, product_ids)
        if len(product_ids) > 1 and len(source_ids) > 1 and not confirmed_distinct:
            reviews.append(IdentityReview(
                provider_id=provider_id,
                product_ids=product_ids,
                display_name=str(items[0].fields.get("name") or normalized_name),
                reason="same provider and display name resolved to multiple canonical IDs",
            ))
    return reviews
