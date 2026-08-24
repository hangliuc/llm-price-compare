from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import pytest

from scripts.pipeline_v3.catalog import build_catalog
from scripts.pipeline_v3.config import V3Config
from scripts.pipeline_v3.fetchers import FetchResponse
from scripts.pipeline_v3.fx import DailyFxSource
from scripts.pipeline_v3.comparison import apply_comparison_values
from scripts.pipeline_v3.models import ModelOffer, Plan
from scripts.pipeline_v3.probe import probe_plan_adapters
from scripts.pipeline_v3.runner import run_pipeline
from scripts.pipeline_v3.sources.models_dev import ModelsDevSource
from scripts.pipeline_v3.sources.official_offers.deepseek import DeepSeekPricingAdapter
from scripts.pipeline_v3.sources.official_offers.kimi import KimiPricingAdapter, KimiPricingPage
from scripts.pipeline_v3.sources.official_offers.minimax import MiniMaxPricingAdapter, MiniMaxPricingPage
from scripts.pipeline_v3.sources.official_offers.zai import ZaiGlobalPricingAdapter
from scripts.pipeline_v3.sources.official_offers.qwen import QwenModelStudioAdapter
from scripts.pipeline_v3.sources.plans.anthropic import AnthropicPlanAdapter
from scripts.pipeline_v3.sources.plans.base import PlanFetch
from scripts.pipeline_v3.sources.plans.base import monthly_usd
from scripts.pipeline_v3.sources.plans import all_plan_adapters, experimental_plan_adapters, verified_plan_adapters
from scripts.pipeline_v3.sources.plans.cursor import CursorHobbyPlanAdapter, CursorPlanAdapter, CursorTeamsPlanAdapter
from scripts.pipeline_v3.sources.plans.github import GitHubCopilotOrganizationPlanAdapter, GitHubCopilotPlanAdapter
from scripts.pipeline_v3.sources.plans.kiro import KiroPlanAdapter
from scripts.pipeline_v3.sources.plans.google import GooglePlanAdapter
from scripts.pipeline_v3.sources.plans.minimax import MiniMaxPlanAdapter
from scripts.pipeline_v3.sources.plans.moonshot import MoonshotPlanAdapter
from scripts.pipeline_v3.sources.plans.openai import OpenAIPlanAdapter
from scripts.pipeline_v3.sources.plans.openai_commercial import OpenAIBusinessPlanAdapter, OpenAIProPlanAdapter
from scripts.pipeline_v3.sources.plans.opencode import OpenCodePlanAdapter
from scripts.pipeline_v3.sources.plans.qwen import QwenTokenPlanAdapter
from scripts.pipeline_v3.sources.plans.xiaomi import XiaomiPlanAdapter
from scripts.pipeline_v3.sources.plans.zhipu import ZhipuPlanAdapter
from scripts.pipeline_v3.storage import V3Store
from scripts.pipeline_v3.validate import ValidationError, validate_offers, validate_plans


ROOT = Path(__file__).resolve().parents[2]


def models_dev_payload():
    model = {
        "id": "claude-test",
        "name": "Claude Test",
        "modalities": {"input": ["text"], "output": ["text"]},
        "limit": {"context": 200000, "output": 8192},
        "cost": {"input": 3, "output": 15, "cache_read": 0.3},
        "release_date": "2026-01-01",
        "last_updated": "2026-01-02",
    }
    return {"anthropic": {"doc": "https://docs.anthropic.com", "models": {"claude-test": model}}}


def fx_payload():
    # EUR base: 1 EUR = 1 USD = 8 CNY, so 1 USD = 8 CNY.
    return {"base": "EUR", "date": "2026-01-02", "rates": {"USD": 1, "CNY": 8, "SGD": 1.4}}


def write_fx_fixture(tmp_path):
    path = tmp_path / "fx.json"
    path.write_text(json.dumps(fx_payload()), encoding="utf-8")
    return path


def offer(**changes):
    base = ModelOffer(
        offer_id="anthropic/claude-test/global/standard",
        modelsdev_provider_id="anthropic",
        provider_id="anthropic",
        provider_name="Anthropic",
        model_id="claude-test",
        model_name="Claude Test",
        input_per_1m=3,
        output_per_1m=15,
        fetched_at="2026-01-01T00:00:00Z",
    )
    return replace(base, **changes)


