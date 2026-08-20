from scripts.pipeline_v2.models import ProductCandidate


def build_catalog(release_id: str, published_at: str, candidates: list[ProductCandidate],
                  provider_metadata: dict[str, dict]) -> dict:
    provider_ids = sorted({item.provider_id for item in candidates})
    providers = []
    for provider_id in provider_ids:
        metadata = provider_metadata.get(provider_id, {})
        providers.append({
            "id": provider_id,
            "name": metadata.get("name", provider_id),
            "name_en": metadata.get("name_en", metadata.get("name", provider_id)),
            "website": metadata.get("website", ""),
            "pricing_url": metadata.get("pricing_url", ""),
            "region": metadata.get("region", "unknown"),
        })

    def serialize(item: ProductCandidate) -> dict:
        return {
            "canonical_id": item.canonical_id,
            "provider_id": item.provider_id,
            "product_id": item.product_id,
            "status": item.status,
            "stale_fields": item.stale_fields,
            "freshness": item.freshness,
            "fields": item.fields,
        }

    return {
        "schema_version": "2.0",
        "release_id": release_id,
        "published_at": published_at,
        "providers": providers,
        "models": [serialize(item) for item in candidates if item.product_kind == "model"],
        "plans": [serialize(item) for item in candidates if item.product_kind == "plan"],
    }
