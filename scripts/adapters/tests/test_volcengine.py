# scripts/adapters/tests/test_volcengine.py
import pytest
from unittest.mock import patch
from scripts.adapters.volcengine import VolcengineAdapter
from scripts.core.models import BillingType

# 与当前 VolcengineAdapter 解析逻辑匹配的 fixture：
# - adapter 用 fetch_html（不是 fetch_html_browser）
# - 遍历所有 <table>，每行 <td> 数 >=2，第一列是模型名
# - 模型名必须在 _WHITELIST 内（doubao-pro-32k / doubao-seed-1.6）
# - 价格从该行所有 <td>[1:] 中提取数字
_FAKE_HTML = """
<html><body>
<table>
  <tr><th>模型</th><th>输入</th><th>输出</th></tr>
  <tr><td>doubao-pro-32k</td><td>¥0.008</td><td>¥0.02</td></tr>
  <tr><td>doubao-seed-1.6</td><td>¥0.012</td><td>¥0.03</td></tr>
</table>
</body></html>
"""


@patch("scripts.adapters.volcengine.fetch_html")
def test_volcengine_parses_token_and_plan(mock_fetch):
    mock_fetch.return_value = _FAKE_HTML
    adapter = VolcengineAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    types = {p.billing_type for p in products}
    assert BillingType.PER_TOKEN in types

    # 验证解析出的价格正确
    pro = next(p for p in products if p.model == "doubao-pro-32k")
    assert pro.prices["input"] == 0.008
    assert pro.prices["output"] == 0.02
    assert pro.prices["currency"] == "CNY"


@pytest.mark.browser
def test_volcengine_live_fetch():
    adapter = VolcengineAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    assert len(products) >= 2
