import json
from pathlib import Path

from scripts.core.models import BillingType, Product
from scripts.pipeline_v2.catalog import build_catalog
from scripts.pipeline_v2.changes import detect_changes
from scripts.pipeline_v2.config import V2Config
from scripts.pipeline_v2.identity import AliasRegistry, find_identity_reviews
from scripts.pipeline_v2.drift import apply_price_drift_guard
from scripts.pipeline_v2.models import Observation
from scripts.pipeline_v2.evidence import persist_evidence
from scripts.pipeline_v2.freshness import apply_freshness
from scripts.pipeline_v2.manual_freshness import inspect_manual_providers
from scripts.pipeline_v2.normalize import manual_dict_to_observations
from scripts.pipeline_v2.publisher import publish, rollback
from scripts.pipeline_v2.release_gate import check_release
from scripts.pipeline_v2.reconcile import find_authoritative_conflicts, reconcile
from scripts.pipeline_v2.runner import run_pipeline
from scripts.pipeline_v2.storage import V2Store
from scripts.pipeline_v2.validate import validate_catalog
from scripts.sources.litellm import _normalize_model_id


def observation(source_id="litellm", source_kind="aggregator", input_price=3):
    return Observation(
        source_id=source_id, source_kind=source_kind, provider_id="anthropic",
        product_id="claude-token", product_kind="model",
        observed_at="2026-08-19T00:00:00Z",
        fields={
            "name": "Claude", "billing_type": "per_token",
            "price.input": input_price, "price.output": 15,
            "price.currency": "USD", "price.unit": "per_1m_tokens",
            "purchase_url": "https://anthropic.com/pricing", "modalities": ["text"],
            "featured_on_home": False,
        },
    )


def test_reconcile_prefers_official_source():
    result = reconcile([
        observation(input_price=4),
        observation("official:anthropic", "official_adapter", 3),
    ])
    assert result[0].fields["price.input"] == 3
    decision = next(item for item in result[0].decisions if item.field == "price.input")
    assert decision.source_kind == "official_adapter"


def test_authoritative_conflict_uses_lkg_and_creates_review():
    old = build_catalog("old", "t1", reconcile([observation(input_price=3)]), {})
    official_a = observation("official:a", "official_adapter", 4)
    official_b = observation("official:b", "official_document", 5)
    conflicts = find_authoritative_conflicts([official_a, official_b])
    assert any(item.field == "price.input" for item in conflicts)
    blocked = {(item.canonical_id, item.field) for item in conflicts}
    candidate = reconcile([official_a, official_b], old, blocked)[0]
    assert candidate.fields["price.input"] == 3
    assert candidate.status == "partial"
    assert "price.input" in candidate.stale_fields


def test_last_known_good_retains_missing_product():
    old = build_catalog("old", "2026-08-18T00:00:00Z", reconcile([observation()]), {
        "anthropic": {"name": "Anthropic"}
    })
    result = reconcile([], old)
    assert result[0].status == "partial"
    assert result[0].fields["price.input"] == 3
    assert "price.input" in result[0].stale_fields


def test_lkg_freshness_reports_age_instead_of_resetting_clock():
    old_candidates = reconcile([observation()])
    apply_freshness(old_candidates, [observation()], "2026-08-19T00:00:00Z")
    old = build_catalog("old", "2026-08-19T00:00:00Z", old_candidates, {})
    current = reconcile([], old)
    apply_freshness(current, [], "2026-08-20T12:00:00Z")
    assert current[0].freshness["lkg_age_hours"] == 36.0
    assert current[0].freshness["latest_observed_at"] is None


def test_manual_verification_time_is_not_replaced_by_run_time():
    provider = {
        "id": "fixture", "source_url": "https://example.com/pricing",
        "verified_at": "2026-07-01T00:00:00Z",
        "expires_at": "2026-10-01T00:00:00Z",
        "products": [{
            "id": "plan", "model": "Fixture Plan", "billing_type": "subscription",
            "prices": {"monthly_price": 10, "currency": "USD"},
        }],
    }
    item = manual_dict_to_observations(provider, "2099-01-01T00:00:00Z")[0]
    assert item.observed_at == provider["verified_at"]
    assert item.expires_at == provider["expires_at"]
    assert item.source_kind == "manual_override"


def test_expired_manual_creates_review_and_stale_product():
    provider = {
        "id": "fixture", "source_url": "https://example.com/pricing",
        "verified_at": "2026-01-01T00:00:00Z",
        "expires_at": "2026-02-01T00:00:00Z",
        "products": [{
            "id": "plan", "model": "Fixture Plan", "billing_type": "subscription",
            "prices": {"monthly_price": 10, "currency": "USD"},
        }],
    }
    reviews, stale = inspect_manual_providers([provider], "2026-08-20T00:00:00Z")
    observations = manual_dict_to_observations(provider)
    candidates = reconcile(observations)
    apply_freshness(candidates, observations, "2026-08-20T00:00:00Z", stale)
    assert reviews[0].reason == "manual source verification expired"
    assert candidates[0].status == "stale"
    assert candidates[0].freshness["manual_stale"] is True


