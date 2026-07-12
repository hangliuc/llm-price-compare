# scripts/run_daily.py
"""每日抓取入口：python3 scripts/run_daily.py"""
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
from scripts.core.models import provider_to_dict, provider_status_to_dict, ProviderStatus
from scripts.core.validate import check_volatility, validate_global
from scripts.core.alert import send_feishu_alerts
from scripts.core.status import update_run_status

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-5s %(message)s",
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


def main() -> int:
    log.info("run_daily started")
    old_data = load_prices_json()
    new_providers = []
    provider_status = []
    alerts = []
    summary = {}

    for adapter in ADAPTERS:
        pid = adapter.provider_id
        try:
            products = adapter.fetch()
            products = adapter.validate(products)

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

            new_providers.append(adapter.to_provider(products))
            status = ProviderStatus(
                provider_id=pid,
                status="ok",
                last_success_at=_now_iso(),
                warnings=volatility.warnings,
            )
            provider_status.append(provider_status_to_dict(status))
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

    # 合并 manual
    manual_providers = load_manual_providers(str(_MANUAL_DIR))
    new_providers.extend(manual_providers)
    for mp in manual_providers:
        pid = mp["id"]
        provider_status.append({
            "provider_id": pid,
            "status": "ok",
            "last_success_at": _now_iso(),
            "stale": False,
            "warnings": [],
        })
        summary[pid] = "ok"

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


def _find_last_success(old_data: dict, pid: str) -> str:
    for s in old_data.get("provider_status", []):
        if s.get("provider_id") == pid:
            return s.get("last_success_at")
    return None


if __name__ == "__main__":
    raise SystemExit(main())