def plan(**changes):
    base = Plan(
        plan_id="anthropic/claude/pro",
        provider_id="anthropic",
        provider_name="Anthropic",
        product_name="Claude Pro",
        plan_category="general_ai",
        billing_type="subscription",
        is_free=False,
        price_amount=20,
        monthly_equivalent=20,
        currency="USD",
        billing_cadence="monthly",
        source_url="https://anthropic.com/pricing",
        source_kind="html",
        fetched_at="2026-01-01T00:00:00Z",
    )
    return replace(base, **changes)


def test_models_dev_normalizes_only_target_providers():
    payload = models_dev_payload()
    payload["unknown"] = payload["anthropic"]
    offers = ModelsDevSource("https://models.dev/api.json").normalize(payload, "now")
    assert len(offers) == 1
    assert offers[0].input_per_1m == 3
    assert offers[0].cache_read_per_1m == .3
    assert offers[0].context_window == 200000


def test_missing_cache_stays_none():
    item = offer(cache_read_per_1m=None)
    assert validate_offers([item])[0].cache_read_per_1m is None


def test_duplicate_offer_is_rejected():
    with pytest.raises(ValidationError, match="duplicate offer_id"):
        validate_offers([offer(), offer()])


def test_large_offer_drop_is_rejected():
    with pytest.raises(ValidationError, match="dropped"):
        validate_offers([offer()], previous_count=10)


def test_plan_source_is_required():
    with pytest.raises(ValidationError, match="identity/source"):
        validate_plans([plan(source_url="")])


def test_catalog_contains_separate_business_entities():
    catalog = build_catalog("r1", "now", [offer()], [plan()])
    assert catalog["schema_version"] == "3.1"
    assert len(catalog["model_offers"]) == 1
    assert len(catalog["plans"]) == 1


def test_store_upgrades_an_existing_v30_database_before_creating_market_index(tmp_path):
    """A V3.0 database cannot create an index on a V3.1 column until after ALTER."""
    db_path = tmp_path / "runtime" / "ppk.db"
    db_path.parent.mkdir()
    connection = sqlite3.connect(db_path)
    connection.execute("CREATE TABLE model_offers (snapshot_id TEXT, provider_id TEXT)")
    connection.execute("CREATE TABLE plans (snapshot_id TEXT, provider_id TEXT)")
    connection.commit()
    connection.close()

    store = V3Store(db_path)
    try:
        fields = {row[1] for row in store.connection.execute("PRAGMA table_info(model_offers)")}
        indexes = {row[1] for row in store.connection.execute("PRAGMA index_list(model_offers)")}
        assert "market" in fields
        assert "idx_offers_market" in indexes
    finally:
        store.close()


def test_dry_run_persists_snapshot_without_publishing(tmp_path):
    source_file = tmp_path / "models.json"
    source_file.write_text(json.dumps(models_dev_payload()), encoding="utf-8")
    fx_file = write_fx_fixture(tmp_path)
    config = V3Config(
        runtime_dir=tmp_path / "runtime",
        db_path=tmp_path / "runtime" / "ppk.db",
        catalog_path=tmp_path / "public" / "catalog.json",
        status_path=tmp_path / "public" / "status.json",
        releases_dir=tmp_path / "runtime" / "releases",
        raw_dir=tmp_path / "runtime" / "raw",
        lock_path=tmp_path / "runtime" / "pipeline.lock",
        models_dev_url="unused",
        minimum_offer_count=1,
    )
    result = run_pipeline(config, dry_run=True, models_dev_file=source_file, fx_file=fx_file)
    assert result["status"] == "candidate"
    assert not config.catalog_path.exists()
    store = V3Store(config.db_path)
    try:
        assert store.latest_status()["status"] == "succeeded"
    finally:
        store.close()


def test_github_plan_adapter_reads_prices_from_official_html():
    raw = b"""
      <main>
        <p>Pricing plans For individuals</p>
        <h2>Free</h2><p>$0 per month</p>
        <h2>Pro</h2><p>$10 per month</p>
        <h2>Pro+</h2><p>$39 per month</p>
        <h2>Max</h2><p>$100 per month</p>
        <p>GitHub Copilot is available on your favorite platforms</p>
      </main>
    """
    plans = GitHubCopilotPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [0, 10, 39, 100]
    assert all(item.source_url == "https://github.com/features/copilot/plans" for item in plans)


