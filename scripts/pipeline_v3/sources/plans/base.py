from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, replace
from html.parser import HTMLParser
import re
from typing import Mapping

from scripts.pipeline_v3.fetchers import BrowserFetcher, StaticHttpFetcher
from scripts.pipeline_v3.models import Plan


@dataclass(frozen=True)
class PlanFetch:
    source: str
    source_url: str
    raw: bytes
    http_status: int
    headers: Mapping[str, str]


class OfficialPlanAdapter(ABC):
    source: str
    source_url: str
    minimum_plan_count: int = 1
    fetch_mode: str = "static"
    wait_selector: str | None = None
    render_settle_ms: int = 1500
    render_ready_headings: tuple[str, ...] = ()
    render_scroll_to_bottom: bool = False

    def __init__(self, *, timeout_seconds: int = 45, fetcher=None):
        self.timeout_seconds = timeout_seconds
        self.fetcher = fetcher or (
            BrowserFetcher(
                self.wait_selector,
                settle_ms=self.render_settle_ms,
                ready_headings=self.render_ready_headings,
                scroll_to_bottom=self.render_scroll_to_bottom,
            )
            if self.fetch_mode == "browser"
            else StaticHttpFetcher()
        )

    def fetch(self) -> PlanFetch:
        response = self.fetcher.fetch(self.source_url, self.timeout_seconds)
        return PlanFetch(
            source=self.source,
            source_url=self.source_url,
            raw=response.raw,
            http_status=response.http_status,
            headers=response.headers,
        )

    @abstractmethod
    def normalize(self, raw: bytes, fetched_at: str) -> list[Plan]:
        raise NotImplementedError


class _VisibleTextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript", "svg"}:
            self.hidden_depth += 1

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript", "svg"} and self.hidden_depth:
            self.hidden_depth -= 1

    def handle_data(self, data):
        if not self.hidden_depth and data.strip():
            self.parts.append(data.strip())


def visible_text(raw: bytes) -> str:
    parser = _VisibleTextParser()
    parser.feed(raw.decode("utf-8", errors="replace"))
    return re.sub(r"\s+", " ", " ".join(parser.parts)).strip()


def product_window(text: str, name: str, next_names: tuple[str, ...], width: int = 900) -> str:
    """Return text near a product heading without crossing the next heading."""

    start = text.casefold().find(name.casefold())
    if start < 0:
        return ""
    end = min(len(text), start + width)
    folded = text.casefold()
    for next_name in next_names:
        candidate = folded.find(next_name.casefold(), start + len(name))
        if candidate >= 0:
            end = min(end, candidate)
    return text[start:end]


_MONTHLY_PRICE_PATTERNS = (
    re.compile(r"(?:之后\s*)?每月\s*(?:US)?\$?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:美元|USD)", re.I),
    re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:美元|USD)\s*(?:/\s*月|每月)", re.I),
    re.compile(r"(?:US)?\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:USD\s*)?(?:/\s*(?:user\s*/\s*)?|per\s+(?:user\s*(?:/|per)\s*)?)mo(?:nth)?", re.I),
    re.compile(r"(?:monthly|month)\s*(?:price)?\s*[:\-]?\s*(?:US)?\$\s*([0-9]+(?:\.[0-9]+)?)", re.I),
    re.compile(r"(?:US)?\$\s*([0-9]+(?:\.[0-9]+)?)\s*(?:monthly|a month)", re.I),
)


def monthly_usd(window: str, *, free: bool = False) -> float | None:
    if free:
        return 0.0
    for pattern in _MONTHLY_PRICE_PATTERNS:
        match = pattern.search(window)
        if match:
            return float(match.group(1))
    return None


def require_complete_prices(plans: list[Plan], expected_count: int, source: str) -> list[Plan]:
    if len(plans) != expected_count:
        raise ValueError(
            f"{source}: parsed {len(plans)} plans; expected {expected_count}; official page likely changed"
        )
    missing = [item.product_name for item in plans if item.price_amount is None]
    if missing:
        raise ValueError(f"{source}: missing official monthly price for {', '.join(missing)}")
    # Keep the raw official window for auditability, but also expose a small
    # structured feature list for the UI. This is deliberately conservative:
    # when the source does not contain a recognizable benefit phrase we leave
    # features empty instead of inventing a claim.
    return [replace(item, features=extract_official_features(item.raw.get("official_text", "")))
            if not item.features else item for item in plans]


