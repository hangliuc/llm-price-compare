# scripts/tests/test_models.py
from scripts.core.models import (
    Product, Provider, BillingType, product_to_dict, provider_to_dict
)

def test_product_per_token_to_dict():
    p = Product(
        id="gpt-4o-token",
        model="GPT-4o",
        billing_type=BillingType.PER_TOKEN,
        context_window=128000,
        modalities=["text", "vision"],
        prices={"input": 2.5, "output": 10, "currency": "USD", "unit": "per_1m_tokens"},
        purchase_url="https://openai.com/api/pricing/",
    )
    d = product_to_dict(p)
    assert d["id"] == "gpt-4o-token"
    assert d["billing_type"] == "per_token"
    assert d["prices"]["input"] == 2.5
    assert d["purchase_url"].startswith("https://")

def test_product_coding_plan_to_dict():
    p = Product(
        id="zhipu-coding-plan",
        model=None,
        billing_type=BillingType.CODING_PLAN,
        context_window=None,
        modalities=[],
        prices={
            "monthly_price": 99,
            "currency": "CNY",
            "included_quota": 500,
            "quota_unit": "次",
            "features": ["GLM-4.5"]
        },
        purchase_url="https://open.bigmodel.cn/pricing",
    )
    d = product_to_dict(p)
    assert d["model"] is None
    assert d["billing_type"] == "coding_plan"
    assert d["prices"]["monthly_price"] == 99

def test_provider_to_dict():
    p = Provider(
        id="openai",
        name="OpenAI",
        name_en="OpenAI",
        region="us",
        website="https://openai.com/",
        pricing_url="https://openai.com/api/pricing/",
        products=[],
    )
    d = provider_to_dict(p)
    assert d["id"] == "openai"
    assert d["region"] == "us"
    assert d["products"] == []
