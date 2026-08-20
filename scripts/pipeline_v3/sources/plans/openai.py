from scripts.pipeline_v3.sources.plans.declarative import DeclarativeHtmlPlanAdapter, PlanSpec


class OpenAIPlanAdapter(DeclarativeHtmlPlanAdapter):
    # chatgpt.com/pricing is localized and may omit numeric prices for an
    # unattended browser. The Help Center publishes the stable USD Plus price
    # explicitly and is therefore the formal automated source for this plan.
    fetch_mode = "browser"
    source = "openai_chatgpt_plus"
    source_url = "https://help.openai.com/en/articles/6950777-what-is-chatgpt-plus"
    purchase_url = source_url
    provider_id = "openai"
    provider_name = "OpenAI"
    product_family = "chatgpt"
    minimum_plan_count = 1
    specs = (
        PlanSpec("plus", "ChatGPT Plus", r"(?:ChatGPT\s+)?Plus\b", "general_ai", "subscription", "USD", featured_on_home=True),
    )
