# scripts/run_daily.py
"""每日抓取入口：python3 scripts/run_daily.py

三源交叉验证流程：
    1. 采集 L1 (LiteLLM) + L2 (OpenRouter) 外部数据源
    2. 对每个 provider：
       - 有官网 adapter：L1 + L2 + L3(adapter) 三源仲裁
       - 无 adapter：L1 + L2 双源仲裁
    3. 现有 20%/50% 波动检测保留（与仲裁是两个维度）
    4. manual yaml 合并：
       - reconcile 处理过的 provider：归一化 id 去重，manual 优先覆盖 sources
       - 未处理的 provider：完整保留
    5. 写盘 + git push + 飞书告警
"""
import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# 确保项目根目录在 sys.path 中，支持直接 python3 scripts/run_daily.py 运行
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.adapters import ADAPTERS
from scripts.core.manual import load_manual_providers
from scripts.core.models import (
    provider_to_dict, provider_status_to_dict, ProviderStatus, BillingType,
)
from scripts.core.validate import check_volatility, validate_global
from scripts.core.alert import send_feishu_alerts
from scripts.core.status import update_run_status
from scripts.core.reconcile import reconcile_provider
from scripts.sources import fetch_all_sources
from scripts.core.db import get_connection
from scripts.core import history

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
)
log = logging.getLogger("run_daily")

_PRICES_PATH = Path("data/prices.json")
_MANUAL_DIR = Path("data/manual")
_CN_TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def load_prices_json() -> dict:
    if not _PRICES_PATH.exists():
        return {"providers": [], "provider_status": []}
    return json.loads(_PRICES_PATH.read_text(encoding="utf-8"))


def write_prices_json(data: dict) -> None:
    _PRICES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PRICES_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def find_provider(data: dict, provider_id: str) -> dict:
    for p in data.get("providers", []):
        if p.get("id") == provider_id:
            return p
    return None


def has_changed(old: dict, new: dict) -> bool:
    return json.dumps(old, sort_keys=True) != json.dumps(new, sort_keys=True)


def git_commit_push() -> bool:
    if os.environ.get("SKIP_PUSH"):
        log.info("SKIP_PUSH set, skipping git commit/push")
        return True
    try:
        subprocess.run(["git", "add", str(_PRICES_PATH)], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore(data): update prices {_now_iso()}", "--", str(_PRICES_PATH)],
            check=True,
        )
        # 兼容容器内首次 push 无 upstream 的情况
        # git push 失败时回退到 --set-upstream 重试一次
        result = subprocess.run(["git", "push"], capture_output=True, text=True)
        if result.returncode != 0:
            if "no upstream branch" in result.stderr or "set-upstream" in result.stderr:
                log.info("no upstream set, retrying with --set-upstream origin master")
                subprocess.run(
                    ["git", "push", "--set-upstream", "origin", "master"],
                    check=True,
                )
            else:
                raise subprocess.CalledProcessError(
                    result.returncode, ["git", "push"], result.stdout, result.stderr
                )
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"git push failed: {e}")
        return False


def _find_last_success(old_data: dict, pid: str) -> str:
    for s in old_data.get("provider_status", []):
        if s.get("provider_id") == pid:
            return s.get("last_success_at")
    return None


def _products_to_dicts(products: list) -> list:
    """把 Product 对象列表转成 dict 列表（兼容已是 dict 的手动数据）。"""
    from scripts.core.models import Product, product_to_dict
    result = []
    for p in products:
        if isinstance(p, Product):
            result.append(product_to_dict(p))
        elif isinstance(p, dict):
            result.append(p)
        else:
            log.warning(f"unknown product type: {type(p)}, skipping")
    return result


