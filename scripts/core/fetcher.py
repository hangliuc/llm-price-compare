# scripts/core/fetcher.py
import requests

# 使用真实浏览器 UA，避免被 Cloudflare/WAF 拦截（OpenAI 等厂商会拦截 bot UA）
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)

_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_html(url: str, timeout: int = 15) -> str:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.text


def fetch_json(url: str, timeout: int = 15) -> dict:
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# Playwright 改用 async API，避免 sync API 在已有 asyncio loop 环境下冲突
import asyncio
import threading
from playwright.async_api import async_playwright


async def _fetch_html_browser_async(url: str, wait_selector: str = None, timeout: int = 20) -> str:
    """用 headless Chromium 抓取动态渲染的页面（async 实现）。"""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        await page.set_extra_http_headers({"User-Agent": USER_AGENT})
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:
            # goto 超时也继续，页面可能部分加载
            pass
        if wait_selector:
            try:
                await page.wait_for_selector(wait_selector, timeout=timeout * 1000)
            except Exception:
                # 等待选择器超时就直接抓现有内容（比抛错好）
                pass
        html = await page.content()
        await browser.close()
        return html


def fetch_html_browser(url: str, wait_selector: str = None, timeout: int = 20) -> str:
    """用 headless Chromium 抓取动态渲染的页面。
    自动处理 asyncio loop 冲突：若已在 loop 内，开新线程跑。
    """
    try:
        asyncio.get_running_loop()
        # 已在运行中的 loop 内：开新线程跑（避免 sync/async 冲突）
        result = {}
        def runner():
            result["html"] = asyncio.run(_fetch_html_browser_async(url, wait_selector, timeout))
        t = threading.Thread(target=runner)
        t.start()
        t.join()
        if "html" not in result:
            raise RuntimeError("playwright thread failed")
        return result["html"]
    except RuntimeError:
        # 没有运行中的 loop，直接 asyncio.run
        return asyncio.run(_fetch_html_browser_async(url, wait_selector, timeout))
