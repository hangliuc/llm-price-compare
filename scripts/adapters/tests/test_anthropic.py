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

    # 当前 adapter 只解析 per_token（subscription 由 manual yaml 维护）
    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types

    # 验证解析出的价格正确
    opus = next(p for p in products if "Opus" in p.model)
    assert opus.prices["input"] == 15.0
    assert opus.prices["output"] == 75.0
    assert opus.prices["currency"] == "USD"
    # Cache Hits 应该被解析为 cached_input
    assert opus.prices.get("cached_input") == 1.5