def test_raw_evidence_is_gzipped_and_content_addressed(tmp_path):
    first = persist_evidence(tmp_path, "source", {"value": 1})
    second = persist_evidence(tmp_path, "source", {"value": 1})
    assert first.sha256 == second.sha256
    assert first.artifact_path == second.artifact_path
    import gzip
    with gzip.open(first.artifact_path, "rt", encoding="utf-8") as handle:
        assert json.load(handle) == {"value": 1}


def test_evidence_retention_preserves_still_referenced_object(tmp_path):
    store = V2Store(tmp_path / "v2.db")
    try:
        store.start_run("old", "payg", "2026-01-01T00:00:00Z")
        store.start_run("new", "payg", "2026-08-20T00:00:00Z")
        record = persist_evidence(tmp_path / "raw", "source", {"same": True})
        store.record_evidence("old", record, "2026-01-01T00:00:00Z")
        store.record_evidence("new", record, "2026-08-20T00:00:00Z")
        result = store.prune_evidence(90, "2026-08-20T00:00:00Z")
        assert result["records"] == 1
        assert result["files"] == 0
        assert Path(record.artifact_path).exists()
    finally:
        store.close()


def test_validation_rejects_negative_price():
    candidate = reconcile([observation(input_price=-1)])
    catalog = build_catalog("r1", "2026-08-19T00:00:00Z", candidate, {
        "anthropic": {"name": "Anthropic"}
    })
    result = validate_catalog(catalog)
    assert not result.accepted
    assert any("negative price.input" in error for error in result.errors)


def test_price_drift_uses_field_lkg_and_creates_review():
    old = build_catalog("old", "t1", reconcile([observation(input_price=3)]), {})
    candidates = reconcile([observation(input_price=30)], old)
    guarded, reviews, warnings = apply_price_drift_guard(candidates, old)
    assert guarded[0].fields["price.input"] == 3
    assert guarded[0].status == "partial"
    assert "price.input" in guarded[0].stale_fields
    assert reviews[0].details["candidate"] == 30.0
    assert warnings == []


def test_price_drift_does_not_compare_different_currency():
    old = build_catalog("old", "t1", reconcile([observation(input_price=3)]), {})
    changed = observation(input_price=30)
    changed.fields["price.currency"] = "CNY"
    guarded, reviews, _ = apply_price_drift_guard(reconcile([changed], old), old)
    assert guarded[0].fields["price.input"] == 30
    assert reviews == []


def test_change_detection_is_field_level():
    first = build_catalog("r1", "t1", reconcile([observation(input_price=3)]), {})
    second = build_catalog("r2", "t2", reconcile([observation(input_price=4)]), {})
    changes = detect_changes(first, second)
    assert changes == [{
        "canonical_id": "anthropic/claude-token", "field": "price.input",
        "old": 3, "new": 4,
    }]


def test_identity_normalization_only_changes_case_and_whitespace():
    registry = AliasRegistry()
    item = observation()
    item = type(item)(**{**item.__dict__, "product_id": " Claude-Preview-20260819 "})
    resolved = registry.resolve(item)
    assert resolved.product_id == "claude-preview-20260819"
    assert resolved.source_product_id == " Claude-Preview-20260819 "
    assert _normalize_model_id("anthropic/claude-20260819", strip_date=False) == "claude-20260819"


def test_explicit_alias_and_ambiguous_identity_review(tmp_path):
    alias_file = tmp_path / "aliases.yaml"
    alias_file.write_text("""
version: 1
aliases:
  - canonical_id: anthropic/claude-sonnet-token
    sources:
      - source_id: openrouter
        product_id: claude-sonnet-latest-token
""", encoding="utf-8")
    registry = AliasRegistry.load(alias_file)
    first = observation("openrouter")
    first = type(first)(**{**first.__dict__, "product_id": "claude-sonnet-latest-token"})
    second = observation("litellm")
    second = type(second)(**{**second.__dict__, "product_id": "claude-sonnet-token"})
    resolved = [registry.resolve(item) for item in (first, second)]
    assert {item.product_id for item in resolved} == {"claude-sonnet-token"}
    assert find_identity_reviews(resolved) == []

    ambiguous = type(second)(**{
        **second.__dict__, "source_id": "official:anthropic",
        "product_id": "claude-sonnet-global-token",
    })
    reviews = find_identity_reviews([registry.resolve(first), registry.resolve(ambiguous)])
    assert len(reviews) == 1
    assert "multiple canonical IDs" in reviews[0].reason