def test_anthropic_plan_adapter_rejects_missing_commercial_price():
    raw = b"""
      <main>
        <p>Plan Price Billing Interval</p>
        <h2>Claude Pro</h2><p>$20 per month</p>
        <h2>Claude Max 5x</h2><p>Contact sales</p>
        <h2>Claude Max 20x</h2><p>$200 per month</p>
      </main>
    """
    with pytest.raises(ValueError, match="missing official monthly price"):
        AnthropicPlanAdapter().normalize(raw, "now")


def test_cursor_plan_adapter_reads_docs_table_and_team_price():
    raw = """
      <main>
        <p>Start (India only) ₹649/mo</p>
        <table><tr><td>Pro</td><td>$20/mo</td></tr>
        <tr><td>Pro Plus</td><td>$60/mo</td></tr>
        <tr><td>Ultra</td><td>$200/mo</td></tr></table>
        <p>Since different models have different API costs</p>
      </main>
    """.encode()
    plans = CursorPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [20, 60, 200]


def test_google_plan_adapter_ignores_early_marketing_mention():
    raw = b"""
      <main>
        <p>Google AI Pro. Study smarter with higher access.</p>
        <h2>Google AI Plus</h2><p>$6.98 SGD /mo</p>
        <h2>Google AI Pro</h2><p>$28.99 SGD /mo</p>
        <h2>Google AI Ultra</h2><p>From $139.99 SGD /mo</p>
      </main>
    """
    plans = GooglePlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [6.98, 28.99, 139.99]
    assert all(item.currency == "SGD" for item in plans)


def test_openai_plan_adapter_reads_plus_from_official_help_page():
    raw = b"""
      <main><h1>What is ChatGPT Plus?</h1>
      <p>ChatGPT Plus is available for $20/month.</p></main>
    """
    plans = OpenAIPlanAdapter().normalize(raw, "now")
    assert [(item.product_name, item.price_amount, item.currency) for item in plans] == [
        ("ChatGPT Plus", 20, "USD")
    ]
    assert plans[0].featured_on_home is True


def test_openai_plan_adapter_does_not_take_free_price_from_navigation():
    raw = """
      <main>免费版 Go Plus Pro
      <h2>免费版</h2><p>SGD 0 /月</p>
      <h2>Go</h2><p>SGD 11 /月</p>
      <h2>Plus</h2><p>SGD 30 /月</p>
      <h2>Pro</h2><p>起价 SGD 138 /月</p></main>
    """.encode()
    plans = OpenAIPlanAdapter().normalize(raw, "now")
    assert [(item.product_name, item.price_amount, item.currency) for item in plans] == [
        ("ChatGPT Free", 0, "SGD"),
        ("ChatGPT Go", 11, "SGD"),
        ("ChatGPT Plus", 30, "SGD"),
        ("ChatGPT Pro", 138, "SGD"),
    ]


def test_openai_pro_adapter_requires_and_emits_both_official_tiers():
    raw = b"""
      <main><p>The $100/month Pro plan provides 5x the usage of Plus.</p>
      <p>The $200/month Pro plan provides 20x the usage of Plus.</p></main>
    """
    plans = OpenAIProPlanAdapter().normalize(raw, "now")
    assert [(item.product_name, item.price_amount) for item in plans] == [
        ("ChatGPT Pro 5x", 100), ("ChatGPT Pro 20x", 200),
    ]


def test_openai_business_adapter_preserves_per_user_and_non_fixed_semantics():
    raw = b"""
      <main><p>Business costs $25 per user per month, or $20 per user per month
      when billed annually. A minimum of 2 users is required.</p>
      <p>Codex seats use credits. Enterprise is available.</p></main>
    """
    plans = OpenAIBusinessPlanAdapter().normalize(raw, "now")
    monthly, annual, codex, enterprise = plans
    assert (monthly.price_amount, monthly.price_scope, monthly.minimum_seats) == (25, "per_user", 2)
    assert (annual.price_amount, annual.monthly_equivalent, annual.billing_cadence) == (240, 20, "annual")
    assert codex.price_status == "usage_based" and codex.price_amount is None
    assert enterprise.price_status == "contact_sales" and enterprise.price_amount is None


def test_daily_fx_derives_cny_comparison_values_without_changing_official_price():
    raw = json.dumps(fx_payload()).encode()
    fx = DailyFxSource("fixture").normalize(raw, fx_payload(), "fx-1", "now")
    usd_offer = offer(currency="USD", input_per_1m=3, output_per_1m=15)
    usd_plan = plan(currency="USD", price_amount=20, monthly_equivalent=20)
    offers, plans = apply_comparison_values([usd_offer], [usd_plan], fx)
    assert offers[0].input_per_1m == 3
    assert offers[0].comparison_input_per_1m == 24
    assert offers[0].comparison_fx_date == "2026-01-02"
    assert plans[0].price_amount == 20
    assert plans[0].comparison_monthly_amount == 160


