from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from scripts.pipeline_v3.models import ModelOffer, Plan


def canonical_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def checksum(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


class V3Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        self.connection.executescript(schema)

    def close(self):
        self.connection.close()

    @contextmanager
    def transaction(self):
        try:
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def start_run(self, run_id: str, started_at: str, profile: str):
        self.connection.execute(
            "INSERT INTO pipeline_runs(run_id, started_at, status, source) VALUES(?,?,?,?)",
            (run_id, started_at, "running", profile),
        )
        self.connection.commit()

    def finish_run(self, run_id: str, finished_at: str, status: str,
                   record_count: int = 0, plan_count: int = 0,
                   release_id: str | None = None, error_code: str | None = None,
                   error_message: str | None = None, summary: dict | None = None):
        self.connection.execute(
            """UPDATE pipeline_runs SET finished_at=?, status=?, record_count=?,
               plan_count=?, published_release_id=?, error_code=?, error_message=?,
               summary_json=? WHERE run_id=?""",
            (finished_at, status, record_count, plan_count, release_id, error_code,
             error_message, canonical_json(summary or {}), run_id),
        )
        self.connection.commit()

    def save_source_snapshot(self, *, snapshot_id: str, run_id: str, source: str,
                             fetched_at: str, source_url: str, http_status: int,
                             raw_path: str, raw: bytes, etag: str | None = None,
                             last_modified: str | None = None):
        self.connection.execute(
            """INSERT INTO source_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (snapshot_id, run_id, source, fetched_at, source_url, http_status,
             etag, last_modified, checksum(raw), len(raw), raw_path),
        )
        self.connection.commit()

    def save_catalog_snapshot(self, *, snapshot_id: str, run_id: str,
                              created_at: str, catalog: dict,
                              offers: Iterable[ModelOffer], plans: Iterable[Plan]):
        offers = list(offers)
        plans = list(plans)
        serialized = canonical_json(catalog)
        provider_count = len({x.provider_id for x in [*offers, *plans]})
        with self.transaction() as connection:
            connection.execute(
                """INSERT INTO catalog_snapshots VALUES(?,?,?,?,?,?,?,?,?)""",
                (snapshot_id, run_id, created_at, catalog["schema_version"],
                 checksum(serialized), provider_count, len(offers), len(plans), serialized),
            )
            offer_rows = [_offer_row(snapshot_id, offer) for offer in offers]
            if offer_rows:
                placeholders = ",".join("?" for _ in offer_rows[0])
                connection.executemany(
                    f"INSERT INTO model_offers VALUES({placeholders})", offer_rows)
            plan_rows = [_plan_row(snapshot_id, plan) for plan in plans]
            if plan_rows:
                placeholders = ",".join("?" for _ in plan_rows[0])
                connection.executemany(
                    f"INSERT INTO plans VALUES({placeholders})", plan_rows)

    def save_release(self, release_id: str, snapshot_id: str, created_at: str,
                     published_at: str, catalog_checksum: str,
                     catalog_path: str, status_path: str):
        self.connection.execute(
            "INSERT INTO releases VALUES(?,?,?,?,?,?,?,?)",
            (release_id, snapshot_id, created_at, published_at, "published",
             catalog_checksum, catalog_path, status_path),
        )
        self.connection.execute(
            "UPDATE releases SET status='superseded' WHERE release_id<>? AND status='published'",
            (release_id,),
        )
        self.connection.commit()

    def latest_published_counts(self) -> tuple[int, int] | None:
        row = self.connection.execute(
            """SELECT c.model_count, c.plan_count FROM releases r
               JOIN catalog_snapshots c ON c.snapshot_id=r.snapshot_id
               ORDER BY r.published_at DESC LIMIT 1"""
        ).fetchone()
        return (row[0], row[1]) if row else None

    def latest_status(self) -> dict:
        row = self.connection.execute(
            "SELECT * FROM pipeline_runs ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else {}


def _offer_row(snapshot_id: str, item: ModelOffer) -> tuple:
    return (
        snapshot_id, item.offer_id, item.modelsdev_provider_id, item.provider_id,
        item.provider_name, item.model_id, item.model_name, item.region,
        item.service_tier, item.currency, item.price_unit, item.input_per_1m,
        item.output_per_1m, item.cache_read_per_1m, item.cache_write_per_1m,
        item.context_window, item.max_output_tokens, canonical_json(item.modalities),
        item.knowledge_cutoff, item.release_date, item.source_url,
        item.source_updated_at, item.fetched_at, canonical_json(item.raw),
    )


def _plan_row(snapshot_id: str, item: Plan) -> tuple:
    content = canonical_json(item.raw)
    return (
        snapshot_id, item.plan_id, item.provider_id, item.provider_name,
        item.product_name, item.plan_category, item.billing_type, int(item.is_free),
        item.price_amount, item.currency, item.billing_cadence,
        item.monthly_equivalent, item.first_period_price, item.included_quota,
        item.quota_unit, item.quota_period, canonical_json(item.features),
        canonical_json(item.supported_models), item.purchase_url, item.source_url,
        item.source_kind, item.source_updated_at, item.fetched_at, checksum(content),
        content, int(item.featured_on_home),
    )