def test_confirmed_distinct_variants_do_not_create_review(tmp_path):
    alias_file = tmp_path / "aliases.yaml"
    alias_file.write_text("""
distinct:
  - provider_id: anthropic
    product_ids: [claude-cn-token, claude-token]
    reason: separate regional offers
""", encoding="utf-8")
    registry = AliasRegistry.load(alias_file)
    first = observation("manual")
    first = type(first)(**{**first.__dict__, "product_id": "claude-cn-token"})
    second = observation("openrouter")
    assert find_identity_reviews(
        [registry.resolve(first), registry.resolve(second)], registry
    ) == []


def test_publish_writes_complete_catalog_and_status(tmp_path):
    catalog_path = tmp_path / "public" / "v2" / "catalog.json"
    status_path = tmp_path / "public" / "v2" / "status.json"
    publish(catalog_path, status_path, {"schema_version": "2.0"}, {"status": "healthy"})
    assert json.loads(catalog_path.read_text())["schema_version"] == "2.0"
    assert json.loads(status_path.read_text())["status"] == "healthy"
    assert catalog_path.stat().st_mode & 0o444


def test_publish_keeps_immutable_release_and_can_rollback(tmp_path):
    public = tmp_path / "public" / "v2"
    releases = tmp_path / "releases"
    first = {"schema_version": "2.0", "release_id": "r1", "models": []}
    first_status = {"schema_version": "2.0", "release_id": "r1", "status": "healthy"}
    publish(public / "catalog.json", public / "status.json", first, first_status, releases)
    second = {"schema_version": "2.0", "release_id": "r2", "models": []}
    second_status = {"schema_version": "2.0", "release_id": "r2", "status": "healthy"}
    publish(public / "catalog.json", public / "status.json", second, second_status, releases)

    status = rollback(
        public / "catalog.json", public / "status.json", releases, "r1",
        "2026-08-19T00:00:00Z")
    assert json.loads((public / "catalog.json").read_text())["release_id"] == "r1"
    assert status["rollback_target"] == "r1"
    assert json.loads((releases / "r2" / "catalog.json").read_text())["release_id"] == "r2"


def test_release_gate_blocks_large_catalog_drop():
    product = {
        "canonical_id": "anthropic/claude", "provider_id": "anthropic",
        "product_id": "claude", "status": "accepted", "stale_fields": [],
        "fields": {"name": "Claude", "billing_type": "per_token",
                   "purchase_url": "https://example.com", "price.input": 1,
                   "price.output": 2, "price.currency": "USD",
                   "price.unit": "per_1m_tokens"},
    }
    base = {"schema_version": "2.0", "providers": [{"id": "anthropic"}],
            "models": [dict(product, canonical_id=f"anthropic/claude-{i}",
                            product_id=f"claude-{i}") for i in range(10)], "plans": []}
    current = {**base, "models": base["models"][:5]}
    result = check_release(current, base)
    assert not result.accepted
    assert "dropped 50.0%" in result.errors[-1]


class FailingSource:
    source_id = "failed"

    def fetch_all(self):
        raise RuntimeError("network down")


def test_all_source_failure_does_not_replace_published_file(tmp_path):
    public = tmp_path / "public" / "v2"
    public.mkdir(parents=True)
    catalog_path = public / "catalog.json"
    catalog_path.write_text('{"release_id":"previous"}', encoding="utf-8")
    config = V2Config(
        runtime_dir=tmp_path, db_path=tmp_path / "v2.db",
        catalog_path=catalog_path, status_path=public / "status.json",
        manual_dir=tmp_path / "manual", alias_path=tmp_path / "aliases.yaml",
        lock_path=tmp_path / "pipeline.lock",
    )
    assert run_pipeline(config, "payg", sources=[FailingSource()], adapters=[]) == 1
    assert json.loads(catalog_path.read_text())["release_id"] == "previous"
    run_status = json.loads((tmp_path / "public" / "run_status.json").read_text())
    assert run_status["status"] == "failed"
    store = V2Store(config.db_path)
    try:
        alerts = store.list_alerts()
        assert alerts[0]["severity"] == "P0"
        assert alerts[0]["delivery_status"] == "skipped"
    finally:
        store.close()


class OneSource:
    source_id = "fixture"

    def fetch_all(self):
        return {"anthropic": [Product(
            id="claude-token", billing_type=BillingType.PER_TOKEN,
            prices={"input": 3, "output": 15, "currency": "USD",
                    "unit": "per_1m_tokens"},
            purchase_url="https://anthropic.com/pricing", model="Claude",
            modalities=["text"],
        )]}


