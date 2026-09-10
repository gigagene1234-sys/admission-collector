import iconv from "iconv-lite";

const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const MAX_HTML_BYTES = 2_500_000;
const DEFAULT_REFRESH_MINUTES = 10;
const FETCH_LAG_MINUTES = 1;
const MAX_OBSERVATION_ROWS = 600;
const MAX_CELLS_PER_ROW = 30;

const MODE_SERVER_PUBLIC = "SERVER_PUBLIC";
const MODE_USER_BROWSER = "USER_BROWSER_PUBLIC_DOM";

export const COMPETITION_TARGETS = [
  {
    id: "knut",
    university: "국립한국교통대학교",
    provider: "JINHAK_APPLY",
    aliases: ["교통대", "한국교통대", "국립한국교통대", "국립한국교통대학교"],
    sourceUrl: "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio30150631.html",
    discoveryUrl: null,
    collectionMode: MODE_USER_BROWSER,
    refreshMinutes: 10,
    refreshSource: "PUBLISHED_NOTICE",
  },
  {
    id: "woosong",
    university: "우송대학교",
    provider: "UWAY_APPLY",
    aliases: ["우송대", "우송대학교"],
    sourceUrl: "http://ratio.uwayapply.com/Sl5KcldhJmFhTkpmJSY6Jko3ZlRm",
    discoveryUrl: "https://ent.wsu.ac.kr/page/index.jsp?code=susi0701",
    collectionMode: MODE_SERVER_PUBLIC,
    refreshMinutes: DEFAULT_REFRESH_MINUTES,
    refreshSource: "ADAPTIVE_DEFAULT",
  },
  {
    id: "hanbat",
    university: "국립한밭대학교",
    provider: "JINHAK_APPLY",
    aliases: ["한밭대", "국립한밭대", "국립한밭대학교"],
    sourceUrl: "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio30040971.html",
    discoveryUrl: null,
    collectionMode: MODE_USER_BROWSER,
    refreshMinutes: 10,
    refreshSource: "PUBLISHED_NOTICE",
  },
  {
    id: "hannam",
    university: "한남대학교",
    provider: "JINHAK_APPLY",
    aliases: ["한남대", "한남대학교"],
    sourceUrl: "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio11560931.html",
    discoveryUrl: null,
    collectionMode: MODE_USER_BROWSER,
    refreshMinutes: 10,
    refreshSource: "PUBLISHED_NOTICE",
  },
  {
    id: "koreatech",
    university: "한국기술교육대학교",
    provider: "UWAY_APPLY",
    aliases: ["한기대", "한국기술교육대학교", "한국기술교대", "한국과학기술교육대학교"],
    sourceUrl: "http://ratio.uwayapply.com/Sl5KfExgMDhgfWE5SmYlJjomSjdmVGY=",
    discoveryUrl: "https://www.koreatech.ac.kr/index.es?sid=01",
    collectionMode: MODE_SERVER_PUBLIC,
    refreshMinutes: DEFAULT_REFRESH_MINUTES,
    refreshSource: "ADAPTIVE_DEFAULT",
  },
  {
    id: "kongju",
    university: "국립공주대학교",
    provider: "JINHAK_APPLY",
    aliases: ["공주대", "국립공주대", "국립공주대학교"],
    sourceUrl: "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio10281081.html",
    discoveryUrl: null,
    collectionMode: MODE_USER_BROWSER,
    refreshMinutes: 10,
    refreshSource: "PUBLISHED_NOTICE",
  },
];

export async function handleCompetitionRequest(request, env, ctx) {
  const url = new URL(request.url);
  if (!url.pathname.startsWith("/v1/competition")) return null;

  if (request.method === "GET" && url.pathname === "/v1/competition/status") {
    await ensureTargets(env);
    return competitionStatus(env);
  }

  if (request.method === "GET" && url.pathname === "/v1/competition/latest") {
    await ensureTargets(env);
    return competitionLatest(env, url.searchParams.get("target") || url.searchParams.get("university"));
  }

  if (request.method === "POST" && url.pathname === "/v1/competition/collect") {
    if (!(await isAuthorized(request, env))) return json({ error: "unauthorized" }, 401);
    const result = await runCompetitionCollector(env, {
      force: url.searchParams.get("force") === "1",
      target: url.searchParams.get("target") || null,
    });
    return json(result);
  }

  if (request.method === "POST" && url.pathname === "/v1/competition/observe") {
    if (!(await isAuthorized(request, env))) return json({ error: "unauthorized" }, 401);
    let body;
    try {
      body = await request.json();
    } catch (_) {
      return json({ error: "invalid_json" }, 400);
    }
    try {
      const result = await ingestBrowserObservation(env, body);
      return json(result, 201);
    } catch (error) {
      return json({ error: String(error?.message || error).slice(0, 500) }, 400);
    }
  }

  return json({ error: "not_found" }, 404);
}

