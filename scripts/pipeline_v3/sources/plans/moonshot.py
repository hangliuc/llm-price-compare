from scripts.pipeline_v3.sources.plans.declarative import DeclarativeHtmlPlanAdapter, PlanSpec


class MoonshotPlanAdapter(DeclarativeHtmlPlanAdapter):
    fetch_mode = "browser"
    source = "moonshot_plans"
    source_url = "https://www.kimi.com/membership/pricing"
    purchase_url = source_url
    provider_id = "moonshot"
    provider_name = "Kimi"
    product_family = "membership"
    minimum_plan_count = 4
    specs = (
        PlanSpec("andante", "Kimi 会员 Andante", r"(?:Kimi\s*)?会员\s*Andante", "general_ai", "subscription", "CNY"),
        PlanSpec("moderato", "Kimi 会员 Moderato", r"(?:Kimi\s*)?会员\s*Moderato", "general_ai", "subscription", "CNY"),
        PlanSpec("allegretto", "Kimi 会员 Allegretto", r"(?:Kimi\s*)?会员\s*Allegretto", "general_ai", "subscription", "CNY"),
        PlanSpec("allegro", "Kimi 会员 Allegro", r"(?:Kimi\s*)?会员\s*Allegro", "general_ai", "subscription", "CNY"),
    )
