# scripts/adapters/openai.py
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://openai.com/api/pricing/"

# 真实页面结构可能变化，这里按 fixture 设计解析逻辑
# 实际实现时需打开 https://openai.com/api/pricing/ 调整选择器
_MODEL_CONTEXT = {
    "GPT-4o": 128000,
    "GPT-4o mini": 128000,
}


def _parse_price(text: str) -> float:
    return float(text.strip().lstrip("$").replace(",", ""))


class OpenAIAdapter(BaseAdapter):
    provider_id = "openai"
    provider_name = "OpenAI"
    provider_name_en = "OpenAI"
    region = "us"
    website = "https://openai.com/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_PRICING_URL)
        soup = BeautifulSoup(html, "html.parser")

        products = []
        rows = soup.select(".model-row")
        for row in rows:
            name_el = row.select_one(".name")
            if not name_el:
                continue
            model = name_el.get_text(strip=True)
            input_el = row.select_one(".input")
            output_el = row.select_one(".output")
            cached_el = row.select_one(".cached")

            if not input_el or not output_el:
                continue

            prices = {
                "input": _parse_price(input_el.get_text()),
                "output": _parse_price(output_el.get_text()),
                "currency": "USD",
                "unit": "per_1m_tokens",
            }
            if cached_el:
                prices["cached_input"] = _parse_price(cached_el.get_text())

            products.append(Product(
                id=f"{model.lower().replace(' ', '-')}-token",
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=_MODEL_CONTEXT.get(model, 128000),
                modalities=["text", "vision"],
                prices=prices,
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