export async function runCompetitionScheduled(env, scheduledTime = Date.now()) {
  return runCompetitionCollector(env, { scheduledTime, force: false });
}

export async function runCompetitionCollector(env, options = {}) {
  await ensureTargets(env);
  const now = new Date(options.scheduledTime || Date.now());
  const q = options.target ? normalize(options.target) : null;
  const stateRows = await env.DB.prepare("SELECT * FROM competition_targets ORDER BY target_id").all();
  const states = new Map((stateRows.results || []).map((row) => [row.target_id, row]));
  const results = [];

  for (const target of COMPETITION_TARGETS) {
    if (q && !targetMatches(target, q)) continue;
    const state = states.get(target.id) || null;

    if (target.collectionMode === MODE_USER_BROWSER) {
      await markTargetWaitingForUserBrowser(env, target.id, now);
      results.push({
        targetId: target.id,
        university: target.university,
        provider: target.provider,
        status: "WAITING_FOR_USER_BROWSER",
        collectionMode: target.collectionMode,
        refreshMinutes: effectiveRefreshMinutes(target, state),
        reason: "UPSTREAM_MANAGED_CHALLENGE",
      });
      continue;
    }

    if (!options.force && !isTargetDue(target, state, now)) {
      results.push({
        targetId: target.id,
        university: target.university,
        provider: target.provider,
        status: "SKIPPED_NOT_DUE",
        refreshMinutes: effectiveRefreshMinutes(target, state),
      });
      continue;
    }

    try {
      results.push(await collectServerTarget(env, target, state, now));
    } catch (error) {
      const message = String(error?.message || error).slice(0, 1000);
      await markTargetError(env, target.id, now, message);
      results.push({
        targetId: target.id,
        university: target.university,
        provider: target.provider,
        status: "ERROR",
        error: message,
      });
    }
  }

  return {
    ok: results.every((x) => x.status !== "ERROR"),
    collectedAt: now.toISOString(),
    results,
  };
}

async function ensureTargets(env) {
  const now = new Date().toISOString();
  for (const target of COMPETITION_TARGETS) {
    await env.DB.prepare(`
      INSERT INTO competition_targets (
        target_id, university, provider, aliases_json,
        configured_source_url, discovery_url,
        configured_refresh_minutes, configured_refresh_source,
        created_at, updated_at
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      ON CONFLICT(target_id) DO UPDATE SET
        university = excluded.university,
        provider = excluded.provider,
        aliases_json = excluded.aliases_json,
        configured_source_url = excluded.configured_source_url,
        discovery_url = excluded.discovery_url,
        configured_refresh_minutes = excluded.configured_refresh_minutes,
        configured_refresh_source = excluded.configured_refresh_source,
        updated_at = excluded.updated_at
    `).bind(
      target.id,
      target.university,
      target.provider,
      JSON.stringify(target.aliases),
      target.sourceUrl,
      target.discoveryUrl,
      target.refreshMinutes,
      target.refreshSource,
      now,
      now
    ).run();
  }
}

function isTargetDue(target, state, now) {
  if (!state?.last_attempt_at) return true;
  const interval = effectiveRefreshMinutes(target, state);
  const lastAttempt = Date.parse(state.last_attempt_at);
  if (Number.isFinite(lastAttempt) && now.getTime() - lastAttempt < Math.max(60_000, (interval - 2) * 60_000)) return false;

  const sourceTime = parseDate(state.last_source_updated_at);
  const offset = sourceTime
    ? (sourceTime.getUTCMinutes() + interval + FETCH_LAG_MINUTES) % interval
    : FETCH_LAG_MINUTES % interval;
  return now.getUTCMinutes() % interval === offset;
}

