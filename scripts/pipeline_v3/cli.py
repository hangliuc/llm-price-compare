import argparse
import json
from pathlib import Path

from scripts.pipeline_v3.config import V3Config
from scripts.pipeline_v3.probe import probe_official_offer_adapters, probe_plan_adapters
from scripts.pipeline_v3.runner import run_pipeline
from scripts.pipeline_v3.seo import render_seo_assets
from scripts.pipeline_v3.sources.official_offers import experimental_official_offer_adapters
from scripts.pipeline_v3.sources.plans import all_plan_adapters, verified_plan_adapters
from scripts.pipeline_v3.storage import V3Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPK V3 data pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="build and optionally publish a V3 catalog")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--models-dev-file", type=Path)
    run.add_argument("--fx-file", type=Path, help="daily FX fixture; intended for offline tests/dry-runs")
    run.add_argument("--official-markets", action="store_true", help="include experimental official market-price adapters")
    run.add_argument(
        "--models-only", action="store_true",
        help="migration diagnostic only: skip plans; production publishing must not use this",
    )
    commands.add_parser("status", help="show latest V3 run")
    commands.add_parser(
        "render-seo",
        help="render crawlable provider pages and sitemap from the current published catalog",
    )
    commands.add_parser(
        "probe-plans",
        help="check every official plan source without publishing",
    )
    commands.add_parser(
        "probe-official-markets",
        help="check official market-price sources without publishing",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config = V3Config.from_env()
    if args.command == "run":
        result = run_pipeline(
            config,
            dry_run=args.dry_run,
            models_dev_file=args.models_dev_file,
            fx_file=args.fx_file,
            plan_adapters=[] if args.models_only else verified_plan_adapters(config.timeout_seconds),
            official_offer_adapters=(
                experimental_official_offer_adapters(config.timeout_seconds)
                if args.official_markets else None
            ),
        )
    elif args.command == "render-seo":
        catalog = json.loads(config.catalog_path.read_text(encoding="utf-8"))
        render_seo_assets(catalog, config.catalog_path.parent / "seo")
        result = {
            "status": "healthy",
            "release_id": catalog.get("release_id"),
            "provider_pages": len(catalog.get("providers", [])),
        }
    elif args.command == "status":
        store = V3Store(config.db_path)
        try:
            result = store.latest_status()
        finally:
            store.close()
    elif args.command == "probe-plans":
        result = probe_plan_adapters(all_plan_adapters(config.timeout_seconds))
    else:
        result = probe_official_offer_adapters(
            experimental_official_offer_adapters(config.timeout_seconds)
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") not in {"failed", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