_FEATURE_MARKERS = re.compile(
    r"(?:included|includes|access to|unlimited|priority|credits?|messages?|requests?|"
    r"code completion|coding|agent|context|models?|storage|generation|"
    r"包含|支持|提供|额度|积分|消息|请求|代码补全|聊天|模型|存储|生成|优先)",
    re.I,
)


def extract_official_features(official_text: str, *, limit: int = 4) -> tuple[str, ...]:
    """Extract benefit-like clauses from an already fetched official window.

    This is not a semantic fallback and does not add product knowledge. It
    only returns clauses that are present in the captured official text.
    """
    if not official_text:
        return ()
    chunks = re.split(r"(?<=[.;。；])\s+|\s*[•·▪◦]\s*|\s{2,}", official_text)
    features: list[str] = []
    for chunk in chunks:
        value = re.sub(r"\s+", " ", chunk).strip(" -–—:：")
        if len(value) < 5 or len(value) > 180 or not _FEATURE_MARKERS.search(value):
            continue
        value = translate_feature(value)
        if value and value not in features:
            features.append(value)
        if len(features) >= limit:
            break
    return tuple(features)


def translate_feature(value: str) -> str:
    """Convert recognized official benefit phrases into concise Chinese."""
    patterns = (
        (r"([\d,]+)\s+completions?\s+per\s+month", lambda m: f"代码补全：每月 {m.group(1)} 次"),
        (r"access to (?:haiku 4\.5, )?gpt-5 mini,? and more", lambda _: "模型访问：Haiku 4.5、GPT-5 mini 等"),
        (r"access to open weight models", lambda _: "可使用开放权重模型"),
        (r"access to premium models", lambda _: "可使用高级模型"),
        (r"access to (?:the )?github copilot student plan", lambda _: "可使用 GitHub Copilot 学生计划"),
        (r"community support", lambda _: "社区支持"),
        (r"no credit card required", lambda _: "无需信用卡"),
        (r"chat, agent mode, code review, copilot cloud agent, copilot cli, and copilot apps", lambda _: "聊天、Agent 模式、代码审查、云端 Agent 与 Copilot Apps"),
        (r"for everyday coding with agents in github copilot", lambda _: "面向日常编码的 Agent 编程辅助"),
        (r"for more complex development with premium models", lambda _: "面向复杂开发的高级模型"),
        (r"for sustained, high-volume agent workflows with github copilot", lambda _: "面向高频、持续的 Agent 编程工作流"),
        (r"([\d,]+)\s+credits?", lambda m: f"使用额度：{m.group(1)} credits"),
        (r"higher usage limits", lambda _: "更高使用额度"),
        (r"more usage", lambda _: "更多使用量"),
        (r"web search", lambda _: "联网搜索"),
        (r"extended thinking", lambda _: "扩展思考"),
        (r"deep research|research", lambda _: "深度研究"),
        (r"file uploads?", lambda _: "文件上传"),
        (r"image generation", lambda _: "图像生成"),
        (r"projects?", lambda _: "项目空间"),
        (r"image, music, and video generation models in Gemini and Search", lambda _: "模型访问：Gemini 与 Google 搜索中的图像、音乐和视频生成模型"),
        (r"features and models in Gemini Notebook", lambda _: "模型访问：Gemini Notebook 中的功能和模型"),
        (r"Gemini 3 Pro in AI Mode for Google Search", lambda _: "模型访问：Google 搜索 AI 模式中的 Gemini 3 Pro"),
        (r"features including Deep Search", lambda _: "功能：深度搜索 Deep Search"),
        (r"Gemini Spark", lambda _: "功能：Gemini Spark"),
    )
    for pattern, builder in patterns:
        match = re.search(pattern, value, flags=re.I)
        if match:
            return builder(match)
    # 已经是中文的官方片段可以保留；纯英文长句不进入前台。
    if re.search(r"[\u4e00-\u9fff]", value) and not re.search(r"\b(?:included|access|support|plan|price)\b", value, flags=re.I):
        return value
    return ""
