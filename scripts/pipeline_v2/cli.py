import argparse
import json
import logging
import os

from scripts.pipeline_v2.config import V2Config
from scripts.pipeline_v2.runner import run_pipeline
from scripts.pipeline_v2.storage import V2Store
from scripts.pipeline_v2.normalize import now_iso
from scripts.pipeline_v2.publisher import FileLock, rollback


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PPK V2 data pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="collect and build one V2 catalog")
    run.add_argument("--profile", choices=["payg", "plans", "full-verify"],
                     default="full-verify")
    run.add_argument("--dry-run", action="store_true")
    sub.add_parser("status", help="show the latest V2 run and source status")
    review = sub.add_parser("review", help="inspect and resolve V2 review items")
    review.add_argument("action", choices=["list", "show", "approve", "reject"],
                        default="list", nargs="?")
    review.add_argument("review_id", nargs="?")
    review.add_argument("--status", default="open")
    review.add_argument("--accept-baseline", action="store_true")
    review.add_argument("--by", default=os.environ.get("USER", "unknown"),
                        help="operator recorded in the audit trail")
    review.add_argument("--reason", default="", help="approval or rejection reason")
    release = sub.add_parser("release", help="list or roll back immutable V2 releases")
    release.add_argument("action", choices=["list", "rollback"], default="list", nargs="?")
    release.add_argument("release_id", nargs="?")
    release.add_argument("--limit", type=int, default=30)
    alerts = sub.add_parser("alerts", help="show recent V2 alerts")
    alerts.add_argument("--limit", type=int, default=50)
    maintenance = sub.add_parser("maintenance", help="V2 storage maintenance")
    maintenance.add_argument("action", choices=["retention"])
    maintenance.add_argument("--dry-run", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    config = V2Config.from_env()
    if args.command == "run":
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s %(levelname)-5s %(name)s: %(message)s")
        return run_pipeline(config, args.profile, args.dry_run)
    store = V2Store(config.db_path)
    try:
        if args.command == "status":
            data = store.latest_status()
        elif args.command == "alerts":
            data = store.list_alerts(args.limit)
        elif args.command == "maintenance":
            data = store.prune_evidence(
                config.evidence_retention_days, now_iso(), args.dry_run)
        elif args.command == "release":
            if args.action == "list":
                data = store.list_releases(args.limit)
            else:
                if not args.release_id:
                    raise SystemExit("release_id is required")
                releases_dir = config.releases_dir or config.runtime_dir / "releases"
                with FileLock(config.lock_path):
                    data = rollback(
                        config.catalog_path, config.status_path, releases_dir,
                        args.release_id, now_iso())
                    store.mark_release_current(args.release_id, now_iso())
        elif args.action == "list":
            data = store.list_reviews(args.status)
        else:
            if not args.review_id:
                raise SystemExit("review_id is required")
            if args.action in {"approve", "reject"} and not args.reason.strip():
                raise SystemExit("--reason is required for approve and reject")
            if args.action == "show":
                data = store.get_review(args.review_id)
                if data is None:
                    raise SystemExit(f"review not found: {args.review_id}")
            elif args.action == "approve":
                data = store.approve_review(
                    args.review_id, now_iso(), accept_baseline=args.accept_baseline,
                    actor=args.by, reason=args.reason)
            else:
                data = store.reject_review(
                    args.review_id, now_iso(), actor=args.by, reason=args.reason)
        print(json.dumps(data, ensure_ascii=False, indent=2))
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
