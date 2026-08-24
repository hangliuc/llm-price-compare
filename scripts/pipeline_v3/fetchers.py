from __future__ import annotations

import asyncio
from dataclasses import dataclass
import threading
from typing import Mapping

import requests


BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)


@dataclass(frozen=True)
class FetchResponse:
    raw: bytes
    http_status: int
    headers: Mapping[str, str]


class StaticHttpFetcher:
    """Fetch server-rendered official pages without executing JavaScript."""

    def fetch(self, url: str, timeout_seconds: int) -> FetchResponse:
        response = requests.get(
            url,
            headers={
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                "User-Agent": BROWSER_USER_AGENT,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return FetchResponse(
            raw=response.content,
            http_status=response.status_code,
            headers=dict(response.headers),
        )


async def _render(
    url: str,
    timeout_seconds: int,
    wait_selector: str | None,
    *,
    settle_ms: int = 1500,
    ready_headings: tuple[str, ...] = (),
    scroll_to_bottom: bool = False,
    locale: str = "zh-CN",
) -> FetchResponse:
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(
            user_agent=BROWSER_USER_AGENT,
            locale=locale,
        )
        response = await page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=timeout_seconds * 1000,
        )
        if wait_selector:
            await page.wait_for_selector(wait_selector, timeout=timeout_seconds * 1000)
        else:
            await page.wait_for_timeout(settle_ms)
        if scroll_to_bottom:
            # Several pricing sites defer lower cards until they enter the
            # viewport.  Trigger that work before snapshotting the DOM.
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(settle_ms)
        if ready_headings:
            await page.wait_for_function(
                """required => required.every(label =>
                    [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
                        .some(node => node.textContent.trim() === label)
                )""",
                arg=list(ready_headings),
                timeout=timeout_seconds * 1000,
            )
        raw = (await page.content()).encode("utf-8")
        status = response.status if response else 200
        headers = await response.all_headers() if response else {}
        await browser.close()
        return FetchResponse(raw=raw, http_status=status, headers=headers)


def _run_coroutine(coroutine):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)

    result: dict = {}
    failure: dict = {}

    def runner():
        try:
            result["value"] = asyncio.run(coroutine)
        except Exception as exc:  # pragma: no cover - re-raised on caller thread
            failure["error"] = exc

    thread = threading.Thread(target=runner)
    thread.start()
    thread.join()
    if "error" in failure:
        raise failure["error"]
    return result["value"]


class BrowserFetcher:
    """Render an official JavaScript page in headless Chromium."""

    def __init__(
        self,
        wait_selector: str | None = None,
        *,
        settle_ms: int = 1500,
        ready_headings: tuple[str, ...] = (),
        scroll_to_bottom: bool = False,
        locale: str = "zh-CN",
    ):
        self.wait_selector = wait_selector
        self.settle_ms = settle_ms
        self.ready_headings = ready_headings
        self.scroll_to_bottom = scroll_to_bottom
        self.locale = locale

    def fetch(self, url: str, timeout_seconds: int) -> FetchResponse:
        return _run_coroutine(
            _render(
                url,
                timeout_seconds,
                self.wait_selector,
                settle_ms=self.settle_ms,
                ready_headings=self.ready_headings,
                scroll_to_bottom=self.scroll_to_bottom,
                locale=self.locale,
            )
        )
