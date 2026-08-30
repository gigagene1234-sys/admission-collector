# Jinhak Collection Plan — Revised 2026-08-30

## Final goal

Admission Hub의 전국 공통 입시정보는 **어디가와 대학 공식 출처를 기준 데이터**로 구축한다. 진학사는 여기에 사용자가 정상적으로 열람할 수 있는 범위에서 얻는 **개인화 합격예측·모의지원·실제합격자 사례·대학별 환산정보를 overlay**하는 역할을 맡는다.

진학사 수시 대학검색 페이지는 서비스 DB에 대해 사람 또는 프로그램에 의한 수집 및 프로그램에 의한 주기적 수집 이용을 금지한다고 명시한다. 따라서 이전 계획의 “진학사를 어디가처럼 unattended 전국 자동 crawl”은 폐기한다. 진학사가 명시적으로 허용한 API/export/license가 확인되지 않는 한 주기적·대량 자동수집을 구현하지 않는다.

## Data layers

### 1. Nationwide official/common admissions baseline

주 데이터 소스: 어디가 + 각 대학 공식 모집요강/입시결과.

- 2027 current admission: 대학, 캠퍼스, 학과/모집단위, 전형, 모집인원, 지원자격, 수능최저, 전형방법, 일정 등.
- 2026 historical official result.
- 2025 historical official result.
- 어디가에서 확인되지 않는 항목은 대학 공식 자료로 보완하되 source를 명시한다.

### 2. Jinhak user-viewed admissions overlay

사용자가 진학사에서 정상적으로 열람하는 읽기 전용 화면을 로컬에서 구조화한다.

- 수시 저장소 / 저장한 모의지원 모집단위
- 대학·학과별 합격예측
- 모의지원 리포트
- 합격예측 리포트
- 실제합격자리포트
- 추천대학 / 대학검색에서 사용자가 확인한 모집단위
- 수능최저, 대학별 환산점수/환산등급 등 명시적으로 표시된 지표

### 3. Jinhak prediction time-series

예측 데이터는 historical actual과 분리한다.

- stability bars / 합격예측 결과
- 합격률/합격가능성(명시된 경우만)
- 모의지원자 수/경쟁률
- 내 순위, 예상 합격선, 충원 관련 예측값
- 대학별 환산점수/등급
- `observedAt`
- stable `applicationIdentityKey`

합격예측 리포트가 주기적으로 업데이트되는 서비스라는 공식 안내를 고려해, 의미 없는 고빈도 주기 수집을 하지 않는다.

### 4. Jinhak historical provider cases

진학사의 실제합격자리포트는 과거 합격자 사례/분포라는 별도 의미로 저장한다.

- `historical-provider-case`
- 공식 어디가 50/70% 결과 등과 동일한 값으로 취급하지 않음
- source/provider semantics를 Hub에서 명확히 표시

## Safety, integrity and service-boundary rules

- Android WebView owns authenticated rendering.
- passwords, cookies, session tokens, CSRF values, CAPTCHA data를 업로드하지 않는다.
- raw authenticated DOM을 Cloud diagnostic으로 보내지 않는다.
- Jinhak protected database에 대한 unattended/periodic mass collection을 구현하지 않는다.
- CAPTCHA/session/authentication bypass를 구현하지 않는다.
- submission/payment/delete/account-change actions를 자동 수행하지 않는다.
- 대학/학과/전형 context는 같은 모집단위 구조에서 확인된 경우만 결합한다.
- uncertain context는 null + low/raw confidence로 남긴다.
- 2027 prediction을 2027 actual result로 표기하지 않는다.
- Local SQLite is the beta source of truth.
- Cloudflare is not used for routine page/data collection; only small privacy-safe diagnostics and later permitted incremental sync.

## Sequential gates

### Gate A — Early-storage parser acceptance (current: v0.5.7 probe)

Current verified state from v0.5.6:

- page type `jinhak-early-storage` verified
- 42 detected card roots → 30 retained prediction records after summary-only cleanup
- university binding 30/30
- department binding 9/30
- admission binding 24/30
- fully bound university+department+admission 7/30

