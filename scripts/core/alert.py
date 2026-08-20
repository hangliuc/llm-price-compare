# scripts/core/alert.py
import os
import requests

_ALERT_TEMPLATES = {
    "warning": "[{i}] 类型: 数据待处理\n任务: {p}\n详情: {msg}",
    "fatal": "[{i}] 类型: Pipeline 失败\n任务: {p}\n详情: {msg}\n当前 Release 保持不变",
}


def format_alert_message(alert: tuple) -> str:
    kind, provider, msg = alert
    template = _ALERT_TEMPLATES.get(kind, "[{i}] 未知告警类型: {kind}\n{msg}")
    return template.format(i="{i}", kind=kind, p=provider, msg=msg)


def send_feishu_alerts(alerts: list, webhook_url: str = None) -> bool:
    """发送飞书告警。webhook_url 未配置时跳过并返回 False。"""
    if not alerts:
        return True

    url = webhook_url or os.environ.get("FEISHU_WEBHOOK_URL")
    if not url:
        return False

    lines = ["[LLM 比价站告警]"]
    for i, alert in enumerate(alerts, 1):
        kind, provider, msg = alert
        template = _ALERT_TEMPLATES.get(kind, "[{i}] 未知告警类型: {kind}\n{msg}")
        lines.append(template.format(i=i, kind=kind, p=provider, msg=msg))
        lines.append("")

    text = "\n".join(lines)
    payload = {"msg_type": "text", "content": {"text": text}}

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        return True
    except Exception:
        return False
