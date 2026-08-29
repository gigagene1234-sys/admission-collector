const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

// Persistent upstream 5xx pages should not be hammered every time the Android app resumes.
// They become retryable again after this cooldown while the run itself remains active.
const SERVER_ERROR_RETRY_COOLDOWN_MS = 6 * 60 * 60 * 1000;

export default {
  async fetch(request, env, ctx) {
    try {
      const url = new URL(request.url);

      if (request.method === "GET" && url.pathname === "/health") {
        return json({
          ok: true,
          service: "admission-collector-offload",
          version: "0.3.8",
          time: new Date().toISOString(),
        });
      }

      if (!(await isAuthorized(request, env))) {
        return json({ error: "unauthorized" }, 401);
      }

      if (request.method === "GET" && url.pathname === "/v1/runs/latest") {
        const provider = String(url.searchParams.get("provider") || "").slice(0, 40);
        if (!provider) return json({ error: "provider is required" }, 400);
        return getLatestActiveRun(env, provider);
      }

      if (request.method === "POST" && url.pathname === "/v1/runs") {
        const body = await readJson(request, 128_000);
        return createRun(env, body);
      }

      const chunkMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)\/chunks$/);
      if (request.method === "POST" && chunkMatch) {
        const runId = decodeURIComponent(chunkMatch[1]);
        const body = await readJson(request, 1_500_000);
        validateChunk(body);

        await assertRunExists(env, runId);

        const message = {
          schemaVersion: 1,
          runId,
          enqueuedAt: new Date().toISOString(),
          chunk: body,
        };
        await env.INGEST_QUEUE.send(message);

        await env.DB.prepare(`
          UPDATE runs
          SET uploaded_chunks = uploaded_chunks + 1,
              updated_at = ?
          WHERE run_id = ?
        `).bind(new Date().toISOString(), runId).run();

        return json({
          accepted: true,
          runId,
          chunkId: body.chunkId,
        }, 202);
      }

      const finishMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)\/finish$/);
      if (request.method === "POST" && finishMatch) {
        const runId = decodeURIComponent(finishMatch[1]);
        const body = await readJson(request, 128_000);
        await assertRunExists(env, runId);

        if ((body.completionReason || "") === "completed") {
          const pending = await env.DB.prepare(`
            SELECT COUNT(*) AS pending_count
            FROM run_pages
            WHERE run_id = ? AND state != 'completed'
          `).bind(runId).first();
          const pendingCount = Number(pending?.pending_count || 0);
          if (pendingCount > 0) {
            return json({ error: "run_incomplete", runId, pendingPages: pendingCount }, 409);
          }
        }

        await env.DB.prepare(`
          UPDATE runs
          SET status = ?,
              completion_reason = ?,
              updated_at = ?,
              client_summary_json = ?
          WHERE run_id = ?
        `).bind(
          body.status || "uploaded",
          body.completionReason || null,
          new Date().toISOString(),
          JSON.stringify(body.summary || {}),
          runId
        ).run();

        return json({ ok: true, runId });
      }

      const statusMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)\/status$/);
      if (request.method === "GET" && statusMatch) {
        const runId = decodeURIComponent(statusMatch[1]);
        return getStatus(env, runId);
      }

      const pendingMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)\/pending-pages$/);
      if (request.method === "GET" && pendingMatch) {
        const runId = decodeURIComponent(pendingMatch[1]);
        const limit = boundedInt(url.searchParams.get("limit") || "500", 1, 500);
        return getPendingPages(env, runId, limit);
      }

      const planMatch = url.pathname.match(/^\/v1\/runs\/([^/]+)\/resume-plan$/);
      if (request.method === "GET" && planMatch) {
        const runId = decodeURIComponent(planMatch[1]);
        const familyKey = url.searchParams.get("familyKey") || "";
        const requestedYear = nullableInt(url.searchParams.get("requestedYear"));
        const totalPages = boundedInt(url.searchParams.get("totalPages"), 1, 5000);
        const limit = boundedInt(url.searchParams.get("limit") || "200", 1, 500);

        if (!familyKey || !totalPages) {
          return json({ error: "familyKey and totalPages are required" }, 400);
        }

        return getResumePlan(env, runId, familyKey, requestedYear, totalPages, limit);
      }

      return json({ error: "not_found" }, 404);
    } catch (error) {
      console.error(JSON.stringify({
        level: "error",
        event: "fetch_failed",
        message: String(error?.message || error),
        stack: error?.stack || null,
      }));
      return json({ error: "internal_error" }, 500);
    }
  },

  async queue(batch, env, ctx) {
    for (const message of batch.messages) {
      try {
        await processChunk(env, message.body);
      } catch (error) {
        console.error(JSON.stringify({
          level: "error",
          event: "queue_chunk_failed",
          messageId: message.id,
          message: String(error?.message || error),
          stack: error?.stack || null,
        }));
        throw error;
      }
    }
  },
};

