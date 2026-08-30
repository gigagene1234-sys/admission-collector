# Admission Collector / Admission Hub Architecture Review — 2026-08-30

## Status rule

This document separates **confirmed behavior** from **hypotheses**. A feature is not considered production-ready merely because code exists or an APK builds; it must also pass device evidence, parser-quality checks, and collection-completeness checks.

## Current maturity

- Adiga: Local-First collection architecture exists with persistent SQLite runs/documents/pages/records, resume planning, error checkpoints, and privacy-safe diagnostics. Automated retries are currently intentionally suspended in the app while the collection behavior is stabilized.
- Jinhak: user-assisted, authenticated single-page analysis works for the early-admission storage page. Jinhak unattended batch crawl remains intentionally disabled.
- Current main version: v0.5.8, a department-boundary diagnostic probe. It intentionally does **not** add speculative department binding.

## Confirmed Jinhak v0.5.x evolution

### v0.5.4
- Prediction UI was reduced from hundreds of metric seeds/candidate nodes to a much smaller set of logical card roots.
- Device diagnostic: 42 detected cards, 36 structured records.
- Exact duplicate logical records were largely removed.
- University binding remained 0/36, showing that metric-card extraction and identity binding are separate problems.

### v0.5.5
- Added explicit university-context inheritance from nearby/ancestor DOM regions.
- University binding rose to 31/36.
- Failure: UI strings such as close/open controls and stability bars contaminated university labels.
- Department binding remained weak.

### v0.5.6
- Normalized university labels and removed stability-bar-only summary cards when richer cards existed.
- Device diagnostic: 30 records, university 30/30, department 9/30, admission 24/30, fully bound 7/30.
- Department context resolver produced no useful inherited bindings. This falsified the assumption that department ownership could be solved by a simple nearest-heading rule.

### v0.5.7
- Switched from speculative binding to a privacy-safe structural probe.
- Device diagnostic showed hundreds of department candidates around 42 card roots, including unrelated departments visible at similar sibling/ancestor distances.
- Conclusion: the dominant department problem is DOM **boundary/ownership**, not lack of department text or regex coverage.

### v0.5.8
- Extends the structural probe with candidate university, metric/prediction presence, header-likeness, text length, candidate count, relation, depth, and distance.
- Does not change production department binding.

## Root-cause model

### 1. DOM ownership is the primary Jinhak blocker

Jinhak's storage UI exposes summary elements, detailed prediction elements, university groups, department labels, and reusable page-level navigation in overlapping DOM neighborhoods. A visually nearby node is not necessarily owned by the same application card. Therefore sibling distance alone is not a safe join key.

Required direction: infer a stable card/group boundary from DOM structure, provider identifiers, attributes, event targets, or repeating containers before binding department/admission identity.

### 2. Representation layers were previously mixed

The same application may appear as a summary bar-only representation and a richer detailed representation. Treating both as independent records inflated counts. v0.5.6's rich-card preference is the correct pattern: choose a canonical representation and preserve lower-detail views only as auxiliary evidence when useful.

### 3. Identity and metrics must remain separate

Metric extraction can be correct while university/department/admission ownership is wrong. The data pipeline must explicitly separate:
1. provider entity identity,
2. record/snapshot identity,
3. metric extraction,
4. evidence/confidence,
5. temporal observation.

Never raise confidence merely because many numeric metrics were parsed.

### 4. Dynamic rendering creates timing risk

WebView page-finished does not prove that SPA/async content has reached a stable semantic state. Snapshot collection needs a page-type-specific readiness contract, not only a navigation completion callback.

### 5. MainActivity currently owns too much state

Navigation queues, retry state, session recovery, parser triggering, local persistence, cloud resume, diagnostics, and UI state are heavily coordinated in one Activity. This is workable during prototyping but increases race/re-entry risk for nationwide collection. Move toward explicit collection state machines and provider-specific orchestration.

## Local-First lessons from Adiga

The strongest architectural result from the Adiga work is not a parser heuristic; it is the persistence model:
- local run identity,
- per-document/per-page checkpoints,
- explicit error/retry state,
- transactional local records,
- resumable plans,
- privacy-safe operational diagnostics.

This must remain the foundation for Jinhak. Cloudflare should coordinate, queue, aggregate, and back up progress; it should not emulate an authenticated browser session or become the sole source of collection state.

## Collection-completeness contract

Nationwide collection must not declare completion because a queue is empty. Completion should require reconciliation against an expected manifest:

