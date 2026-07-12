# scripts/adapters/tests/test_anthropic.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.anthropic import AnthropicAdapter
from scripts.core.models import BillingType

FIXTURES = Path(__file__).parent / "fixtures"


@patch("scripts.adapters.anthropic.fetch_html")
def test_anthropic_parses_api_and_subscription(mock_fetch):
    mock_fetch.return_value = (FIXTURES / "anthropic_pricing.html").read_text(encoding="utf-8")
    adapter = AnthropicAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    # 至少有一个 per_token 和一个 subscription
    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types
    assert BillingType.SUBSCRIPTION in types

    # 找到 subscription，验证 monthly_price
    sub = next(p for p in products if p.billing_type == BillingType.SUBSCRIPTION)
    assert sub.prices["monthly_price"] == 20
    assert "features" in sub.prices
