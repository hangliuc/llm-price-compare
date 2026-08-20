import os
from dataclasses import dataclass
from typing import Callable

from scripts.core.alert import send_feishu_alerts


@dataclass(frozen=True)
class AlertDelivery:
    channel: str
    status: str
    alert_count: int
    error: str = ""


def deliver_alerts(alerts: list, sender: Callable = send_feishu_alerts) -> AlertDelivery:
    if not alerts:
        return AlertDelivery("feishu", "not_needed", 0)
    if not os.environ.get("FEISHU_WEBHOOK_URL"):
        return AlertDelivery("feishu", "skipped", len(alerts), "webhook not configured")
    try:
        delivered = sender(alerts)
    except Exception as exc:
        return AlertDelivery("feishu", "failed", len(alerts), str(exc))
    if delivered:
        return AlertDelivery("feishu", "delivered", len(alerts))
    return AlertDelivery("feishu", "failed", len(alerts), "sender returned false")


def deliver_pipeline_alert(severity: str, code: str, message: str) -> tuple[str, str]:
    """Reuse the lightweight Feishu channel without making it mandatory."""
    kind = "fatal" if severity == "P0" else "warning"
    payload = [(kind, "pipeline-v2", f"[{code}] {message}")]
    delivery = deliver_alerts(payload)
    return delivery.status, delivery.error


def alerting_configured() -> bool:
    return bool(os.environ.get("FEISHU_WEBHOOK_URL"))
