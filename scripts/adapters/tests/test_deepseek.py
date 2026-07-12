# scripts/adapters/tests/test_deepseek.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.deepseek import DeepSeekAdapter

FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _load_expected(name: str) -> list:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@patch("scripts.adapters.deepseek.fetch_html")
def test_deepseek_parses_pricing_table(mock_fetch):
    mock_fetch.return_value = _load_fixture("deepseek_pricing.html")
    adapter = DeepSeekAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    expected = _load_expected("deepseek_expected.json")
    assert len(products) == len(expected)
    for got, want in zip(products, expected):
        assert got.id == want["id"]
        assert got.model == want["model"]
        assert got.billing_type.value == want["billing_type"]
        assert got.prices["input"] == want["prices"]["input"]
        assert got.prices["output"] == want["prices"]["output"]
        assert got.prices["currency"] == want["prices"]["currency"]
