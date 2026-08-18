import json

import pytest

from scripts.core.models import BillingType, Product
from scripts.core.reconcile import reconcile_provider
from scripts.pipeline.alerts import deliver_alerts
from scripts.pipeline.changes import detect_changes
from scripts.pipeline.collector import collect_sources
from scripts.pipeline.config import PipelineConfig
from scripts.pipeline.guardrails import guard_provider, validate_product
from scripts.pipeline.publisher import atomic_write_json
from scripts.pipeline.runner import run_pipeline
from scripts.pipeline.storage import PipelineStore


def _product(product_id="model-a", input_price=1.0, output_price=2.0):
    return Product(
        id=product_id,
        model=product_id,
        billing_type=BillingType.PER_TOKEN,
        prices={
            "input": input_price,
            "output": output_price,
            "currency": "USD",
            "unit": "1M tokens",
        },
        purchase_url="https://example.com/pricing",
    )


def _provider(products=None, status="live", source="test"):
    from scripts.core.models import product_to_dict

    products = products or [product_to_dict(_product())]
    return {
        "id": "test-provider",
        "name": "Test Provider",
        "name_en": "Test Provider",
        "region": "Global",
        "website": "https://example.com",
        "pricing_url": "https://example.com/pricing",
        "products": products,
    }


class FailingSource:
    source_id = "failing"

    def fetch_all(self):
        raise RuntimeError("upstream unavailable")


def test_alert_delivery_reports_missing_configuration(monkeypatch):
    monkeypatch.delenv("FEISHU_WEBHOOK_URL", raising=False)
    result = deliver_alerts([("failed", "test", "boom")])
    assert result.status == "skipped"
    assert result.alert_count == 1


def test_source_failure_is_structured():
    result = collect_sources([FailingSource()])[0]
    assert result.status == "failed"
    assert result.products == {}
    assert "upstream unavailable" in result.error


def test_reconcile_uses_primary_source_for_close_prices():
    result = reconcile_provider(
        "test-provider", [_product(input_price=1.0)],
        [_product(input_price=1.01)], [],
    )
    assert result.products[0].prices["input"] == 1.0
    assert result.confidence == "medium"


def test_validation_rejects_missing_output_price():
    from scripts.core.models import product_to_dict

    product = product_to_dict(_product())
    product["prices"]["output"] = None
    errors = validate_product(product)
    assert any("prices.output" in error for error in errors)


def test_provider_guard_blocks_large_drop():
    from scripts.core.models import product_to_dict

    old = _provider([product_to_dict(_product(str(index))) for index in range(10)])
    new = _provider([product_to_dict(_product("only-one"))])
    decision = guard_provider(new, old, min_ratio=0.5)
    assert decision.accepted is False
    assert any("product count dropped" in error for error in decision.errors)


def test_provider_guard_blocks_exact_threshold_drop():
    from scripts.core.models import product_to_dict

    old = _provider([product_to_dict(_product(str(index))) for index in range(10)])
    new = _provider([product_to_dict(_product(str(index))) for index in range(5)])
    decision = guard_provider(new, old, min_ratio=0.5)
    assert decision.accepted is False


def test_last_known_good_only_exposes_published_release(tmp_path):
    store = PipelineStore(tmp_path / "pipeline.db")
    run_id = "test-run"
    store.start_run(run_id)
    dataset = {"generated_at": "2026-08-18T00:00:00+08:00", "providers": [_provider()]}
    store.stage_release(run_id, dataset)
    assert store.load_last_published() is None
    store.mark_release_published(run_id)
    assert store.load_last_published()["providers"][0]["name"] == "Test Provider"
    store.close()


def test_atomic_publish_preserves_existing_file_on_serialization_error(tmp_path):
    target = tmp_path / "prices.json"
    target.write_text('{"version": "old"}', encoding="utf-8")
    with pytest.raises(TypeError):
        atomic_write_json(target, {"invalid": object()})
    assert json.loads(target.read_text(encoding="utf-8"))["version"] == "old"
    assert [path for path in tmp_path.iterdir() if path != target] == []


def test_change_detection_records_price_field_changes():
    from scripts.core.models import product_to_dict

    old = {"providers": [_provider([product_to_dict(_product(input_price=1.0))])]}
    new = {"providers": [_provider([product_to_dict(_product(input_price=1.5))])]}
    changes = detect_changes(old, new)
    assert len(changes) == 1
    assert changes[0]["field"] == "input"
    assert changes[0]["old_value"] == 1.0
    assert changes[0]["new_value"] == 1.5


def test_pipeline_preserves_output_on_total_source_outage(tmp_path):
    output = tmp_path / "prices.json"
    output.write_text(json.dumps({
        "generated_at": "2026-08-17T00:00:00+08:00",
        "providers": [_provider()],
        "provider_status": [{
            "provider_id": "test-provider", "status": "ok",
            "last_success_at": "2026-08-17T00:00:00+08:00", "stale": False,
        }],
    }), encoding="utf-8")
    config = PipelineConfig(
        output_path=output,
        status_path=tmp_path / "run_status.json",
        db_path=tmp_path / "pipeline.db",
        manual_dir=tmp_path / "manual",
        lock_path=tmp_path / "pipeline.lock",
        min_providers=1,
        min_products=1,
        provider_min_ratio=0.5,
        dataset_min_ratio=0.5,
    )

    before = output.read_bytes()
    assert run_pipeline(config, sources=[FailingSource()], adapters=[], send_alerts=False) == 1
    assert output.read_bytes() == before
    published = json.loads(output.read_text(encoding="utf-8"))
    assert published["providers"][0]["products"][0]["id"] == "model-a"
    status = json.loads(config.status_path.read_text(encoding="utf-8"))
    assert status["status"] == "failed"
    assert status["published"] is False
