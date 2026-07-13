# scripts/core/reconcile.py
"""三源交叉验证仲裁层。

输入：
    - LiteLLM 源（L1 主源）
    - OpenRouter 源（L2 交叉源）
    - 官网 Scraper（L3 兜底，仅 OpenAI/Anthropic/DeepSeek）

输出：
    - 仲裁后的 per_token Product 列表
    - 置信度（high/medium/low）
    - 告警列表（价差过大、源缺失等）

仲裁规则（按 product_id 维度对齐）：
    - 3 源都有，价差 <5%: 采信 L1，confidence=high
    - 3 源都有，1 源偏离 >20%: 采信另两源均值，confidence=medium，warning
    - 3 源都有，互差 >20%: 采信中位数，confidence=low，warning
    - 2 源都有，价差 <5%: 采信 L1，confidence=medium
    - 2 源都有，价差 >20%: 采信 Scraper（官网最权威），confidence=medium，warning
    - 1 源: 采信该源，confidence=low
    - 0 源: 跳过（由 run_daily 回退旧数据）

特殊规则：
    - LiteLLM 价格 = 0：源层已过滤（视为缺失）
    - Scraper 失败：不影响 L1/L2 仲裁
    - 现有 20%/50% 波动检测保留，叠加在仲裁之后
"""
import logging
import statistics
from dataclasses import dataclass, field
from typing import Optional

from scripts.core.models import Product, BillingType

log = logging.getLogger("core.reconcile")

# 价差阈值
_TIGHT_PCT = 5.0     # <5% 视为一致
_DIVERGE_PCT = 20.0  # >20% 视为偏离

# 价格字段
_PRICE_FIELDS = ["input", "output", "cached_input"]


@dataclass
class ReconcileResult:
    """单 provider 仲裁结果。"""
    products: list[Product] = field(default_factory=list)
    confidence: str = "low"  # "high" / "medium" / "low"
    warnings: list[str] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    # 每个 product 的来源标记：{product_id: "litellm" / "openrouter" / "adapter" / "merged"}
    product_sources: dict = field(default_factory=dict)


def reconcile_provider(
    provider_id: str,
    litellm_products: list[Product],
    openrouter_products: list[Product],
    adapter_products: list[Product],
) -> ReconcileResult:
    """对单个 provider 做三源仲裁。

    Args:
        provider_id: 厂商 ID
        litellm_products: LiteLLM 源采集的 per_token 产品（可能为空 list）
        openrouter_products: OpenRouter 源采集的 per_token 产品（可能为空 list）
        adapter_products: 官网 Scraper 抓取的产品（含 per_token + 订阅/coding_plan，
                         仅 per_token 参与仲裁，其他类型原样保留）

    Returns:
        ReconcileResult
    """
    result = ReconcileResult()
    sources_used = []
    if litellm_products:
        sources_used.append("litellm")
    if openrouter_products:
        sources_used.append("openrouter")
    if adapter_products:
        sources_used.append("adapter")
    result.sources_used = sources_used

    # 按 product_id 索引
    by_id = {
        "litellm": {p.id: p for p in litellm_products if p.billing_type == BillingType.PER_TOKEN},
        "openrouter": {p.id: p for p in openrouter_products if p.billing_type == BillingType.PER_TOKEN},
        "adapter": {p.id: p for p in adapter_products if p.billing_type == BillingType.PER_TOKEN},
    }

    # 所有出现过的 product_id
    all_ids = set()
    for src in by_id.values():
        all_ids.update(src.keys())

    # 收集每个 product 的置信度，取最低作为 provider 整体置信度
    confidences = []

    for pid in sorted(all_ids):
        litellm_p = by_id["litellm"].get(pid)
        openrouter_p = by_id["openrouter"].get(pid)
        adapter_p = by_id["adapter"].get(pid)

        # 收集非空源
        sources_present = []
        if litellm_p:
            sources_present.append(("litellm", litellm_p))
        if openrouter_p:
            sources_present.append(("openrouter", openrouter_p))
        if adapter_p:
            sources_present.append(("adapter", adapter_p))

        if not sources_present:
            continue

        # 仲裁价格
        final_product, confidence, warnings = _arbitrage_product(
            pid, sources_present
        )
        result.products.append(final_product)
        result.product_sources[pid] = confidence
        confidences.append(confidence)
        result.warnings.extend(warnings)

    # 非_per_token 类型（订阅/coding_plan）直接保留 from adapter
    for p in adapter_products:
        if p.billing_type != BillingType.PER_TOKEN:
            result.products.append(p)
            result.product_sources[p.id] = "adapter"

    # 整体置信度取最低
    if confidences:
        if "low" in confidences:
            result.confidence = "low"
        elif "medium" in confidences:
            result.confidence = "medium"
        else:
            result.confidence = "high"

    log.info(
        "reconcile %s: %d products, confidence=%s, sources=%s, %d warnings",
        provider_id, len(result.products), result.confidence,
        sources_used, len(result.warnings),
    )
    return result


