import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from scripts.core.db import get_connection
from scripts.pipeline.collector import CollectionResult
from scripts.pipeline.alerts import AlertDelivery


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def canonical_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def checksum(data: dict) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()


class PipelineStore:
    def __init__(self, db_path: Path):
        self.conn = get_connection(db_path)

    def close(self) -> None:
        self.conn.close()

    def start_run(self, run_id: str) -> None:
        self.conn.execute(
            "INSERT INTO pipeline_runs(run_id, started_at, status) VALUES (?, ?, 'running')",
            (run_id, now_iso()),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, status: str, summary: dict,
                   error: Optional[str] = None, published: bool = False) -> None:
        self.conn.execute(
            """UPDATE pipeline_runs SET finished_at=?, status=?, published_at=?, error=?, summary_json=?
               WHERE run_id=?""",
            (now_iso(), status, now_iso() if published else None, error,
             json.dumps(summary, ensure_ascii=False), run_id),
        )
        self.conn.commit()

    def record_collection(self, run_id: str, result: CollectionResult) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO pipeline_source_runs
               (run_id, source_id, status, product_count, duration_ms, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, result.source_id, result.status, result.product_count,
             result.duration_ms, result.error),
        )
        from scripts.pipeline.normalize import products_to_dicts
        for provider_id, products in result.products.items():
            payload = products_to_dicts(products)
            self.conn.execute(
                """INSERT INTO pipeline_raw_fetches
                   (run_id, source_id, provider_id, payload_json, product_count, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (run_id, result.source_id, provider_id,
                 json.dumps(payload, ensure_ascii=False), len(payload), now_iso()),
            )
        self.conn.commit()

    def record_provider(self, run_id: str, provider_id: str, status: str,
                        product_count: int, stale: bool, warnings: list,
                        error: Optional[str] = None) -> None:
        self.conn.execute(
            """INSERT OR REPLACE INTO pipeline_provider_runs
               (run_id, provider_id, status, product_count, stale, error, warnings_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (run_id, provider_id, status, product_count, int(stale), error,
             json.dumps(warnings, ensure_ascii=False)),
        )
        self.conn.commit()

    def stage_release(self, run_id: str, data: dict) -> str:
        digest = checksum(data)
        self.conn.execute(
            """INSERT INTO pipeline_releases
               (run_id, status, checksum, payload_json, created_at)
               VALUES (?, 'candidate', ?, ?, ?)""",
            (run_id, digest, json.dumps(data, ensure_ascii=False), now_iso()),
        )
        self.conn.commit()
        return digest

    def mark_release_published(self, run_id: str) -> None:
        self.conn.execute(
            "UPDATE pipeline_releases SET status='published', published_at=? WHERE run_id=?",
            (now_iso(), run_id),
        )
        self.conn.commit()

    def load_last_published(self) -> Optional[dict]:
        row = self.conn.execute(
            """SELECT payload_json FROM pipeline_releases
               WHERE status='published' ORDER BY published_at DESC LIMIT 1"""
        ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def record_changes(self, run_id: str, changes: list) -> None:
        created_at = now_iso()
        self.conn.executemany(
            """INSERT INTO pipeline_changes
               (run_id, provider_id, product_id, billing_type, field,
                old_value, new_value, change_pct, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [(
                run_id, item["provider_id"], item["product_id"],
                item.get("billing_type"), item["field"], item.get("old_value"),
                item.get("new_value"), item.get("change_pct"), created_at,
            ) for item in changes],
        )
        self.conn.commit()

    def record_alert(self, run_id: str, delivery: AlertDelivery) -> None:
        self.conn.execute(
            """INSERT INTO pipeline_alerts
               (run_id, channel, status, alert_count, error, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, delivery.channel, delivery.status, delivery.alert_count,
             delivery.error or None, now_iso()),
        )
        self.conn.commit()

    def latest_status(self) -> dict:
        run = self.conn.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not run:
            return {"status": "never_run"}
        run_id = run["run_id"]
        sources = self.conn.execute(
            "SELECT * FROM pipeline_source_runs WHERE run_id=? ORDER BY source_id", (run_id,)
        ).fetchall()
        providers = self.conn.execute(
            "SELECT * FROM pipeline_provider_runs WHERE run_id=? ORDER BY provider_id", (run_id,)
        ).fetchall()
        alerts = self.conn.execute(
            "SELECT * FROM pipeline_alerts WHERE run_id=? ORDER BY id", (run_id,)
        ).fetchall()
        result = dict(run)
        result["summary"] = json.loads(result.pop("summary_json") or "{}")
        result["sources"] = [dict(row) for row in sources]
        result["providers"] = [dict(row) for row in providers]
        result["alerts"] = [dict(row) for row in alerts]
        return result
