PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs_v2 (
  run_id TEXT PRIMARY KEY,
  profile TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status TEXT NOT NULL,
  error TEXT,
  summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS source_runs_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  status TEXT NOT NULL,
  product_count INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  error TEXT,
  UNIQUE(run_id, source_id),
  FOREIGN KEY(run_id) REFERENCES runs_v2(run_id)
);

CREATE TABLE IF NOT EXISTS field_observations_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  canonical_id TEXT NOT NULL,
  field TEXT NOT NULL,
  value_json TEXT,
  source_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  source_url TEXT,
  FOREIGN KEY(run_id) REFERENCES runs_v2(run_id)
);

CREATE TABLE IF NOT EXISTS field_decisions_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  canonical_id TEXT NOT NULL,
  field TEXT NOT NULL,
  value_json TEXT,
  source_id TEXT NOT NULL,
  source_kind TEXT NOT NULL,
  reason TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs_v2(run_id)
);

CREATE TABLE IF NOT EXISTS review_items_v2 (
  review_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  canonical_id TEXT,
  field TEXT,
  reason TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  details_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_json TEXT,
  FOREIGN KEY(run_id) REFERENCES runs_v2(run_id)
);

CREATE TABLE IF NOT EXISTS accepted_field_baselines_v2 (
  canonical_id TEXT NOT NULL,
  field TEXT NOT NULL,
  value_json TEXT NOT NULL,
  currency TEXT,
  unit TEXT,
  review_id TEXT NOT NULL,
  approved_at TEXT NOT NULL,
  PRIMARY KEY(canonical_id, field),
  FOREIGN KEY(review_id) REFERENCES review_items_v2(review_id)
);

CREATE TABLE IF NOT EXISTS releases_v2 (
  release_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  status TEXT NOT NULL,
  checksum TEXT NOT NULL,
  catalog_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  published_at TEXT,
  FOREIGN KEY(run_id) REFERENCES runs_v2(run_id)
);

CREATE TABLE IF NOT EXISTS release_changes_v2 (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  release_id TEXT NOT NULL,
  canonical_id TEXT NOT NULL,
  field TEXT NOT NULL,
  old_value_json TEXT,
  new_value_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(release_id) REFERENCES releases_v2(release_id)
);

CREATE TABLE IF NOT EXISTS alerts_v2 (
  alert_id TEXT PRIMARY KEY,
  run_id TEXT,
  severity TEXT NOT NULL,
  code TEXT NOT NULL,
  message TEXT NOT NULL,
  details_json TEXT NOT NULL DEFAULT '{}',
  delivery_status TEXT NOT NULL DEFAULT 'pending',
  delivery_error TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY(run_id) REFERENCES runs_v2(run_id)
);

CREATE TABLE IF NOT EXISTS evidence_v2 (
  evidence_id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  artifact_kind TEXT NOT NULL,
  content_type TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  artifact_path TEXT NOT NULL,
  byte_size INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(run_id, source_id, sha256),
  FOREIGN KEY(run_id) REFERENCES runs_v2(run_id)
);

CREATE INDEX IF NOT EXISTS idx_v2_observation_product ON field_observations_v2(canonical_id, field);
CREATE INDEX IF NOT EXISTS idx_v2_decision_product ON field_decisions_v2(canonical_id, field);
CREATE INDEX IF NOT EXISTS idx_v2_release_published ON releases_v2(published_at);
CREATE INDEX IF NOT EXISTS idx_v2_review_status ON review_items_v2(status, created_at);
CREATE INDEX IF NOT EXISTS idx_v2_alert_created ON alerts_v2(created_at);
CREATE INDEX IF NOT EXISTS idx_v2_evidence_hash ON evidence_v2(sha256);
CREATE INDEX IF NOT EXISTS idx_v2_evidence_run ON evidence_v2(run_id, source_id);
