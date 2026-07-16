# scripts/core/history.py
"""历史数据 DAO：写入快照、原始数据、检测价格变动。

所有 SQL 集中在此文件，run_daily.py 只调用高层接口。
后续迁移 MySQL/Postgres 只需改本文件的 SQL 语法（? → %s 等）。
"""
import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Optional

log = logging.getLogger("history")

_CN_TZ = timezone(timedelta(hours=8))

# 价格字段：用于 price_changes 自动 diff
# per_token: input/output/cached_input；subscription/coding_plan: monthly_price/first_month_price
_PRICE_FIELDS = {
    "per_token": ["input_price", "output_price", "cached_input_price"],
    "subscription": ["monthly_price", "first_month_price"],
    "coding_plan": ["monthly_price", "first_month_price"],
}


def _now_iso() -> str:
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def _today() -> str:
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d")


def write_snapshot(
    conn: sqlite3.Connection,
    provider_id: str,
    product: dict,
    confidence: str = "",
    sources_used: list = None,
) -> None:
    """写入单个产品的当日快照。

    若当日已存在相同 (snapshot_date, provider_id, product_id) 则 REPLACE。
    """
    prices = product.get("prices") or {}
    billing_type = product.get("billing_type", "")
    snapshot_date = _today()

    # 按计费类型提取字段
    input_price = prices.get("input") if billing_type == "per_token" else None
    output_price = prices.get("output") if billing_type == "per_token" else None
    cached_input_price = prices.get("cached_input") if billing_type == "per_token" else None
    price_unit = prices.get("unit") if billing_type == "per_token" else None

    monthly_price = prices.get("monthly_price") if billing_type in ("subscription", "coding_plan") else None
    included_quota = prices.get("included_quota") if billing_type in ("subscription", "coding_plan") else None
    quota_unit = prices.get("quota_unit") if billing_type in ("subscription", "coding_plan") else None
    first_month_price = prices.get("first_month_price") if billing_type in ("subscription", "coding_plan") else None
    features = prices.get("features") if billing_type in ("subscription", "coding_plan") else None

    conn.execute(
        """
        INSERT OR REPLACE INTO price_snapshots (
            snapshot_date, provider_id, product_id, billing_type, model,
            context_window, modalities, release_date,
            input_price, output_price, cached_input_price, price_unit,
            monthly_price, included_quota, quota_unit, first_month_price, features,
            currency, purchase_url, notes,
            confidence, sources_used, raw_prices_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            snapshot_date,
            provider_id,
            product.get("id"),
            billing_type,
            product.get("model"),
            product.get("context_window"),
            json.dumps(product.get("modalities") or [], ensure_ascii=False),
            product.get("release_date"),
            input_price,
            output_price,
            cached_input_price,
            price_unit,
            monthly_price,
            included_quota,
            quota_unit,
            first_month_price,
            json.dumps(features or [], ensure_ascii=False) if features else None,
            prices.get("currency"),
            product.get("purchase_url"),
            product.get("notes"),
            confidence,
            json.dumps(sources_used or [], ensure_ascii=False),
            json.dumps(prices, ensure_ascii=False),
            _now_iso(),
        ),
    )


def write_provider_snapshots(
    conn: sqlite3.Connection,
    provider_id: str,
    products: list,
    confidence: str = "",
    sources_used: list = None,
) -> int:
    """批量写入一个厂商的所有产品快照，返回写入数量。"""
    count = 0
    for product in products:
        try:
            write_snapshot(conn, provider_id, product, confidence, sources_used)
            count += 1
        except Exception as e:
            log.error(f"write_snapshot failed for {provider_id}/{product.get('id')}: {e}")
    conn.commit()
    return count


def write_raw_fetch(
    conn: sqlite3.Connection,
    source: str,
    provider_id: str,
    raw_data: list,
) -> None:
    """写入一个源的原始抓取数据（litellm/openrouter/adapter）。"""
    conn.execute(
        """
        INSERT INTO raw_fetches (fetch_date, source, provider_id, raw_json, product_count, fetched_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            _today(),
            source,
            provider_id,
            json.dumps(raw_data, ensure_ascii=False),
            len(raw_data) if isinstance(raw_data, list) else None,
            _now_iso(),
        ),
    )
    conn.commit()


