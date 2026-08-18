from dataclasses import dataclass
import os
from typing import Callable

from scripts.core.alert import send_feishu_alerts


@dataclass(frozen=True)
class AlertDelivery:
    channel: str
    status: str
    alert_count: int
    error: str = ""


def deliver_alerts(alerts: list, sender: Callable = send_feishu_alerts) -> AlertDelivery:
    """Deliver one aggregate alert and expose skipped/failed outcomes."""
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
