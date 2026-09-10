const JSON_HEADERS = {
  "content-type": "application/json; charset=utf-8",
  "cache-control": "no-store",
};

const DEFAULT_REFRESH_MINUTES = 10;
const FETCH_LAG_MINUTES = 1;
const MAX_HTML_BYTES = 2_500_000;

export const COMPETITION_TARGETS = [
  {
    id: "knut",
    university: "국립한국교통대학교",
    provider: "JINHAK_APPLY",
    aliases: ["교통대", "한국교통대", "국립한국교통대", "국립한국교통대학교"],
    sourceUrl: "https://addon.jinhakapply.com/RatioV1/RatioH/Ratio30150631.html",
    discoveryUrl: null,
    refreshMinutes: 10,
    refreshSource: "PUBLISHED_NOTICE",
  },
  {
    id: "woosong",
    university: "우송대학교",
    provider: "UWAY_APPLY",
    aliases: ["우송대", "우송대학교"],
    sourceUrl: null,
    discoveryUrl: "https://ent.wsu.ac.kr/page/index.jsp?code=susi0701",
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
    refreshMinutes: 10,
    refreshSource: "PUBLISHED_NOTICE",
  },
  {
    id: "koreatech",
    university: "한국기술교육대학교",
    provider: "UWAY_APPLY",
    aliases: ["한기대", "한국기술교육대학교", "한국기술교대", "한국과학기술교육대학교"],
    sourceUrl: null,
    discoveryUrl: "https://www.koreatech.ac.kr/index.es?sid=01",
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
    if (!(await isAuthorized(request, env))) {
      return json({ error: "unauthorized" }, 401);
    }
    const force = url.searchParams.get("force") === "1";
    const target = url.searchParams.get("target") || null;
    const result = await runCompetitionCollector(env, { force, target });
    return json(result);
  }

  return json({ error: "not_found" }, 404);
}

export async function runCompetitionScheduled(env, scheduledTime = Date.now()) {
  return runCompetitionCollector(env, { force: false, scheduledTime });
}

