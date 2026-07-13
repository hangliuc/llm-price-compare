# scripts/sources/__init__.py
"""外部数据源采集层。

三源交叉验证架构：
    L1: LiteLLM JSON      —— per_token 主源（静态 JSON，覆盖 9/12 厂商）
    L2: OpenRouter API    —— per_token 交叉源 + 能力元数据
    L3: 官网 Scraper      —— 兜底 + 订阅/Coding Plan 唯一来源（见 scripts/adapters/）

每个 Source 实现 fetch_all() -> dict[provider_id, list[Product]]，
不直接写 prices.json，由 reconcile.py 仲裁后统一落盘。
"""
from scripts.sources.base import SourceBase, SourceResult
from scripts.sources.litellm import LiteLLMSource
from scripts.sources.openrouter import OpenRouterSource

# 注册顺序即优先级（主源在前）
SOURCES: list[SourceBase] = [
    LiteLLMSource(),
    OpenRouterSource(),
]


def fetch_all_sources() -> dict[str, dict[str, list]]:
    """采集所有外部数据源。

    Returns:
        {
            "litellm":     {provider_id: [Product, ...], ...},
            "openrouter":  {provider_id: [Product, ...], ...},
        }
        采集失败的源值为 {}，不会抛异常。
    """
    result = {}
    for src in SOURCES:
        try:
            result[src.source_id] = src.fetch_all()
        except Exception as e:
            # 单源失败不阻塞其他源
            import logging
            logging.getLogger("sources").error(
                "source %s failed: %s", src.source_id, e
            )
            result[src.source_id] = {}
    return result
