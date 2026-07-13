# scripts/adapters/deepseek.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_PRICING_URL = "https://api-docs.deepseek.com/quick_start/pricing"

# DeepSeek 2026 新模型 lineup（deepseek-chat/reasoner 2026/07/24 弃用，对应 v4-flash）
_CONTEXT_WINDOW = {
    "deepseek-v4-flash": 1_000_000,
    "deepseek-v4-pro": 1_000_000,
    "deepseek-chat": 1_000_000,
    "deepseek-reasoner": 1_000_000,
}


def _parse_price(text: str) -> float:
    """从 '$0.14' 或 '0.14' 提取价格。"""
    m = re.search(r"[\d.]+", text.replace(",", ""))
    return float(m.group()) if m else 0.0


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

        table = soup.find("table")
        if not table:
            raise RuntimeError("DeepSeek: pricing table not found")

        # Step 1: 从表头提取模型 ID（文本以 'deepseek-' 开头，清理括号后缀如 '(1)'）
        model_ids = []
        for tr in table.find_all("tr"):
            for cell in tr.find_all(["th", "td"]):
                txt = cell.get_text(strip=True)
                # 清理括号后缀：'deepseek-v4-flash(1)' → 'deepseek-v4-flash'
                clean = re.sub(r"\([^)]*\)", "", txt).strip()
                if clean.lower().startswith("deepseek-") and clean not in model_ids:
                    model_ids.append(clean)
            if model_ids:
                break

        if not model_ids:
            raise RuntimeError("DeepSeek: no model IDs found in pricing header")

        # Step 2: 按 label 关键字匹配 input/output/cache_hit 价格
        # 表格是转置结构（property-as-row, model-as-column），价格单元格以 '$' 开头
        prices = {m: {"input": None, "output": None, "cached_input": None} for m in model_ids}

        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if not cells:
                continue
            label = " ".join(cells).upper()
            # 只取以 '$' 开头的单元格作为价格值，避免误匹配 '1M INPUT TOKENS' 等标签
            price_vals = [c for c in cells if c.startswith("$")]

            # 缓存命中价（cache hit）—— 需在 CACHE MISS 之前判断，避免被 'CACHE' 误匹配
            if "CACHE HIT" in label:
                for i, m in enumerate(model_ids):
                    if i < len(price_vals):
                        val = _parse_price(price_vals[i])
                        if val > 0:
                            prices[m]["cached_input"] = val
            # 输入价：取 CACHE MISS 行（标准输入价，非缓存）
            elif "CACHE MISS" in label:
                for i, m in enumerate(model_ids):
                    if i < len(price_vals):
                        prices[m]["input"] = _parse_price(price_vals[i])
            # 输出价
            elif "OUTPUT TOKENS" in label:
                for i, m in enumerate(model_ids):
                    if i < len(price_vals):
                        prices[m]["output"] = _parse_price(price_vals[i])

        # Step 3: 组装 products
        products = []
        for m in model_ids:
            inp = prices[m]["input"]
            out = prices[m]["output"]
            if inp is None or out is None:
                continue
            price_data = {
                "input": inp,
                "output": out,
                "currency": "USD",
                "unit": "per_1m_tokens",
            }
            if prices[m]["cached_input"] is not None:
                price_data["cached_input"] = prices[m]["cached_input"]
            products.append(Product(
                id=f"{m}-token",
                model=m,
                billing_type=BillingType.PER_TOKEN,
                context_window=_CONTEXT_WINDOW.get(m, 1_000_000),
                modalities=["text"],
                prices=price_data,
                purchase_url=_PRICING_URL,
            ))

        self.assert_min_products(products, minimum=2)
        return products
