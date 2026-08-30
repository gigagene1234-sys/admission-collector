# Jinhak Collection Plan — Revised 2026-08-30

## Final goal

Admission Hub의 전국 공통 입시정보는 **어디가와 대학 공식 출처를 기준 데이터**로 구축한다. 진학사는 그와 별개로 사용자가 정상적으로 확인하는 합격예측·모의지원·실제합격자 리포트의 의미를 분석하는 보조 계층으로 다룬다.

진학사 수시 대학검색 페이지는 서비스 DB에 대해 **사람에 의한 수집 및 프로그램에 의한 주기적 수집 이용**을 금지한다고 명시한다. 공개 문구만으로 개인 사용자의 제한적 로컬 구조화·보관이 어느 범위까지 허용되는지는 **제공된 정보로는 확인할 수 없습니다.** 따라서 이전 계획의 “진학사를 어디가처럼 전국 자동 crawl/DB화”는 폐기하고, 진학사에서 명시적으로 허용한 API/export/license 또는 별도 허가 범위가 확인되기 전에는 **전국·지속적 진학사 데이터 축적 기능을 구현하지 않는다.**

현재 v0.5.x 작업은 대량수집기가 아니라 **사용자가 직접 연 화면에서 파서가 무엇을 올바르게/잘못 읽는지 확인하는 최소 진단 단계**로 한정한다. 진학사 원본 데이터를 장기간·대규모로 축적하는 production 기능은 service-boundary 확인 전까지 acceptance 대상이 아니다.

## Data layers

### 1. Nationwide official/common admissions baseline

주 데이터 소스: 어디가 + 각 대학 공식 모집요강/입시결과.

- 2027 current admission: 대학, 캠퍼스, 학과/모집단위, 전형, 모집인원, 지원자격, 수능최저, 전형방법, 일정 등.
- 2026 historical official result.
- 2025 historical official result.
- 어디가에서 확인되지 않는 항목은 대학 공식 자료로 보완하되 source를 명시한다.

이 계층이 “모든 대학의 입시정보” 목표를 담당한다.

### 2. Jinhak on-demand analysis layer

service-boundary 확인 전에는 사용자가 직접 연 화면에 대한 일회성/최소 분석만 대상으로 한다.

현재 파서가 인식하는 후보 화면:

- 수시 저장소 / 저장한 모의지원 모집단위
- 대학·학과별 합격예측
- 모의지원 리포트
- 합격예측 리포트
- 실제합격자리포트
- 추천대학 / 대학검색의 현재 열람 화면
- 수능최저, 대학별 환산점수/환산등급 등 명시적으로 표시된 지표

대규모 persistent ingestion은 허용된 경로가 확인되기 전까지 보류한다.

### 3. Prediction semantics

예측 데이터는 historical actual과 분리한다.

- stability bars / 합격예측 결과
- 합격률/합격가능성(명시된 경우만)
- 모의지원자 수/경쟁률
- 내 순위, 예상 합격선, 충원 관련 예측값
- 대학별 환산점수/등급
- 관측시각

진학사 공식 가이드상 합격예측과 모의지원 리포트는 업데이트 성격이 다를 수 있으므로, service-boundary가 해결되더라도 의미 없는 고빈도 주기 수집을 설계하지 않는다.

### 4. Jinhak historical provider cases

진학사의 실제합격자리포트는 과거 합격자 사례/분포라는 별도 의미로 해석한다.

- 공식 어디가 50/70% 결과 등과 동일한 값으로 취급하지 않음
- source/provider semantics를 Hub에서 명확히 표시
- persistent import는 허용 범위가 확인된 뒤에만 구현

## Safety, integrity and service-boundary rules

- Android WebView owns authenticated rendering.
- passwords, cookies, session tokens, CSRF values, CAPTCHA data를 업로드하지 않는다.
- raw authenticated DOM을 Cloud diagnostic으로 보내지 않는다.
- Jinhak protected database에 대한 unattended/periodic mass collection을 구현하지 않는다.
- nationwide/persistent Jinhak aggregation은 permission/API/export/license 확인 전까지 구현하지 않는다.
- CAPTCHA/session/authentication bypass를 구현하지 않는다.
- submission/payment/delete/account-change actions를 자동 수행하지 않는다.
- 대학/학과/전형 context는 같은 모집단위 구조에서 확인된 경우만 결합한다.
- uncertain context는 null + low/raw confidence로 남긴다.
- 2027 prediction을 2027 actual result로 표기하지 않는다.
- Cloudflare는 routine page/data collection에 사용하지 않는다.
- current diagnostic은 사용자가 명시적으로 실행한 privacy-minimized parser 검증에 한정한다.

