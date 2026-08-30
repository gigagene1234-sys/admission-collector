# Jinhak Collection Plan

## Final goal
Build a Local-First authenticated WebView collector for Jinhak that reaches the same practical coverage goal as the Adiga collector for nationwide university admissions information, then adds Jinhak-only prediction data as time-series snapshots.

## Data layers

### 1. Nationwide common admissions data
Target every accessible university / department / admission track, with explicit year and role separation.
- 2027 current admission information: university, department, admission track, capacity, eligibility, minimum CSAT requirements, evaluation method, schedule and other structured admissions fields exposed by Jinhak.
- 2026 historical result information where Jinhak exposes it.
- 2025 historical result information where Jinhak exposes it.
- Historical metrics may include competition, registered/admitted grade or score distributions, 50/70 percent cuts, additional admits and other explicitly displayed result fields.

### 2. Jinhak-only prediction layer
Treat prediction data as volatile observations, never as historical actual admission results.
- Early-storage / saved simulated applications.
- Acceptance prediction / stability bars.
- Acceptance probability when explicitly displayed.
- Mock applicant count and competition.
- My rank / predicted cut / support judgment when explicitly displayed.
- Student-specific converted score or grade when available on the authenticated page.
- Every prediction record keeps `observedAt` and is preserved as a time-series snapshot.

## Safety and data-integrity rules
- Android WebView owns authenticated navigation and rendering.
- Never upload passwords, cookies, session tokens, CSRF values, CAPTCHA data or raw authenticated DOM to diagnostics.
- A prediction metric must be bound to the university / department / admission track found in the same local DOM card or row. Do not borrow context from another card.
- If university / department / admission context is uncertain, preserve null/low confidence instead of guessing.
- 2027 prediction data must never be labeled as 2027 actual results.
- Local SQLite is the durable source of truth during beta collection.
- Cloudflare is excluded from routine bulk collection while Local-First beta is active; only privacy-safe small diagnostics may be sent when explicitly used.

## Sequential phases

### Phase A — Early-storage card parser (v0.5.3)
- Classify `수시저장소` before generic prediction pages.
- Segment each saved/mock application into its own card-level record.
- Extract prediction metrics only inside that card.
- Save time-series snapshots locally.
- Validate with the user's actual early-storage page.

### Phase B — Route and navigation discovery
- Identify Jinhak university-search/list routes and university-detail/report routes from the authenticated WebView.
- Build a bounded navigation graph and checkpoint it locally.
- Avoid actions related to application submission, payment, deletion or account changes.

### Phase C — Nationwide current admissions crawl
- Enumerate accessible universities, departments and admission tracks.
- Normalize 2027 current admission fields.
- Add local checkpoint/resume, dedupe and per-document error handling.

### Phase D — Historical-results crawl
- Discover and parse 2026 and 2025 actual result views where explicitly available.
- Keep `historical-result` separate from current admission and prediction records.
- Validate counts and university/department coverage, not just completion status.

### Phase E — Prediction crawl
- Traverse prediction/report pages for relevant accessible admission tracks.
- Store `observedAt` snapshots without overwriting prior observations.
- Prefer saved/mock-supported tracks first, then expand only where the authenticated account/site exposes prediction data.

### Phase F — Completeness verification and Hub integration
- Compare discovered university / department / admission counts across Jinhak and Adiga where comparable.
- Flag missing/ambiguous records instead of silently filling gaps.
- Export incremental normalized records to Admission Hub.
- Revisit the deferred Hanbat Adiga page after Jinhak analysis work, as a separate recovery task.
