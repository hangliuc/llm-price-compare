#!/usr/bin/env python3
# scripts/query_history.py
"""历史数据查询命令行工具。

用法：
    # 查看数据库统计
    python3 scripts/query_history.py stats

    # 查询某产品最近 30 天历史
    python3 scripts/query_history.py product <provider_id> <product_id> [--days 30]

    # 查询某厂商最近 30 天价格变动
    python3 scripts/query_history.py changes <provider_id> [--days 30]

    # 查询全平台最近 7 天价格变动
    python3 scripts/query_history.py changes-all [--days 7]

    # 查询某厂商原始抓取数据（最近 3 天，可选源）
    python3 scripts/query_history.py raw <provider_id> [--source litellm|openrouter|adapter] [--days 3]

    # 列出所有厂商/产品（便于查询前确认 id）
    python3 scripts/query_history.py list
"""
import argparse
import json
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.core.db import get_connection
from scripts.core import history


def cmd_stats(args):
    conn = get_connection()
    stats = history.get_stats(conn)
    conn.close()
    print("=== 数据库统计 ===")
    for table, count in stats.items():
        if table == "snapshot_date_range":
            print(f"  快照日期范围: {count['min']} ~ {count['max']}")
        else:
            print(f"  {table}: {count} 条")


def cmd_product(args):
    conn = get_connection()
    rows = history.get_product_history(conn, args.provider, args.product, args.days)
    conn.close()
    if not rows:
        print(f"未找到 {args.provider}/{args.product} 的历史记录")
        return
    print(f"=== {args.provider}/{args.product} 最近 {args.days} 天历史 ===")
    for r in rows:
        print(f"\n[{r['snapshot_date']}] conf={r['confidence']} sources={r['sources_used']}")
        print(f"  billing_type: {r['billing_type']}")
        print(f"  model: {r['model']}")
        if r['billing_type'] == 'per_token':
            print(f"  input={r['input_price']} output={r['output_price']} cached={r['cached_input_price']} {r['price_unit']}")
        else:
            print(f"  monthly={r['monthly_price']} {r['currency']} quota={r['included_quota']} {r['quota_unit']}")
        if r['raw_prices_json']:
            print(f"  raw: {r['raw_prices_json']}")


def cmd_changes(args):
    conn = get_connection()
    if args.provider == 'all':
        rows = history.get_all_changes(conn, args.days)
        title = f"=== 全平台最近 {args.days} 天价格变动 ==="
    else:
        rows = history.get_provider_changes(conn, args.provider, args.days)
        title = f"=== {args.provider} 最近 {args.days} 天价格变动 ==="
    conn.close()
    print(title)
    if not rows:
        print("  无变动记录")
        return
    for r in rows:
        pct_str = f"{r['change_pct']}%" if r['change_pct'] is not None else "N/A"
        print(f"  [{r['change_date']}] {r['provider_id']}/{r['product_id']} "
              f"{r['billing_type']}.{r['field']}: {r['old_value']} → {r['new_value']} ({pct_str})")


def cmd_raw(args):
    conn = get_connection()
    rows = history.get_raw_fetches(conn, args.provider, args.source, args.days)
    conn.close()
    if not rows:
        print(f"未找到 {args.provider} 的原始数据")
        return
    print(f"=== {args.provider} 最近 {args.days} 天原始抓取 ===")
    for r in rows:
        print(f"\n[{r['fetch_date']}] source={r['source']} count={r['product_count']}")
        print(f"  raw_json: {r['raw_json'][:500]}...")


def cmd_list(args):
    """列出当前 prices.json 中所有厂商/产品，便于查询前确认 id。"""
    prices_path = Path("data/prices.json")
    if not prices_path.exists():
        print("data/prices.json 不存在")
        return
    data = json.loads(prices_path.read_text(encoding="utf-8"))
    print("=== 厂商/产品列表 ===")
    for p in data.get("providers", []):
        print(f"\n{p['id']} ({p['name']})")
        for prod in p.get("products", []):
            print(f"  - {prod['id']:<40} {prod.get('billing_type',''):<15} {prod.get('model','')}")


def main():
    parser = argparse.ArgumentParser(description="PPK 历史数据查询工具")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("stats", help="数据库统计")

    p_product = sub.add_parser("product", help="查询单产品历史")
    p_product.add_argument("provider", help="厂商 id")
    p_product.add_argument("product", help="产品 id")
    p_product.add_argument("--days", type=int, default=30, help="天数（默认 30）")

    p_changes = sub.add_parser("changes", help="查询价格变动（provider=all 查全部）")
    p_changes.add_argument("provider", help="厂商 id 或 all")
    p_changes.add_argument("--days", type=int, default=30, help="天数（默认 30）")

    p_raw = sub.add_parser("raw", help="查询原始抓取数据")
    p_raw.add_argument("provider", help="厂商 id")
    p_raw.add_argument("--source", choices=["litellm", "openrouter", "adapter"], help="源")
    p_raw.add_argument("--days", type=int, default=3, help="天数（默认 3）")

    sub.add_parser("list", help="列出所有厂商/产品 id")

    args = parser.parse_args()

    if args.cmd == "stats":
        cmd_stats(args)
    elif args.cmd == "product":
        cmd_product(args)
    elif args.cmd == "changes":
        cmd_changes(args)
    elif args.cmd == "raw":
        cmd_raw(args)
    elif args.cmd == "list":
        cmd_list(args)


if __name__ == "__main__":
    main()