def _build_provider_dict(
    adapter_or_pid,
    products,
    confidence: str = "",
    sources_used: list = None,
) -> dict:
    """构造 provider dict（兼容 adapter 对象和裸 provider_id）。

    如果是 adapter：用 adapter 静态字段
    如果是 provider_id 字符串：从 _PROVIDER_META 取静态字段
    """
    from scripts.adapters.base import BaseAdapter
    if isinstance(adapter_or_pid, BaseAdapter):
        provider = adapter_or_pid.to_provider(products)
        d = provider_to_dict(provider)
    else:
        pid = adapter_or_pid
        meta = _PROVIDER_META.get(pid, {})
        from scripts.core.models import Provider
        provider = Provider(
            id=pid,
            name=meta.get("name", pid),
            name_en=meta.get("name_en", pid),
            region=meta.get("region", "us"),
            website=meta.get("website", ""),
            pricing_url=meta.get("pricing_url", ""),
            products=products,
        )
        d = provider_to_dict(provider)
    return d


# 无 adapter 的厂商元数据（用于 sources-only 路径）
_PROVIDER_META = {
    "google": {
        "name": "Google", "name_en": "Google", "region": "us",
        "website": "https://ai.google.dev/",
        "pricing_url": "https://ai.google.dev/pricing",
    },
    "aws": {
        "name": "AWS", "name_en": "Amazon Web Services", "region": "us",
        "website": "https://aws.amazon.com/",
        "pricing_url": "https://aws.amazon.com/bedrock/pricing/",
    },
    "moonshot": {
        "name": "Kimi", "name_en": "Moonshot AI", "region": "cn",
        "website": "https://platform.moonshot.cn/",
        "pricing_url": "https://platform.moonshot.cn/docs/pricing",
        "pricing_url_overseas": "https://platform.moonshot.ai/docs/pricing",
    },
    "qwen": {
        "name": "阿里通义", "name_en": "Alibaba Qwen", "region": "cn",
        "website": "https://help.aliyun.com/zh/dashscope/",
        "pricing_url": "https://help.aliyun.com/zh/dashscope/product-overview/billing",
        "pricing_url_overseas": "https://www.alibabacloud.com/help/en/model-studio/billing-for-model-studio",
    },
    "volcengine": {
        "name": "火山引擎", "name_en": "Volcengine", "region": "cn",
        "website": "https://www.volcengine.com/",
        "pricing_url": "https://www.volcengine.com/docs/82379/1099320",
    },
    "minimax": {
        "name": "MiniMax", "name_en": "MiniMax", "region": "cn",
        "website": "https://platform.minimaxi.com/",
        "pricing_url": "https://platform.minimaxi.com/docs/guides/pricing-paygo",
    },
    "xiaomi": {
        "name": "小米", "name_en": "Xiaomi", "region": "cn",
        "website": "https://mimo.xiaomi.com/",
        "pricing_url": "https://platform.xiaomimimo.com/",
    },
}