def _arbitrage_product(
    product_id: str,
    sources: list[tuple[str, Product]],
) -> tuple[Product, str, list[str]]:
    """对单个 product 做价格仲裁。

    Args:
        product_id: 如 "claude-sonnet-5-token"
        sources: [("litellm", Product), ("openrouter", Product), ...]

    Returns:
        (最终 Product, confidence, warnings)
    """
    warnings = []

    # 收集每个源的价格
    price_map = {}  # {source_id: {field: value}}
    for src_id, p in sources:
        price_map[src_id] = p.prices

    # 对每个价格字段做投票
    final_prices = {}
    field_confidences = []

    for f in _PRICE_FIELDS:
        values = []  # [(source_id, value)]
        for src_id, prices in price_map.items():
            if f in prices and prices[f] is not None and prices[f] > 0:
                values.append((src_id, float(prices[f])))

        if not values:
            continue

        final_val, field_conf, warning = _vote_price(product_id, f, values)
        final_prices[f] = final_val
        field_confidences.append(field_conf)
        if warning:
            warnings.append(warning)

    # 补齐 currency/unit（任取一源）
    for src_id, p in sources:
        if "currency" in p.prices:
            final_prices.setdefault("currency", p.prices["currency"])
        if "unit" in p.prices:
            final_prices.setdefault("unit", p.prices["unit"])
        break

    # 字段置信度取最低
    if "low" in field_confidences:
        confidence = "low"
    elif "medium" in field_confidences:
        confidence = "medium"
    else:
        confidence = "high"

    # 元数据合并
    final_context = _merge_context_window([p for _, p in sources])
    final_modalities = _merge_modalities([p for _, p in sources])
    final_notes = _merge_notes([p for _, p in sources])
    final_purchase_url = _pick_purchase_url(sources)
    final_release_date = _merge_release_date(sources)
    final_model = sources[0][1].model  # 任取一源的 model 名

    product = Product(
        id=product_id,
        model=final_model,
        billing_type=BillingType.PER_TOKEN,
        context_window=final_context,
        modalities=final_modalities,
        prices=final_prices,
        purchase_url=final_purchase_url,
        release_date=final_release_date,
        notes=final_notes,
    )
    return product, confidence, warnings


def _vote_price(
    product_id: str, field: str, values: list[tuple[str, float]],
) -> tuple[float, str, Optional[str]]:
    """对单价格字段做多源投票。

    Returns:
        (最终价格, confidence, warning_msg_or_None)
    """
    if len(values) == 1:
        return values[0][1], "low", None

    if len(values) == 2:
        (s1, v1), (s2, v2) = values
        pct = _pct_diff(v1, v2)
        if pct < _TIGHT_PCT:
            # 一致，采信主源（litellm > adapter > openrouter）
            return _pick_preferred(values), "medium", None
        elif pct > _DIVERGE_PCT:
            # 偏离大，采信官网（如果有），否则采信主源
            preferred = next((v for s, v in values if s == "adapter"), None)
            if preferred is not None:
                return preferred, "medium", (
                    f"{product_id} prices.{field}: 2 源价差 {pct:.1f}% "
                    f"({s1}={v1}, {s2}={v2})，采信官网"
                )
            return _pick_preferred(values), "low", (
                f"{product_id} prices.{field}: 2 源价差 {pct:.1f}% "
                f"({s1}={v1}, {s2}={v2})，无官网兜底"
            )
        else:
            # 5-20% 之间，采信主源，warning
            return _pick_preferred(values), "medium", (
                f"{product_id} prices.{field}: 2 源价差 {pct:.1f}% "
                f"({s1}={v1}, {s2}={v2})，采信主源"
            )

    # 3 源
    vals = [v for _, v in values]
    max_pct = max(_pct_diff(vals[i], vals[j])
                  for i in range(len(vals))
                  for j in range(i + 1, len(vals)))

    if max_pct < _TIGHT_PCT:
        # 全部一致，采信主源
        return _pick_preferred(values), "high", None

    if max_pct < _DIVERGE_PCT:
        # 5-20% 之间，采信主源，warning
        return _pick_preferred(values), "medium", (
            f"{product_id} prices.{field}: 3 源价差 {max_pct:.1f}%，采信主源"
        )

    # >20%，检查是否有 2 源一致（偏离源单独）
    consistent_pair, outlier = _find_outlier(values)
    if consistent_pair:
        # 采信一致的两源均值
        avg = sum(v for _, v in consistent_pair) / len(consistent_pair)
        outlier_src, outlier_val = outlier
        return round(avg, 6), "medium", (
            f"{product_id} prices.{field}: {outlier_src}={outlier_val} 偏离，"
            f"采信 {[s for s, _ in consistent_pair]} 均值={avg:.4f}"
        )

    # 3 源互差 >20% 且无一致对，采信中位数
    median = statistics.median(vals)
    return round(median, 6), "low", (
        f"{product_id} prices.{field}: 3 源互差 {max_pct:.1f}% "
        f"({[(s, v) for s, v in values]})，采信中位数={median:.4f}"
    )


