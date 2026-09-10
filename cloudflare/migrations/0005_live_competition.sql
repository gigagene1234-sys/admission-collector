PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS competition_targets (
  target_id TEXT PRIMARY KEY,
  university TEXT NOT NULL,
  provider TEXT NOT NULL,
  aliases_json TEXT NOT NULL DEFAULT '[]',
  configured_source_url TEXT,
  discovery_url TEXT,
  resolved_source_url TEXT,
  configured_refresh_minutes INTEGER NOT NULL DEFAULT 10,
  configured_refresh_source TEXT NOT NULL DEFAULT 'ADAPTIVE_DEFAULT',
  learned_refresh_minutes INTEGER,
  learned_refresh_source TEXT,
  last_attempt_at TEXT,
  last_success_at TEXT,
  last_source_updated_at TEXT,
  last_content_hash TEXT,
  consecutive_failures INTEGER NOT NULL DEFAULT 0,
  last_error TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_competition_targets_provider
  ON competition_targets(provider, target_id);

CREATE TABLE IF NOT EXISTS competition_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  target_id TEXT NOT NULL,
  university TEXT NOT NULL,
  provider TEXT NOT NULL,
  source_url TEXT NOT NULL,
  source_updated_at TEXT,
  collected_at TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  page_title TEXT,
  row_count INTEGER NOT NULL DEFAULT 0,
  FOREIGN KEY (target_id) REFERENCES competition_targets(target_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_competition_snapshots_target_time
  ON competition_snapshots(target_id, id DESC);

CREATE INDEX IF NOT EXISTS idx_competition_snapshots_source_time
  ON competition_snapshots(target_id, source_updated_at);

CREATE TABLE IF NOT EXISTS competition_rows (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  snapshot_id INTEGER NOT NULL,
  target_id TEXT NOT NULL,
  university TEXT NOT NULL,
  admission TEXT,
  department TEXT,
  quota INTEGER,
  applicants INTEGER,
  ratio REAL,
  cells_json TEXT NOT NULL DEFAULT '[]',
  row_ordinal INTEGER NOT NULL,
  FOREIGN KEY (snapshot_id) REFERENCES competition_snapshots(id) ON DELETE CASCADE,
  FOREIGN KEY (target_id) REFERENCES competition_targets(target_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_competition_rows_snapshot
  ON competition_rows(snapshot_id, row_ordinal);

CREATE INDEX IF NOT EXISTS idx_competition_rows_target_department
  ON competition_rows(target_id, department);
