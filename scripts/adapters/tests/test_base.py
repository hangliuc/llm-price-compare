# scripts/adapters/tests/test_base.py
import pytest
from scripts.adapters.base import BaseAdapter
from scripts.core.models import Product, BillingType
from scripts.core.validate import ValidationError


class DummyAdapter(BaseAdapter):
    provider_id = "dummy"
    provider_name = "Dummy"
    provider_name_en = "Dummy"
    region = "us"
    website = "https://example.com/"
    pricing_url = "https://example.com/pricing"

    def fetch(self):
        return []


def test_to_provider_constructs_provider():
    a = DummyAdapter()
    p = a.to_provider([])
    assert p.id == "dummy"
    assert p.region == "us"


def test_assert_min_products_passes():
    a = DummyAdapter()
    prods = [Product(id=f"p{i}", billing_type=BillingType.PER_TOKEN,
                     prices={"input": 1, "output": 1, "currency": "USD", "unit": "per_1m_tokens"},
                     purchase_url="https://example.com") for i in range(3)]
    a.assert_min_products(prods, minimum=3)


def test_assert_min_products_raises():
    a = DummyAdapter()
    with pytest.raises(RuntimeError, match="page structure"):
        a.assert_min_products([], minimum=1)