def test_fx_without_cny_rate_is_rejected():
    payload = {"base": "EUR", "date": "2026-01-02", "rates": {"USD": 0.8}}
    with pytest.raises(ValueError, match="CNY"):
        DailyFxSource("fixture").normalize(b"{}", payload, "fx-1", "now")


def test_cursor_hobby_and_teams_use_their_official_markers():
    hobby = CursorHobbyPlanAdapter().normalize(b"<p>Hobby Free</p>", "now")
    teams = CursorTeamsPlanAdapter().normalize(
        b"<p>Teams offers Standard ($40/user/mo) and Premium ($120/user/mo)</p>", "now")
    assert hobby[0].price_amount == 0
    assert [item.price_amount for item in teams] == [40, 120]


def test_github_organization_adapter_uses_billing_document():
    raw = b"""
      <p>Copilot Business at $19 USD per user per month, includes credits.</p>
      <p>Copilot Enterprise at $39 USD per user per month, includes credits.</p>
    """
    plans = GitHubCopilotOrganizationPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [19, 39]


def test_kiro_plan_adapter_reads_current_five_tiers_and_credits():
    raw = b"""
      <main>
        <h3>KIRO FREE</h3><p>$0 per month</p><p>50 credits</p>
        <h3>KIRO PRO</h3><p>$20 per user / month</p><p>1,000 credits</p>
        <h3>KIRO PRO+</h3><p>$40 per user / month</p><p>2,000 credits</p>
        <h3>KIRO PRO MAX</h3><p>$100 per user / month</p><p>5,000 credits</p>
        <h3>KIRO POWER</h3><p>$200 per user / month</p><p>10,000 credits</p>
      </main>
    """
    plans = KiroPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [0, 20, 40, 100, 200]
    assert [item.included_quota for item in plans] == [50, 1000, 2000, 5000, 10000]


@pytest.mark.parametrize("adapter_type", [
    MoonshotPlanAdapter,
    OpenAIPlanAdapter,
    OpenCodePlanAdapter,
    XiaomiPlanAdapter,
])
def test_declarative_official_adapters_require_page_prices(adapter_type):
    adapter = adapter_type()
    blocks = []
    expected = []
    for index, spec in enumerate(adapter.specs, start=1):
        if spec.is_free:
            blocks.append(f"<h2>{spec.product_name}</h2><p>Free plan</p>")
            expected.append(0)
        elif spec.currency == "USD":
            blocks.append(f"<h2>{spec.product_name}</h2><p>${index * 10}/month</p>")
            expected.append(index * 10)
        else:
            blocks.append(f"<h2>{spec.product_name}</h2><p>\u00a5{index * 10}/月</p>")
            expected.append(index * 10)
    plans = adapter.normalize("".join(blocks).encode(), "now")
    assert [item.price_amount for item in plans] == expected
    assert all(item.raw["official_text"] for item in plans)


def test_declarative_adapter_never_uses_a_hardcoded_price_fallback():
    raw = b"<h2>OpenCode Go</h2><p>Pricing is temporarily unavailable</p>"
    with pytest.raises(ValueError, match="missing official monthly price"):
        OpenCodePlanAdapter().normalize(raw, "now")


def test_google_adapter_preserves_official_regional_currency():
    raw = b"""
      <p>Google AI Plus $6.98 SGD /mo</p>
      <p>Google AI Pro $28.99 SGD /mo</p>
      <p>Google AI Ultra From $139.99 SGD /mo</p>
    """
    plans = GooglePlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [6.98, 28.99, 139.99]
    assert {item.currency for item in plans} == {"SGD"}


def test_zhipu_adapter_uses_standard_monthly_price_not_discounted_price():
    raw = """
      Lite 适合小型 Repo ¥ 94.4 /月 ¥ 118 /月
      Pro 最受欢迎 ¥ 430.4 /月 ¥ 538 /月
      Max 适合高阶用户 ¥ 862.4 /月 ¥ 1078 /月
    """.encode()
    plans = ZhipuPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [118, 538, 1078]
    assert plans[0].raw["displayed_monthly_prices"] == [94.4, 118]