def main() -> int:
    log.info("run_daily started")
    old_data = load_prices_json()
    new_providers = []
    provider_status = []
    alerts = []
    summary = {}

    # 初始化 SQLite 连接（自动建表）
    db_conn = get_connection()

    # ========== 1. 采集外部数据源 ==========
    log.info("step 1: fetching external sources")
    sources_data = fetch_all_sources()
    litellm_data = sources_data.get("litellm", {})
    openrouter_data = sources_data.get("openrouter", {})
    log.info(
        "sources fetched: litellm=%d providers, openrouter=%d providers",
        len(litellm_data), len(openrouter_data),
    )

    # 写入 L1/L2 原始数据留痕（便于仲裁失败时回溯）
    for pid, products in litellm_data.items():
        try:
            history.write_raw_fetch(db_conn, "litellm", pid, _products_to_dicts(products))
        except Exception as e:
            log.error(f"write_raw_fetch litellm/{pid} failed: {e}")
    for pid, products in openrouter_data.items():
        try:
            history.write_raw_fetch(db_conn, "openrouter", pid, _products_to_dicts(products))
        except Exception as e:
            log.error(f"write_raw_fetch openrouter/{pid} failed: {e}")

    # 记录已通过 reconcile 处理的 provider_id（用于后续 manual 合并）
    reconciled_pids = set()

    # ========== 2. 处理有 adapter 的厂商（三源仲裁）==========
    log.info("step 2: reconciling providers with adapter (L1+L2+L3)")
    for adapter in ADAPTERS:
        pid = adapter.provider_id
        reconciled_pids.add(pid)

        try:
            # L3: 官网 Scraper
            adapter_products = adapter.fetch()
            adapter_products = adapter.validate(adapter_products)

            # L3 原始数据留痕
            try:
                history.write_raw_fetch(db_conn, "adapter", pid, _products_to_dicts(adapter_products))
            except Exception as e:
                log.error(f"write_raw_fetch adapter/{pid} failed: {e}")

            # L1 + L2 + L3 仲裁
            litellm_products = litellm_data.get(pid, [])
            openrouter_products = openrouter_data.get(pid, [])

            reconcile_result = reconcile_provider(
                pid, litellm_products, openrouter_products, adapter_products,
            )
            products = reconcile_result.products

            # 仲裁告警 → 飞书
            for w in reconcile_result.warnings:
                alerts.append(("warning", pid, f"reconcile: {w}"))

            # 现有波动检测（与仲裁正交）
            old_provider = find_provider(old_data, pid)
            volatility = check_volatility(old_provider, products)

            if volatility.should_block:
                alerts.append(("blocked", pid, f"波动 {volatility.max_pct}%"))
                if old_provider:
                    new_providers.append(old_provider)
                status = ProviderStatus(
                    provider_id=pid,
                    status="failed",
                    last_success_at=_find_last_success(old_data, pid),
                    error=f"volatility blocked: {volatility.max_pct}%",
                    stale=True,
                )
                provider_status.append(provider_status_to_dict(status))
                summary[pid] = "blocked"
                continue

            if volatility.warnings:
                alerts.append(("warning", pid, f"波动 {volatility.max_pct}%"))

            new_providers.append(_build_provider_dict(adapter, products))
            status_dict = provider_status_to_dict(ProviderStatus(
                provider_id=pid,
                status="ok",
                last_success_at=_now_iso(),
                warnings=volatility.warnings,
            ))
            # 注入 confidence 字段
            status_dict["confidence"] = reconcile_result.confidence
            status_dict["sources"] = reconcile_result.sources_used
            provider_status.append(status_dict)
            summary[pid] = "ok"

            # 写入 SQLite 历史快照
            history.write_provider_snapshots(
                db_conn, pid, _products_to_dicts(products),
                confidence=reconcile_result.confidence,
                sources_used=reconcile_result.sources_used,
            )

        except Exception as e:
            log.error(f"{pid} failed: {e}")
            alerts.append(("failed", pid, str(e)))
            old_provider = find_provider(old_data, pid)
            if old_provider:
                new_providers.append(old_provider)
            status = ProviderStatus(
                provider_id=pid,
                status="failed",
                last_success_at=_find_last_success(old_data, pid),
                error=str(e),
                stale=True,
            )
            provider_status.append(provider_status_to_dict(status))
            summary[pid] = "failed"

    # ========== 3. 处理仅 sources 覆盖的厂商（双源仲裁）==========
    log.info("step 3: reconciling sources-only providers (L1+L2)")
    sources_only_pids = (
        (set(litellm_data.keys()) | set(openrouter_data.keys())) - reconciled_pids
    )
    for pid in sources_only_pids:
        reconciled_pids.add(pid)
        litellm_products = litellm_data.get(pid, [])
        openrouter_products = openrouter_data.get(pid, [])

        if not litellm_products and not openrouter_products:
            # 两源都空（如 volcengine 价格为 0 被过滤），交给 manual 兜底
            log.info(f"{pid}: both sources empty, fallback to manual")
            continue

        try:
            reconcile_result = reconcile_provider(
                pid, litellm_products, openrouter_products, [],
            )
            products = reconcile_result.products

            # AWS Bedrock: 只保留 us-east-1 region 的产品（同一模型不同 region 价格不同）
            if pid == "aws":
                original_count = len(products)
                products = [
                    p for p in products
                    if p.id.startswith("us-east-1/") or "/" not in p.id
                ]
                for p in products:
                    p.notes = "us-east-1 区域价格，其他区域可能不同"
                log.info(f"aws: filtered to us-east-1 only: {original_count} → {len(products)}")

            if not products:
                log.info(f"{pid}: reconcile returned 0 products, fallback to manual")
                continue

            for w in reconcile_result.warnings:
                alerts.append(("warning", pid, f"reconcile: {w}"))

            old_provider = find_provider(old_data, pid)
            volatility = check_volatility(old_provider, products)

            if volatility.should_block:
                alerts.append(("blocked", pid, f"波动 {volatility.max_pct}%"))
                if old_provider:
                    new_providers.append(old_provider)
                status = ProviderStatus(
                    provider_id=pid,
                    status="failed",
                    last_success_at=_find_last_success(old_data, pid),
                    error=f"volatility blocked: {volatility.max_pct}%",
                    stale=True,
                )
                provider_status.append(provider_status_to_dict(status))
                summary[pid] = "blocked"
                continue

            if volatility.warnings:
                alerts.append(("warning", pid, f"波动 {volatility.max_pct}%"))

            new_providers.append(_build_provider_dict(pid, products))
            status_dict = provider_status_to_dict(ProviderStatus(
                provider_id=pid,
                status="ok",
                last_success_at=_now_iso(),
                warnings=volatility.warnings,
            ))
            status_dict["confidence"] = reconcile_result.confidence
            status_dict["sources"] = reconcile_result.sources_used
            provider_status.append(status_dict)
            summary[pid] = "ok"

            # 写入 SQLite 历史快照
            history.write_provider_snapshots(
                db_conn, pid, _products_to_dicts(products),
                confidence=reconcile_result.confidence,
                sources_used=reconcile_result.sources_used,
            )

        except Exception as e:
            log.error(f"{pid} sources-only reconcile failed: {e}")
            # 降级：交给 manual 兜底
            continue

    # ========== 4. 合并 manual yaml ==========
    log.info("step 4: merging manual yaml")
    manual_providers = load_manual_providers(str(_MANUAL_DIR))
    for mp in manual_providers:
        pid = mp["id"]
        if pid in reconciled_pids:
            # 已通过 reconcile 处理：归一化 id 去重，manual 优先覆盖 sources
            # manual 的人工确认数据（官网 CNY 定价）覆盖 sources 的低置信度数据（USD）
            # manual 的分段产品（id 不同）自动补充，不覆盖 sources 中无对应 manual 的产品
            existing = next((p for p in new_providers if p["id"] == pid), None)
            if existing:
                # manual 的 provider 级别字段覆盖 existing（如 pricing_url、pricing_url_overseas）
                for key in ("name", "name_en", "region", "website",
                            "pricing_url", "pricing_url_overseas"):
                    if key in mp:
                        existing[key] = mp[key]

                manual_products = mp.get("products", [])
                manual_norm_ids = {
                    (prod.get("id") or "").lower() for prod in manual_products
                }
                # 保留 sources 中不被 manual 覆盖的产品
                kept = [
                    prod for prod in existing.get("products", [])
                    if (prod.get("id") or "").lower() not in manual_norm_ids
                ]
                # manual 产品覆盖（含 per_token/subscription/coding_plan）
                kept.extend(manual_products)
                existing["products"] = kept

                if manual_products:
                    log.info(
                        f"{pid}: merged {len(manual_products)} manual products "
                        f"(overrode sources where id matched)"
                    )
                    # 被波动 block 的厂商：existing 来自 old_provider，step 2/3 未写快照
                    # 需要写入完整产品列表（旧 sources + 新 manual）作为今日快照
                    # 正常 reconcile 的厂商：step 2/3 已写 sources 快照，这里只补 manual 部分
                    if summary.get(pid) == "blocked":
                        history.write_provider_snapshots(
                            db_conn, pid, existing.get("products", []),
                            confidence="manual",
                            sources_used=["manual", "stale_sources"],
                        )
                        log.info(f"{pid}: wrote full snapshot (blocked, includes stale sources + fresh manual)")
                    else:
                        history.write_provider_snapshots(
                            db_conn, pid, manual_products,
                            confidence="manual",
                            sources_used=["manual"],
                        )
                # reconcile 已写入 status，不重复追加
                continue
            else:
                # reconcile 失败但 manual 有该 provider，全部保留
                new_providers.append(mp)
                log.info(f"{pid}: reconcile failed, kept all manual products")
                history.write_provider_snapshots(
                    db_conn, pid, mp.get("products", []),
                    confidence="manual",
                    sources_used=["manual"],
                )
        else:
            # 未被 reconcile 处理（opencode/zhipu/volcengine），完整保留 manual
            new_providers.append(mp)
            log.info(f"{pid}: kept all manual products (not in sources)")
            history.write_provider_snapshots(
                db_conn, pid, mp.get("products", []),
                confidence="manual",
                sources_used=["manual"],
            )

        # 仅对未被 reconcile 处理的 manual provider 补充 status
        provider_status.append({
            "provider_id": pid,
            "status": "ok",
            "last_success_at": _now_iso(),
            "stale": False,
            "warnings": [],
            "confidence": "manual",
            "sources": ["manual"],
        })
        summary[pid] = "ok"

    # ========== 4.5 统一 per_token 产品的 purchase_url 为厂商官方定价页 ==========
    # OpenRouter/LiteLLM 来源的 purchase_url 指向 openrouter.ai，对终端用户无意义
    # 统一覆盖为厂商官方 pricing_url，subscription/coding_plan 保持 manual 的精准购买页
    # 双定价厂商：CNY 产品 → pricing_url（国内），USD 产品 → pricing_url_overseas（海外）
    log.info("step 4.5: unifying per_token purchase_url to vendor pricing page")
    for provider in new_providers:
        pid = provider.get("id", "")
        pricing_url = provider.get("pricing_url", "")
        pricing_url_overseas = provider.get("pricing_url_overseas", "")
        if not pricing_url:
            log.warning(f"{pid}: missing pricing_url, skip purchase_url override")
            continue
        per_token_count = 0
        for prod in provider.get("products", []):
            if prod.get("billing_type") == "per_token":
                cur = prod.get("prices", {}).get("currency", "")
                if cur == "USD" and pricing_url_overseas:
                    prod["purchase_url"] = pricing_url_overseas
                else:
                    prod["purchase_url"] = pricing_url
                per_token_count += 1
        if per_token_count:
            log.info(f"{pid}: unified {per_token_count} per_token purchase_url")

    # ========== 5. 价格变动检测（对比今日与昨日快照）==========
    log.info("step 5: detecting price changes")
    try:
        changes = history.detect_price_changes(db_conn)
        if changes:
            log.info(f"detected {len(changes)} price changes")
            # 大幅变动（>20%）加入告警
            for c in changes:
                pct = c.get("change_pct")
                if pct is not None and abs(pct) >= 20:
                    alerts.append((
                        "warning",
                        c["provider_id"],
                        f"{c['product_id']}.{c['field']} 变动 {pct}% ({c['old_value']}→{c['new_value']})",
                    ))
    except Exception as e:
        log.error(f"detect_price_changes failed: {e}")

    # ========== 6. 写盘 + 告警 ==========
    new_data = {
        "generated_at": _now_iso(),
        "providers": new_providers,
        "provider_status": provider_status,
    }

    if validate_global(new_data):
        write_prices_json(new_data)
        if has_changed(old_data, new_data):
            git_commit_push()
        update_run_status(success=True, providers_summary=summary)
        if alerts:
            send_feishu_alerts(alerts)
        db_conn.close()
        log.info(f"run_daily finished, {len(summary)} providers, {len(alerts)} alerts")
        return 0
    else:
        alerts.append(("fatal", "global", "Global validation failed"))
        update_run_status(success=False, providers_summary=summary)
        send_feishu_alerts(alerts)
        db_conn.close()
        log.error("run_daily failed: global validation failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