def test_runner_publishes_v2_catalog(tmp_path):
    public = tmp_path / "public" / "v2"
    config = V2Config(
        runtime_dir=tmp_path, db_path=tmp_path / "v2.db",
        catalog_path=public / "catalog.json", status_path=public / "status.json",
        manual_dir=tmp_path / "manual", alias_path=tmp_path / "aliases.yaml",
        lock_path=tmp_path / "pipeline.lock",
    )
    assert run_pipeline(config, "payg", sources=[OneSource()], adapters=[]) == 0
    catalog = json.loads(config.catalog_path.read_text())
    assert catalog["schema_version"] == "2.0"
    assert catalog["models"][0]["canonical_id"] == "anthropic/claude-token"
    assert (tmp_path / "releases" / catalog["release_id"] / "catalog.json").exists()
    run_status = json.loads((tmp_path / "public" / "run_status.json").read_text())
    assert run_status["status"] == "published"
    store = V2Store(config.db_path)
    try:
        evidence = store.list_evidence(run_status["run_id"])
        assert evidence[0]["artifact_kind"] == "normalized_snapshot"
    finally:
        store.close()


def test_evidence_write_failure_keeps_published_catalog(tmp_path, monkeypatch):
    public = tmp_path / "public" / "v2"
    public.mkdir(parents=True)
    catalog_path = public / "catalog.json"
    catalog_path.write_text('{"release_id":"previous"}', encoding="utf-8")
    config = V2Config(
        runtime_dir=tmp_path, db_path=tmp_path / "v2.db",
        catalog_path=catalog_path, status_path=public / "status.json",
        manual_dir=tmp_path / "manual", alias_path=tmp_path / "aliases.yaml",
        lock_path=tmp_path / "pipeline.lock",
    )

    def fail(*args, **kwargs):
        raise OSError("evidence disk full")

    monkeypatch.setattr("scripts.pipeline_v2.runner.persist_evidence", fail)
    assert run_pipeline(config, "payg", sources=[OneSource()], adapters=[]) == 1
    assert json.loads(catalog_path.read_text())["release_id"] == "previous"


def test_runner_blocks_large_price_change_after_first_release(tmp_path):
    public = tmp_path / "public" / "v2"
    config = V2Config(
        runtime_dir=tmp_path, db_path=tmp_path / "v2.db",
        catalog_path=public / "catalog.json", status_path=public / "status.json",
        manual_dir=tmp_path / "manual", alias_path=tmp_path / "aliases.yaml",
        lock_path=tmp_path / "pipeline.lock",
    )
    source = OneSource()
    assert run_pipeline(config, "payg", sources=[source], adapters=[]) == 0
    original_fetch = source.fetch_all

    def changed_fetch():
        products = original_fetch()
        products["anthropic"][0].prices["input"] = 30
        return products

    source.fetch_all = changed_fetch
    assert run_pipeline(config, "payg", sources=[source], adapters=[]) == 0
    catalog = json.loads(config.catalog_path.read_text())
    assert catalog["models"][0]["fields"]["price.input"] == 3
    assert catalog["models"][0]["status"] == "partial"
    store = V2Store(config.db_path)
    try:
        reviews = store.list_reviews()
        assert len(reviews) == 1
        approved = store.approve_review(
            reviews[0]["review_id"], "2026-08-19T00:00:00Z", accept_baseline=True,
            actor="tester", reason="confirmed on official pricing page")
        assert approved["status"] == "approved"
        assert approved["resolution"]["actor"] == "tester"
    finally:
        store.close()

    # The exact reviewed value, currency and unit can become the next V2
    # baseline; a different future spike would still be blocked.
    assert run_pipeline(config, "payg", sources=[source], adapters=[]) == 0
    catalog = json.loads(config.catalog_path.read_text())
    assert catalog["models"][0]["fields"]["price.input"] == 30
    assert catalog["models"][0]["status"] == "accepted"


def test_reject_review_does_not_create_baseline(tmp_path):
    store = V2Store(tmp_path / "v2.db")
    try:
        store.start_run("run", "payg", "2026-08-19T00:00:00Z")
        from scripts.pipeline_v2.models import ReviewItem
        store.record_review_items("run", [ReviewItem(
            "anthropic/claude-token", "price.input", "price change",
            {"candidate": 30, "currency": "USD", "unit": "per_1m_tokens"},
        )], "2026-08-19T00:00:00Z")
        review_id = store.list_reviews()[0]["review_id"]
        rejected = store.reject_review(
            review_id, "2026-08-19T00:00:00Z", actor="tester", reason="unit mismatch")
        assert rejected["status"] == "rejected"
        assert rejected["resolution"]["reason"] == "unit mismatch"
        assert store.accepted_baselines() == {}
    finally:
        store.close()