def _pct_diff(a: float, b: float) -> float:
    """两值价差百分比。"""
    if a == 0 and b == 0:
        return 0.0
    if a == 0 or b == 0:
        return 100.0
    return abs(a - b) / min(a, b) * 100.0


def _pick_preferred(values: list[tuple[str, float]]) -> float:
    """从多源中按优先级取值：litellm > adapter > openrouter。"""
    priority = ["litellm", "adapter", "openrouter"]
    for src in priority:
        for s, v in values:
            if s == src:
                return v
    return values[0][1]


def _find_outlier(
    values: list[tuple[str, float]],
) -> tuple[Optional[list[tuple[str, float]]], Optional[tuple[str, float]]]:
    """3 源中找出 2 源一致（价差<5%）、1 源偏离的配对。

    Returns:
        (consistent_pair, outlier) 或 (None, None)
        consistent_pair: [(source_id, value), (source_id, value)]
        outlier: (source_id, value)
    """
    for i in range(3):
        for j in range(i + 1, 3):
            s1, v1 = values[i]
            s2, v2 = values[j]
            if _pct_diff(v1, v2) < _TIGHT_PCT:
                # i, j 一致，k 是 outlier
                k = 3 - i - j
                return [values[i], values[j]], values[k]
    return None, None


def _merge_context_window(products: list[Product]) -> Optional[int]:
    """三源 context_window 取众数（多数派）。"""
    vals = [p.context_window for p in products if p.context_window]
    if not vals:
        return None
    # 取众数
    from collections import Counter
    counter = Counter(vals)
    return counter.most_common(1)[0][0]


def _merge_modalities(products: list[Product]) -> list:
    """modalities 取并集。"""
    merged = set()
    for p in products:
        for m in (p.modalities or []):
            merged.add(m)
    return sorted(merged)


def _merge_notes(products: list[Product]) -> Optional[str]:
    """notes 优先取 OpenRouter 的（含 benchmarks/reasoning 元数据）。"""
    # 找 OpenRouter 源的 product（notes 非空）
    for p in products:
        if p.notes and "benchmarks" in (p.notes or ""):
            return p.notes
    # 退而求其次，任取非空
    for p in products:
        if p.notes:
            return p.notes
    return None


def _merge_release_date(sources: list[tuple[str, Product]]) -> Optional[str]:
    """release_date 优先取 OpenRouter 的（LiteLLM 不提供此字段）。"""
    # 优先级：openrouter > adapter > litellm
    priority = ["openrouter", "adapter", "litellm"]
    for src in priority:
        for s, p in sources:
            if s == src and p.release_date:
                return p.release_date
    # 兜底：任取非空
    for _, p in sources:
        if p.release_date:
            return p.release_date
    return None


def _pick_purchase_url(sources: list[tuple[str, Product]]) -> str:
    """purchase_url 优先级：adapter > litellm > openrouter。"""
    priority = ["adapter", "litellm", "openrouter"]
    for src in priority:
        for s, p in sources:
            if s == src and p.purchase_url:
                return p.purchase_url
    # 兜底
    for _, p in sources:
        if p.purchase_url:
            return p.purchase_url
    return ""