def test_qwen_adapter_reads_three_official_monthly_token_plans():
    raw = """
      Lite版本 入门探索 ¥ 39 .00 /1个月
      Standard版本 效率升级 ¥ 139 .00 /1个月
      Pro版本 专业优选 ¥ 499 .00 /1个月
    """.encode()
    plans = QwenTokenPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [39, 139, 499]
    assert all(item.plan_category == "developer_api" for item in plans)


def test_minimax_adapter_reads_monthly_comparison_table():
    raw = """
      哪个计划更适合你？ 订阅计划 Plus ¥49 / 月 Max ¥119 / 月 Ultra ¥469 / 月
      积分购买
    """.encode()
    plans = MiniMaxPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [49, 119, 469]


def test_minimax_adapter_reads_official_embedded_faq_prices():
    raw = b'''
      <script id="__NEXT_DATA__">{"id":"available-plans","answer":"|
      Plus | \xc2\xa549 / \xe6\x9c\x88 | 3-4 \xe4\xb8\xaa Agent |\n|
      Max | \xc2\xa5119 / \xe6\x9c\x88 | 4-5 \xe4\xb8\xaa Agent |\n|
      Ultra | \xc2\xa5469 / \xe6\x9c\x88 | 6-7 \xe4\xb8\xaa Agent |"}</script>
    '''
    plans = MiniMaxPlanAdapter().normalize(raw, "now")
    assert [item.price_amount for item in plans] == [49, 119, 469]
    assert all(item.source_kind == "static" for item in plans)


def test_monthly_usd_understands_official_chinese_recurring_price():
    text = "OpenCode Go 首月 5 美元，之后 每月 10 美元"
    assert monthly_usd(text) == 10


def test_qwen_official_adapter_keeps_market_and_tier_prices_separate():
    raw = """
      <h3>华北 2（北京）</h3>
      <table><tr><th>模型 ID</th><th>模式</th><th>单次请求的输入 Token 数</th><th>输入单价</th><th>输出单价</th></tr>
      <tr><td>qwen3-max</td><td>标准</td><td>0&lt;Token≤32K</td><td>2.5 元</td><td>10 元</td></tr>
      <tr><td>qwen3-max</td><td>标准</td><td>32K&lt;Token≤128K</td><td>4 元</td><td>16 元</td></tr></table>
      <h3>新加坡</h3>
      <table><tr><th>模型 ID</th><th>模式</th><th>单次请求的输入 Token 数</th><th>输入单价</th><th>输出单价</th></tr>
      <tr><td>qwen3-max</td><td>标准</td><td>0&lt;Token≤32K</td><td>8.807 元</td><td>44.035 元</td></tr></table>
    """.encode()
    offers = QwenModelStudioAdapter().normalize(raw, "now")
    assert len(offers) == 3
    assert {(item.market, item.pricing_condition) for item in offers} == {
        ("cn_beijing", "input_lte_32k"),
        ("cn_beijing", "input_lte_128k"),
        ("sg_international", "input_lte_32k"),
    }
    assert all(item.currency == "CNY" and item.access_channel == "official_api" for item in offers)
    assert len({item.offer_id for item in offers}) == 3


def test_deepseek_official_adapter_keeps_peak_and_off_peak_offers_separate():
    raw = """
      <table>
      <tr><th>模型</th><th>deepseek-v4-flash</th><th>deepseek-v4-pro</th></tr>
      <tr><td>百万tokens输入（缓存命中）</td><td>空闲时段</td><td>0.05元</td><td>0.15元</td></tr>
      <tr><td>高峰时段</td><td>0.10元</td><td>0.30元</td></tr>
      <tr><td>百万tokens输入（缓存未命中）</td><td>空闲时段</td><td>1.5元</td><td>4.5元</td></tr>
      <tr><td>高峰时段</td><td>3.0元</td><td>9.0元</td></tr>
      <tr><td>百万tokens输出</td><td>空闲时段</td><td>4.5元</td><td>13.5元</td></tr>
      <tr><td>高峰时段</td><td>9.0元</td><td>27.0元</td></tr>
      </table>
    """.encode()
    offers = DeepSeekPricingAdapter().normalize(raw, "now")
    assert len(offers) == 4
    flash_off_peak = next(item for item in offers if item.model_id == "deepseek-v4-flash" and item.pricing_condition == "off_peak")
    flash_peak = next(item for item in offers if item.model_id == "deepseek-v4-flash" and item.pricing_condition == "peak")
    assert (flash_off_peak.input_per_1m, flash_off_peak.cache_read_per_1m, flash_off_peak.output_per_1m) == (1.5, 0.05, 4.5)
    assert (flash_peak.input_per_1m, flash_peak.cache_read_per_1m, flash_peak.output_per_1m) == (3.0, 0.10, 9.0)
    assert all(item.market == "cn_mainland" and item.currency == "CNY" for item in offers)


