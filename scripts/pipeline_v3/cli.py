import argparse
import json
from pathlib import Path

from scripts.pipeline_v3.config import V3Config
from scripts.pipeline_v3.probe import probe_plan_adapters
from scripts.pipeline_v3.runner import run_pipeline
from scripts.pipeline_v3.sources.plans import all_plan_adapters, verified_plan_adapters
from scripts.pipeline_v3.storage import V3Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPK V3 data pipeline")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="build and optionally publish a V3 catalog")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--models-dev-file", type=Path)
    run.add_argument(
        "--models-only", action="store_true",
        help="migration diagnostic only: skip plans; production publishing must not use this",
    )
    commands.add_parser("status", help="show latest V3 run")
    commands.add_parser(
        "probe-plans",
        help="check every official plan source without publishing",
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
            plan_adapters=[] if args.models_only else verified_plan_adapters(config.timeout_seconds),
        )
    elif args.command == "status":
        store = V3Store(config.db_path)
        try:
            result = store.latest_status()
        finally:
            store.close()
    else:
        result = probe_plan_adapters(all_plan_adapters(config.timeout_seconds))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") not in {"failed", "degraded"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
