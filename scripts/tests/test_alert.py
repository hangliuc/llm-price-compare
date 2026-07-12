# scripts/tests/test_alert.py
from unittest.mock import patch, MagicMock
from scripts.core.alert import send_feishu_alerts, format_alert_message


def test_format_alert_message_failed():
    msg = format_alert_message(("failed", "volcengine", "timeout"))
    assert "适配器失败" in msg
    assert "volcengine" in msg
    assert "timeout" in msg


def test_format_alert_message_warning():
    msg = format_alert_message(("warning", "zhipu", "波动 30%"))
    assert "价格波动" in msg
    assert "30%" in msg


def test_format_alert_message_blocked():
    msg = format_alert_message(("blocked", "openai", "波动 80%"))
    assert "阻断" in msg


@patch("scripts.core.alert.requests.post")
def test_send_feishu_alerts_success(mock_post):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"code": 0}
    mock_post.return_value = mock_resp

    alerts = [("failed", "volcengine", "timeout")]
    ok = send_feishu_alerts(alerts, webhook_url="https://open.feishu.cn/openapis/bot/v2/hook/xxx")
    assert ok is True
    mock_post.assert_called_once()


@patch("scripts.core.alert.requests.post")
def test_send_feishu_alerts_no_webhook_returns_false(mock_post):
    import os
    # 确保环境变量未设置
    with patch.dict(os.environ, {}, clear=True):
        ok = send_feishu_alerts([("failed", "x", "y")], webhook_url=None)
        assert ok is False
        mock_post.assert_not_called()


@patch("scripts.core.alert.requests.post")
def test_send_feishu_alerts_empty_list_returns_true(mock_post):
    ok = send_feishu_alerts([], webhook_url="https://example.com")
    assert ok is True
    mock_post.assert_not_called()