function effectiveRefreshMinutes(target, state) {
  const learned = Number(state?.learned_refresh_minutes || 0);
  if (learned >= 1 && learned <= 120) return learned;
  const configured = Number(state?.configured_refresh_minutes || target.refreshMinutes || DEFAULT_REFRESH_MINUTES);
  return Math.max(1, Math.min(120, configured));
}

async function collectServerTarget(env, target, state, now) {
  await noteAttempt(env, target.id, now);
  const pageResponse = await fetchPublicHtml(target.sourceUrl);
  if (pageResponse.challenge) throw new Error("SOURCE_REQUIRES_USER_BROWSER");
  const parsed = parseCompetitionPage(pageResponse.html, pageResponse.lastModified, target);
  if (!parsed.rows.length) throw new Error(`NO_COMPETITION_ROWS:${target.sourceUrl}`);

  const previousSourceTime = parseDate(state?.last_source_updated_at);
  const sourceTime = parseDate(parsed.sourceUpdatedAt);
  const detectedRefresh = detectRefreshMinutes(parsed.text);
  const observedRefresh = inferObservedRefreshMinutes(previousSourceTime, sourceTime);
  const learnedRefresh = detectedRefresh || observedRefresh || Number(state?.learned_refresh_minutes || 0) || null;
  const learnedSource = detectedRefresh
    ? "SOURCE_NOTICE"
    : observedRefresh
      ? "OBSERVED_SOURCE_TIMESTAMP"
      : state?.learned_refresh_source || null;

  const saved = await saveSnapshot(env, {
    target,
    sourceUrl: pageResponse.finalUrl || target.sourceUrl,
    sourceUpdatedAt: parsed.sourceUpdatedAt,
    collectedAt: now,
    pageTitle: parsed.title,
    rows: parsed.rows,
    previousHash: state?.last_content_hash || null,
  });

  await env.DB.prepare(`
    UPDATE competition_targets
       SET resolved_source_url = ?,
           last_success_at = ?,
           last_source_updated_at = COALESCE(?, last_source_updated_at),
           last_content_hash = ?,
           learned_refresh_minutes = COALESCE(?, learned_refresh_minutes),
           learned_refresh_source = COALESCE(?, learned_refresh_source),
           last_error = NULL,
           consecutive_failures = 0,
           updated_at = ?
     WHERE target_id = ?
  `).bind(
    pageResponse.finalUrl || target.sourceUrl,
    now.toISOString(),
    parsed.sourceUpdatedAt,
    saved.contentHash,
    learnedRefresh,
    learnedSource,
    now.toISOString(),
    target.id
  ).run();

  return {
    targetId: target.id,
    university: target.university,
    provider: target.provider,
    status: saved.unchanged ? "UNCHANGED" : "SNAPSHOT_SAVED",
    sourceUrl: pageResponse.finalUrl || target.sourceUrl,
    sourceUpdatedAt: parsed.sourceUpdatedAt,
    rows: parsed.rows.length,
    snapshotId: saved.snapshotId,
    refreshMinutes: learnedRefresh || target.refreshMinutes,
    refreshSource: learnedSource || target.refreshSource,
    cadenceVerified: Boolean(learnedSource),
  };
}

