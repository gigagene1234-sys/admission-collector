PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  collector_version TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'collecting',
  completion_reason TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  uploaded_chunks INTEGER NOT NULL DEFAULT 0,
  processed_chunks INTEGER NOT NULL DEFAULT 0,
  received_records INTEGER NOT NULL DEFAULT 0,
  unique_records INTEGER NOT NULL DEFAULT 0,
  duplicate_records INTEGER NOT NULL DEFAULT 0,
  error_count INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT NOT NULL DEFAULT '{}',
  client_summary_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS processed_chunks (
  run_id TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  processed_at TEXT NOT NULL,
  PRIMARY KEY (run_id, chunk_id),
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS records (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fingerprint TEXT NOT NULL UNIQUE,
  run_id TEXT NOT NULL,
  provider TEXT,
  record_type TEXT,
  year INTEGER,
  university TEXT,
  campus TEXT,
  department TEXT,
  admission TEXT,
  metrics_json TEXT NOT NULL DEFAULT '{}',
  source_page TEXT,
  source_page_number INTEGER,
  source_row_ordinal INTEGER,
  confidence TEXT,
  raw_evidence TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_records_run_id
  ON records(run_id);

CREATE INDEX IF NOT EXISTS idx_records_university_department
  ON records(university, department);

CREATE INDEX IF NOT EXISTS idx_records_source_page_number
  ON records(source_page, source_page_number);

CREATE TABLE IF NOT EXISTS run_pages (
  run_id TEXT NOT NULL,
  family_key TEXT NOT NULL,
  requested_year INTEGER NOT NULL DEFAULT -1,
  page_number INTEGER NOT NULL,
  state TEXT NOT NULL,
  retry_count INTEGER NOT NULL DEFAULT 0,
  error_type TEXT,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (run_id, family_key, requested_year, page_number),
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_run_pages_resume
  ON run_pages(run_id, family_key, requested_year, state, page_number);

CREATE TABLE IF NOT EXISTS run_errors (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  chunk_id TEXT,
  error_type TEXT,
  page_number INTEGER,
  family_key TEXT,
  requested_year INTEGER,
  retry_count INTEGER,
  detail_json TEXT NOT NULL DEFAULT '{}',
  created_at TEXT NOT NULL,
  FOREIGN KEY (run_id) REFERENCES runs(run_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_run_errors_run
  ON run_errors(run_id, id DESC);
