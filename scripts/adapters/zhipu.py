# scripts/adapters/zhipu.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html_browser
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://open.bigmodel.cn/pricing"


def _parse_cny(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


def _parse_quota(text: str) -> tuple:
    m = re.search(r"(\d+)\s*(次|token)", text)
    return (int(m.group(1)), m.group(2)) if m else (0, "")


class ZhipuAdapter(BaseAdapter):
    provider_id = "zhipu"
    provider_name = "智谱"
    provider_name_en = "Zhipu AI"
    region = "cn"
    website = "https://open.bigmodel.cn/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        html = fetch_html_browser(_PRICING_URL, wait_selector=".model-list, .plan-list")
        soup = BeautifulSoup(html, "html.parser")
        products = []

        # per-token models
        for item in soup.select(".model-item"):
            name_el = item.select_one(".name")
            input_el = item.select_one(".input")
            output_el = item.select_one(".output")
            if not (name_el and input_el and output_el):
                continue
            model = name_el.get_text(strip=True)
            products.append(Product(
                id=f"{model.lower().replace(' ', '-')}-token",
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=128000,
                modalities=["text", "vision"],
                prices={
                    "input": _parse_cny(input_el.get_text()),
                    "output": _parse_cny(output_el.get_text()),
                    "currency": "CNY",
                    "unit": "per_1m_tokens",
                },
                purchase_url=_PRICING_URL,
            ))

        # coding plan
        for item in soup.select(".plan-item"):
            name_el = item.select_one(".plan-name")
            price_el = item.select_one(".plan-price")
            quota_el = item.select_one(".plan-quota")
            if not (name_el and price_el):
                continue
            quota, quota_unit = _parse_quota(quota_el.get_text()) if quota_el else (0, "")
            products.append(Product(
                id=f"{name_el.get_text(strip=True).lower().replace(' ', '-')}-plan",
                model=None,
                billing_type=BillingType.CODING_PLAN,
                prices={
                    "monthly_price": _parse_cny(price_el.get_text()),
                    "currency": "CNY",
                    "included_quota": quota,
                    "quota_unit": quota_unit,
                    "features": [],
                },
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