function json(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: JSON_HEADERS,
  });
}

async function isAuthorized(request, env) {
  const token = env.INGEST_TOKEN;
  if (!token) return false;
  const header = request.headers.get("authorization") || "";
  const expected = `Bearer ${token}`;
  const encoder = new TextEncoder();
  const left = encoder.encode(header);
  const right = encoder.encode(expected);
  if (left.byteLength !== right.byteLength) return false;
  return crypto.subtle.timingSafeEqual(left, right);
}

async function readJson(request, maxBytes) {
  const contentLength = Number(request.headers.get("content-length") || 0);
  if (contentLength && contentLength > maxBytes) {
    throw new Error(`payload too large: ${contentLength}`);
  }
  const text = await request.text();
  if (new TextEncoder().encode(text).byteLength > maxBytes) {
    throw new Error("payload too large");
  }
  if (!text) return {};
  return JSON.parse(text);
}

async function getLatestActiveRun(env, provider) {
  const row = await env.DB.prepare(`
    SELECT r.run_id, r.provider, r.collector_version, r.status, r.created_at, r.updated_at,
           EXISTS(
             SELECT 1 FROM run_pages p
             WHERE p.run_id = r.run_id AND p.state != 'completed'
           ) AS has_pending
    FROM runs r
    WHERE r.provider = ?
      AND (
        r.status = 'collecting'
        OR EXISTS(
          SELECT 1 FROM run_pages p
          WHERE p.run_id = r.run_id AND p.state != 'completed'
        )
      )
    ORDER BY CASE WHEN r.status = 'collecting' THEN 0 ELSE 1 END,
             r.updated_at DESC
    LIMIT 1
  `).bind(provider).first();

  if (row && row.status !== "collecting" && Number(row.has_pending || 0) > 0) {
    const now = new Date().toISOString();
    await env.DB.prepare(`
      UPDATE runs
      SET status = 'collecting', completion_reason = NULL, updated_at = ?
      WHERE run_id = ?
    `).bind(now, row.run_id).run();
    row.status = "collecting";
    row.updated_at = now;
  }

  return json({
    runId: row?.run_id || null,
    provider: row?.provider || provider,
    collectorVersion: row?.collector_version || null,
    status: row?.status || null,
    updatedAt: row?.updated_at || null,
    recoveredPending: Number(row?.has_pending || 0) > 0,
  });
}

async function createRun(env, body) {
  const now = new Date().toISOString();
  const runId = body.runId || crypto.randomUUID();
  const provider = String(body.provider || "unknown").slice(0, 40);
  const collectorVersion = String(body.collectorVersion || "unknown").slice(0, 40);

  await env.DB.prepare(`
    INSERT INTO runs (
      run_id, provider, collector_version, status,
      created_at, updated_at, metadata_json
    ) VALUES (?, ?, ?, 'collecting', ?, ?, ?)
    ON CONFLICT(run_id) DO UPDATE SET
      updated_at = excluded.updated_at,
      metadata_json = excluded.metadata_json
  `).bind(
    runId,
    provider,
    collectorVersion,
    now,
    now,
    JSON.stringify(body.metadata || {})
  ).run();

  return json({ runId, status: "collecting" }, 201);
}

async function assertRunExists(env, runId) {
  const row = await env.DB.prepare(
    "SELECT run_id FROM runs WHERE run_id = ? LIMIT 1"
  ).bind(runId).first();

  if (!row) throw new Error(`unknown run: ${runId}`);
}

function validateChunk(body) {
  if (!body || typeof body !== "object") throw new Error("invalid chunk");
  if (!body.chunkId || typeof body.chunkId !== "string") throw new Error("chunkId is required");
  if (!Array.isArray(body.records)) throw new Error("records must be an array");
  if (body.records.length > 250) throw new Error("too many records in one chunk");
}

