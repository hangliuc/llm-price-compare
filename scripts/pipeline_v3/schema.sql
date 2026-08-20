PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS pipeline_runs (
  run_id TEXT PRIMARY KEY,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  source TEXT NOT NULL,
  source_http_status INTEGER,
  record_count INTEGER,
  plan_count INTEGER,
  published_release_id TEXT,
  error_code TEXT,
  error_message TEXT,
  summary_json TEXT
);

CREATE TABLE IF NOT EXISTS source_snapshots (
  source_snapshot_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  source TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  source_url TEXT NOT NULL,
  http_status INTEGER NOT NULL,
  etag TEXT,
  last_modified TEXT,
  checksum TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  raw_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_snapshots (
  snapshot_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  created_at TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  checksum TEXT NOT NULL,
  provider_count INTEGER NOT NULL,
  model_count INTEGER NOT NULL,
  plan_count INTEGER NOT NULL,
  catalog_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_offers (
  snapshot_id TEXT NOT NULL REFERENCES catalog_snapshots(snapshot_id),
  offer_id TEXT NOT NULL,
  modelsdev_provider_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  provider_name TEXT NOT NULL,
  model_id TEXT NOT NULL,
  model_name TEXT NOT NULL,
  region TEXT NOT NULL,
  service_tier TEXT NOT NULL,
  currency TEXT NOT NULL,
  price_unit TEXT NOT NULL,
  input_per_1m REAL,
  output_per_1m REAL,
  cache_read_per_1m REAL,
  cache_write_per_1m REAL,
  context_window INTEGER,
  max_output_tokens INTEGER,
  modalities_json TEXT,
  knowledge_cutoff TEXT,
  release_date TEXT,
  source_url TEXT NOT NULL,
  source_updated_at TEXT,
  fetched_at TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  market TEXT NOT NULL DEFAULT 'global',
  access_channel TEXT NOT NULL DEFAULT 'unspecified_endpoint',
  pricing_condition TEXT NOT NULL DEFAULT 'standard',
  source_id TEXT NOT NULL DEFAULT 'models_dev',
  comparison_currency TEXT NOT NULL DEFAULT 'CNY',
  comparison_fx_rate REAL,
  comparison_fx_date TEXT,
  comparison_input_per_1m REAL,
  comparison_output_per_1m REAL,
  comparison_cache_read_per_1m REAL,
  comparison_cache_write_per_1m REAL,
  PRIMARY KEY (snapshot_id, offer_id)
);

CREATE TABLE IF NOT EXISTS plans (
  snapshot_id TEXT NOT NULL REFERENCES catalog_snapshots(snapshot_id),
  plan_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  provider_name TEXT NOT NULL,
  product_name TEXT NOT NULL,
  plan_category TEXT NOT NULL,
  billing_type TEXT NOT NULL,
  is_free INTEGER NOT NULL,
  price_amount REAL,
  currency TEXT NOT NULL,
  billing_cadence TEXT NOT NULL,
  monthly_equivalent REAL,
  first_period_price REAL,
  included_quota REAL,
  quota_unit TEXT,
  quota_period TEXT,
  features_json TEXT,
  supported_models_json TEXT,
  purchase_url TEXT,
  source_url TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  source_updated_at TEXT,
  fetched_at TEXT NOT NULL,
  content_checksum TEXT NOT NULL,
  raw_json TEXT NOT NULL,
  featured_on_home INTEGER NOT NULL DEFAULT 0,
  market TEXT NOT NULL DEFAULT 'global',
  seat_type TEXT,
  minimum_seats INTEGER,
  price_status TEXT NOT NULL DEFAULT 'priced',
  price_scope TEXT NOT NULL DEFAULT 'per_account',
  comparison_currency TEXT,
  comparison_fx_rate REAL,
  comparison_fx_date TEXT,
  comparison_monthly_amount REAL,
  PRIMARY KEY (snapshot_id, plan_id)
);

CREATE TABLE IF NOT EXISTS fx_snapshots (
  fx_snapshot_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES pipeline_runs(run_id),
  base_currency TEXT NOT NULL,
  rates_json TEXT NOT NULL,
  source_url TEXT NOT NULL,
  published_date TEXT NOT NULL,
  fetched_at TEXT NOT NULL,
  checksum TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS releases (
  release_id TEXT PRIMARY KEY,
  snapshot_id TEXT NOT NULL REFERENCES catalog_snapshots(snapshot_id),
  created_at TEXT NOT NULL,
  published_at TEXT,
  status TEXT NOT NULL,
  checksum TEXT NOT NULL,
  catalog_path TEXT NOT NULL,
  status_path TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_runs_started_at ON pipeline_runs(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_offers_provider ON model_offers(snapshot_id, provider_id);
CREATE INDEX IF NOT EXISTS idx_plans_provider ON plans(snapshot_id, provider_id);
CREATE INDEX IF NOT EXISTS idx_offers_market ON model_offers(snapshot_id, market);
