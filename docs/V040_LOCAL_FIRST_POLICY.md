# Admission Collector v0.4.0 Local-First Policy

## Goal
Complete the Adiga collector without increasing Cloudflare workload during the beta period.

## Collection policy
- 2027: current university / department / admission information.
- 2027 university detail: current 2027 criteria + 2026 actual admission-result section.
- 2026 university detail: current 2026 criteria + 2025 actual admission-result section.
- 2027 and 2026 admission search pages are retained because each exposes previous-year competition/result fields.
- The very large 2026 department list is intentionally not seeded; prior device runs showed it duplicated the 2027 list and it is not required for the 2025 historical result objective.

## Local-first state
- Cloudflare is not called from the Adiga batch loop in v0.4.0.
- SQLite stores run state, document checkpoints, pagination checkpoints, normalized records, and terminal errors.
- Stopped/incomplete runs are resumed instead of restarted.
- Dynamic first pages are revisited to rebuild total-page plans; already completed calculated pages are skipped from SQLite checkpoints.
- Completed static detail documents are skipped across app restarts.
- A batch with unresolved local errors is marked incomplete and can be resumed on the next run.

## Cloud production
Cloudflare Worker/D1 production remains on v0.3.9 and is deliberately not changed or deployed by the v0.4.0 build workflow.