Next:

- v0.5.7 department context probe를 실제 수시저장소에서 1회 검증
- direct/previous/next/ancestor/near-child 관계를 근거로 department binding rule 확정
- 다른 카드 context를 빌려오는 추론 금지
- probe 완료 후 diagnostic-only 후보정보 제거

Acceptance conditions:

- no polluted university labels
- no cross-card university/department/admission inheritance in validated sample
- summary/detail duplicates correlated by identity, not global heuristic only
- uncertain fields remain null
- stable application identity introduced

### Gate B — Local DB v2 and clean Jinhak run

Before Hub integration:

- implement SQLite schema migration (`onUpgrade`)
- add `capture_version`, `data_scope`, `observed_at`, `quality_state`
- add provider/canonical identity fields
- quarantine existing v0.5.x Jinhak beta run; do not silently mix old false records with accepted parser output
- start a clean accepted Jinhak run
- preserve Adiga data unchanged
- distinguish newly inserted / replaced / superseded counts
- stream/paginate large exports instead of loading the whole run into memory

### Gate C — Page-specific user-initiated analyzers

Implement dedicated read-only parsers, one page type at a time:

1. 수시 저장소
2. 대학검색 결과 currently viewed by the user
3. 대학·학과별 합격예측
4. 모의지원 리포트
5. 합격예측 리포트
6. 실제합격자리포트
7. 수능최저/성적산출 related read-only pages

GenericAdmissionParser is fallback only. Each dedicated parser must have synthetic regression fixtures using fictitious institutions, never the user's real admissions data in the public repository.

### Gate D — Canonical identity / provider merge

- keep Jinhak raw label and Adiga raw label
- introduce canonical university/campus/department/admission identity
- prefer explicit non-sensitive provider entity IDs when safely available
- allowlist only identity-related URL parameters locally; continue stripping sensitive parameters
- account for yearly department/admission renaming

### Gate E — Nationwide official baseline completion

Use Adiga and official university sources to establish nationwide coverage.

Completeness is verified from entity/record coverage, not only run completion status.

The deferred Adiga Hanbat page 381 recovery remains a targeted task after Jinhak parser acceptance. Do not rerun unrelated completed pages.

### Gate F — Jinhak overlay accumulation

When the user views supported Jinhak pages:

- persist structured records locally
- preserve prediction snapshots at meaningful update points
- correlate the same saved application through stable identity
- keep Jinhak historical cases separate from official actual results
- export only incremental accepted records to Hub later

### Gate G — Optional permitted bulk interface

Only if Jinhak explicitly provides a permitted API/export/license or other authorized bulk data path:

- design a separate importer for that interface
- keep rate, access and data-use conditions explicit
- never repurpose the authenticated WebView as an unattended periodic crawler

### Gate H — Admission Hub integration

Hub data layers must remain distinguishable:

- `official-current-admission`
- `official-historical-result`
- `jinhak-historical-provider-case`
- `jinhak-current-prediction`
- `user-calculated-score`
- AI-derived analysis (separate from raw/provider facts)

## Engineering quality gates

Before future parser expansion:

- one canonical Android source tree; remove duplicate root `MainActivity.kt`
- stop version-specific Python string patching as the normal release path
- CI builds/tests committed source and does not modify main
- extract embedded SnapshotScript JavaScript and run syntax validation
- synthetic DOM fixtures for card boundary/context binding/metrics
- bounded retry for every navigational retry path
- content identity proof before checkpoint completion
- separate APK signing secret from Cloud ingest token
- classify diagnostic messages separately from runtime errors

## Reference

Detailed analysis: `JINHAK_ARCHITECTURE_FAILURE_ANALYSIS_2026-08-30.md`

Official Jinhak public references checked 2026-08-30:

- https://www.jinhak.com/jh/high3/early/manual
- https://www.jinhak.com/jh/high3/early/four-year-university/search
- https://www.jinhak.com/jh/high3/jinhak-tv/1921
