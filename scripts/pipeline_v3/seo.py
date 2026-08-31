"""Render crawlable, provider-level SEO pages from a published catalog.

The interactive site intentionally uses hash routing.  These pages provide
stable, server-readable URLs for discovery without duplicating the app's
filtering interface or maintaining a second price database.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
import shutil
import tempfile


SITE_URL = "https://llmppk.top"


def _money(value: object, currency: str) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{currency} {number:,.4f}".rstrip("0").rstrip(".")


def _context(value: object) -> str:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number / 1_000_000:g}M" if number >= 1_000_000 else f"{number / 1_000:g}K"


def _published_date(value: str | None) -> str:
    if not value:
        return "最新发布版本"
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return value


def _provider_page(provider: dict, offers: list[dict], plans: list[dict], published_at: str | None) -> str:
    provider_id = escape(str(provider["id"]))
    name = escape(str(provider.get("name") or provider_id))
    name_en = escape(str(provider.get("name_en") or name))
    canonical = f"{SITE_URL}/providers/{provider_id}/"
    offers = sorted(offers, key=lambda row: (str(row.get("model_name", "")), str(row.get("market", ""))))
    rows = "".join(
        "<tr>"
        f"<td>{escape(str(row.get('model_name') or row.get('model_id') or '—'))}</td>"
        f"<td>{escape(str(row.get('market') or 'global'))}</td>"
        f"<td>{_money(row.get('input_per_1m'), escape(str(row.get('currency') or '')))}</td>"
        f"<td>{_money(row.get('output_per_1m'), escape(str(row.get('currency') or '')))}</td>"
        f"<td>{_money(row.get('cache_read_per_1m'), escape(str(row.get('currency') or '')))}</td>"
        f"<td>{_context(row.get('context_window'))}</td>"
        f"<td><a rel=\"nofollow noopener\" href=\"{escape(str(row.get('source_url') or '#'), quote=True)}\" target=\"_blank\">官方来源</a></td>"
        "</tr>"
        for row in offers
    ) or "<tr><td colspan=\"7\">暂未收录按需 API 报价。</td></tr>"
    plan_text = "、".join(escape(str(row.get("product_name"))) for row in plans[:6])
    plan_sentence = f"另收录 {plan_text} 等订阅或 Coding Plan。" if plan_text else ""
    description = f"{name} API Token 价格对比：查看输入、输出、缓存价格、上下文与官方市场报价。"
    schema = json.dumps({
        "@context": "https://schema.org",
        "@type": "Dataset",
        "name": f"{name} 大模型价格目录",
        "url": canonical,
        "description": description,
        "inLanguage": "zh-CN",
        "dateModified": _published_date(published_at),
        "isAccessibleForFree": True,
        "creator": {"@type": "Organization", "name": "LLMPPK", "url": SITE_URL},
        "distribution": {"@type": "DataDownload", "contentUrl": f"{SITE_URL}/data/catalog.json", "encodingFormat": "application/json"},
        "includedInDataCatalog": {"@type": "DataCatalog", "name": "LLMPPK 大模型价格目录", "url": SITE_URL},
    }, ensure_ascii=False)
    return f"""<!doctype html>
