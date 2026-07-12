# scripts/adapters/tests/test_openai.py
import json
from pathlib import Path
from unittest.mock import patch
from scripts.adapters.openai import OpenAIAdapter

FIXTURES = Path(__file__).parent / "fixtures"


@patch("scripts.adapters.openai.fetch_html")
def test_openai_parses_models(mock_fetch):
    mock_fetch.return_value = (FIXTURES / "openai_pricing.html").read_text(encoding="utf-8")
    adapter = OpenAIAdapter()
    products = adapter.fetch()
    adapter.validate(products)
    adapter.assert_min_products(products, minimum=2)

    expected = json.loads((FIXTURES / "openai_expected.json").read_text(encoding="utf-8"))
    assert len(products) == len(expected)
    for got, want in zip(products, expected):
        assert got.id == want["id"]
        assert got.prices["cached_input"] == want["prices"]["cached_input"]