async function ingestBrowserObservation(env, body) {
  await ensureTargets(env);
  const target = resolveTarget(body?.targetId || body?.university || "");
  if (!target) throw new Error("target_not_found");
  if (!Array.isArray(body?.rows) || body.rows.length < 1 || body.rows.length > MAX_OBSERVATION_ROWS) {
    throw new Error("invalid_rows");
  }
  if (!isAllowedSourceUrl(target, body?.sourceUrl)) throw new Error("source_url_not_allowed");

  const rows = body.rows.map((row, i) => normalizeObservedRow(row, i));
  const now = new Date();
  const state = await env.DB.prepare("SELECT * FROM competition_targets WHERE target_id = ?").bind(target.id).first();
  const saved = await saveSnapshot(env, {
    target,
    sourceUrl: body.sourceUrl || target.sourceUrl,
    sourceUpdatedAt: normalizeIsoDate(body.sourceUpdatedAt),
    collectedAt: now,
    pageTitle: String(body.pageTitle || `${target.university} 경쟁률`).slice(0, 300),
    rows,
    previousHash: state?.last_content_hash || null,
  });

  const previousSourceTime = parseDate(state?.last_source_updated_at);
  const sourceTime = parseDate(normalizeIsoDate(body.sourceUpdatedAt));
  const observedRefresh = inferObservedRefreshMinutes(previousSourceTime, sourceTime);
  const learnedRefresh = observedRefresh || Number(state?.learned_refresh_minutes || 0) || null;
  const learnedSource = observedRefresh ? "OBSERVED_BROWSER_SOURCE_TIMESTAMP" : state?.learned_refresh_source || null;

  await env.DB.prepare(`
    UPDATE competition_targets
       SET resolved_source_url = ?,
           last_attempt_at = ?,
           last_success_at = ?,
           last_source_updated_at = COALESCE(?, last_source_updated_at),
           last_content_hash = ?,
           learned_refresh_minutes = COALESCE(?, learned_refresh_minutes),
           learned_refresh_source = COALESCE(?, learned_refresh_source),
           last_error = NULL,
           consecutive_failures = 0,
           updated_at = ?
     WHERE target_id = ?
  `).bind(
    body.sourceUrl || target.sourceUrl,
    now.toISOString(),
    now.toISOString(),
    normalizeIsoDate(body.sourceUpdatedAt),
    saved.contentHash,
    learnedRefresh,
    learnedSource,
    now.toISOString(),
    target.id
  ).run();

  return {
    ok: true,
    targetId: target.id,
    university: target.university,
    provider: target.provider,
    origin: "USER_BROWSER_PUBLIC_DOM",
    credentialExported: false,
    sessionSecretExported: false,
    status: saved.unchanged ? "UNCHANGED" : "SNAPSHOT_SAVED",
    snapshotId: saved.snapshotId,
    rows: rows.length,
  };
}

function normalizeObservedRow(row, ordinal) {
  const cells = Array.isArray(row?.cells)
    ? row.cells.slice(0, MAX_CELLS_PER_ROW).map((x) => String(x ?? "").replace(/\s+/g, " ").trim().slice(0, 500))
    : [];
  return {
    admission: cleanLabel(row?.admission),
    department: cleanLabel(row?.department),
    quota: nullableInteger(row?.quota),
    applicants: nullableInteger(row?.applicants),
    ratio: nullableRatio(row?.ratio),
    cells,
    ordinal: ordinal + 1,
  };
}

