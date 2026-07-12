# scripts/adapters/tests/test_opencode.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.opencode import OpenCodeAdapter
from scripts.core.models import BillingType

FIXTURES = Path(__file__).parent / "fixtures"


@patch("scripts.adapters.opencode.fetch_html")
def test_opencode_parses_coding_plan(mock_fetch):
    mock_fetch.return_value = (FIXTURES / "opencode_pricing.html").read_text(encoding="utf-8")
    adapter = OpenCodeAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=1)

    p = products[0]
    assert p.billing_type == BillingType.CODING_PLAN
    assert p.prices["monthly_price"] == 99
    assert p.prices["currency"] == "CNY"
    assert p.prices["included_quota"] == 500
    assert p.prices["quota_unit"] == "次"
    assert len(p.prices["features"]) == 2
