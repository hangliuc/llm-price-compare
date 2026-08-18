from copy import deepcopy
from typing import Optional

from scripts.core.models import Product, product_to_dict


PROVIDER_META = {
    "openai": ("OpenAI", "OpenAI", "us", "https://openai.com/", "https://openai.com/api/pricing/"),
    "anthropic": ("Anthropic", "Anthropic", "us", "https://www.anthropic.com/", "https://www.anthropic.com/pricing"),
    "google": ("Google", "Google", "us", "https://ai.google.dev/", "https://ai.google.dev/pricing"),
    "aws": ("AWS", "Amazon Web Services", "us", "https://aws.amazon.com/", "https://aws.amazon.com/bedrock/pricing/"),
    "deepseek": ("DeepSeek", "DeepSeek", "cn", "https://www.deepseek.com/", "https://api-docs.deepseek.com/quick_start/pricing"),
    "moonshot": ("Kimi", "Moonshot AI", "cn", "https://platform.moonshot.cn/", "https://platform.moonshot.cn/docs/pricing"),
    "qwen": ("阿里通义", "Alibaba Qwen", "cn", "https://help.aliyun.com/zh/dashscope/", "https://help.aliyun.com/zh/dashscope/product-overview/billing"),
    "minimax": ("MiniMax", "MiniMax", "cn", "https://platform.minimaxi.com/", "https://platform.minimaxi.com/docs/guides/pricing-paygo"),
    "xiaomi": ("小米", "Xiaomi", "cn", "https://mimo.xiaomi.com/", "https://platform.xiaomimimo.com/"),
    "volcengine": ("火山引擎", "Volcengine", "cn", "https://www.volcengine.com/", "https://www.volcengine.com/docs/82379/1099320"),
    "zhipu": ("智谱", "Zhipu AI", "cn", "https://www.bigmodel.cn/", "https://www.bigmodel.cn/pricing"),
    "opencode": ("OpenCode", "OpenCode", "us", "https://opencode.ai/", "https://opencode.ai/zh/go"),
}


def products_to_dicts(products: list) -> list[dict]:
    return [product_to_dict(p) if isinstance(p, Product) else deepcopy(p) for p in products]


def build_provider(provider_id: str, products: list, manual: Optional[dict] = None) -> dict:
    manual = manual or {}
    fallback = PROVIDER_META.get(provider_id, (provider_id, provider_id, "us", "", ""))
    provider = {
        "id": provider_id,
        "name": manual.get("name", fallback[0]),
        "name_en": manual.get("name_en", fallback[1]),
        "region": manual.get("region", fallback[2]),
        "website": manual.get("website", fallback[3]),
        "pricing_url": manual.get("pricing_url", fallback[4]),
        "products": products_to_dicts(products),
    }
    if manual.get("pricing_url_overseas"):
        provider["pricing_url_overseas"] = manual["pricing_url_overseas"]
    return provider


def merge_manual(provider: Optional[dict], manual: dict) -> dict:
    """Manual data is an explicit product-id override plus provider metadata override."""
    if provider is None:
        return deepcopy(manual)
    result = deepcopy(provider)
    for key in ("name", "name_en", "region", "website", "pricing_url", "pricing_url_overseas"):
        if key in manual:
            result[key] = manual[key]
    manual_products = {p["id"].lower(): deepcopy(p) for p in manual.get("products", [])}
    kept = [p for p in result.get("products", []) if p.get("id", "").lower() not in manual_products]
    result["products"] = kept + list(manual_products.values())
    return result


def normalize_purchase_urls(provider: dict) -> None:
    domestic = provider.get("pricing_url", "")
    overseas = provider.get("pricing_url_overseas", "")
    for product in provider.get("products", []):
        if product.get("billing_type") != "per_token":
            continue
        currency = (product.get("prices") or {}).get("currency")
        target = overseas if currency == "USD" and overseas else domestic
        if target:
            product["purchase_url"] = target
