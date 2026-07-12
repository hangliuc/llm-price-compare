# scripts/adapters/tests/test_zhipu.py
import pytest
from unittest.mock import patch
from scripts.adapters.zhipu import ZhipuAdapter
from scripts.core.models import BillingType

_FAKE_HTML = """
<html><body>
<div class="model-list">
  <div class="model-item">
    <span class="name">GLM-4-Plus</span>
    <span class="input">¥0.05</span>
    <span class="output">¥0.05</span>
  </div>
</div>
<div class="plan-list">
  <div class="plan-item">
    <span class="plan-name">智谱 Coding Plan</span>
    <span class="plan-price">¥99/月</span>
    <span class="plan-quota">500 次</span>
  </div>
</div>
</body></html>
"""


@patch("scripts.adapters.zhipu.fetch_html_browser")
def test_zhipu_parses_token_and_plan(mock_fetch):
    mock_fetch.return_value = _FAKE_HTML
    adapter = ZhipuAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types
    assert BillingType.CODING_PLAN in types

    plan = next(p for p in products if p.billing_type == BillingType.CODING_PLAN)
    assert plan.prices["currency"] == "CNY"
    assert plan.prices["included_quota"] == 500


@pytest.mark.browser
def test_zhipu_live_fetch():
    """真实抓取测试，仅本地手动跑，CI 跳过。"""
    adapter = ZhipuAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    assert len(products) >= 2