## Sequential gates

### Gate A — Early-storage parser correctness (current: v0.5.7 probe)

Current verified state from v0.5.6:

- page type `jinhak-early-storage` verified
- 42 detected card roots → 30 retained prediction records after summary-only cleanup
- university binding 30/30
- department binding 9/30
- admission binding 24/30
- fully bound university+department+admission 7/30

Next after the user returns:

- v0.5.7 department context probe를 동일 수시저장소 화면에서 1회 검증
- direct/previous/next/ancestor/near-child 관계를 근거로 department binding rule 확정
- 다른 카드 context를 빌려오는 추론 금지
- probe 완료 후 diagnostic-only 후보정보 제거

Acceptance conditions for parser correctness:

- no polluted university labels
- no cross-card university/department/admission inheritance in validated sample
- summary/detail duplicates correlated by identity, not global heuristic only
- uncertain fields remain null

이 gate는 “대량 저장 허용” 판정이 아니라 parser correctness 판정이다.

### Gate B — Local DB integrity redesign

기존 v0.5.x Jinhak beta 분석 레코드에는 서로 다른 parser 세대의 오탐이 같은 run에 혼재할 위험이 있다. service-boundary와 별개로 저장소 자체는 다음과 같이 정비한다.

- SQLite schema migration (`onUpgrade`) 설계
- `capture_version`, `data_scope`, `observed_at`, `quality_state` 추가
- provider/canonical identity 설계
- 기존 v0.5.x Jinhak beta run은 `legacy-beta`로 격리할 수 있게 설계
- 어디가 데이터는 변경하지 않음
- 신규/갱신/superseded 카운트 분리
- 전체 run 메모리 로드 대신 streaming/paging 설계

실제 Jinhak production accumulation을 활성화하는 것은 허용 경로 확인 이후다.

### Gate C — Page-specific parser library

파서 자체는 fictitious/synthetic fixture를 이용해 개발·검증할 수 있다.

1. 수시 저장소
2. 대학검색 결과
3. 대학·학과별 합격예측
4. 모의지원 리포트
5. 합격예측 리포트
6. 실제합격자리포트
7. 수능최저/성적산출 읽기 화면

GenericAdmissionParser는 fallback으로 제한한다. public repository의 fixture에는 사용자의 실제 대학 지원/성적 데이터를 넣지 않는다.

### Gate D — Canonical identity / provider merge design

- Jinhak raw label과 Adiga raw label의 개념적 mapping 구조 설계
- canonical university/campus/department/admission identity
- 학년도별 학과/전형 개편 대응

Jinhak provider IDs의 실제 수집·보존은 허용 범위 확인 뒤 결정한다.

### Gate E — Nationwide official baseline completion

Use Adiga and official university sources to establish nationwide coverage.

Completeness is verified from entity/record coverage, not only run completion status.

The deferred Adiga Hanbat page 381 recovery remains a targeted task after the current Jinhak parser analysis cycle. Do not rerun unrelated completed pages.

### Gate F — Jinhak service-boundary resolution

전국 또는 장기 축적을 다시 논의하려면 먼저 다음 중 하나가 필요하다.

- 진학사가 명시적으로 제공하는 허용 API
- 명시적 export/import 사용 허가 범위
- license/제휴/별도 서면 허가
- 이용약관/서비스 정책상 개인적 구조화·보관 범위에 대한 충분한 확인

그 전에는 protected DB를 체계적으로 축적하는 기능을 production 목표로 두지 않는다.

### Gate G — Optional permitted importer

Gate F가 충족된 경우에만 별도 importer를 설계한다.

- authorized interface only
- explicit rate/access/data-use conditions
- no CAPTCHA/session bypass
- no hidden unattended periodic WebView crawler

### Gate H — Admission Hub integration

Hub data layers must remain distinguishable:

- `official-current-admission`
- `official-historical-result`
- `jinhak-derived-analysis` 또는 허가된 경우 `jinhak-*` provider layer
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
