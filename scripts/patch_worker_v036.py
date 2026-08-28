from pathlib import Path

P = Path(__file__).resolve().parents[1] / 'cloudflare/src/index.js'
text = P.read_text()


def once(old, new, label):
    global text
    if new in text:
        return
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 match, found {n}')
    text = text.replace(old, new, 1)


once(
'''const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};
''',
'''const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

// Persistent upstream 5xx pages should not be hammered every time the Android app resumes.
// They become retryable again after this cooldown while the run itself remains active.
const SERVER_ERROR_RETRY_COOLDOWN_MS = 6 * 60 * 60 * 1000;
''',
'cooldown constant')

once('version: "0.3.3"', 'version: "0.3.6"', 'health version')

once(
'      return json({ error: "internal_error", message: String(error?.message || error) }, 500);',
'      return json({ error: "internal_error" }, 500);',
'generic production error')

once(
'''    SELECT page_number, state, retry_count, error_type
    FROM run_pages
''',
'''    SELECT page_number, state, retry_count, error_type, updated_at
    FROM run_pages
''',
'resume select updated_at')

once(
'''  const missing = [];
  const retry = [];

  for (let page = 1; page <= totalPages; page += 1) {
''',
'''  const missing = [];
  const retry = [];
  const deferred = [];
  const nowMs = Date.now();

  for (let page = 1; page <= totalPages; page += 1) {
''',
'deferred accumulator')

once(
'''    if (row.state !== "completed" && retry.length < limit) {
      retry.push({
        page,
        state: row.state,
        retryCount: Number(row.retry_count || 0),
        errorType: row.error_type || null,
      });
    }
''',
'''    if (row.state !== "completed") {
      const retryCount = Number(row.retry_count || 0);
      const errorType = row.error_type || null;
      const updatedMs = Date.parse(row.updated_at || "");
      const shouldDeferServerError =
        errorType === "server-error" &&
        retryCount >= 2 &&
        Number.isFinite(updatedMs) &&
        nowMs - updatedMs < SERVER_ERROR_RETRY_COOLDOWN_MS;

      if (shouldDeferServerError) {
        if (deferred.length < limit) {
          deferred.push({
            page,
            state: row.state,
            retryCount,
            errorType,
            retryAfter: new Date(updatedMs + SERVER_ERROR_RETRY_COOLDOWN_MS).toISOString(),
          });
        }
      } else if (retry.length < limit) {
        retry.push({
          page,
          state: row.state,
          retryCount,
          errorType,
        });
      }
    }
''',
'defer repeated server errors')

once(
'''    missing,
    retry,
    truncated: missing.length >= limit || retry.length >= limit,
''',
'''    missing,
    retry,
    deferred,
    serverErrorCooldownSeconds: Math.floor(SERVER_ERROR_RETRY_COOLDOWN_MS / 1000),
    truncated: missing.length >= limit || retry.length >= limit || deferred.length >= limit,
''',
'resume response deferred')

P.write_text(text)
print('Cloudflare v0.3.6 server-error cooldown patch applied')
