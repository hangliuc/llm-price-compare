# scripts/tests/test_run_daily.py
import json
import tempfile
import os
from pathlib import Path
from unittest.mock import patch, MagicMock
from scripts.core.models import Product, BillingType


def _make_adapter(provider_id: str, products: list = None, raises: Exception = None):
    a = MagicMock()
    a.provider_id = provider_id
    if raises:
        a.fetch.side_effect = raises
    else:
        a.fetch.return_value = products or []
        a.validate.return_value = products or []
    a.to_provider.return_value = {
        "id": provider_id,
        "name": provider_id,
        "name_en": provider_id,
        "region": "cn",
        "website": "https://example.com/",
        "pricing_url": "https://example.com/p",
        "products": [],
    }
    return a


@patch("scripts.run_daily.ADAPTERS", [])
@patch("scripts.run_daily.load_manual_providers")
@patch("scripts.run_daily.write_prices_json")
@patch("scripts.run_daily.git_commit_push")
def test_run_daily_empty_adapters(mock_git, mock_write, mock_manual):
    mock_manual.return_value = []
    from scripts.run_daily import main
    rc = main()
    assert rc == 0
    mock_write.assert_called_once()


@patch("scripts.run_daily.ADAPTERS", [])
@patch("scripts.run_daily.load_manual_providers")
@patch("scripts.run_daily.send_feishu_alerts")
@patch("scripts.run_daily.write_prices_json")
@patch("scripts.run_daily.git_commit_push")
def test_run_daily_adapter_failure_does_not_block(mock_git, mock_write, mock_alert, mock_manual):
    """单适配器失败不影响其他。"""
    bad_adapter = _make_adapter("bad", raises=RuntimeError("boom"))
    good_adapter = _make_adapter("good", products=[
        Product(id="p1", billing_type=BillingType.PER_TOKEN,
                prices={"input": 1, "output": 1, "currency": "USD", "unit": "per_1m_tokens"},
                purchase_url="https://example.com")
    ])

    with patch("scripts.run_daily.ADAPTERS", [bad_adapter, good_adapter]):
        from scripts.run_daily import main
        rc = main()

    assert rc == 0
    mock_write.assert_called_once()
    # 应该有告警
    assert mock_alert.called


@patch("scripts.run_daily.ADAPTERS", [])
@patch("scripts.run_daily.load_manual_providers")
@patch("scripts.run_daily.has_changed", return_value=False)
@patch("scripts.run_daily.git_commit_push")
def test_run_daily_no_change_no_commit(mock_git, mock_changed, mock_manual):
    mock_manual.return_value = []
    from scripts.run_daily import main
    rc = main()
    assert rc == 0
    mock_git.assert_not_called()
