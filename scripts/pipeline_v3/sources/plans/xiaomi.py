from scripts.pipeline_v3.sources.plans.declarative import DeclarativeHtmlPlanAdapter, PlanSpec


class XiaomiPlanAdapter(DeclarativeHtmlPlanAdapter):
    fetch_mode = "browser"
    source = "xiaomi_plans"
    source_url = "https://platform.xiaomimimo.com/"
    purchase_url = source_url
    provider_id = "xiaomi"
    provider_name = "小米"
    product_family = "token-plan"
    minimum_plan_count = 4
    specs = (
        PlanSpec("lite", "MiMo Token Plan Lite", r"MiMo\s+Token\s+Plan\s+Lite", "developer_api", "coding_plan", "CNY"),
        PlanSpec("standard", "MiMo Token Plan Standard", r"MiMo\s+Token\s+Plan\s+Standard", "developer_api", "coding_plan", "CNY"),
        PlanSpec("pro", "MiMo Token Plan Pro", r"MiMo\s+Token\s+Plan\s+Pro", "developer_api", "coding_plan", "CNY"),
        PlanSpec("max", "MiMo Token Plan Max", r"MiMo\s+Token\s+Plan\s+Max", "developer_api", "coding_plan", "CNY"),
    )
