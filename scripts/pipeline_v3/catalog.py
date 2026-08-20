from scripts.pipeline_v3 import SCHEMA_VERSION
from scripts.pipeline_v3.models import ModelOffer, Plan


PROVIDER_METADATA = {
    "anthropic": {"name": "Anthropic", "name_en": "Anthropic", "region": "us", "website": "https://anthropic.com"},
    "aws": {"name": "AWS", "name_en": "Amazon Web Services", "region": "us", "website": "https://aws.amazon.com/bedrock/"},
    "deepseek": {"name": "DeepSeek", "name_en": "DeepSeek", "region": "cn", "website": "https://deepseek.com"},
    "google": {"name": "Google", "name_en": "Google", "region": "us", "website": "https://ai.google.dev"},
    "minimax": {"name": "MiniMax", "name_en": "MiniMax", "region": "cn", "website": "https://minimaxi.com"},
    "moonshot": {"name": "Kimi", "name_en": "Moonshot AI", "region": "cn", "website": "https://moonshot.ai"},
    "openai": {"name": "OpenAI", "name_en": "OpenAI", "region": "us", "website": "https://openai.com"},
    "qwen": {"name": "阿里通义", "name_en": "Alibaba Qwen", "region": "cn", "website": "https://tongyi.aliyun.com"},
    "xiaomi": {"name": "小米", "name_en": "Xiaomi", "region": "cn", "website": "https://platform.xiaomimimo.com"},
    "zhipu": {"name": "智谱", "name_en": "Zhipu AI", "region": "cn", "website": "https://bigmodel.cn"},
    "cursor": {"name": "Cursor", "name_en": "Cursor", "region": "us", "website": "https://cursor.com"},
    "githubcopilot": {"name": "GitHub Copilot", "name_en": "GitHub Copilot", "region": "us", "website": "https://github.com/features/copilot"},
    "kiro": {"name": "Kiro", "name_en": "Kiro", "region": "us", "website": "https://kiro.dev"},
    "opencode": {"name": "OpenCode", "name_en": "OpenCode", "region": "us", "website": "https://opencode.ai"},
}


def build_catalog(release_id: str, published_at: str,
                  offers: list[ModelOffer], plans: list[Plan]) -> dict:
    provider_ids = sorted({x.provider_id for x in [*offers, *plans]})
    providers = []
    for provider_id in provider_ids:
        metadata = PROVIDER_METADATA.get(provider_id, {})
        providers.append({
            "id": provider_id,
            "name": metadata.get("name", provider_id),
            "name_en": metadata.get("name_en", metadata.get("name", provider_id)),
            "region": metadata.get("region", "unknown"),
            "website": metadata.get("website", ""),
        })
    return {
        "schema_version": SCHEMA_VERSION,
        "release_id": release_id,
        "published_at": published_at,
        "providers": providers,
        "model_offers": [item.to_dict() for item in offers],
        "plans": [item.to_dict() for item in plans],
        "summary": {
            "provider_count": len(providers),
            "model_offer_count": len(offers),
            "plan_count": len(plans),
            "automatic_sources": 1 + len({x.source_url for x in plans}),
        },
    }

