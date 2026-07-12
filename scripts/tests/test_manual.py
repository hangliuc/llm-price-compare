# scripts/tests/test_manual.py
import tempfile
import os
from pathlib import Path
from scripts.core.manual import load_manual_providers


def test_load_manual_providers_returns_list():
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "a.yaml").write_text("""
id: a
name: A
name_en: A
region: us
website: https://a.com/
pricing_url: https://a.com/p
products:
  - id: a-1
    billing_type: per_token
    prices: {input: 1, output: 2, currency: USD, unit: per_1m_tokens}
    purchase_url: https://a.com/buy
""", encoding="utf-8")
        (Path(d) / "b.yaml").write_text("""
id: b
name: B
name_en: B
region: cn
website: https://b.com/
pricing_url: https://b.com/p
products: []
""", encoding="utf-8")
        providers = load_manual_providers(d)
        assert len(providers) == 2
        ids = [p["id"] for p in providers]
        assert "a" in ids and "b" in ids
        a = next(p for p in providers if p["id"] == "a")
        assert len(a["products"]) == 1
        assert a["products"][0]["prices"]["input"] == 1


def test_load_manual_providers_empty_dir():
    with tempfile.TemporaryDirectory() as d:
        providers = load_manual_providers(d)
        assert providers == []
