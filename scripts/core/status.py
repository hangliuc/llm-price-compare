# scripts/core/status.py
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

_DEFAULT_PATH = "data/run_status.json"
_CN_TZ = timezone(timedelta(hours=8))


def _now_iso() -> str:
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def load_run_status(path: str = None) -> dict:
    p = Path(path or _DEFAULT_PATH)
    if not p.exists():
        return {"consecutive_failures": 0, "providers_summary": {}}
    return json.loads(p.read_text(encoding="utf-8"))


def update_run_status(success: bool, providers_summary: dict, path: str = None) -> None:
    p = Path(path or _DEFAULT_PATH)
    old = load_run_status(str(p))
    now = _now_iso()

    new = {
        "last_run_at": now,
        "last_success_at": now if success else old.get("last_success_at"),
        "consecutive_failures": 0 if success else old.get("consecutive_failures", 0) + 1,
        "last_push_at": now if success else old.get("last_push_at"),
        "providers_summary": providers_summary,
    }

    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(new, ensure_ascii=False, indent=2), encoding="utf-8")
