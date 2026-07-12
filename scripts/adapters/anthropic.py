# scripts/adapters/anthropic.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_API_URL = "https://docs.anthropic.com/en/docs/about-claude/pricing"
_SUB_URL = "https://claude.ai/pricing"


def _parse_price(text: str) -> float:
    return float(text.strip().lstrip("$").replace(",", "").replace("/month", ""))


class AnthropicAdapter(BaseAdapter):
    provider_id = "anthropic"
    provider_name = "Anthropic"
    provider_name_en = "Anthropic"
    region = "us"
    website = "https://anthropic.com/"
    pricing_url = _API_URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_API_URL)
        soup = BeautifulSoup(html, "html.parser")
        products = []

        # API pricing table
        api_table = soup.find("table", class_="api-pricing") or soup.find("table")
        if api_table:
            for row in api_table.find_all("tr")[1:]:
                cells = row.find_all("td")
                if len(cells) < 3:
                    continue
                model = cells[0].get_text(strip=True)
                products.append(Product(
                    id=f"{model.lower().replace(' ', '-').replace('.', '-')}-token",
                    model=model,
                    billing_type=BillingType.PER_TOKEN,
                    context_window=200000,
                    modalities=["text", "vision"],
                    prices={
                        "input": _parse_price(cells[1].get_text()),
                        "output": _parse_price(cells[2].get_text()),
                        "currency": "USD",
                        "unit": "per_1m_tokens",
                    },
                    purchase_url=_API_URL,
                ))

        # Subscription block
        sub = soup.select_one(".subscription")
        if sub:
            name_el = sub.select_one(".plan-name")
            price_el = sub.select_one(".price")
            features = [li.get_text(strip=True) for li in sub.select(".features li")]
            if name_el and price_el:
                products.append(Product(
                    id=f"{name_el.get_text(strip=True).lower().replace(' ', '-')}-subscription",
                    model=None,
                    billing_type=BillingType.SUBSCRIPTION,
                    prices={
                        "monthly_price": _parse_price(price_el.get_text()),
                        "currency": "USD",
                        "features": features,
                    },
                    purchase_url=_SUB_URL,
                ))

        self.assert_min_products(products, minimum=2)
        return products