def test_kimi_official_adapter_reads_native_cny_cache_input_output_and_context():
    raw = '''
    # 官方价格
    <DocTable rows={[
      ["kimi-k2.7-code", "1M tokens", "¥1.30", "¥6.50", "¥27.00", "262,144 tokens"],
      ["kimi-k2.7-code-highspeed", "1M tokens", "¥2.60", "¥13.00", "¥54.00", "262,144 tokens"]
    ]}/>
    '''.encode()
    adapter = KimiPricingAdapter(KimiPricingPage("fixture_kimi", "https://example.test/kimi.md"))
    offers = adapter.normalize(raw, "now")
    assert len(offers) == 2
    code = offers[0]
    assert (code.cache_read_per_1m, code.input_per_1m, code.output_per_1m) == (1.3, 6.5, 27)
    assert code.context_window == 262144
    assert (code.market, code.currency, code.access_channel) == ("cn_mainland", "CNY", "official_api")


def test_zai_global_adapter_keeps_official_usd_and_real_zero_free_prices():
    raw = '''
    # Pricing
    | Model | Input | Cached Input | Cached Input Storage | Output |
    | :---- | :---- | :----------- | :------------------- | :----- |
    | GLM-5.3 | \\$1.4 | \\$0.26 | Limited-time Free | \\$4.4 |
    | GLM-4.7-Flash | Free | Free | Free | Free |

    ### Built-in Tools
    | Tool | Cost |
    | :--- | :--- |
    | Web Search | \\$0.01 / use |
    '''.encode()
    adapter = ZaiGlobalPricingAdapter()
    adapter.minimum_offer_count = 1
    offers = adapter.normalize(raw, "now")
    premium = next(item for item in offers if item.model_id == "glm-5.3")
    free = next(item for item in offers if item.model_id == "glm-4.7-flash")
    assert (premium.input_per_1m, premium.cache_read_per_1m, premium.output_per_1m) == (1.4, .26, 4.4)
    assert (free.input_per_1m, free.cache_read_per_1m, free.output_per_1m) == (0, 0, 0)
    assert (premium.market, premium.currency, premium.access_channel) == ("global", "USD", "official_api")


def test_minimax_adapters_keep_mainland_and_global_offers_independent():
    cn_raw = '''
    | **模型** | **输入价格**<br /> 元/百万 tokens | **输出价格** <br /> 元/百万 tokens | **缓存读取**<br /> 元/百万 tokens | **缓存写入**<br /> 元/百万 tokens |
    | :--- | :---: | :---: | :---: | :---: |
    | **MiniMax-M2.7** | 2.1 | 8.4 | 0.42 | 2.625 |
    '''.encode()
    global_raw = '''
    <Tab title="Standard">
    | Model | Input | Output | Prompt caching Read |
    | :--- | :--- | :--- | :--- |
    | **MiniMax-M3**<br />≤ 512k input tokens | ~~\\$0.60~~ \\$0.30 / M tokens | ~~\\$2.40~~ \\$1.20 / M tokens | ~~\\$0.12~~ \\$0.06 / M tokens |
    '''.encode()
    cn = MiniMaxPricingAdapter(MiniMaxPricingPage("fixture_cn", "https://example.test/cn", "cn_mainland", "CNY", 1)).normalize(cn_raw, "now")[0]
    global_offer = MiniMaxPricingAdapter(MiniMaxPricingPage("fixture_global", "https://example.test/global", "global", "USD", 1)).normalize(global_raw, "now")[0]
    assert (cn.input_per_1m, cn.output_per_1m, cn.cache_read_per_1m, cn.cache_write_per_1m) == (2.1, 8.4, .42, 2.625)
    assert (global_offer.input_per_1m, global_offer.output_per_1m, global_offer.cache_read_per_1m) == (.3, 1.2, .06)
    assert (cn.market, cn.currency) == ("cn_mainland", "CNY")
    assert (global_offer.market, global_offer.currency, global_offer.pricing_condition) == ("global", "USD", "input_lte_512k")


