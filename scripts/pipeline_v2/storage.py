import hashlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from pathlib import Path
from typing import Optional

from scripts.pipeline_v2.models import FieldDecision, Observation, ReviewItem
from scripts.pipeline_v2.evidence import EvidenceRecord


def canonical_json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class V2Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.conn.executescript(schema)
        self._apply_dev_migrations()

    def _apply_dev_migrations(self) -> None:
        """Keep pre-production V2 databases usable while the schema evolves."""
        columns = {row["name"] for row in self.conn.execute(
            "PRAGMA table_info(review_items_v2)"
        ).fetchall()}
        if "resolved_at" not in columns:
            self.conn.execute("ALTER TABLE review_items_v2 ADD COLUMN resolved_at TEXT")
        if "resolution_json" not in columns:
            self.conn.execute("ALTER TABLE review_items_v2 ADD COLUMN resolution_json TEXT")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def start_run(self, run_id: str, profile: str, started_at: str) -> None:
        self.conn.execute(
            "INSERT INTO runs_v2(run_id, profile, started_at, status) VALUES (?, ?, ?, 'running')",
            (run_id, profile, started_at),
        )
        self.conn.commit()

    def finish_run(self, run_id: str, finished_at: str, status: str,
                   summary: dict, error: Optional[str] = None) -> None:
        self.conn.execute(
            "UPDATE runs_v2 SET finished_at=?, status=?, error=?, summary_json=? WHERE run_id=?",
            (finished_at, status, error, json.dumps(summary, ensure_ascii=False), run_id),
        )
        self.conn.commit()

    def record_source(self, run_id: str, source_id: str, status: str,
                      count: int, duration_ms: int, error: Optional[str]) -> None:
        self.conn.execute(
            """INSERT INTO source_runs_v2
               (run_id, source_id, status, product_count, duration_ms, error)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (run_id, source_id, status, count, duration_ms, error),
        )
        self.conn.commit()

    def record_evidence(self, run_id: str, evidence: EvidenceRecord,
                        created_at: str) -> str:
        evidence_id = uuid4().hex
        self.conn.execute(
            """INSERT OR IGNORE INTO evidence_v2
               (evidence_id,run_id,source_id,artifact_kind,content_type,sha256,
                artifact_path,byte_size,created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (evidence_id, run_id, evidence.source_id, evidence.artifact_kind,
             evidence.content_type, evidence.sha256, evidence.artifact_path,
             evidence.byte_size, created_at),
        )
        self.conn.commit()
        return evidence_id

    def list_evidence(self, run_id: str) -> list[dict]:
        return [dict(row) for row in self.conn.execute(
            """SELECT source_id,artifact_kind,content_type,sha256,artifact_path,
                      byte_size,created_at FROM evidence_v2
               WHERE run_id=? ORDER BY source_id""", (run_id,)
        ).fetchall()]

    def prune_evidence(self, retention_days: int, now: Optional[str] = None,
                       dry_run: bool = False) -> dict:
        current = datetime.fromisoformat((now or datetime.now(timezone.utc).isoformat())
                                         .replace("Z", "+00:00"))
        cutoff = (current - timedelta(days=retention_days)).isoformat()
        rows = self.conn.execute(
            "SELECT evidence_id,artifact_path FROM evidence_v2 "
            "WHERE datetime(created_at) < datetime(?)", (cutoff,)
        ).fetchall()
        paths = sorted({row["artifact_path"] for row in rows})
        if dry_run:
            return {"records": len(rows), "files": len(paths), "cutoff": cutoff,
                    "dry_run": True}
        ids = [row["evidence_id"] for row in rows]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            self.conn.execute(f"DELETE FROM evidence_v2 WHERE evidence_id IN ({placeholders})", ids)
            self.conn.commit()
        removed = 0
        for path in paths:
            referenced = self.conn.execute(
                "SELECT 1 FROM evidence_v2 WHERE artifact_path=? LIMIT 1", (path,)
            ).fetchone()
            if not referenced:
                artifact = Path(path)
                if artifact.exists():
                    artifact.unlink()
                    removed += 1
        return {"records": len(rows), "files": removed, "cutoff": cutoff,
                "dry_run": False}

    def record_observations(self, run_id: str, observations: list[Observation]) -> None:
        rows = []
        for item in observations:
            for name, value in item.fields.items():
                rows.append((run_id, item.canonical_id, name,
                             json.dumps(value, ensure_ascii=False), item.source_id,
                             item.source_kind, item.observed_at, item.source_url))
        self.conn.executemany(
            """INSERT INTO field_observations_v2
               (run_id, canonical_id, field, value_json, source_id,
                source_kind, observed_at, source_url)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", rows,
        )
        self.conn.commit()

    def record_decisions(self, run_id: str, decisions: list[FieldDecision]) -> None:
        self.conn.executemany(
            """INSERT INTO field_decisions_v2
               (run_id, canonical_id, field, value_json, source_id,
                source_kind, reason, observed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(run_id, d.canonical_id, d.field, json.dumps(d.value, ensure_ascii=False),
              d.source_id, d.source_kind, d.reason, d.observed_at) for d in decisions],
        )
        self.conn.commit()

    def record_identity_reviews(self, run_id: str, reviews: list, created_at: str) -> None:
        self.conn.executemany(
            """INSERT INTO review_items_v2
               (review_id, run_id, canonical_id, field, reason, status, details_json, created_at)
               VALUES (?, ?, ?, 'identity', ?, 'open', ?, ?)""",
            [(uuid4().hex, run_id, f"{item.provider_id}/{item.product_ids[0]}",
              item.reason, json.dumps({
                  "provider_id": item.provider_id,
                  "display_name": item.display_name,
                  "product_ids": list(item.product_ids),
              }, ensure_ascii=False), created_at) for item in reviews],
        )
        self.conn.commit()

    def record_review_items(self, run_id: str, reviews: list[ReviewItem], created_at: str) -> int:
        inserted = 0
        for item in reviews:
            details_json = json.dumps(item.details, ensure_ascii=False, sort_keys=True)
            duplicate = self.conn.execute(
                """SELECT 1 FROM review_items_v2
                   WHERE status='open' AND canonical_id=? AND field=? AND reason=?
                     AND details_json=? LIMIT 1""",
                (item.canonical_id, item.field, item.reason, details_json),
            ).fetchone()
            if duplicate:
                continue
            self.conn.execute(
                """INSERT INTO review_items_v2
                   (review_id, run_id, canonical_id, field, reason, status, details_json, created_at)
                   VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
                (uuid4().hex, run_id, item.canonical_id, item.field, item.reason,
                details_json, created_at),
            )
            inserted += 1
        self.conn.commit()
        return inserted

    def stage_release(self, release_id: str, run_id: str, catalog: dict, created_at: str) -> str:
        payload = canonical_json(catalog)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.conn.execute(
            """INSERT INTO releases_v2
               (release_id, run_id, status, checksum, catalog_json, created_at)
               VALUES (?, ?, 'candidate', ?, ?, ?)""",
            (release_id, run_id, digest, payload, created_at),
        )
        self.conn.commit()
        return digest

    def publish_release(self, release_id: str, published_at: str) -> None:
        self.conn.execute(
            "UPDATE releases_v2 SET status='published', published_at=? WHERE release_id=?",
            (published_at, release_id),
        )
        self.conn.commit()

    def last_catalog(self) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT catalog_json FROM releases_v2 WHERE status='published' "
            "ORDER BY published_at DESC LIMIT 1"
        ).fetchone()
        return json.loads(row["catalog_json"]) if row else None

    def record_changes(self, release_id: str, changes: list[dict], created_at: str) -> None:
        self.conn.executemany(
            """INSERT INTO release_changes_v2
               (release_id, canonical_id, field, old_value_json, new_value_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            [(release_id, c["canonical_id"], c["field"],
              json.dumps(c.get("old"), ensure_ascii=False),
              json.dumps(c.get("new"), ensure_ascii=False), created_at) for c in changes],
        )
        self.conn.commit()

    def list_releases(self, limit: int = 30) -> list[dict]:
        return [dict(row) for row in self.conn.execute(
            """SELECT release_id,run_id,status,checksum,created_at,published_at
               FROM releases_v2 ORDER BY created_at DESC LIMIT ?""", (limit,)
        ).fetchall()]

    def mark_release_current(self, release_id: str, published_at: str) -> None:
        row = self.conn.execute(
            "SELECT 1 FROM releases_v2 WHERE release_id=?", (release_id,)
        ).fetchone()
        if not row:
            raise KeyError(f"release not found: {release_id}")
        with self.conn:
            self.conn.execute(
                "UPDATE releases_v2 SET status='superseded' WHERE status='published'"
            )
            self.conn.execute(
                "UPDATE releases_v2 SET status='published',published_at=? WHERE release_id=?",
                (published_at, release_id),
            )

    def record_alert(self, run_id: Optional[str], severity: str, code: str,
                     message: str, details: dict, created_at: str,
                     delivery_status: str = "pending", delivery_error: str = "") -> str:
        alert_id = uuid4().hex
        self.conn.execute(
            """INSERT INTO alerts_v2
               (alert_id,run_id,severity,code,message,details_json,
                delivery_status,delivery_error,created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (alert_id, run_id, severity, code, message,
             json.dumps(details, ensure_ascii=False), delivery_status,
             delivery_error, created_at),
        )
        self.conn.commit()
        return alert_id

    def list_alerts(self, limit: int = 50) -> list[dict]:
        result = []
        for row in self.conn.execute(
            "SELECT * FROM alerts_v2 ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall():
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    def latest_status(self) -> dict:
        run = self.conn.execute(
            "SELECT * FROM runs_v2 ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        if not run:
            return {"schema_version": "2.0", "status": "never_run"}
        result = dict(run)
        result["summary"] = json.loads(result.pop("summary_json") or "{}")
        result["sources"] = [dict(row) for row in self.conn.execute(
            "SELECT source_id,status,product_count,duration_ms,error "
            "FROM source_runs_v2 WHERE run_id=? ORDER BY source_id", (run["run_id"],)
        ).fetchall()]
        release = self.conn.execute(
            "SELECT release_id,status,checksum,published_at FROM releases_v2 "
            "WHERE run_id=? ORDER BY created_at DESC LIMIT 1", (run["run_id"],)
        ).fetchone()
        result["release"] = dict(release) if release else None
        result["open_reviews"] = self.conn.execute(
            "SELECT COUNT(*) FROM review_items_v2 WHERE status='open'"
        ).fetchone()[0]
        return result

    def list_reviews(self, status: str = "open") -> list[dict]:
        rows = self.conn.execute(
            """SELECT review_id,run_id,canonical_id,field,reason,status,details_json,
                      created_at,resolved_at,resolution_json
               FROM review_items_v2 WHERE status=? ORDER BY created_at,review_id""",
            (status,),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["details"] = json.loads(item.pop("details_json") or "{}")
            item["resolution"] = json.loads(item.pop("resolution_json") or "null")
            result.append(item)
        return result

    def get_review(self, review_id: str) -> Optional[dict]:
        row = self.conn.execute(
            "SELECT * FROM review_items_v2 WHERE review_id=?", (review_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["details"] = json.loads(item.pop("details_json") or "{}")
        item["resolution"] = json.loads(item.pop("resolution_json") or "null")
        return item

    def approve_review(self, review_id: str, approved_at: str,
                       accept_baseline: bool = False, actor: str = "unknown",
                       reason: str = "") -> dict:
        review = self.get_review(review_id)
        if not review:
            raise KeyError(f"review not found: {review_id}")
        if review["status"] != "open":
            raise ValueError(f"review is already {review['status']}")
        details = review["details"]
        resolution = {"action": "approved", "actor": actor, "reason": reason,
                      "accept_baseline": accept_baseline}
        with self.conn:
            self.conn.execute(
                """UPDATE review_items_v2
                   SET status='approved',resolved_at=?,resolution_json=? WHERE review_id=?""",
                (approved_at, json.dumps(resolution, ensure_ascii=False), review_id),
            )
            if accept_baseline:
                if "candidate" not in details:
                    raise ValueError("review does not contain a candidate field value")
                self.conn.execute(
                    """INSERT INTO accepted_field_baselines_v2
                       (canonical_id,field,value_json,currency,unit,review_id,approved_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(canonical_id,field) DO UPDATE SET
                         value_json=excluded.value_json,
                         currency=excluded.currency,
                         unit=excluded.unit,
                         review_id=excluded.review_id,
                         approved_at=excluded.approved_at""",
                    (review["canonical_id"], review["field"],
                     json.dumps(details["candidate"], ensure_ascii=False),
                     details.get("currency"), details.get("unit"), review_id, approved_at),
                )
        return self.get_review(review_id)

    def reject_review(self, review_id: str, rejected_at: str = "",
                      actor: str = "unknown", reason: str = "") -> dict:
        review = self.get_review(review_id)
        if not review:
            raise KeyError(f"review not found: {review_id}")
        if review["status"] != "open":
            raise ValueError(f"review is already {review['status']}")
        resolution = {"action": "rejected", "actor": actor, "reason": reason}
        self.conn.execute(
            """UPDATE review_items_v2
               SET status='rejected',resolved_at=?,resolution_json=? WHERE review_id=?""",
            (rejected_at, json.dumps(resolution, ensure_ascii=False), review_id),
        )
        self.conn.commit()
        return self.get_review(review_id)

    def accepted_baselines(self) -> dict[tuple[str, str], dict]:
        result = {}
        for row in self.conn.execute("SELECT * FROM accepted_field_baselines_v2").fetchall():
            item = dict(row)
            item["value"] = json.loads(item.pop("value_json"))
            result[(item["canonical_id"], item["field"])] = item
        return result