export async function runCompetitionCollector(env, options = {}) {
  await ensureTargets(env);
  const now = new Date(options.scheduledTime || Date.now());
  const targetFilter = options.target ? normalize(options.target) : null;
  const stateRows = await env.DB.prepare(`
    SELECT * FROM competition_targets ORDER BY target_id
  `).all();
  const states = new Map((stateRows.results || []).map((row) => [row.target_id, row]));

  const results = [];
  for (const target of COMPETITION_TARGETS) {
    if (targetFilter && !targetMatches(target, targetFilter)) continue;
    const state = states.get(target.id) || null;
    if (!options.force && !isTargetDue(target, state, now)) {
      results.push({ targetId: target.id, university: target.university, status: "SKIPPED_NOT_DUE" });
      continue;
    }
    try {
      results.push(await collectTarget(env, target, state, now));
    } catch (error) {
      const message = String(error?.message || error).slice(0, 1000);
      await markTargetError(env, target.id, now, message);
      results.push({ targetId: target.id, university: target.university, status: "ERROR", error: message });
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
  const refreshMinutes = effectiveRefreshMinutes(target, state);
  const lastAttempt = Date.parse(state.last_attempt_at);
  if (Number.isFinite(lastAttempt) && now.getTime() - lastAttempt < Math.max(60_000, (refreshMinutes - 2) * 60_000)) {
    return false;
  }

  const sourceTime = parseDate(state.last_source_updated_at);
  let offset = FETCH_LAG_MINUTES % refreshMinutes;
  if (sourceTime) offset = (sourceTime.getUTCMinutes() + FETCH_LAG_MINUTES) % refreshMinutes;
  return now.getUTCMinutes() % refreshMinutes === offset;
}

function effectiveRefreshMinutes(target, state) {
  const learned = Number(state?.learned_refresh_minutes || 0);
  if (learned >= 1 && learned <= 120) return learned;
  const configured = Number(state?.configured_refresh_minutes || target.refreshMinutes || DEFAULT_REFRESH_MINUTES);
  return Math.min(120, Math.max(1, configured));
}

async function collectTarget(env, target, state, now) {
  await env.DB.prepare(`
    UPDATE competition_targets
    SET last_attempt_at = ?, updated_at = ?
    WHERE target_id = ?
  `).bind(now.toISOString(), now.toISOString(), target.id).run();

  const resolved = await resolveCompetitionPage(target, state);
  if (!resolved) throw new Error("COMPETITION_PAGE_NOT_RESOLVED");

  const page = parseCompetitionPage(resolved.html, target);
  if (!page.rows.length) {
    throw new Error(`NO_COMPETITION_ROWS:${resolved.url}`);
  }

  const detectedRefresh = detectRefreshMinutes(page.text);
  const previousSourceTime = parseDate(state?.last_source_updated_at);
  const sourceTime = page.sourceUpdatedAt ? parseDate(page.sourceUpdatedAt) : null;
  const observedRefresh = inferObservedRefreshMinutes(previousSourceTime, sourceTime);
  const learnedRefresh = detectedRefresh || observedRefresh || Number(state?.learned_refresh_minutes || 0) || null;
  const learnedSource = detectedRefresh
    ? "SOURCE_NOTICE"
    : observedRefresh
      ? "OBSERVED_SOURCE_TIMESTAMP"
      : state?.learned_refresh_source || null;

  const stablePayload = JSON.stringify({
    sourceUpdatedAt: page.sourceUpdatedAt,
    rows: page.rows.map((r) => [r.admission, r.department, r.quota, r.applicants, r.ratio, r.cells]),
  });
  const contentHash = await sha256Hex(stablePayload);
  const unchanged = state?.last_content_hash === contentHash;

  let snapshotId = null;
  if (!unchanged) {
    const insert = await env.DB.prepare(`
      INSERT INTO competition_snapshots (
        target_id, university, provider, source_url,
        source_updated_at, collected_at, content_hash,
        page_title, row_count
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    `).bind(
      target.id,
      target.university,
      target.provider,
      resolved.url,
      page.sourceUpdatedAt,
      now.toISOString(),
      contentHash,
      page.title,
      page.rows.length
    ).run();
    snapshotId = Number(insert?.meta?.last_row_id || 0) || null;

    if (snapshotId) {
      const statements = page.rows.map((row, ordinal) => env.DB.prepare(`
        INSERT INTO competition_rows (
          snapshot_id, target_id, university, admission, department,
          quota, applicants, ratio, cells_json, row_ordinal
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
      `).bind(
        snapshotId,
        target.id,
        target.university,
        row.admission,
        row.department,
        row.quota,
        row.applicants,
        row.ratio,
        JSON.stringify(row.cells),
        ordinal + 1
      ));
      if (statements.length) await env.DB.batch(statements);
    }
  }

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
    resolved.url,
    now.toISOString(),
    page.sourceUpdatedAt,
    contentHash,
    learnedRefresh,
    learnedSource,
    now.toISOString(),
    target.id
  ).run();

  return {
    targetId: target.id,
    university: target.university,
    provider: target.provider,
    status: unchanged ? "UNCHANGED" : "SNAPSHOT_SAVED",
    sourceUrl: resolved.url,
    sourceUpdatedAt: page.sourceUpdatedAt,
    rows: page.rows.length,
    snapshotId,
    refreshMinutes: learnedRefresh || target.refreshMinutes,
    refreshSource: learnedSource || target.refreshSource,
  };
}

async function resolveCompetitionPage(target, state) {
  const tried = new Set();
  const directUrls = [target.sourceUrl, state?.resolved_source_url].filter(Boolean);
  for (const url of directUrls) {
    if (tried.has(url)) continue;
    tried.add(url);
    try {
      const html = await fetchHtml(url);
      if (looksLikeCompetitionPage(html)) return { url, html };
    } catch (_) {}
  }

  if (!target.discoveryUrl) return null;
  let frontier = [target.discoveryUrl];
  for (let depth = 0; depth < 3; depth += 1) {
    const next = [];
    for (const url of frontier.slice(0, 8)) {
      if (tried.has(url)) continue;
      tried.add(url);
      let html;
      try {
        html = await fetchHtml(url);
      } catch (_) {
        continue;
      }
      if (looksLikeCompetitionPage(html)) return { url, html };
      const candidates = extractCompetitionLinks(html, url, target);
      for (const candidate of candidates) {
        if (!tried.has(candidate.url)) next.push(candidate.url);
      }
    }
    frontier = [...new Set(next)].slice(0, 12);
    if (!frontier.length) break;
  }
  return null;
}

async function fetchHtml(url) {
  const response = await fetch(url, {
    method: "GET",
    redirect: "follow",
    headers: {
      "accept": "text/html,application/xhtml+xml",
      "accept-language": "ko-KR,ko;q=0.9,en;q=0.5",
      "user-agent": "AdmissionHub-CompetitionCollector/1.0 (public-read-only; +https://github.com/gigagene1234-sys/admission-collector)",
    },
  });
  if (!response.ok) throw new Error(`HTTP_${response.status}:${url}`);
  const length = Number(response.headers.get("content-length") || 0);
  if (length > MAX_HTML_BYTES) throw new Error(`HTML_TOO_LARGE:${length}`);
  const html = await response.text();
  if (new TextEncoder().encode(html).byteLength > MAX_HTML_BYTES) throw new Error("HTML_TOO_LARGE");
  return html;
}

function extractCompetitionLinks(html, baseUrl, target) {
  const candidates = [];
  const push = (raw, label = "") => {
    const decoded = decodeHtmlEntities(String(raw || "").trim());
    if (!decoded || /^#/.test(decoded)) return;
    if (/^javascript:/i.test(decoded)) {
      for (const nested of stringsFromScript(decoded)) push(nested, label);
      return;
    }
    let url;
    try { url = new URL(decoded, baseUrl).href; } catch (_) { return; }
    if (!/^https?:/i.test(url)) return;
    const score = scoreCompetitionLink(url, label, target);
    if (score > 0) candidates.push({ url, score });
  };

  const anchorRe = /<a\b([^>]*)>([\s\S]*?)<\/a>/gi;
  let match;
  while ((match = anchorRe.exec(html))) {
    const attrs = match[1];
    const label = htmlToText(match[2]);
    const href = attrValue(attrs, "href");
    if (href) push(href, label);
    const onclick = attrValue(attrs, "onclick");
    if (onclick) {
      for (const raw of stringsFromScript(onclick)) push(raw, label);
    }
  }

  const iframeRe = /<iframe\b([^>]*)>/gi;
  while ((match = iframeRe.exec(html))) {
    const src = attrValue(match[1], "src");
    if (src) push(src, "iframe");
  }

  const absoluteRe = /https?:\\?\/\\?\/[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+/gi;
  for (const raw of html.match(absoluteRe) || []) push(raw.replace(/\\\//g, "/"), "embedded");

  return [...new Map(candidates.sort((a, b) => b.score - a.score).map((x) => [x.url, x])).values()].slice(0, 12);
}

function scoreCompetitionLink(url, label, target) {
  const u = normalize(url);
  const t = normalize(label);
  let score = 0;
  if (/경쟁률|지원현황|원서접수현황/.test(label)) score += 120;
  if (/ratio|competition|applyrate|supportstatus|applystatus/.test(u)) score += 90;
  if (/jinhakapply\.com|uwayapply\.com/.test(u)) score += 55;
  if (target.provider === "UWAY_APPLY" && /uwayapply\.com/.test(u)) score += 40;
  if (target.provider === "JINHAK_APPLY" && /jinhakapply\.com/.test(u)) score += 40;
  if (/2027|susi|수시/.test(u + t)) score += 15;
  if (/result|pass|합격|등록포기|refund/.test(u + t)) score -= 100;
  return score;
}

function stringsFromScript(value) {
  const out = [];
  const re = /['"]([^'"]{2,500})['"]/g;
  let match;
  while ((match = re.exec(value))) out.push(match[1]);
  return out;
}

function attrValue(attrs, name) {
  const re = new RegExp(`${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)'|([^\\s>]+))`, "i");
  const match = String(attrs || "").match(re);
  return match ? (match[1] ?? match[2] ?? match[3] ?? "") : null;
}

function looksLikeCompetitionPage(html) {
  const text = htmlToText(html).slice(0, 300_000);
  const hasCompetitionWords = /경쟁률/.test(text) && /(모집인원|지원인원|지원자)/.test(text);
  if (!hasCompetitionWords) return false;
  const rows = parseTableRows(html);
  return rows.some((cells) => cells.some((cell) => parseRatio(cell) != null));
}

function parseCompetitionPage(html, target) {
  const text = htmlToText(html);
  const titleMatch = html.match(/<title\b[^>]*>([\s\S]*?)<\/title>/i);
  const title = titleMatch ? htmlToText(titleMatch[1]).slice(0, 300) : null;
  const tableRows = parseTableRows(html);
  const rows = extractStructuredRows(tableRows);
  return {
    title,
    text,
    sourceUpdatedAt: extractSourceUpdatedAt(text),
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
    const joined = cells.join(" | ");
    const detectedHeader = detectHeader(cells);
    if (detectedHeader.ratioIndex >= 0 && (detectedHeader.departmentIndex >= 0 || detectedHeader.quotaIndex >= 0)) {
      header = detectedHeader;
      continue;
    }

    if (cells.length <= 3 && !cells.some((c) => parseRatio(c) != null) && !cells.every((c) => /^\d+$/.test(c.replace(/,/g, "")))) {
      const candidate = cells.join(" ").trim();
      if (candidate.length <= 160 && !/합계|총계|모집인원|지원인원|경쟁률/.test(candidate)) section = candidate;
    }

    let ratioIndex = header?.ratioIndex ?? cells.findIndex((c) => parseRatio(c) != null);
    if (ratioIndex < 0) ratioIndex = cells.findLastIndex ? cells.findLastIndex((c) => parseRatio(c) != null) : findLastIndex(cells, (c) => parseRatio(c) != null);
    if (ratioIndex < 0) continue;
    const ratio = parseRatio(cells[ratioIndex]);
    if (ratio == null) continue;

    let department = valueAt(cells, header?.departmentIndex);
    let admission = valueAt(cells, header?.admissionIndex) || section;
    let quota = parseInteger(valueAt(cells, header?.quotaIndex));
    let applicants = parseInteger(valueAt(cells, header?.applicantsIndex));

    if (!department) {
      const textCells = cells.slice(0, ratioIndex).filter((c) => !isNumericLike(c));
      department = textCells.length ? textCells[textCells.length - 1] : null;
      if (!admission && textCells.length >= 2) admission = textCells[textCells.length - 2];
    }

    if (quota == null || applicants == null) {
      const numeric = cells.slice(0, ratioIndex).map((c) => ({ n: parseInteger(c) })).filter((x) => x.n != null);
      if (numeric.length >= 2) {
        if (quota == null) quota = numeric[numeric.length - 2].n;
        if (applicants == null) applicants = numeric[numeric.length - 1].n;
      }
    }

    if (!department && quota == null && applicants == null) continue;
    output.push({
      admission: cleanLabel(admission),
      department: cleanLabel(department),
      quota,
      applicants,
      ratio,
      cells,
      raw: joined,
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
  const indexes = {
    admissionIndex: -1,
    departmentIndex: -1,
    quotaIndex: -1,
    applicantsIndex: -1,
    ratioIndex: -1,
  };
  cells.forEach((cell, i) => {
    const c = normalize(cell);
    if (indexes.admissionIndex < 0 && /전형명|전형/.test(c)) indexes.admissionIndex = i;
    if (indexes.departmentIndex < 0 && /모집단위|학과|전공/.test(c)) indexes.departmentIndex = i;
    if (indexes.quotaIndex < 0 && /모집인원|모집정원|정원/.test(c)) indexes.quotaIndex = i;
    if (indexes.applicantsIndex < 0 && /지원인원|지원자수|지원자/.test(c)) indexes.applicantsIndex = i;
    if (indexes.ratioIndex < 0 && /경쟁률/.test(c)) indexes.ratioIndex = i;
  });
  return indexes;
}

function extractSourceUpdatedAt(text) {
  const patterns = [
    /(20\d{2})\s*[.\/-]\s*(\d{1,2})\s*[.\/-]\s*(\d{1,2})[^\d]{0,30}(\d{1,2})\s*:\s*(\d{2})/,
    /(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일[^\d]{0,30}(\d{1,2})\s*:\s*(\d{2})/,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (!match) continue;
    const [, y, m, d, hh, mm] = match;
    return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}T${String(hh).padStart(2, "0")}:${mm}:00+09:00`;
  }
  return null;
}

function detectRefreshMinutes(text) {
  const snippets = text.match(/.{0,40}(?:업데이트|갱신|경쟁률).{0,40}/g) || [];
  for (const snippet of snippets) {
    let match = snippet.match(/(?:매\s*)?(\d{1,3})\s*분\s*(?:단위|마다|간격)?[^\d]{0,20}(?:업데이트|갱신)/);
    if (!match) match = snippet.match(/(?:업데이트|갱신)[^\d]{0,20}(\d{1,3})\s*분/);
    if (match) {
      const n = Number(match[1]);
      if (n >= 1 && n <= 120) return n;
    }
  }
  return null;
}

function inferObservedRefreshMinutes(previous, current) {
  if (!previous || !current || current <= previous) return null;
  const diff = Math.round((current.getTime() - previous.getTime()) / 60_000);
  if (diff < 1 || diff > 120) return null;
  const common = [1, 2, 3, 5, 10, 15, 20, 30, 60, 120];
  return common.includes(diff) ? diff : null;
}

async function competitionStatus(env) {
  const rows = await env.DB.prepare(`
    SELECT target_id, university, provider, aliases_json,
           configured_source_url, discovery_url, resolved_source_url,
           configured_refresh_minutes, configured_refresh_source,
           learned_refresh_minutes, learned_refresh_source,
           last_attempt_at, last_success_at, last_source_updated_at,
           consecutive_failures, last_error, updated_at
    FROM competition_targets
    ORDER BY target_id
  `).all();
  return json({ targets: (rows.results || []).map(formatTargetState) });
}

async function competitionLatest(env, query) {
  let targetId = null;
  if (query) {
    const q = normalize(query);
    const target = COMPETITION_TARGETS.find((x) => targetMatches(x, q));
    if (!target) return json({ error: "target_not_found" }, 404);
    targetId = target.id;
  }

  const targets = targetId ? COMPETITION_TARGETS.filter((x) => x.id === targetId) : COMPETITION_TARGETS;
  const result = [];
  for (const target of targets) {
    const snapshot = await env.DB.prepare(`
      SELECT id, target_id, university, provider, source_url, source_updated_at,
             collected_at, content_hash, page_title, row_count
      FROM competition_snapshots
      WHERE target_id = ?
      ORDER BY id DESC
      LIMIT 1
    `).bind(target.id).first();
    if (!snapshot) {
      result.push({ targetId: target.id, university: target.university, snapshot: null, rows: [] });
      continue;
    }
    const rows = await env.DB.prepare(`
      SELECT admission, department, quota, applicants, ratio, cells_json, row_ordinal
      FROM competition_rows
      WHERE snapshot_id = ?
      ORDER BY row_ordinal
    `).bind(snapshot.id).all();
    result.push({
      targetId: target.id,
      university: target.university,
      snapshot,
      rows: (rows.results || []).map((r) => ({ ...r, cells: safeJson(r.cells_json, []) })),
    });
  }
  return json({ targets: result });
}

function formatTargetState(row) {
  const effective = Number(row.learned_refresh_minutes || row.configured_refresh_minutes || DEFAULT_REFRESH_MINUTES);
  const source = row.learned_refresh_source || row.configured_refresh_source;
  return {
    targetId: row.target_id,
    university: row.university,
    provider: row.provider,
    aliases: safeJson(row.aliases_json, []),
    sourceUrl: row.resolved_source_url || row.configured_source_url || null,
    discoveryUrl: row.discovery_url,
    refreshMinutes: effective,
    refreshSource: source,
    cadenceVerified: ["PUBLISHED_NOTICE", "SOURCE_NOTICE", "OBSERVED_SOURCE_TIMESTAMP"].includes(source),
    lastAttemptAt: row.last_attempt_at,
    lastSuccessAt: row.last_success_at,
    lastSourceUpdatedAt: row.last_source_updated_at,
    consecutiveFailures: Number(row.consecutive_failures || 0),
    lastError: row.last_error,
  };
}

async function markTargetError(env, targetId, now, message) {
  await env.DB.prepare(`
    UPDATE competition_targets
    SET last_attempt_at = ?,
        last_error = ?,
        consecutive_failures = consecutive_failures + 1,
        updated_at = ?
    WHERE target_id = ?
  `).bind(now.toISOString(), message, now.toISOString(), targetId).run();
}

function targetMatches(target, normalizedQuery) {
  return normalize(target.id) === normalizedQuery || normalize(target.university) === normalizedQuery || target.aliases.some((x) => normalize(x) === normalizedQuery);
}

function parseRatio(value) {
  if (value == null) return null;
  const text = String(value).replace(/,/g, "").trim();
  let match = text.match(/(\d+(?:\.\d+)?)\s*(?::|대)\s*1/);
  if (!match && /^\d+(?:\.\d+)?$/.test(text) && text.includes(".")) match = [text, text];
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
  const named = {
    amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " ",
  };
  return String(value || "")
    .replace(/&(#x[0-9a-f]+|#\d+|amp|lt|gt|quot|apos|nbsp);/gi, (_, entity) => {
      if (entity[0] === "#") {
        const n = entity[1].toLowerCase() === "x" ? parseInt(entity.slice(2), 16) : parseInt(entity.slice(1), 10);
        return Number.isFinite(n) ? String.fromCodePoint(n) : _;
      }
      return named[entity.toLowerCase()] ?? _;
    });
}

function normalize(value) {
  return String(value || "").toLowerCase().replace(/[\s·._()\-]/g, "");
}

function parseDate(value) {
  if (!value) return null;
  const time = Date.parse(value);
  return Number.isFinite(time) ? new Date(time) : null;
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
  const header = request.headers.get("authorization") || "";
  const expected = `Bearer ${token}`;
  const encoder = new TextEncoder();
  const left = encoder.encode(header);
  const right = encoder.encode(expected);
  if (left.byteLength !== right.byteLength) return false;
  return crypto.subtle.timingSafeEqual(left, right);
}

function json(value, status = 200) {
  return new Response(JSON.stringify(value), { status, headers: JSON_HEADERS });
}