class _FakeFetcher:
    def fetch(self, url, timeout_seconds):
        assert url == "https://opencode.ai/docs/zh-cn/go/"
        assert timeout_seconds == 12
        return FetchResponse(
            raw=b"<h2>OpenCode Go</h2><p>$10/month</p>",
            http_status=200,
            headers={"ETag": "test"},
        )


def test_plan_adapter_fetcher_is_injectable_for_dynamic_pages():
    adapter = OpenCodePlanAdapter(timeout_seconds=12, fetcher=_FakeFetcher())
    fetched = adapter.fetch()
    plans = adapter.normalize(fetched.raw, "now")
    assert fetched.http_status == 200
    assert plans[0].price_amount == 10
    assert plans[0].source_kind == "browser"


class _FixturePlanAdapter(AnthropicPlanAdapter):
    minimum_plan_count = 1

    def fetch(self):
        return PlanFetch(
            source=self.source,
            source_url=self.source_url,
            raw=b"<h2>Claude Pro</h2><p>$20 per month</p>",
            http_status=200,
            headers={"ETag": "fixture"},
        )

    def normalize(self, raw, fetched_at):
        return [plan(fetched_at=fetched_at)]


class _BrokenPlanAdapter(_FixturePlanAdapter):
    source = "broken_official_source"
    source_url = "https://example.invalid/pricing"

    def fetch(self):
        raise RuntimeError("official page unavailable")


class _RetainedBrokenPlanAdapter(_FixturePlanAdapter):
    source = "retained_broken_source"
    source_url = "https://example.invalid/retained-pricing"

    def fetch(self):
        raise RuntimeError("official page temporarily unavailable")


def test_plan_probe_reports_all_sources_without_stopping():
    result = probe_plan_adapters([_BrokenPlanAdapter(), _FixturePlanAdapter()])
    assert result["status"] == "degraded"
    assert result["healthy_sources"] == 1
    assert result["total_sources"] == 2
    assert result["plan_count"] == 1
    assert result["sources"][0]["error_type"] == "RuntimeError"
    assert result["sources"][1]["plans"] == ["Claude Pro"]


def test_pipeline_retains_a_failed_plan_source_from_last_published_release(tmp_path):
    source_file = tmp_path / "models.json"
    source_file.write_text(json.dumps(models_dev_payload()), encoding="utf-8")
    fx_file = write_fx_fixture(tmp_path)
    config = V3Config(
        runtime_dir=tmp_path / "runtime", db_path=tmp_path / "runtime" / "ppk.db",
        catalog_path=tmp_path / "public" / "catalog.json", status_path=tmp_path / "public" / "status.json",
        releases_dir=tmp_path / "runtime" / "releases", raw_dir=tmp_path / "runtime" / "raw",
        lock_path=tmp_path / "runtime" / "pipeline.lock", models_dev_url="unused",
        minimum_offer_count=1, minimum_plan_count=1,
    )
    retained = plan(source_url=_RetainedBrokenPlanAdapter.source_url)
    run_pipeline(config, models_dev_file=source_file, fx_file=fx_file, plans=[retained])

    result = run_pipeline(
        config, dry_run=True, models_dev_file=source_file, fx_file=fx_file,
        plan_adapters=[_RetainedBrokenPlanAdapter()],
    )
    source_status = result["sources"]["plan_adapters"]
    assert result["summary"]["plan_count"] == 1
    assert source_status["status"] == "degraded"
    assert source_status["sources"]["retained_broken_source"]["retained_from"] == "last_known_good"


def test_pipeline_bootstraps_a_failed_plan_source_from_current_published_catalog(tmp_path):
    source_file = tmp_path / "models.json"
    source_file.write_text(json.dumps(models_dev_payload()), encoding="utf-8")
    fx_file = write_fx_fixture(tmp_path)
    catalog_path = tmp_path / "public" / "catalog.json"
    catalog_path.parent.mkdir(parents=True)
    retained = plan(source_url=_RetainedBrokenPlanAdapter.source_url)
    # This emulates the current public V3.0 artifact during the first V3.1
    # release, before the new SQLite history has a published release.
    catalog_path.write_text(json.dumps({"schema_version": "3.0", "plans": [retained.to_dict()]}), encoding="utf-8")
    config = V3Config(
        runtime_dir=tmp_path / "runtime", db_path=tmp_path / "runtime" / "ppk.db",
        catalog_path=catalog_path, status_path=tmp_path / "public" / "status.json",
        releases_dir=tmp_path / "runtime" / "releases", raw_dir=tmp_path / "runtime" / "raw",
        lock_path=tmp_path / "runtime" / "pipeline.lock", models_dev_url="unused",
        minimum_offer_count=1, minimum_plan_count=1,
    )

    result = run_pipeline(
        config, dry_run=True, models_dev_file=source_file, fx_file=fx_file,
        plan_adapters=[_RetainedBrokenPlanAdapter()],
    )

    assert result["summary"]["plan_count"] == 1
    source_status = result["sources"]["plan_adapters"]
    assert source_status["status"] == "degraded"
    assert source_status["sources"]["retained_broken_source"]["retained_from"] == "last_known_good"


