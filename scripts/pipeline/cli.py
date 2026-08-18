import argparse
import json
import logging

from scripts.pipeline.config import PipelineConfig
from scripts.pipeline.runner import run_pipeline
from scripts.pipeline.storage import PipelineStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPK data pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="collect, validate and publish one dataset")
    sub.add_parser("status", help="show the latest pipeline run")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config = PipelineConfig.from_env()
    if args.command == "run":
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)-5s %(name)s: %(message)s")
        return run_pipeline(config)
    store = PipelineStore(config.db_path)
    try:
        print(json.dumps(store.latest_status(), ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
