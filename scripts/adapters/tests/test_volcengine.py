# scripts/adapters/tests/test_volcengine.py
import pytest
from unittest.mock import patch
from scripts.adapters.volcengine import VolcengineAdapter
from scripts.core.models import BillingType

_FAKE_HTML = """
<html><body>
<div class="ark-models">
  <div class="model">
    <span class="name">Doubao-pro-32k</span>
    <span class="input">¥0.008</span>
    <span class="output">¥0.02</span>
  </div>
</div>
<div class="ark-plans">
  <div class="plan">
    <span class="plan-name">火山 Coding Plan</span>
    <span class="plan-price">¥199/月</span>
    <span class="plan-quota">1000 次</span>
  </div>
</div>
</body></html>
"""


@patch("scripts.adapters.volcengine.fetch_html_browser")
def test_volcengine_parses_token_and_plan(mock_fetch):
    mock_fetch.return_value = _FAKE_HTML
    adapter = VolcengineAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types
    assert BillingType.CODING_PLAN in types

    plan = next(p for p in products if p.billing_type == BillingType.CODING_PLAN)
    assert plan.prices["monthly_price"] == 199
    assert plan.prices["included_quota"] == 1000


@pytest.mark.browser
def test_volcengine_live_fetch():
    adapter = VolcengineAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    assert len(products) >= 2