def detect_price_changes(conn: sqlite3.Connection) -> list:
    """对比今日与昨日快照，记录价格变动到 price_changes 表。

    返回变动列表，每项为 dict（便于告警）。
    """
    today = _today()
    # 取昨日日期：从 price_snapshots 中取小于今天的最大日期
    row = conn.execute(
        "SELECT MAX(snapshot_date) AS d FROM price_snapshots WHERE snapshot_date < ?",
        (today,),
    ).fetchone()
    yesterday = row["d"] if row else None
    if not yesterday:
        return []

    # 取今日和昨日快照
    today_rows = conn.execute(
        "SELECT * FROM price_snapshots WHERE snapshot_date = ?",
        (today,),
    ).fetchall()
    yesterday_map = {
        (r["provider_id"], r["product_id"]): r
        for r in conn.execute(
            "SELECT * FROM price_snapshots WHERE snapshot_date = ?",
            (yesterday,),
        ).fetchall()
    }

    changes = []
    for today_row in today_rows:
        key = (today_row["provider_id"], today_row["product_id"])
        yesterday_row = yesterday_map.get(key)
        if not yesterday_row:
            continue  # 新增产品，不算变动

        billing_type = today_row["billing_type"]
        fields = _PRICE_FIELDS.get(billing_type, [])
        for field in fields:
            old_val = yesterday_row[field]
            new_val = today_row[field]
            if old_val is None and new_val is None:
                continue
            if old_val is None or new_val is None:
                # 从无到有或从有到无，记录但不算百分比
                change_pct = None
            elif old_val == 0:
                change_pct = None if new_val == 0 else float("inf")
            else:
                change_pct = round((new_val - old_val) / old_val * 100, 2)

            if old_val != new_val:
                conn.execute(
                    """
                    INSERT INTO price_changes (
                        change_date, provider_id, product_id, billing_type,
                        field, old_value, new_value, change_pct, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        today,
                        today_row["provider_id"],
                        today_row["product_id"],
                        billing_type,
                        field,
                        old_val,
                        new_val,
                        change_pct,
                        _now_iso(),
                    ),
                )
                changes.append({
                    "provider_id": today_row["provider_id"],
                    "product_id": today_row["product_id"],
                    "billing_type": billing_type,
                    "field": field,
                    "old_value": old_val,
                    "new_value": new_val,
                    "change_pct": change_pct,
                })

    conn.commit()
    return changes


# ============ 查询接口（供 query_history.py 调用） ============

def get_product_history(
    conn: sqlite3.Connection,
    provider_id: str,
    product_id: str,
    days: int = 30,
) -> list:
    """查询单个产品最近 N 天的历史快照。"""
    rows = conn.execute(
        """
        SELECT * FROM price_snapshots
        WHERE provider_id = ? AND product_id = ?
        ORDER BY snapshot_date DESC
        LIMIT ?
        """,
        (provider_id, product_id, days),
    ).fetchall()
    return [dict(r) for r in rows]


def get_provider_changes(
    conn: sqlite3.Connection,
    provider_id: str,
    days: int = 30,
) -> list:
    """查询某厂商最近 N 天的价格变动。"""
    rows = conn.execute(
        """
        SELECT * FROM price_changes
        WHERE provider_id = ?
        AND change_date >= date('now', ?)
        ORDER BY change_date DESC, product_id, field
        """,
        (provider_id, f"-{days} days"),
    ).fetchall()
    return [dict(r) for r in rows]


def get_all_changes(
    conn: sqlite3.Connection,
    days: int = 7,
) -> list:
    """查询全平台最近 N 天的价格变动。"""
    rows = conn.execute(
        """
        SELECT * FROM price_changes
        WHERE change_date >= date('now', ?)
        ORDER BY change_date DESC, provider_id, product_id
        """,
        (f"-{days} days",),
    ).fetchall()
    return [dict(r) for r in rows]


def get_raw_fetches(
    conn: sqlite3.Connection,
    provider_id: str,
    source: Optional[str] = None,
    days: int = 3,
) -> list:
    """查询某厂商最近 N 天的原始抓取数据。"""
    if source:
        rows = conn.execute(
            """
            SELECT * FROM raw_fetches
            WHERE provider_id = ? AND source = ?
            AND fetch_date >= date('now', ?)
            ORDER BY fetch_date DESC
            """,
            (provider_id, source, f"-{days} days"),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT * FROM raw_fetches
            WHERE provider_id = ?
            AND fetch_date >= date('now', ?)
            ORDER BY fetch_date DESC
            """,
            (provider_id, f"-{days} days"),
        ).fetchall()
    return [dict(r) for r in rows]


def get_stats(conn: sqlite3.Connection) -> dict:
    """数据库统计信息（供调试用）。"""
    tables = ["price_snapshots", "raw_fetches", "price_changes"]
    stats = {}
    for t in tables:
        row = conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()
        stats[t] = row["c"]
    # 日期范围
    row = conn.execute(
        "SELECT MIN(snapshot_date) AS min_d, MAX(snapshot_date) AS max_d FROM price_snapshots"
    ).fetchone()
    stats["snapshot_date_range"] = {"min": row["min_d"], "max": row["max_d"]}
    return stats
