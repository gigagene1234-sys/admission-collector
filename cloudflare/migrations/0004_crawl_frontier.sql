CREATE TABLE IF NOT EXISTS crawl_frontier (
  task_id TEXT PRIMARY KEY,
  provider TEXT NOT NULL,
  url TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  source_safe_path TEXT,
  state TEXT NOT NULL DEFAULT 'pending',
  priority INTEGER NOT NULL DEFAULT 100,
  public_fetch_eligible INTEGER NOT NULL DEFAULT 0,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  lease_owner TEXT,
  lease_expires_at TEXT,
  error_type TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(provider, url_hash)
);
CREATE INDEX IF NOT EXISTS idx_crawl_frontier_claim ON crawl_frontier(provider,state,priority,updated_at);
CREATE INDEX IF NOT EXISTS idx_crawl_frontier_public ON crawl_frontier(provider,public_fetch_eligible,state,updated_at);

CREATE TABLE IF NOT EXISTS public_page_snapshots (
  provider TEXT NOT NULL,
  url_hash TEXT NOT NULL,
  url TEXT NOT NULL,
  status_code INTEGER,
  content_type TEXT,
  title TEXT,
  body_hash TEXT,
  discovered_links_json TEXT NOT NULL DEFAULT '[]',
  observed_at TEXT NOT NULL,
  PRIMARY KEY(provider, url_hash)
);
