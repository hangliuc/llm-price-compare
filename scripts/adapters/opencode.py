# scripts/adapters/opencode.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_URL = "https://opencode.ai/zh/go"


def _parse_cny(text: str) -> float:
    """解析 '¥99/月' → 99.0"""
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


def _parse_quota(text: str) -> tuple:
    """解析 '包含 500 次调用' → (500, '次')"""
    m = re.search(r"(\d+)\s*(次|token|tokens)", text)
    if m:
        return int(m.group(1)), m.group(2)
    return 0, ""


class OpenCodeAdapter(BaseAdapter):
    provider_id = "opencode"
    provider_name = "OpenCode"
    provider_name_en = "OpenCode"
    region = "us"
    website = "https://opencode.ai/"
    pricing_url = _URL

    def fetch(self) -> list[Product]:
        html = fetch_html(_URL)
        soup = BeautifulSoup(html, "html.parser")
        products = []

        cards = soup.select(".pricing-card")
        for card in cards:
            name_el = card.select_one(".plan-name")
            price_el = card.select_one(".price")
            quota_el = card.select_one(".quota")
            buy_el = card.select_one(".buy-link")
            features = [li.get_text(strip=True) for li in card.select(".features li")]

            if not name_el or not price_el:
                continue

            quota, quota_unit = (0, "")
            if quota_el:
                quota, quota_unit = _parse_quota(quota_el.get_text())

            purchase_url = buy_el["href"] if buy_el and buy_el.has_attr("href") else _URL

            products.append(Product(
                id=f"{name_el.get_text(strip=True).lower().replace(' ', '-')}-plan",
                model=None,
                billing_type=BillingType.CODING_PLAN,
                prices={
                    "monthly_price": _parse_cny(price_el.get_text()),
                    "currency": "CNY",
                    "included_quota": quota,
                    "quota_unit": quota_unit,
                    "features": features,
                },
                purchase_url=purchase_url,
            ))

        self.assert_min_products(products, minimum=1)
        return products