async function processChunk(env, envelope) {
  const { runId, chunk } = envelope || {};
  if (!runId || !chunk) throw new Error("invalid queue envelope");

  const duplicate = await env.DB.prepare(`
    SELECT 1 AS found
    FROM processed_chunks
    WHERE run_id = ? AND chunk_id = ?
    LIMIT 1
  `).bind(runId, chunk.chunkId).first();

  if (duplicate) return;

  const now = new Date().toISOString();
  let inserted = 0;
  let duplicates = 0;

  for (const record of chunk.records) {
    const fingerprint = String(
      record.sourceRowFingerprint ||
      record.fingerprint ||
      fallbackFingerprint(record)
    );

    const result = await env.DB.prepare(`
      INSERT OR IGNORE INTO records (
        fingerprint, run_id, provider, record_type, year,
        university, campus, department, admission, metrics_json,
        source_page, source_page_number, source_row_ordinal,
        confidence, raw_evidence, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      fingerprint,
      runId,
      String(record.provider || chunk.provider || ""),
      nullableString(record.recordType),
      nullableInt(record.year),
      nullableString(record.university),
      nullableString(record.campus),
      nullableString(record.department),
      nullableString(record.admission),
      JSON.stringify(record.metrics || {}),
      nullableString(record.sourcePage),
      nullableInt(record.sourcePageNumber),
      nullableInt(record.sourceRowOrdinal),
      nullableString(record.confidence),
      nullableString(record.rawEvidence),
      now
    ).run();

    const changes = Number(result?.meta?.changes || 0);
    if (changes > 0) inserted += 1;
    else duplicates += 1;
  }

  const page = chunk.page || null;
  if (page && page.familyKey && page.page) {
    await env.DB.prepare(`
      INSERT INTO run_pages (
        run_id, family_key, requested_year, page_number,
        state, retry_count, error_type, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(run_id, family_key, requested_year, page_number)
      DO UPDATE SET
        state = excluded.state,
        retry_count = excluded.retry_count,
        error_type = excluded.error_type,
        updated_at = excluded.updated_at
    `).bind(
      runId,
      String(page.familyKey),
      page.requestedYear == null ? -1 : Number(page.requestedYear),
      Number(page.page),
      String(page.state || "completed"),
      Number(page.retryCount || 0),
      nullableString(page.errorType),
      now
    ).run();
  }

  await env.DB.prepare(`
    INSERT INTO processed_chunks (run_id, chunk_id, processed_at)
    VALUES (?, ?, ?)
  `).bind(runId, chunk.chunkId, now).run();

  await env.DB.prepare(`
    UPDATE runs
    SET processed_chunks = processed_chunks + 1,
        received_records = received_records + ?,
        unique_records = unique_records + ?,
        duplicate_records = duplicate_records + ?,
        error_count = error_count + ?,
        updated_at = ?
    WHERE run_id = ?
  `).bind(
    chunk.records.length,
    inserted,
    duplicates,
    chunk.error ? 1 : 0,
    now,
    runId
  ).run();

  if (chunk.error) {
    await env.DB.prepare(`
      INSERT INTO run_errors (
        run_id, chunk_id, error_type, page_number,
        family_key, requested_year, retry_count,
        detail_json, created_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      runId,
      chunk.chunkId,
      nullableString(chunk.error.type),
      nullableInt(chunk.error.page),
      nullableString(chunk.error.familyKey),
      nullableInt(chunk.error.requestedYear),
      nullableInt(chunk.error.retryCount),
      JSON.stringify(chunk.error),
      now
    ).run();
  }
}

async function getStatus(env, runId) {
  const run = await env.DB.prepare(`
    SELECT *
    FROM runs
    WHERE run_id = ?
    LIMIT 1
  `).bind(runId).first();

  if (!run) return json({ error: "run_not_found" }, 404);

  const recentErrors = await env.DB.prepare(`
    SELECT error_type, page_number, family_key, requested_year,
           retry_count, detail_json, created_at
    FROM run_errors
    WHERE run_id = ?
    ORDER BY id DESC
    LIMIT 20
  `).bind(runId).all();

  return json({
    run,
    recentErrors: recentErrors.results || [],
  });
}

async function getPendingPages(env, runId, limit) {
  const run = await env.DB.prepare(`
    SELECT run_id FROM runs WHERE run_id = ? LIMIT 1
  `).bind(runId).first();
  if (!run) return json({ error: "run_not_found" }, 404);

  const countRow = await env.DB.prepare(`
    SELECT COUNT(*) AS pending_count
    FROM run_pages
    WHERE run_id = ? AND state != 'completed'
  `).bind(runId).first();

  const rows = await env.DB.prepare(`
    SELECT p.family_key, p.requested_year, p.page_number, p.state,
           p.retry_count, p.error_type, p.updated_at,
           (
             SELECT MAX(p2.page_number)
             FROM run_pages p2
             WHERE p2.run_id = p.run_id
               AND p2.family_key = p.family_key
               AND p2.requested_year = p.requested_year
           ) AS total_pages
    FROM run_pages p
    WHERE p.run_id = ? AND p.state != 'completed'
    ORDER BY p.requested_year DESC, p.family_key, p.page_number
    LIMIT ?
  `).bind(runId, limit).all();

  const retry = [];
  const deferred = [];
  const nowMs = Date.now();
  for (const row of rows.results || []) {
    const retryCount = Number(row.retry_count || 0);
    const errorType = row.error_type || null;
    const updatedMs = Date.parse(row.updated_at || "");
    const shouldDeferServerError =
      errorType === "server-error" &&
      retryCount >= 2 &&
      Number.isFinite(updatedMs) &&
      nowMs - updatedMs < SERVER_ERROR_RETRY_COOLDOWN_MS;
    const item = {
      familyKey: row.family_key,
      requestedYear: Number(row.requested_year) === -1 ? null : Number(row.requested_year),
      page: Number(row.page_number),
      totalPages: Number(row.total_pages || row.page_number),
      state: row.state,
      retryCount,
      errorType,
      updatedAt: row.updated_at,
    };
    if (shouldDeferServerError) {
      item.retryAfter = new Date(updatedMs + SERVER_ERROR_RETRY_COOLDOWN_MS).toISOString();
      deferred.push(item);
    } else {
      retry.push(item);
    }
  }

  const pendingCount = Number(countRow?.pending_count || 0);
  return json({
    runId,
    pendingCount,
    retryCount: retry.length,
    deferredCount: deferred.length,
    retry,
    deferred,
    serverErrorCooldownSeconds: Math.floor(SERVER_ERROR_RETRY_COOLDOWN_MS / 1000),
    truncated: pendingCount > (retry.length + deferred.length),
  });
}

async function getResumePlan(env, runId, familyKey, requestedYear, totalPages, limit) {
  const rows = await env.DB.prepare(`
    SELECT page_number, state, retry_count, error_type, updated_at
    FROM run_pages
    WHERE run_id = ?
      AND family_key = ?
      AND requested_year = ?
  `).bind(runId, familyKey, requestedYear == null ? -1 : requestedYear).all();

  const stateByPage = new Map();
  for (const row of rows.results || []) {
    stateByPage.set(Number(row.page_number), row);
  }

  const missing = [];
  const retry = [];
  const deferred = [];
  const nowMs = Date.now();

  for (let page = 1; page <= totalPages; page += 1) {
    const row = stateByPage.get(page);
    if (!row) {
      if (missing.length < limit) missing.push(page);
      continue;
    }
    if (row.state !== "completed") {
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
  }

  return json({
    runId,
    familyKey,
    requestedYear,
    totalPages,
    knownPages: stateByPage.size,
    missing,
    retry,
    deferred,
    serverErrorCooldownSeconds: Math.floor(SERVER_ERROR_RETRY_COOLDOWN_MS / 1000),
    truncated: missing.length >= limit || retry.length >= limit || deferred.length >= limit,
  });
}

function fallbackFingerprint(record) {
  const stable = JSON.stringify({
    recordType: record.recordType || null,
    year: record.year || null,
    university: record.university || null,
    campus: record.campus || null,
    department: record.department || null,
    admission: record.admission || null,
    sourcePage: record.sourcePage || null,
    sourcePageNumber: record.sourcePageNumber || null,
    sourceRowOrdinal: record.sourceRowOrdinal || null,
    rawEvidence: record.rawEvidence || null,
  });
  // This is an idempotency fallback, not a security hash.
  let h1 = 0x811c9dc5;
  for (let i = 0; i < stable.length; i += 1) {
    h1 ^= stable.charCodeAt(i);
    h1 = Math.imul(h1, 0x01000193);
  }
  return `fallback-${(h1 >>> 0).toString(16).padStart(8, "0")}`;
}

function nullableString(value) {
  if (value === null || value === undefined) return null;
  const text = String(value).trim();
  return text ? text : null;
}

function nullableInt(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isInteger(number) ? number : null;
}

function boundedInt(value, min, max) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < min || number > max) return null;
  return number;
}
