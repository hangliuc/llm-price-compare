from datetime import datetime, timezone
from typing import Optional

from scripts.pipeline_v2.models import ReviewItem


def parse_timestamp(value: object) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip()
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def inspect_manual_providers(providers: list[dict], now: str) -> tuple[list[ReviewItem], set[str]]:
    """Validate manual provenance without pretending a pipeline run is a verification."""
    current = parse_timestamp(now) or datetime.now(timezone.utc)
    reviews: list[ReviewItem] = []
    stale: set[str] = set()
    for provider in providers:
        provider_id = provider.get("id", "unknown")
        verified = parse_timestamp(provider.get("verified_at"))
        expires = parse_timestamp(provider.get("expires_at"))
        source_url = provider.get("source_url")
        problems = []
        if not source_url:
            problems.append("source_url missing")
        if not verified:
            problems.append("verified_at missing or invalid")
        if not expires:
            problems.append("expires_at missing or invalid")
        if verified and expires and expires <= verified:
            problems.append("expires_at must be later than verified_at")
        if problems:
            stale.add(provider_id)
            reviews.append(ReviewItem(
                canonical_id=f"{provider_id}/*", field="manual.freshness",
                reason="manual provenance incomplete",
                details={"problems": problems, "source_url": source_url or "",
                         "verified_at": provider.get("verified_at"),
                         "expires_at": provider.get("expires_at")},
            ))
        elif expires and expires < current:
            stale.add(provider_id)
            reviews.append(ReviewItem(
                canonical_id=f"{provider_id}/*", field="manual.freshness",
                reason="manual source verification expired",
                details={"source_url": source_url, "verified_at": provider["verified_at"],
                         "expires_at": provider["expires_at"]},
            ))
    return reviews, stale
