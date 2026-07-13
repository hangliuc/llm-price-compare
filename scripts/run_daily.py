# scripts/run_daily.py
"""每日抓取入口：python3 scripts/run_daily.py

三源交叉验证流程：
    1. 采集 L1 (LiteLLM) + L2 (OpenRouter) 外部数据源
    2. 对每个 provider：
       - 有官网 adapter：L1 + L2 + L3(adapter) 三源仲裁
       - 无 adapter：L1 + L2 双源仲裁
    3. 现有 20%/50% 波动检测保留（与仲裁是两个维度）
    4. manual yaml 合并：
       - reconcile 处理过的 provider：跳过 per_token 产品，保留订阅/coding_plan
       - 未处理的 provider：完整保留
    5. 写盘 + git push + 飞书告警
"""
import json
import logging
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
    try:
        subprocess.run(["git", "add", str(_PRICES_PATH)], check=True)
        subprocess.run(
            ["git", "commit", "-m", f"chore(data): update prices {_now_iso()}", "--", str(_PRICES_PATH)],
            check=True,
        )
        subprocess.run(["git", "push"], check=True)
        return True
    except subprocess.CalledProcessError as e:
        log.error(f"git push failed: {e}")
        return False


def _find_last_success(old_data: dict, pid: str) -> str:
    for s in old_data.get("provider_status", []):
        if s.get("provider_id") == pid:
            return s.get("last_success_at")
    return None


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
    },
    "qwen": {
        "name": "通义千问", "name_en": "Alibaba Qwen", "region": "cn",
        "website": "https://help.aliyun.com/zh/dashscope/",
        "pricing_url": "https://help.aliyun.com/zh/dashscope/product-overview/billing",
    },
    "volcengine": {
        "name": "火山引擎", "name_en": "Volcengine", "region": "cn",
        "website": "https://www.volcengine.com/",
        "pricing_url": "https://www.volcengine.com/docs/82379/1099320",
    },
    "minimax": {
        "name": "MiniMax", "name_en": "MiniMax", "region": "cn",
        "website": "https://platform.minimaxi.com/",
        "pricing_url": "https://platform.minimaxi.com/document/Price",
    },
    "xiaomi": {
        "name": "小米", "name_en": "Xiaomi", "region": "cn",
        "website": "https://mimo.xiaomi.com/",
        "pricing_url": "https://mimo.xiaomi.com/",
    },
}


def main() -> int:
    log.info("run_daily started")
    old_data = load_prices_json()
    new_providers = []
    provider_status = []
    alerts = []
    summary = {}

    # ========== 1. 采集外部数据源 ==========
    log.info("step 1: fetching external sources")
    sources_data = fetch_all_sources()
    litellm_data = sources_data.get("litellm", {})
    openrouter_data = sources_data.get("openrouter", {})
    log.info(
        "sources fetched: litellm=%d providers, openrouter=%d providers",
        len(litellm_data), len(openrouter_data),
    )

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
            # 已通过 reconcile 处理：跳过 manual 的 per_token 产品，
            # 仅保留订阅/coding_plan 产品（追加到 new_providers 中对应的 provider）
            existing = next((p for p in new_providers if p["id"] == pid), None)
            if existing:
                non_per_token = [
                    prod for prod in mp.get("products", [])
                    if prod.get("billing_type") != BillingType.PER_TOKEN.value
                ]
                if non_per_token:
                    existing["products"].extend(non_per_token)
                    log.info(f"{pid}: merged {len(non_per_token)} non-per_token from manual")
                # reconcile 已写入 status，不重复追加
                continue
            else:
                # reconcile 失败但 manual 有该 provider，全部保留
                new_providers.append(mp)
                log.info(f"{pid}: reconcile failed, kept all manual products")
        else:
            # 未被 reconcile 处理（opencode/zhipu/volcengine），完整保留 manual
            new_providers.append(mp)
            log.info(f"{pid}: kept all manual products (not in sources)")

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

    # ========== 5. 写盘 + 告警 ==========
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
        log.info(f"run_daily finished, {len(summary)} providers, {len(alerts)} alerts")
        return 0
    else:
        alerts.append(("fatal", "global", "Global validation failed"))
        update_run_status(success=False, providers_summary=summary)
        send_feishu_alerts(alerts)
        log.error("run_daily failed: global validation failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
