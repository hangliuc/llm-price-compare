# scripts/tests/test_fetcher.py
import pytest
from unittest.mock import patch, MagicMock
from scripts.core.fetcher import fetch_html, fetch_json, USER_AGENT


@patch("scripts.core.fetcher.requests.get")
def test_fetch_html_returns_text(mock_get):
    mock_resp = MagicMock()
    mock_resp.text = "<html>hello</html>"
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    html = fetch_html("https://example.com/pricing")
    assert html == "<html>hello</html>"
    args, kwargs = mock_get.call_args
    assert kwargs["headers"]["User-Agent"] == USER_AGENT
    assert USER_AGENT.startswith("LLM-Price-Bot")


@patch("scripts.core.fetcher.requests.get")
def test_fetch_json_returns_dict(mock_get):
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"key": "value"}
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_get.return_value = mock_resp

    data = fetch_json("https://example.com/api")
    assert data == {"key": "value"}


@patch("scripts.core.fetcher.requests.get")
def test_fetch_html_raises_on_403(mock_get):
    import requests
    mock_resp = MagicMock()
    mock_resp.status_code = 403
    mock_resp.raise_for_status.side_effect = requests.HTTPError("403")
    mock_get.return_value = mock_resp

    with pytest.raises(requests.HTTPError):
        fetch_html("https://example.com/forbidden")


# 追加到 scripts/tests/test_fetcher.py
from unittest.mock import patch, MagicMock
from scripts.core.fetcher import fetch_html_browser


@patch("scripts.core.fetcher.sync_playwright")
def test_fetch_html_browser_returns_html(mock_pw):
    # 构造 mock 链：sync_playwright().start().browser.new_page().content()
    mock_context = MagicMock()
    mock_browser = MagicMock()
    mock_page = MagicMock()
    mock_page.content.return_value = "<html>dynamic</html>"
    mock_browser.new_page.return_value = mock_page
    mock_context.chromium.launch.return_value = mock_browser
    mock_pw.return_value.start.return_value = mock_context

    html = fetch_html_browser("https://example.com", wait_selector=".price")
    assert html == "<html>dynamic</html>"
    mock_page.goto.assert_called_once_with("https://example.com")
    mock_page.wait_for_selector.assert_called_once_with(".price", timeout=15000)