<html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">
<title>{name} API Token 价格对比与模型列表 | LLMPPK</title>
<meta name=\"description\" content=\"{description}\"><meta name=\"robots\" content=\"index,follow\">
<link rel=\"canonical\" href=\"{canonical}\"><script type=\"application/ld+json\">{schema}</script>
<style>body{{max-width:1120px;margin:44px auto;padding:0 24px;color:#202631;font:16px/1.7 system-ui,-apple-system,"Noto Sans SC",sans-serif}}h1{{font-size:34px;line-height:1.3;margin-bottom:8px}}h2{{margin-top:40px}}a{{color:#165dff}}.meta,.notice{{color:#5f6b7a}}.notice{{padding:14px 16px;background:#f4f7ff;border-radius:10px}}table{{width:100%;border-collapse:collapse;font-size:14px}}th,td{{padding:11px 9px;border-bottom:1px solid #e5e9f0;text-align:left;vertical-align:top}}th{{white-space:nowrap;background:#f7f9fc}}@media(max-width:700px){{body{{padding:0 16px}}table{{font-size:12px}}th,td{{padding:8px 5px}}}}</style>
</head><body><main>
<p><a href=\"/\">← 返回 LLMPPK 大模型价格对比</a></p>
<h1>{name} API Token 价格对比</h1><p>{name_en} 的公开 API 模型价格目录。以下保留不同官方市场的独立报价，按每 100 万 Tokens 展示。</p>
<p class=\"meta\">数据版本：{escape(_published_date(published_at))} · 共 {len(offers)} 条按需报价。{plan_sentence}</p>
<h2>{name} 模型价格</h2><table><thead><tr><th>模型</th><th>市场</th><th>输入 / 1M</th><th>输出 / 1M</th><th>缓存读取 / 1M</th><th>上下文</th><th>来源</th></tr></thead><tbody>{rows}</tbody></table>
<p class=\"notice\"><strong>如何理解价格：</strong>官方原币价格是权威记录；税费、地区可用性、限额和最终结算以厂商页面为准。需要筛选和跨厂商比较，请使用 <a href=\"/#/compare\">交互式价格对比工具</a>。</p>
<p><a href=\"/methodology.html\">了解数据来源与更新方法</a></p>
</main></body></html>"""


def _llms_txt(catalog: dict, provider_ids: list[str]) -> str:
    published = _published_date(catalog.get("published_at"))
    provider_urls = "\n".join(
        f"- {provider_id}: {SITE_URL}/providers/{provider_id}/"
        for provider_id in provider_ids
    )
    return f"""# LLMPPK (Price Per Token)

> A Chinese-language, non-commercial comparison site for LLM API Token pricing, subscriptions, and AI Coding Plans.

Canonical site: {SITE_URL}/
Catalog version: {published}

## Scope and data quality

- The site compares input, output, cached-input Token pricing, context windows, subscriptions, and AI Coding Plans where publicly available.
- Each official market, purchase channel, and service tier is kept as a separate record. Do not infer a user's eligible price from IP address, language, or cookies.
- Per-token data comes from Models.dev and verified official-market adapters. Subscription and plan records come from official vendor pages or adapters.
- The catalog is collected twice daily, normalized, validated, and atomically published. A failed collection keeps the last successful catalog in place.
- Official native-currency prices are authoritative. CNY reference values are comparison-only and must not be represented as settlement prices.
- For a purchase, availability, tax, quota, or final price claim, verify the linked official vendor source.

## How to cite this site

State the access date, model or plan name, market, and currency. Cite LLMPPK as a comparison source and link to the vendor's official pricing page for a purchasing decision.

Suggested wording: "According to LLMPPK's published comparison catalog (accessed [date]), [model or plan] is listed at [price and currency] for [market]. Verify the final price with the vendor."

## Useful URLs

- Interactive comparison: {SITE_URL}/#/compare
- Per-token pricing: {SITE_URL}/#/billing/per_token
- Subscriptions: {SITE_URL}/#/billing/subscription
- AI Coding Plans: {SITE_URL}/#/billing/coding_plan
- Methodology and limitations: {SITE_URL}/methodology.html
- Machine-readable catalog: {SITE_URL}/data/catalog.json
- Sitemap: {SITE_URL}/sitemap.xml

## Provider pages

{provider_urls}
"""


def render_seo_assets(catalog: dict, output_dir: Path) -> None:
    """Atomically replace generated provider pages and their sitemap."""
    parent = output_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".seo-", dir=parent))
    # These files are bind-mounted into the unprivileged Nginx container.
    # mkdtemp defaults to 0700, which would make otherwise valid pages appear
    # as 404/403 to the web server after the atomic directory replacement.
    os.chmod(temporary, 0o755)
    try:
        provider_offers: dict[str, list[dict]] = defaultdict(list)
        provider_plans: dict[str, list[dict]] = defaultdict(list)
        for offer in catalog.get("model_offers", []):
            provider_offers[str(offer.get("provider_id"))].append(offer)
        for plan in catalog.get("plans", []):
            provider_plans[str(plan.get("provider_id"))].append(plan)
        urls = [f"{SITE_URL}/", f"{SITE_URL}/methodology.html"]
        provider_ids: list[str] = []
        for provider in catalog.get("providers", []):
            provider_id = str(provider.get("id") or "")
            if not provider_id or "/" in provider_id or ".." in provider_id:
                continue
            page_dir = temporary / "providers" / provider_id
            page_dir.mkdir(parents=True)
            (page_dir / "index.html").write_text(
                _provider_page(provider, provider_offers[provider_id], provider_plans[provider_id], catalog.get("published_at")),
                encoding="utf-8",
            )
            urls.append(f"{SITE_URL}/providers/{provider_id}/")
            provider_ids.append(provider_id)
        sitemap = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
        sitemap.extend(f"  <url><loc>{url}</loc><changefreq>daily</changefreq></url>" for url in urls)
        sitemap.extend(["</urlset>", ""])
        (temporary / "sitemap.xml").write_text("\n".join(sitemap), encoding="utf-8")
        (temporary / "llms.txt").write_text(_llms_txt(catalog, provider_ids), encoding="utf-8")
        if output_dir.exists():
            backup = parent / f".{output_dir.name}.previous"
            shutil.rmtree(backup, ignore_errors=True)
            os.replace(output_dir, backup)
            try:
                os.replace(temporary, output_dir)
            except Exception:
                os.replace(backup, output_dir)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        else:
            os.replace(temporary, output_dir)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary, ignore_errors=True)