def test_verified_and_experimental_plan_registries_are_separate():
    verified = {item.source for item in verified_plan_adapters()}
    experimental = {item.source for item in experimental_plan_adapters()}
    assert verified.isdisjoint(experimental)
    assert {item.source for item in all_plan_adapters()} == verified | experimental
    assert {
        "openai_chatgpt_pro", "openai_chatgpt_business", "cursor_hobby_plan",
        "moonshot_plans", "xiaomi_plans",
    } == experimental
    assert "openai_chatgpt_plus" in verified


def test_plan_adapter_raw_and_plan_row_are_persisted(tmp_path):
    source_file = tmp_path / "models.json"
    source_file.write_text(json.dumps(models_dev_payload()), encoding="utf-8")
    fx_file = write_fx_fixture(tmp_path)
    config = V3Config(
        runtime_dir=tmp_path / "runtime",
        db_path=tmp_path / "runtime" / "ppk.db",
        catalog_path=tmp_path / "public" / "catalog.json",
        status_path=tmp_path / "public" / "status.json",
        releases_dir=tmp_path / "runtime" / "releases",
        raw_dir=tmp_path / "runtime" / "raw",
        lock_path=tmp_path / "runtime" / "pipeline.lock",
        models_dev_url="unused",
        minimum_offer_count=1,
        minimum_plan_count=1,
    )
    result = run_pipeline(
        config,
        dry_run=True,
        models_dev_file=source_file,
        fx_file=fx_file,
        plan_adapters=[_FixturePlanAdapter()],
    )
    assert result["summary"]["plan_count"] == 1
    store = V3Store(config.db_path)
    try:
        assert store.connection.execute("SELECT COUNT(*) FROM plans").fetchone()[0] == 1
        assert store.connection.execute("SELECT COUNT(*) FROM source_snapshots").fetchone()[0] == 3
        assert store.connection.execute("SELECT COUNT(*) FROM fx_snapshots").fetchone()[0] == 1
    finally:
        store.close()


def test_v3_publishes_the_frontend_contract_atomically(tmp_path):
    source_file = tmp_path / "models.json"
    source_file.write_text(json.dumps(models_dev_payload()), encoding="utf-8")
    fx_file = write_fx_fixture(tmp_path)
    config = V3Config(
        runtime_dir=tmp_path / "runtime",
        db_path=tmp_path / "runtime" / "ppk.db",
        catalog_path=tmp_path / "public" / "catalog.json",
        status_path=tmp_path / "public" / "status.json",
        releases_dir=tmp_path / "runtime" / "releases",
        raw_dir=tmp_path / "runtime" / "raw",
        lock_path=tmp_path / "runtime" / "pipeline.lock",
        models_dev_url="unused",
        minimum_offer_count=1,
        minimum_plan_count=1,
    )
    result = run_pipeline(config, models_dev_file=source_file, fx_file=fx_file, plans=[plan()])
    assert result["status"] == "healthy"
    catalog = json.loads(config.catalog_path.read_text())
    assert catalog["schema_version"] == "3.1"
    assert catalog["comparison"]["fx_snapshot"]["published_date"] == "2026-01-02"
    assert json.loads(config.status_path.read_text())["published_at"]


def test_ui_reads_only_the_v3_catalog_and_explains_current_sources():
    app = (ROOT / "ui" / "app.js").read_text(encoding="utf-8")
    page = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert 'const DATA_PATHS = ["../data/catalog.json"]' in app
    assert 'DATA_PATHS.push("../runtime/public/catalog.json")' in app
    assert "function catalogV3ToViewData(catalog)" in app
    assert "LiteLLM" not in page
    assert "OpenRouter" not in page
    assert "多源仲裁" not in page
