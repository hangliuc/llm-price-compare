# scripts/tests/test_fetcher.py
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
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
    # USER_AGENT 已改为真实浏览器 UA（避免被 Cloudflare/WAF 拦截）
    # 不再以 "LLM-Price-Bot" 开头
    assert "Mozilla" in USER_AGENT


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


# fetch_html_browser 已改为 async_playwright 实现，不再使用 sync_playwright
# 测试用 AsyncMock mock async_playwright 链路验证
from scripts.core.fetcher import fetch_html_browser


@patch("scripts.core.fetcher.async_playwright")
def test_fetch_html_browser_returns_html(mock_pw):
    # 构造 mock 链：async with async_playwright() as pw:
    #     browser = await pw.chromium.launch()
    #     page = await browser.new_page()
    #     ... await page.content()
    mock_page = MagicMock()
    mock_page.content = AsyncMock(return_value="<html>dynamic</html>")
    mock_page.goto = AsyncMock(return_value=None)
    mock_page.wait_for_selector = AsyncMock(return_value=None)
    mock_page.set_extra_http_headers = AsyncMock(return_value=None)

    mock_browser = MagicMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock(return_value=None)

    mock_context = MagicMock()
    mock_context.chromium.launch = AsyncMock(return_value=mock_browser)

    # async with async_playwright() as pw: 需要异步上下文管理器
    mock_pw.return_value.__aenter__ = AsyncMock(return_value=mock_context)
    mock_pw.return_value.__aexit__ = AsyncMock(return_value=None)

    html = fetch_html_browser("https://example.com", wait_selector=".price")
    assert html == "<html>dynamic</html>"
