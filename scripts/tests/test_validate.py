# scripts/tests/test_validate.py
import pytest
from scripts.core.models import Product, Provider, BillingType
from scripts.core.validate import validate_product, ValidationError


def _make_per_token_product(**overrides):
    base = dict(
        id="gpt-4o",
        billing_type=BillingType.PER_TOKEN,
        prices={"input": 2.5, "output": 10, "currency": "USD", "unit": "per_1m_tokens"},
        purchase_url="https://openai.com/",
    )
    base.update(overrides)
    return Product(**base)


def test_validate_product_per_token_ok():
    p = _make_per_token_product()
    validate_product(p)  # 不抛异常即通过


def test_validate_product_missing_id():
    p = _make_per_token_product(id="")
    with pytest.raises(ValidationError, match="id"):
        validate_product(p)


def test_validate_product_missing_input():
    p = _make_per_token_product(prices={"output": 10, "currency": "USD", "unit": "per_1m_tokens"})
    with pytest.raises(ValidationError, match="input"):
        validate_product(p)


def test_validate_product_negative_price():
    p = _make_per_token_product(prices={"input": -1, "output": 10, "currency": "USD", "unit": "per_1m_tokens"})
    with pytest.raises(ValidationError, match="non-negative"):
        validate_product(p)


def test_validate_product_missing_purchase_url():
    p = _make_per_token_product(purchase_url="")
    with pytest.raises(ValidationError, match="purchase_url"):
        validate_product(p)


def test_validate_product_coding_plan_missing_quota():
    p = Product(
        id="plan",
        billing_type=BillingType.CODING_PLAN,
        prices={"monthly_price": 99, "currency": "CNY"},
        purchase_url="https://example.com",
    )
    with pytest.raises(ValidationError, match="included_quota"):
        validate_product(p)


def test_validate_product_subscription_ok():
    p = Product(
        id="plus",
        billing_type=BillingType.SUBSCRIPTION,
        prices={"monthly_price": 20, "currency": "USD"},
        purchase_url="https://example.com",
    )
    validate_product(p)