`academicYear × provider × university × campus × admissionType × admission × department × dataScope`

For each expected item store a state such as discovered / scheduled / visited / parsed / empty-valid / blocked / retryable-error / terminal-error / verified.

A run is complete only when every expected item is in an accepted terminal state and aggregate counts satisfy consistency checks.

## Time-series model for 2027 prediction

Prediction data must use an explicit logical application key and separate observations. Proposed logical key:

`provider + academicYear + universityId + campusId + admissionId + departmentId`

Proposed observation key:

`logicalApplicationId + observedAt + metricSchemaVersion`

Do not use a content hash plus minute bucket as the permanent time-series schema. Hashes are suitable for ingestion idempotency, not for analytical identity.

Historical 2025/2026 results should be modeled separately from 2027 live prediction snapshots so that historical facts are not overwritten by changing predictions.

## Cloudflare role and load policy

Cloudflare Worker/D1/Queue should perform:
- authenticated ingestion,
- idempotent chunk processing,
- checkpoint/resume queries,
- aggregate status,
- rate-limited retry scheduling,
- compact diagnostics.

It should not perform:
- Jinhak/Adiga login,
- CAPTCHA/session circumvention,
- browser DOM rendering,
- high-frequency polling where the Android authenticated client can collect once and upload a compact result.

Use bounded chunks, backpressure, exponential/cooldown retry, and separate diagnostic runs from production collection runs.

## Security requirements

1. Split the Android signing password from `ADMISSION_INGEST_TOKEN`. Secret reuse between code signing and ingestion authentication is an unnecessary blast-radius coupling.
2. Keep credentials/cookies/CSRF/CAPTCHA/local DOM outside Cloudflare diagnostics.
3. Give diagnostic and production ingestion separate provider/run lifecycles and preferably separate scoped tokens.
4. Rotate secrets after the split and document recovery procedures.
5. Avoid long-lived diagnostic runs whose run-level collector version becomes stale; each diagnostic batch should preserve its actual client version in queryable metadata.

## Test strategy

### Static gates
- Embedded JavaScript syntax.
- Privacy-boundary assertions.
- Explicit prohibition on unattended Jinhak batch navigation until architecture review.

### Fixture parser tests
Create sanitized fixtures for every supported page type and test:
- expected card count,
- identity binding,
- metric values,
- no cross-card ownership,
- duplicate suppression,
- malformed/empty states,
- UI-layout variants.

### Device golden tests
For a known storage page, maintain an expected human-verified set of applications. Compare each version against precision/recall rather than only record count.

### Completeness tests
Test interruption, process death, login expiry, network loss, Cloudflare outage, duplicate upload, resumed run, changed page count, empty valid page, server 5xx, and partial queue processing.

### Time-series tests
Repeated captures with unchanged values should preserve the intended sampling semantics without uncontrolled duplicate growth; changed prediction metrics must create a new observation without changing logical application identity.

## Roadmap gates

### Gate A — Jinhak storage parser freeze
Required before expansion:
- clean university identity: near-100% on golden fixture,
- department/admission ownership precision high enough for decision use,
- no known cross-card joins,
- canonical summary/detail handling,
- fixture + device regression tests.

### Gate B — Provider entity discovery
Build stable university/campus/admission/department identifiers and discovery manifests. Do not depend on display names alone.

### Gate C — Historical results
Collect 2025/2026 actual-results pages independently, reconcile expected coverage, and store immutable historical-result records.

### Gate D — 2027 prediction snapshots
Capture user-authorized prediction pages into explicit observation tables, with a defined sampling cadence and completeness/quality flags.

### Gate E — Nationwide execution
Only after A–D: enable provider-specific batch navigation behind rate limits, resumable Local-First state, stop controls, health reporting, and completeness auditing.

### Gate F — Admission Hub integration
The Hub should read normalized entities, historical results, prediction observations, user-specific score calculations, quality/confidence fields, and collection freshness separately. It must expose missing/stale data instead of silently treating absence as zero.

## Current no-go conditions

Do not enable unattended nationwide Jinhak crawl while any of the following remains true:
- department ownership is heuristic and unverified,
- stable provider entity identifiers are missing,
- collection completeness cannot be reconciled,
- authenticated dynamic-page readiness is not defined,
- production/diagnostic run lifecycle is ambiguous,
- security secret reuse remains unresolved.

These are architecture gates, not minor parser bugs.
