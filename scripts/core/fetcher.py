# scripts/core/fetcher.py
import requests

USER_AGENT = "LLM-Price-Bot/1.0 (+https://github.com/llm-price-compare/llm-price-compare)"

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


def fetch_html(url: str, timeout: int = 10) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_json(url: str, timeout: int = 10) -> dict:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# 追加到 scripts/core/fetcher.py
from playwright.sync_api import sync_playwright


def fetch_html_browser(url: str, wait_selector: str = None, timeout: int = 15) -> str:
    """用 headless Chromium 抓取动态渲染的页面。"""
    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=True)
    page = browser.new_page()
    page.set_extra_http_headers({"User-Agent": USER_AGENT})
    page.goto(url)
    if wait_selector:
        page.wait_for_selector(wait_selector, timeout=timeout * 1000)
    html = page.content()
    browser.close()
    return html