async function saveSnapshot(env, data) {
  const stablePayload = JSON.stringify({
    sourceUpdatedAt: data.sourceUpdatedAt || null,
    rows: data.rows.map((r) => [r.admission, r.department, r.quota, r.applicants, r.ratio, r.cells]),
  });
  const contentHash = await sha256Hex(stablePayload);
  if (data.previousHash && data.previousHash === contentHash) return { unchanged: true, snapshotId: null, contentHash };

  const inserted = await env.DB.prepare(`
    INSERT INTO competition_snapshots (
      target_id, university, provider, source_url,
      source_updated_at, collected_at, content_hash, page_title, row_count
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    data.target.id,
    data.target.university,
    data.target.provider,
    data.sourceUrl,
    data.sourceUpdatedAt || null,
    data.collectedAt.toISOString(),
    contentHash,
    data.pageTitle || null,
    data.rows.length
  ).run();
  const snapshotId = Number(inserted?.meta?.last_row_id || 0) || null;
  if (!snapshotId) throw new Error("snapshot_insert_failed");

  const statements = data.rows.map((row, ordinal) => env.DB.prepare(`
    INSERT INTO competition_rows (
      snapshot_id, target_id, university, admission, department,
      quota, applicants, ratio, cells_json, row_ordinal
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
  `).bind(
    snapshotId,
    data.target.id,
    data.target.university,
    row.admission,
    row.department,
    row.quota,
    row.applicants,
    row.ratio,
    JSON.stringify(row.cells || []),
    ordinal + 1
  ));
  if (statements.length) await env.DB.batch(statements);
  return { unchanged: false, snapshotId, contentHash };
}

async function fetchPublicHtml(url) {
  const response = await fetch(url, {
    method: "GET",
    redirect: "follow",
    headers: {
      accept: "text/html,application/xhtml+xml",
      "accept-language": "ko-KR,ko;q=0.9,en;q=0.5",
      "user-agent": "AdmissionHub-CompetitionCollector/2.0 (public-read-only; +https://github.com/gigagene1234-sys/admission-collector)",
    },
  });
  const contentType = response.headers.get("content-type") || "";
  const cfMitigated = response.headers.get("cf-mitigated") || "";
  const lastModified = response.headers.get("last-modified") || null;
  const length = Number(response.headers.get("content-length") || 0);
  if (length > MAX_HTML_BYTES) throw new Error(`HTML_TOO_LARGE:${length}`);

  const bytes = new Uint8Array(await response.arrayBuffer());
  if (bytes.byteLength > MAX_HTML_BYTES) throw new Error(`HTML_TOO_LARGE:${bytes.byteLength}`);
  const charsetMatch = contentType.match(/charset\s*=\s*["']?([^;"'\s]+)/i);
  const charset = (charsetMatch?.[1] || "utf-8").toLowerCase();
  let html;
  if (/euc-?kr|ks_c_5601-1987|cp949|windows-949/i.test(charset)) {
    html = iconv.decode(Buffer.from(bytes), "euc-kr");
  } else {
    html = new TextDecoder("utf-8").decode(bytes);
  }

  const challenge = /challenge/i.test(cfMitigated) || /안전한\s*접속\s*확인|Security\s*Check\s*\|\s*JINHAKAPPLY/i.test(html.slice(0, 30000));
  if (!response.ok && !challenge) throw new Error(`HTTP_${response.status}:${url}`);
  return { html, challenge, lastModified, finalUrl: response.url || url, status: response.status, charset };
}

function parseCompetitionPage(html, lastModified, target) {
  const text = htmlToText(html);
  const titleMatch = html.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i);
  const title = titleMatch ? htmlToText(titleMatch[1]).slice(0, 300) : null;
  const tableRows = parseTableRows(html);
  const rows = extractStructuredRows(tableRows);
  const textTimestamp = extractSourceUpdatedAt(text);
  const headerTimestamp = normalizeIsoDate(lastModified);
  return {
    title,
    text,
    sourceUpdatedAt: headerTimestamp || textTimestamp,
    rows,
    university: target.university,
  };
}

function parseTableRows(html) {
  const rows = [];
  const rowRe = /<tr\b[^>]*>([\s\S]*?)<\/tr>/gi;
  let rowMatch;
  while ((rowMatch = rowRe.exec(html))) {
    const cells = [];
    const cellRe = /<t[dh]\b[^>]*>([\s\S]*?)<\/t[dh]>/gi;
    let cellMatch;
    while ((cellMatch = cellRe.exec(rowMatch[1]))) {
      const text = htmlToText(cellMatch[1]);
      if (text) cells.push(text);
    }
    if (cells.length) rows.push(cells);
  }
  return rows;
}

function extractStructuredRows(tableRows) {
  const output = [];
  let header = null;
  let section = null;
  for (const cells of tableRows) {
    const detected = detectHeader(cells);
    if (detected.ratioIndex >= 0 && (detected.departmentIndex >= 0 || detected.quotaIndex >= 0)) {
      header = detected;
      continue;
    }

    if (cells.length <= 3 && !cells.some((c) => parseRatio(c) != null)) {
      const candidate = cells.join(" ").trim();
      if (candidate && candidate.length < 180 && !/합계|총계|모집인원|지원인원|경쟁률/.test(candidate)) section = candidate;
    }

    let ratioIndex = header?.ratioIndex ?? -1;
    if (ratioIndex < 0 || ratioIndex >= cells.length || parseRatio(cells[ratioIndex]) == null) {
      ratioIndex = findLastIndex(cells, (c) => parseRatio(c) != null);
    }
    if (ratioIndex < 0) continue;
    const ratio = parseRatio(cells[ratioIndex]);
    if (ratio == null) continue;

    const beforeRatio = cells.slice(0, ratioIndex);
    const integerCells = [];
    for (let i = 0; i < beforeRatio.length; i += 1) {
      const value = parseInteger(beforeRatio[i]);
      if (value != null) integerCells.push({ index: i, value });
    }

    // Uway/Jinhak competition tables can collapse rowspan cells on subsequent rows, so fixed
    // header indices are not stable. The two right-most integer cells immediately before the
    // published ratio are the row's 모집인원 and 지원인원. Prefer that structural invariant.
    let quota = null;
    let applicants = null;
    let numericTailStart = ratioIndex;
    if (integerCells.length >= 2) {
      const quotaCell = integerCells[integerCells.length - 2];
      const applicantCell = integerCells[integerCells.length - 1];
      quota = quotaCell.value;
      applicants = applicantCell.value;
      numericTailStart = quotaCell.index;
    } else {
      quota = parseInteger(valueAt(cells, header?.quotaIndex));
      applicants = parseInteger(valueAt(cells, header?.applicantsIndex));
    }

    const labelCells = beforeRatio.slice(0, numericTailStart).filter((c) => !isNumericLike(c));
    let department = labelCells.length ? labelCells[labelCells.length - 1] : valueAt(cells, header?.departmentIndex);
    let admission = section;
    const indexedAdmission = valueAt(cells, header?.admissionIndex);
    if (indexedAdmission && !isNumericLike(indexedAdmission) && indexedAdmission !== department) {
      admission = indexedAdmission;
    } else if (!admission && labelCells.length > 1) {
      admission = labelCells[labelCells.length - 2];
    }

    // Reject structurally inconsistent rows instead of silently persisting shifted columns.
    if (!ratioMatchesCounts(quota, applicants, ratio)) continue;
    if (!department && quota == null && applicants == null) continue;
    output.push({
      admission: cleanLabel(admission),
      department: cleanLabel(department),
      quota,
      applicants,
      ratio,
      cells,
    });
  }

  const dedup = new Map();
  for (const row of output) {
    const key = JSON.stringify([row.admission, row.department, row.quota, row.applicants, row.ratio]);
    if (!dedup.has(key)) dedup.set(key, row);
  }
  return [...dedup.values()];
}

function detectHeader(cells) {
  const out = { admissionIndex: -1, departmentIndex: -1, quotaIndex: -1, applicantsIndex: -1, ratioIndex: -1 };
  cells.forEach((cell, i) => {
    const c = normalize(cell);
    if (out.admissionIndex < 0 && /전형명|전형/.test(c)) out.admissionIndex = i;
    if (out.departmentIndex < 0 && /모집단위|학과|전공/.test(c)) out.departmentIndex = i;
    if (out.quotaIndex < 0 && /모집인원|모집정원|정원/.test(c)) out.quotaIndex = i;
    if (out.applicantsIndex < 0 && /지원인원|지원자수|지원자/.test(c)) out.applicantsIndex = i;
    if (out.ratioIndex < 0 && /경쟁률/.test(c)) out.ratioIndex = i;
  });
  return out;
}

function detectRefreshMinutes(text) {
  const snippets = text.match(/.{0,70}(?:업데이트|갱신|경쟁률).{0,70}/g) || [];
  for (const snippet of snippets) {
    const a = snippet.match(/(?:매\s*)?(\d{1,3})\s*분\s*(?:단위|마다|간격)?[^\d]{0,30}(?:업데이트|갱신)/);
    const b = snippet.match(/(?:업데이트|갱신)[^\d]{0,30}(\d{1,3})\s*분/);
    const n = Number((a || b)?.[1] || 0);
    if (n >= 1 && n <= 120) return n;
  }
  return null;
}

function extractSourceUpdatedAt(text) {
  const patterns = [
    /(20\d{2})\s*[.\/-]\s*(\d{1,2})\s*[.\/-]\s*(\d{1,2})[^\d]{0,40}(\d{1,2})\s*:\s*(\d{2})/,
    /(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일[^\d]{0,40}(\d{1,2})\s*:\s*(\d{2})/,
  ];
  for (const pattern of patterns) {
    const m = text.match(pattern);
    if (!m) continue;
    return `${m[1]}-${String(m[2]).padStart(2, "0")}-${String(m[3]).padStart(2, "0")}T${String(m[4]).padStart(2, "0")}:${m[5]}:00+09:00`;
  }
  return null;
}

function inferObservedRefreshMinutes(previous, current) {
  if (!previous || !current || current <= previous) return null;
  const diff = Math.round((current.getTime() - previous.getTime()) / 60_000);
  if (diff < 1 || diff > 120) return null;
  const common = [1, 2, 3, 5, 10, 15, 20, 30, 60, 120];
  if (common.includes(diff)) return diff;
  for (const n of common) if (diff % n === 0 && diff / n <= 6) return n;
  return null;
}

async function competitionStatus(env) {
  const rows = await env.DB.prepare("SELECT * FROM competition_targets ORDER BY target_id").all();
  const byId = new Map((rows.results || []).map((r) => [r.target_id, r]));
  return json({
    targets: COMPETITION_TARGETS.map((target) => {
      const row = byId.get(target.id) || {};
      const learned = Number(row.learned_refresh_minutes || 0) || null;
      const refreshSource = row.learned_refresh_source || target.refreshSource;
      return {
        targetId: target.id,
        university: target.university,
        provider: target.provider,
        aliases: target.aliases,
        collectionMode: target.collectionMode,
        sourceUrl: row.resolved_source_url || target.sourceUrl,
        discoveryUrl: target.discoveryUrl,
        refreshMinutes: learned || target.refreshMinutes,
        refreshSource,
        cadenceVerified: target.refreshSource === "PUBLISHED_NOTICE" || ["SOURCE_NOTICE", "OBSERVED_SOURCE_TIMESTAMP", "OBSERVED_BROWSER_SOURCE_TIMESTAMP"].includes(refreshSource),
        requiresUserBrowser: target.collectionMode === MODE_USER_BROWSER,
        lastAttemptAt: row.last_attempt_at || null,
        lastSuccessAt: row.last_success_at || null,
        lastSourceUpdatedAt: row.last_source_updated_at || null,
        consecutiveFailures: Number(row.consecutive_failures || 0),
        lastError: row.last_error || null,
      };
    }),
  });
}

async function competitionLatest(env, query) {
  const target = query ? resolveTarget(query) : null;
  if (query && !target) return json({ error: "target_not_found" }, 404);
  const targets = target ? [target] : COMPETITION_TARGETS;
  const result = [];
  for (const t of targets) {
    const snapshot = await env.DB.prepare(`
      SELECT id, target_id, university, provider, source_url, source_updated_at,
             collected_at, content_hash, page_title, row_count
        FROM competition_snapshots
       WHERE target_id = ?
       ORDER BY id DESC LIMIT 1
    `).bind(t.id).first();
    if (!snapshot) {
      result.push({ targetId: t.id, university: t.university, snapshot: null, rows: [] });
      continue;
    }
    const rows = await env.DB.prepare(`
      SELECT admission, department, quota, applicants, ratio, cells_json, row_ordinal
        FROM competition_rows WHERE snapshot_id = ? ORDER BY row_ordinal
    `).bind(snapshot.id).all();
    result.push({
      targetId: t.id,
      university: t.university,
      snapshot,
      rows: (rows.results || []).map((r) => ({ ...r, cells: safeJson(r.cells_json, []) })),
    });
  }
  return json({ targets: result });
}

async function markTargetWaitingForUserBrowser(env, targetId, now) {
  await env.DB.prepare(`
    UPDATE competition_targets
       SET last_error = NULL,
           consecutive_failures = 0,
           updated_at = ?
     WHERE target_id = ?
  `).bind(now.toISOString(), targetId).run();
}

async function noteAttempt(env, targetId, now) {
  await env.DB.prepare("UPDATE competition_targets SET last_attempt_at = ?, updated_at = ? WHERE target_id = ?")
    .bind(now.toISOString(), now.toISOString(), targetId).run();
}

async function markTargetError(env, targetId, now, message) {
  await env.DB.prepare(`
    UPDATE competition_targets
       SET last_attempt_at = ?, last_error = ?, consecutive_failures = consecutive_failures + 1, updated_at = ?
     WHERE target_id = ?
  `).bind(now.toISOString(), message, now.toISOString(), targetId).run();
}

function resolveTarget(value) {
  const q = normalize(value);
  return COMPETITION_TARGETS.find((target) => targetMatches(target, q)) || null;
}

function targetMatches(target, q) {
  return normalize(target.id) === q || normalize(target.university) === q || target.aliases.some((x) => normalize(x) === q);
}

function isAllowedSourceUrl(target, value) {
  if (!value) return true;
  try {
    const url = new URL(value);
    const configured = new URL(target.sourceUrl);
    if (url.protocol !== "https:" && url.protocol !== "http:") return false;
    return url.hostname === configured.hostname;
  } catch (_) {
    return false;
  }
}

function detectHeaderSafeInteger(value) {
  const n = Number(value);
  return Number.isSafeInteger(n) ? n : null;
}

function nullableInteger(value) {
  if (value == null || value === "") return null;
  return detectHeaderSafeInteger(value);
}

function nullableRatio(value) {
  if (value == null || value === "") return null;
  const n = Number(value);
  return Number.isFinite(n) && n >= 0 && n < 100000 ? n : null;
}

function ratioMatchesCounts(quota, applicants, ratio) {
  if (quota == null || applicants == null || ratio == null) return true;
  if (quota === 0) return applicants === 0 && Math.abs(ratio) <= 0.005;
  const expected = applicants / quota;
  // Published ratios are normally rounded to two decimals. Allow only a narrow rounding margin.
  return Math.abs(expected - ratio) <= 0.015;
}

function parseRatio(value) {
  if (value == null) return null;
  const text = String(value).replace(/,/g, "").trim();
  const match = text.match(/(\d+(?:\.\d+)?)\s*(?::|대)\s*1/);
  if (!match) return null;
  const n = Number(match[1]);
  return Number.isFinite(n) ? n : null;
}

function parseInteger(value) {
  if (value == null) return null;
  const text = String(value).replace(/,/g, "").trim();
  if (!/^\d+$/.test(text)) return null;
  const n = Number(text);
  return Number.isSafeInteger(n) ? n : null;
}

function isNumericLike(value) {
  return parseInteger(value) != null || parseRatio(value) != null || /^[-–—]$/.test(String(value || "").trim());
}

function valueAt(cells, index) {
  return Number.isInteger(index) && index >= 0 && index < cells.length ? cells[index] : null;
}

function cleanLabel(value) {
  if (value == null) return null;
  const text = String(value).replace(/\s+/g, " ").trim();
  if (!text || isNumericLike(text)) return null;
  return text.slice(0, 300);
}

function htmlToText(value) {
  return decodeHtmlEntities(String(value || "")
    .replace(/<script\b[\s\S]*?<\/script>/gi, " ")
    .replace(/<style\b[\s\S]*?<\/style>/gi, " ")
    .replace(/<br\s*\/?\s*>/gi, " ")
    .replace(/<[^>]+>/g, " "))
    .replace(/\s+/g, " ")
    .trim();
}

function decodeHtmlEntities(value) {
  const named = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
  return String(value || "").replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (whole, entity) => {
    if (entity[0] === "#") {
      const n = entity[1].toLowerCase() === "x" ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
      return Number.isFinite(n) ? String.fromCodePoint(n) : whole;
    }
    return named[entity.toLowerCase()] ?? whole;
  });
}

function normalize(value) {
  return String(value || "").toLowerCase().replace(/[\s·._()\-]/g, "");
}

function normalizeIsoDate(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? d.toISOString() : null;
}

function parseDate(value) {
  if (!value) return null;
  const d = new Date(value);
  return Number.isFinite(d.getTime()) ? d : null;
}

function safeJson(value, fallback) {
  try { return JSON.parse(value); } catch (_) { return fallback; }
}

function findLastIndex(array, predicate) {
  for (let i = array.length - 1; i >= 0; i -= 1) if (predicate(array[i], i)) return i;
  return -1;
}

async function sha256Hex(value) {
  const bytes = new TextEncoder().encode(value);
  const hash = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(hash)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function isAuthorized(request, env) {
  const token = env.INGEST_TOKEN;
  if (!token) return false;
  const actual = request.headers.get("authorization") || "";
  const expected = `Bearer ${token}`;
  const left = new TextEncoder().encode(actual);
  const right = new TextEncoder().encode(expected);
  if (left.byteLength !== right.byteLength) return false;
  return crypto.subtle.timingSafeEqual(left, right);
}

function json(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });
}
