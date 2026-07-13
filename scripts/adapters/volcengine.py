# scripts/adapters/volcengine.py
import re
from bs4 import BeautifulSoup
from scripts.adapters.base import BaseAdapter
from scripts.core.fetcher import fetch_html
from scripts.core.models import Product, BillingType

# 改用静态文档页（无需 Playwright），数据更完整
_PRICING_URL = "https://www.volcengine.com/docs/82379/1099320"

# 模型 → 上下文窗口 / 模态
_MODEL_META = {
    "doubao-pro-32k":          (32_000,   ["text"]),
    "doubao-lite-32k":         (32_000,   ["text"]),
    "doubao-1.5-pro-32k":      (32_000,   ["text"]),
    "doubao-1.5-lite-32k":     (32_000,   ["text"]),
    "doubao-seed-1.6":         (256_000,  ["text"]),
    "doubao-seed-1.6-lite":    (256_000,  ["text"]),
    "doubao-seed-1.6-flash":   (256_000,  ["text"]),
    "doubao-seed-1.6-vision":  (256_000,  ["text", "vision"]),
    "doubao-seed-1.6-thinking":(256_000,  ["text"]),
    "deepseek-v3.1":           (128_000,  ["text"]),
    "deepseek-r1":             (64_000,   ["text"]),
    "kimi-k2":                 (128_000,  ["text"]),
}

# 只抓白名单内的模型（避免数据爆炸）
_WHITELIST = set(_MODEL_META.keys())


def _parse_cny(text: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(m.group(1)) if m else 0.0


class VolcengineAdapter(BaseAdapter):
    provider_id = "volcengine"
    provider_name = "火山引擎"
    provider_name_en = "Volcengine"
    region = "cn"
    website = "https://www.volcengine.com/"
    pricing_url = _PRICING_URL

    def fetch(self) -> list[Product]:
        # 改用静态抓取，规避 Playwright sync/async 冲突
        html = fetch_html(_PRICING_URL, timeout=20)
        soup = BeautifulSoup(html, "html.parser")
        products = []
        seen = set()

        # 文档页是标准 HTML 表格，遍历所有 table
        for table in soup.select("table"):
            for tr in table.select("tr"):
                tds = tr.find_all("td")
                if len(tds) < 2:
                    continue
                model_name = tds[0].get_text(strip=True)
                # 只抓白名单模型
                if model_name not in _WHITELIST or model_name in seen:
                    continue

                # 从该行所有单元格提取价格数字
                prices = [_parse_cny(td.get_text()) for td in tds[1:]]
                if not prices:
                    continue

                ctx, mods = _MODEL_META[model_name]
                # 基础档：输入取最小非零价、输出取最大价
                # 火山文档按输入长度分档定价，这里取最便宜档作为基准
                input_p = next((p for p in prices if p > 0), 0.0)
                output_p = max(prices) if prices else 0.0

                products.append(Product(
                    id=f"{model_name}-token",
                    model=model_name,
                    billing_type=BillingType.PER_TOKEN,
                    context_window=ctx,
                    modalities=mods,
                    prices={
                        "input": input_p,
                        "output": output_p,
                        "currency": "CNY",
                        "unit": "per_1m_tokens",
                    },
                    purchase_url=_PRICING_URL,
                ))
                seen.add(model_name)

        self.assert_min_products(products, minimum=2)
        return products
