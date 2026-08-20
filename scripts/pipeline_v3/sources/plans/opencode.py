from scripts.pipeline_v3.sources.plans.declarative import DeclarativeHtmlPlanAdapter, PlanSpec


class OpenCodePlanAdapter(DeclarativeHtmlPlanAdapter):
    fetch_mode = "browser"
    source = "opencode_plans"
    source_url = "https://opencode.ai/docs/zh-cn/go/"
    purchase_url = "https://opencode.ai/auth"
    provider_id = "opencode"
    provider_name = "OpenCode"
    product_family = "go"
    minimum_plan_count = 1
    specs = (
        PlanSpec("monthly", "OpenCode Go", r"OpenCode\s+Go", "coding_tool", "coding_plan", "USD"),
    )
