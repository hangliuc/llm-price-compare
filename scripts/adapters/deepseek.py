# scripts/adapters/deepseek.py
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing"
_CONTEXT_WINDOW = {
    "deepseek-chat": 64000,
    "deepseek-reasoner": 64000,
}


class DeepSeekAdapter(BaseAdapter):
    provider_id = "deepseek"
    provider_name = "DeepSeek"
    provider_name_en = "DeepSeek"
    region = "cn"
    website = "https://deepseek.com/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_PRICING_URL)
        soup = BeautifulSoup(html, "html.parser")

        products = []
        table = soup.find("table", class_="pricing") or soup.find("table")
        if not table:
            raise RuntimeError("DeepSeek: pricing table not found")

        rows = table.find_all("tr")[1:]  # skip header
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 3:
                continue
            model = cells[0].get_text(strip=True)
            input_price = float(cells[1].get_text(strip=True).lstrip("$"))
            output_price = float(cells[2].get_text(strip=True).lstrip("$"))

            products.append(Product(
                id=f"{model}-token",
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=_CONTEXT_WINDOW.get(model, 64000),
                modalities=["text"],
                prices={
                    "input": input_price,
                    "output": output_price,
                    "currency": "USD",
                    "unit": "per_1m_tokens",
                },
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
