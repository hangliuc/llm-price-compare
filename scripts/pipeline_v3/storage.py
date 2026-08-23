from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from scripts.pipeline_v3.models import ModelOffer, Plan


OFFER_COLUMNS = (
    "snapshot_id", "offer_id", "modelsdev_provider_id", "provider_id", "provider_name",
    "model_id", "model_name", "region", "service_tier", "currency", "price_unit",
    "input_per_1m", "output_per_1m", "cache_read_per_1m", "cache_write_per_1m",
    "context_window", "max_output_tokens", "modalities_json", "knowledge_cutoff",
    "release_date", "source_url", "source_updated_at", "fetched_at", "raw_json",
    "market", "access_channel", "pricing_condition", "source_id", "comparison_currency",
    "comparison_fx_rate", "comparison_fx_date", "comparison_input_per_1m",
    "comparison_output_per_1m", "comparison_cache_read_per_1m",
    "comparison_cache_write_per_1m",
)
PLAN_COLUMNS = (
    "snapshot_id", "plan_id", "provider_id", "provider_name", "product_name",
    "plan_category", "billing_type", "is_free", "price_amount", "currency",
    "billing_cadence", "monthly_equivalent", "first_period_price", "included_quota",
    "quota_unit", "quota_period", "features_json", "supported_models_json", "purchase_url",
    "source_url", "source_kind", "source_updated_at", "fetched_at", "content_checksum",
    "raw_json", "featured_on_home", "market", "seat_type", "minimum_seats", "price_status",
    "price_scope", "comparison_currency", "comparison_fx_rate", "comparison_fx_date",
    "comparison_monthly_amount",
)
from scripts.pipeline_v3.fx import FxSnapshot


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
        self._migrate_v31_columns()
        # This index must be created after the additive migration: an existing
        # V3.0 `model_offers` table has no `market` column when `CREATE TABLE
        # IF NOT EXISTS` runs above.
        self.connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_offers_market ON model_offers(snapshot_id, market)"
        )
        self.connection.commit()

    def _migrate_v31_columns(self):
        """Additive migration for V3 databases created before schema 3.1."""
        additions = {
            "model_offers": [
                ("market", "TEXT NOT NULL DEFAULT 'global'"),
                ("access_channel", "TEXT NOT NULL DEFAULT 'unspecified_endpoint'"),
                ("pricing_condition", "TEXT NOT NULL DEFAULT 'standard'"),
                ("source_id", "TEXT NOT NULL DEFAULT 'models_dev'"),
                ("comparison_currency", "TEXT NOT NULL DEFAULT 'CNY'"),
                ("comparison_fx_rate", "REAL"),
                ("comparison_fx_date", "TEXT"),
                ("comparison_input_per_1m", "REAL"),
                ("comparison_output_per_1m", "REAL"),
                ("comparison_cache_read_per_1m", "REAL"),
                ("comparison_cache_write_per_1m", "REAL"),
            ],
            "plans": [
                ("market", "TEXT NOT NULL DEFAULT 'global'"),
                ("seat_type", "TEXT"),
                ("minimum_seats", "INTEGER"),
                ("price_status", "TEXT NOT NULL DEFAULT 'priced'"),
                ("price_scope", "TEXT NOT NULL DEFAULT 'per_account'"),
                ("comparison_currency", "TEXT"),
                ("comparison_fx_rate", "REAL"),
                ("comparison_fx_date", "TEXT"),
                ("comparison_monthly_amount", "REAL"),
            ],
        }
        for table, columns in additions.items():
            existing = {row[1] for row in self.connection.execute(f"PRAGMA table_info({table})")}
            for name, declaration in columns:
                if name not in existing:
                    self.connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")
        self.connection.commit()

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

    def save_fx_snapshot(self, *, run_id: str, snapshot: FxSnapshot):
        self.connection.execute(
            """INSERT OR REPLACE INTO fx_snapshots
               (fx_snapshot_id, run_id, base_currency, rates_json, source_url,
                published_date, fetched_at, checksum) VALUES(?,?,?,?,?,?,?,?)""",
            (snapshot.snapshot_id, run_id, snapshot.base_currency,
             canonical_json(snapshot.rates_to_cny), snapshot.source_url,
             snapshot.published_date, snapshot.fetched_at, checksum(snapshot.raw)),
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
                    f"INSERT INTO model_offers ({','.join(OFFER_COLUMNS)}) VALUES({placeholders})", offer_rows)
            plan_rows = [_plan_row(snapshot_id, plan) for plan in plans]
            if plan_rows:
                placeholders = ",".join("?" for _ in plan_rows[0])
                connection.executemany(
                    f"INSERT INTO plans ({','.join(PLAN_COLUMNS)}) VALUES({placeholders})", plan_rows)

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

    def latest_published_plans_for_source(self, source_url: str) -> list[Plan]:
        """Return a source's last published, validated plans.

        This is deliberately scoped to one *official source URL*.  A temporary
        WAF/network failure may reuse that source's last known good records,
        but it can never borrow data from a different provider or source.
        Without a previously published source snapshot the caller must fail
        closed instead of publishing an incomplete catalog.
        """
        row = self.connection.execute(
            """SELECT c.catalog_json FROM releases r
               JOIN catalog_snapshots c ON c.snapshot_id=r.snapshot_id
               WHERE r.status='published'
               ORDER BY r.published_at DESC LIMIT 1"""
        ).fetchone()
        if not row:
            return []
        catalog = json.loads(row[0])
        plans: list[Plan] = []
        for record in catalog.get("plans", []):
            if record.get("source_url") != source_url:
                continue
            payload = dict(record)
            payload["features"] = tuple(payload.get("features") or ())
            payload["supported_models"] = tuple(payload.get("supported_models") or ())
            plans.append(Plan(**payload))
        return plans

    @staticmethod
    def published_catalog_offers(catalog_path: Path) -> list[ModelOffer]:
        """Load the last served offers for safe source-degradation fallback."""
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        allowed = set(ModelOffer.__dataclass_fields__)
        offers: list[ModelOffer] = []
        for record in catalog.get("model_offers", []):
            payload = dict(record)
            payload["modalities"] = tuple(payload.get("modalities") or ())
            try:
                offers.append(ModelOffer(**{key: value for key, value in payload.items() if key in allowed}))
            except TypeError:
                continue
        return offers

    @staticmethod
    def published_catalog_plans_for_source(catalog_path: Path, source_url: str) -> list[Plan]:
        """Load a source-scoped Last Known Good set from the public artifact.

        The SQLite release history is authoritative during normal operation.
        This narrow fallback exists for the first V3.1 publication after a
        database migration, or after a recoverable database rebuild: the
        currently served catalog is itself a previously published artifact.
        It never accepts arbitrary local JSON, never mixes source URLs, and
        returns no records if the published artifact cannot be read.
        """
        try:
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        plans: list[Plan] = []
        for record in catalog.get("plans", []):
            if record.get("source_url") != source_url:
                continue
            payload = dict(record)
            payload["features"] = tuple(payload.get("features") or ())
            payload["supported_models"] = tuple(payload.get("supported_models") or ())
            allowed = set(Plan.__dataclass_fields__)
            try:
                plans.append(Plan(**{key: value for key, value in payload.items() if key in allowed}))
            except TypeError:
                # A malformed legacy record must not silently become a price.
                continue
        return plans

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
        item.market, item.access_channel, item.pricing_condition, item.source_id,
        item.comparison_currency, item.comparison_fx_rate, item.comparison_fx_date,
        item.comparison_input_per_1m, item.comparison_output_per_1m,
        item.comparison_cache_read_per_1m, item.comparison_cache_write_per_1m,
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
        content, int(item.featured_on_home), item.market, item.seat_type,
        item.minimum_seats, item.price_status, item.price_scope,
        item.comparison_currency, item.comparison_fx_rate, item.comparison_fx_date,
        item.comparison_monthly_amount,
    )
