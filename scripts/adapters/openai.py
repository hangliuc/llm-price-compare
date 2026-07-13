# scripts/adapters/openai.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

# 优先抓 platform.openai.com/docs/pricing（结构化表格，UA 限制宽松）
_PRICING_URL = "https://platform.openai.com/docs/pricing"
_FALLBACK_URL = "https://openai.com/api/pricing/"

# 模型 → 上下文窗口（OpenAI 2026 最新模型 lineup）
_MODEL_CONTEXT = {
    "gpt-5.6-sol": 270000,
    "gpt-5.5": 270000,
    "gpt-5.5-pro": 270000,
    "gpt-5.4": 270000,
    "gpt-5.4-mini": 270000,
    "gpt-5.4-nano": 270000,
    "gpt-5.4-pro": 270000,
    "gpt-4.1": 1000000,
    "gpt-4.1-mini": 1000000,
    "gpt-4.1-nano": 1000000,
    "gpt-4o": 128000,
    "gpt-4o-mini": 128000,
    "o3": 200000,
    "o3-deep-research": 200000,
    "o4-mini": 200000,
    "o4-mini-deep-research": 200000,
    "o1": 200000,
    "o1-pro": 200000,
    "chat-latest": 128000,
    "gpt-5.3-codex": 270000,
    "gpt-4o-transcribe": 16000,
    "gpt-4o-mini-transcribe": 16000,
}


def _parse_price(text: str) -> float:
    """从 '$2.50' 或 '2.50' 或 '-' 提取价格，'-' 表示不可用返回 0。"""
    if "-" in text and not re.search(r"\d", text):
        return 0.0
    m = re.search(r"[\d.]+", text.replace(",", ""))
    return float(m.group()) if m else 0.0


def _parse_tables(html: str) -> list:
    """解析 platform.openai.com/docs/pricing 页面的表格。
    页面是 Next.js SSR，表格是双行表头：
      row0: ['', 'Short context', 'Long context']  (分组)
      row1: ['Model', 'Input', 'Cached input', 'Cache writes', 'Output', 'Input', ...]
    """
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen_ids = set()

    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue

        # 找到含 'Model' 和 'Input' 的行作为表头
        header_row = None
        header_idx = None
        for i, row in enumerate(rows[:3]):  # 前 3 行内找表头
            cells = [c.get_text(strip=True).lower() for c in row.find_all(["th", "td"])]
            if any("model" in c for c in cells) and any("input" in c for c in cells):
                header_row = cells
                header_idx = i
                break

        if header_row is None:
            continue

        # 识别列索引
        model_idx = next((i for i, h in enumerate(header_row) if "model" in h), None)
        input_idx = next((i for i, h in enumerate(header_row) if h == "input" or ("input" in h and "cache" not in h and "write" not in h)), None)
        cached_idx = next((i for i, h in enumerate(header_row) if "cached" in h), None)
        output_idx = next((i for i, h in enumerate(header_row) if "output" in h), None)

        if model_idx is None or input_idx is None or output_idx is None:
            continue

        # 数据行（表头行之后）
        for row in rows[header_idx + 1:]:
            cells = row.find_all(["th", "td"])
            if len(cells) <= max(model_idx, input_idx, output_idx):
                continue
            model = cells[model_idx].get_text(strip=True)
            if not model or model.lower() == "model":
                continue

            # 跳过非模型行（如 'Text', 'Audio', 'Image' 等模态行）
            model_key = model.lower().replace(" ", "-")
            if model_key in ("text", "audio", "image", "video", ""):
                continue

            # 只收录已知模型
            if model_key not in _MODEL_CONTEXT:
                continue

            product_id = f"{model_key}-token"
            if product_id in seen_ids:
                continue

            prices = {
                "input": _parse_price(cells[input_idx].get_text()),
                "output": _parse_price(cells[output_idx].get_text()),
                "currency": "USD",
                "unit": "per_1m_tokens",
            }
            if cached_idx is not None and cached_idx < len(cells):
                cached_val = _parse_price(cells[cached_idx].get_text())
                if cached_val > 0:
                    prices["cached_input"] = cached_val

            products.append(Product(
                id=product_id,
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=_MODEL_CONTEXT[model_key],
                modalities=["text", "vision"],
                prices=prices,
                purchase_url=_PRICING_URL,
            ))
            seen_ids.add(product_id)

    return products


class OpenAIAdapter(BaseAdapter):
    provider_id = "openai"
    provider_name = "OpenAI"
    provider_name_en = "OpenAI"
    region = "us"
    website = "https://openai.com/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        # 优先抓 platform.openai.com/docs/pricing
        try:
            html = fetch_html(_PRICING_URL)
            products = _parse_tables(html)
            if products:
                self.assert_min_products(products, minimum=2)
                return products
        except Exception:
            pass

        # 备用：openai.com/api/pricing/（可能 403）
        html = fetch_html(_FALLBACK_URL)
        products = _parse_tables(html)
        self.assert_min_products(products, minimum=2)
        return products
