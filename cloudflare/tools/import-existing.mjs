#!/usr/bin/env node
import fs from "node:fs/promises";
import crypto from "node:crypto";

const [,, inputPath, baseUrlArg] = process.argv;
const baseUrl = (baseUrlArg || process.env.COLLECTOR_WORKER_URL || "").replace(/\/+$/, "");
const token = process.env.COLLECTOR_INGEST_TOKEN;

if (!inputPath || !baseUrl || !token) {
  console.error(
    "Usage: COLLECTOR_INGEST_TOKEN=... node tools/import-existing.mjs <batch.json> <worker-url>\n" +
    "or set COLLECTOR_WORKER_URL."
  );
  process.exit(2);
}

const raw = await fs.readFile(inputPath, "utf8");
const data = JSON.parse(raw);

const create = await api("/v1/runs", {
  method: "POST",
  body: {
    provider: data.provider || "unknown",
    collectorVersion: data.collectorVersion || "unknown",
    metadata: {
      importedFrom: inputPath,
      sourceCollectedAt: data.collectedAt || null,
      sourceCompletion: data.completion || null,
    },
  },
});
const runId = create.runId;

const groups = new Map();

for (const snapshot of data.snapshots || []) {
  const p = pageDescriptorFromSnapshot(snapshot);
  if (!p) continue;
  const key = pageKey(p);
  if (!groups.has(key)) groups.set(key, { page: p, records: [] });
}

for (const record of data.records || []) {
  const page = {
    familyKey: familyFromSourcePage(record.sourcePage),
    requestedYear: requestedYearFromUrl(record.sourcePage) ?? record.year ?? null,
    page: Number(record.sourcePageNumber || 0) || null,
    state: "completed",
    retryCount: 0,
    errorType: null,
  };

  const key = page.page && page.familyKey
    ? pageKey(page)
    : `unpaged:${record.recordType || "record"}:${record.sourcePage || ""}`;

  if (!groups.has(key)) groups.set(key, { page: page.page ? page : null, records: [] });
  groups.get(key).records.push(record);
}

let seq = 0;
for (const group of groups.values()) {
  const chunks = chunkArray(group.records, 150);
  if (chunks.length === 0) chunks.push([]);

  for (const records of chunks) {
    seq += 1;
    await api(`/v1/runs/${encodeURIComponent(runId)}/chunks`, {
      method: "POST",
      body: {
        chunkId: `${seq}-${crypto.randomUUID()}`,
        provider: data.provider || "unknown",
        page: group.page,
        records,
      },
    });
    process.stdout.write(`queued ${seq}\r`);
  }
}

for (const err of data.errors || []) {
  seq += 1;
  const page = err.page ? {
    familyKey: err.familyKey || familyFromSourcePage(err.url),
    requestedYear: err.requestedYear ?? requestedYearFromUrl(err.url),
    page: Number(err.page),
    state: "error",
    retryCount: Number(err.retryCount || 0),
    errorType: err.type || "error",
  } : null;

  await api(`/v1/runs/${encodeURIComponent(runId)}/chunks`, {
    method: "POST",
    body: {
      chunkId: `${seq}-${crypto.randomUUID()}`,
      provider: data.provider || "unknown",
      page,
      records: [],
      error: err,
    },
  });
}

await api(`/v1/runs/${encodeURIComponent(runId)}/finish`, {
  method: "POST",
  body: {
    status: "uploaded",
    completionReason: data.completion || "imported",
    summary: data.summary || {},
  },
});

console.log(`\nImported. runId=${runId}`);
console.log(`${baseUrl}/v1/runs/${runId}/status`);

async function api(path, { method, body }) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: {
      "authorization": `Bearer ${token}`,
      "content-type": "application/json",
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

  const text = await response.text();
  let parsed;
  try { parsed = text ? JSON.parse(text) : {}; }
  catch { parsed = { raw: text }; }

  if (!response.ok) {
    throw new Error(`${response.status} ${JSON.stringify(parsed)}`);
  }
  return parsed;
}

function chunkArray(items, size) {
  const out = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

function pageDescriptorFromSnapshot(snapshot) {
  const page = Number(snapshot.collectionPage || snapshot.collectionPagination?.page || 0);
  const familyKey = snapshot.collectionPagination?.familyKey || familyFromSourcePage(snapshot.url);
  if (!page || !familyKey) return null;
  return {
    familyKey,
    requestedYear:
      snapshot.collectionPagination?.requestedYear ??
      requestedYearFromUrl(snapshot.url),
    page,
    state: snapshot.pageState?.isError ? "error" : "completed",
    retryCount: Number(snapshot.collectionPagination?.retry || 0),
    errorType: snapshot.pageState?.errorType || null,
  };
}

function pageKey(page) {
  return `${page.familyKey}|${page.requestedYear ?? "null"}|${page.page}`;
}

function familyFromSourcePage(url) {
  if (!url) return "";
  try {
    const u = new URL(url);
    const menuId = u.searchParams.get("menuId");
    return `${u.pathname}${menuId ? `?menuId=${menuId}` : ""}`;
  } catch {
    return "";
  }
}

function requestedYearFromUrl(url) {
  if (!url) return null;
  try {
    const value = Number(new URL(url).searchParams.get("searchSyr"));
    return Number.isInteger(value) ? value : null;
  } catch {
    return null;
  }
}
