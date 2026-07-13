# scripts/adapters/anthropic.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

_API_URL = "https://docs.anthropic.com/en/docs/about-claude/pricing"

# 模型 → 上下文窗口
_CONTEXT_WINDOW = {
    "Claude Fable 5": 1_000_000,
    "Claude Mythos 5": 1_000_000,
    "Claude Opus 4.8": 1_000_000,
    "Claude Opus 4.7": 1_000_000,
    "Claude Opus 4.6": 1_000_000,
    "Claude Opus 4.5": 200_000,
    "Claude Sonnet 5": 1_000_000,
    "Claude Sonnet 4.6": 1_000_000,
    "Claude Sonnet 4.5": 200_000,
    "Claude Haiku 4.5": 200_000,
}


def _parse_price(text: str) -> float:
    """解析 '$10 / MTok' '$0.50 / MTok' '$20/month' 等格式。"""
    s = text.strip().lstrip("$").replace(",", "")
    # 切掉所有 '/ xxx' 后缀（/ MTok, /month 等）
    s = re.split(r"\s*/\s*", s, maxsplit=1)[0]
    s = re.sub(r"[^\d.]", "", s)
    return float(s) if s else 0.0


def _clean_model_name(raw: str) -> tuple:
    """清洗模型名，返回 (clean_name, note)。
    'Claude Opus 4.1 (deprecated)' -> ('Claude Opus 4.1', 'deprecated')
    'Claude Sonnet 5through August 31, 2026' -> ('Claude Sonnet 5', 'through August 31, 2026')
    """
    note = None
    # 先处理括号内备注
    m = re.search(r"\(([^)]+)\)", raw)
    if m:
        note = m.group(1)
    name = re.sub(r"\s*\([^)]*\)", "", raw).strip()

    # 处理无空格粘连的日期备注（如 'Claude Sonnet 5through August 31, 2026'）
    # 按 _CONTEXT_WINDOW 中的已知模型名匹配，最长优先避免部分匹配
    for known in sorted(_CONTEXT_WINDOW.keys(), key=len, reverse=True):
        if name.startswith(known):
            remainder = name[len(known):].strip()
            if remainder:
                note = f"{note} {remainder}".strip() if note else remainder
            name = known
            break

    return name, note


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

        # 第一个 table 是 Model pricing 表（6 列）
        # 列：Model | Base Input | 5m Cache Writes | 1h Cache Writes | Cache Hits | Output
        api_table = soup.find("table")
        if not api_table:
            raise RuntimeError("Anthropic: pricing table not found")

        rows = api_table.find_all("tr")
        for row in rows[1:]:  # 跳过表头
            cells = row.find_all("td")
            if len(cells) < 6:
                continue
            raw_model = cells[0].get_text(strip=True)
            if not raw_model:
                continue
            model, note = _clean_model_name(raw_model)
            # 跳过 retired 模型
            if note and "retired" in note.lower():
                continue

            input_price = _parse_price(cells[1].get_text())   # Base Input Tokens
            output_price = _parse_price(cells[5].get_text())  # Output Tokens
            cache_read = _parse_price(cells[4].get_text())    # Cache Hits

            prices = {
                "input": input_price,
                "output": output_price,
                "currency": "USD",
                "unit": "per_1m_tokens",
            }
            if cache_read > 0:
                prices["cached_input"] = cache_read

            # 处理 Sonnet 5 的两行（优惠价 + 标准价）
            product_id = f"{model.lower().replace(' ', '-').replace('.', '-')}-token"
            if note and "september" in note.lower():
                product_id = product_id.replace("-token", "-standard-token")

            products.append(Product(
                id=product_id,
                model=model,
                billing_type=BillingType.PER_TOKEN,
                context_window=_CONTEXT_WINDOW.get(model, 200_000),
                modalities=["text", "vision"],
                prices=prices,
                purchase_url=_API_URL,
                notes=note,
            ))

        self.assert_min_products(products, minimum=2)
        return products
