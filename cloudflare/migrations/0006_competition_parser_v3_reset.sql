-- Early live-competition snapshots were collected before the right-aligned numeric parser
-- was validated. Remove only that experimental competition history so incorrect quota /
-- applicant column assignments cannot enter later trend calculations.
DELETE FROM competition_rows
 WHERE snapshot_id IN (SELECT id FROM competition_snapshots WHERE provider = 'UWAY_APPLY');

DELETE FROM competition_snapshots WHERE provider = 'UWAY_APPLY';

UPDATE competition_targets
   SET last_attempt_at = NULL,
       last_success_at = NULL,
       last_source_updated_at = NULL,
       last_content_hash = NULL,
       learned_refresh_minutes = NULL,
       learned_refresh_source = NULL,
       last_error = NULL,
       consecutive_failures = 0,
       updated_at = datetime('now')
 WHERE provider = 'UWAY_APPLY';

-- JINHAK targets now intentionally wait for a user-browser observation. Clear stale errors
-- left by the retired server-fetch implementation; these were not current failures.
UPDATE competition_targets
   SET last_error = NULL,
       consecutive_failures = 0,
       updated_at = datetime('now')
 WHERE provider = 'JINHAK_APPLY';
