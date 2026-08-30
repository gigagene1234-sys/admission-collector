# Admission Hub Full-Automation Roadmap — 2026-08-31

이 로드맵의 목표는 **사용자가 기능 제한을 체감하지 않는 완전 자동화**다. 단, 완전 자동화는 사이트 구조와 서비스 허용 범위를 무시한 무차별 crawler를 의미하지 않는다. Hub는 provider별로 허용된 자동화 채널을 사용하고, 최종 UX는 한 번의 실행으로 통일한다.

## Target UX

사용자가 하는 일은 최대한 다음 두 가지뿐이다.

1. `통합 동기화 시작` 1회
2. 세션이 만료된 provider가 있을 때 로그인 1회

그 뒤에는 Hub가 자동으로:

- 어디가 공식정보 갱신
- 사용자 성적 기반 대학별 산출정보 갱신
- 진학사 허가된 데이터 채널 동기화
- provider별 의미 보존
- 대학/모집단위/전형 canonical mapping
- 중복/오류/누락 검증
- 지원 6장 대시보드 갱신

까지 수행한다.

---

# Phase 0 — Live topology audit [DONE]

2026-08-31 실제 공개 사이트를 직접 탐색하여 다음 구조를 확인했다.

- Adiga: 대학/학과/전형/성적분석이 분리된 deterministic 구조
- Jinhak modern UI: `www.jinhak.com/jh/high3/...`
- Jinhak legacy/service: `hijinhak.jinhak.com`
- Jinhak teacher/student management: `tong.jinhak.com`
- Jinhak login: `member.jinhak.com`
- Jinhak public university detail: `UnivCode` 기반
- Jinhak protected prediction pages: 로그인 redirect
- Jinhak public terms: protected DB의 사람/프로그램에 의한 주기적 수집 금지

Evidence document:

`SITE_STRUCTURE_AUDIT_2026-08-31.md`

Acceptance: completed.

---

# Phase 1 — Collector architecture reset

## 1.1 One orchestrator, multiple acquisition engines

기존 `supportsBatchCrawl` 하나로 모든 provider를 표현하지 않는다.

새 capability model:

```text
PUBLIC_DETERMINISTIC_COLLECTION
AUTHENTICATED_USER_WORKFLOW
AUTHORIZED_API_SYNC
AUTHORIZED_EXPORT_IMPORT
USER_VIEW_CAPTURE_FALLBACK
```

각 source가 어떤 방법으로 자동화 가능한지 명시한다.

## 1.2 UnifiedSyncSession

하나의 session이 다음 상태를 가진다.

```text
PRECHECK
  -> ADIGA_PUBLIC_SYNC
  -> ADIGA_USER_SCORE_SYNC (optional/authenticated)
  -> JINHAK_AUTHORIZED_SYNC
  -> CANONICAL_MERGE
  -> QUALITY_AUDIT
  -> HUB_PUBLISH
  -> COMPLETE
```

로그인이 필요한 경우만:

```text
*_AUTH_REQUIRED -> USER_LOGIN -> AUTO_RESUME
```

## 1.3 No manual per-page collection in final UX

현재의 `현재 페이지 수집`, `현재 화면 분석` 버튼은 debugging/admin 기능으로만 남긴다.

Acceptance:

- 일반 사용자는 provider별 페이지를 직접 순회할 필요가 없음
- 앱 process death 후 동일 UnifiedSyncSession에서 자동 재개
- provider switch가 사용자의 수동 조작을 요구하지 않음

---

# Phase 2 — Adiga deterministic full automation

## 2.1 Entity plan instead of blind crawl

현재 link discovery + pagination crawler를 다음 구조로 치환한다.

```text
AcademicYearPlan
  -> UniversityCatalog
     -> University IDs
        -> UniversityDetail
        -> Departments
        -> Admissions
        -> Current criteria
        -> Historical result sections
```

대학 상세 URL의 `searchSyr`, `unvCd`를 canonical traversal key로 사용한다.

## 2.2 Official-source enrichment

Adiga record에 대학 공식 모집요강/입시결과 출처를 추가할 수 있는 source slot을 만든다.

우선순위:

1. 대학 공식 source
2. Adiga official portal
3. other provider reference

충돌 시 원문을 덮어쓰지 않고 conflict record를 만든다.

## 2.3 Score analysis automation

사용자의 학생부/수능 정보와 Adiga 로그인 세션이 준비되면:

- 대학별성적분석 entry 탐지
- target university/admission 자동 선택
- 결과 화면 구조화
- `user-calculated-score`로 저장

CAPTCHA나 별도 사용자 확인이 등장하면 우회하지 않고 auth-required state로 전환한다.

## 2.4 Reliability

- page/action absolute timeout
- bounded retry
- blocking alert quarantine
- server error quarantine
- checkpoint per entity ID/year
- streaming export
- no full DB materialization in RAM

Acceptance:

- 이미 완료된 대학/연도는 재수집하지 않음
- 오류 1건이 전체 batch를 멈추지 않음
- 전국 entity coverage를 DB count로 검증
- 어디가 오류창 사용자 개입 0회

---

# Phase 3 — Canonical Admissions Graph

## 3.1 Identity graph

다음 canonical entity를 분리한다.

```text
University
Campus
Department / RecruitmentUnit
AdmissionTrack
AcademicYear
ProviderEntity
```

동일 대학의 provider별 표기 차이는 alias table로 관리한다.

예:

```text
국립한국교통대학교
한국교통대
국립한국교통대
```

은 canonical university에 연결하되 campus/모집단위는 별도로 확인한다.

## 3.2 Semantic layers

- `official-current-admission`
- `official-historical-result`
- `provider-public-reference`
- `jinhak-current-prediction`
- `jinhak-provider-historical-case`
- `user-calculated-score`
- `hub-derived-analysis`

Prediction은 actual을 overwrite하지 않는다.

## 3.3 Temporal model

모든 변동 source는:

- `observedAt`
- `effectiveAcademicYear`
- `providerUpdatedAt` if visible
- `supersedes`

를 지원한다.

Acceptance:

- provider 이름이 달라도 동일 모집단위로 안전하게 연결
- 불확실한 department/admission은 null 유지
- historical/prediction 혼합 0건

---

# Phase 4 — Jinhak authorized full-automation connector

이 단계가 **진학사 완전 자동화의 본체**다.

## 4.1 Interface first

앱 내부에 다음 인터페이스를 먼저 만든다.

```text
JinhakAuthorizedConnector
  discoverCapabilities()
  authenticateOrResume()
  syncStudentProfile()
  syncSavedApplications()
  syncRecommendations()
  syncPredictionReports()
  syncMockSupportReports()
  syncActualAdmitReports()
  syncScoreCalculations()
  syncSatMinimum()
```

UI는 connector implementation이 무엇인지 알 필요가 없다.

## 4.2 Authorized acquisition priority

우선순위는 아래와 같다.

### A. Official API

진학사가 공식 API를 제공하거나 별도 이용권한을 부여하면 최우선 사용한다.

### B. Official structured export

CSV/XLSX/JSON 등 공식 export가 있으면 파일 생성/변경을 감지하여 자동 import한다.

### C. Official report output

공식 PDF/print/report output을 개인적으로 저장·가공할 수 있는 범위가 확인되면 report importer를 사용한다.

### D. Licensed/partner channel

제휴/라이선스 데이터 제공이 가능하면 Cloud backend connector로 분리한다.

### E. User-view capture fallback

위 채널이 없을 때만 현재 WebView current-screen capture를 fallback으로 사용한다. 최종 UX의 주 경로가 아니다.

## 4.3 Capability discovery

다음 APK에서는 protected 데이터를 긁는 대신 **현재 로그인된 UI가 제공하는 공식 출력 기능 metadata**를 진단한다.

찾을 것:

- 다운로드 버튼
- PDF/인쇄
- Excel/CSV
- 내보내기
- 리포트 저장
- 이메일 발송
- data export/help text

수집하는 것은 버튼 label/action type과 safe path뿐이며 raw protected data를 진단 서버로 올리지 않는다.

## 4.4 Full-automation activation condition

다음 중 하나가 확인되면 Jinhak connector를 자동화 모드로 승격한다.

- documented API
- officially supported export
- explicit license/permission
- service policy상 자동 import가 허용되는 report/output

승격 후 최종 UX:

```text
통합 동기화 시작
 -> 기존 Jinhak 로그인 세션 확인
 -> connector 자동 sync
 -> report/prediction snapshot 저장
 -> merge
```

사용자의 페이지 클릭은 0회를 목표로 한다.

## 4.5 Explicitly rejected implementation

다음 방식은 완전자동화 로드맵에 포함하지 않는다.

- protected DB nationwide WebView crawler
- 반복적인 hidden endpoint 직접 호출
- CAPTCHA/session/auth bypass
- 계정 공유
- 서비스가 금지한 주기적 수집을 우회하는 rate-limit trick

이유는 기술적 불가능이 아니라 **서비스 이용조건과 충돌하기 때문**이다. 이런 방식은 안정성도 낮고 계정 차단 위험 때문에 사용 편의성을 오히려 악화시킨다.

Acceptance:

- connector가 authorized channel을 사용
- 인증 후 page-by-page 사용자 조작 0회
- prediction snapshots가 `observedAt`으로 누적
- 공식 historical과 의미 혼합 0건

---

# Phase 5 — Jinhak parser and report import library

자동화 채널과 별개로 parser는 완성한다.

지원 page/report types:

1. 학생 기본정보
2. 수시 저장소
3. 추천대학
4. 대학검색
5. 대학·학과별 합격예측
6. 모의지원 리포트
7. 합격예측 리포트
8. 실제합격자 리포트
9. 수능최저
10. 대학별 성적산출
11. 대학정보/3개년 경쟁률

대학정보 페이지는 `UnivCode`를 provider entity ID로 보존한다.

PDF/report import를 위한 공통 parser interface도 함께 둔다.

Acceptance:

- 실제 UI/official output fixture 기반 parser tests
- menu/editorial text가 record로 오인되지 않음
- cross-card inheritance 없음
- coverage metrics가 page/report type별로 노출됨

---

# Phase 6 — Zero-touch session management

## 6.1 Session persistence

- Android CookieManager
- encrypted local auth state metadata
- no password storage
- no raw cookie upload

## 6.2 Login UX

세션 유효:

`자동 진행`

세션 만료:

`해당 provider login UI만 표시 -> 로그인 성공 감지 -> 자동 복귀`

## 6.3 Session expiry handling

- expiry banner/button detection
- safe session extension when site provides official extend action
- auth redirect detection
- no repeated login loop

Acceptance:

- 정상 세션에서는 추가 로그인 0회
- 만료돼도 사용자가 로그인만 하면 원래 단계 자동 복구

---

# Phase 7 — Quality audit before Hub publish

각 sync 종료 전 자동 audit:

- provider coverage
- missing university/department/admission IDs
- duplicate identity
- year conflicts
- prediction/actual conflicts
- stale snapshot
- unresolved pages/documents
- source provenance

지원 6장 관련 대학은 별도 priority audit한다.

오류가 있어도 전체 Hub 갱신은 가능한 부분까지 진행하고 incomplete badge를 붙인다.

---

# Phase 8 — Admission Hub presentation

한 모집단위 상세 화면 예:

```text
[공식 2027 전형]
어디가/대학 공식

[공식 과거 결과]
2026 / 2025

[내 대학별 환산]
공식 계산 또는 Hub 계산

[진학사 현재 예측]
칸수 / 판정 / 내 위치 / 모의지원 지표
관측시각

[진학사 과거 사례]
provider historical case

[Hub 분석]
공식사실과 예측을 구분한 종합 평가
```

사용자에게 source semantics가 명확히 보이도록 한다.

---

# Phase 9 — Background refresh

## 9.1 Official sources

어디가/대학 공식자료는 변경 탐지를 통해 자동 갱신 가능하도록 설계한다.

## 9.2 Jinhak

background refresh는 authorized connector가 제공하는 조건 안에서만 동작한다.

- 공식 API가 polling/webhook을 허용하면 해당 방식
- export 기반이면 새 output 생성 시 import
- provider 정책상 manual refresh만 허용하면 Hub의 한 번짜리 `통합 동기화`로 실행

합격예측은 provider 자체 업데이트 주기를 고려해 무의미한 고빈도 갱신을 하지 않는다.

---

# Release order

## Next release — Architecture/Foundation

버전 번호는 구현 시 결정한다.

포함:

- ProviderCapability model
- UnifiedSyncSession state machine
- Adiga deterministic ID/year planner skeleton
- Canonical Admissions Graph schema
- `JinhakAuthorizedConnector` interface
- Jinhak official export/report capability detector
- current v0.6.6 memory/crash protections 유지

**이 릴리스에서 Jinhak protected crawler를 다시 켜지 않는다.**

## Following release — Adiga full deterministic sync

- nationwide official baseline
- score analysis workflow
- coverage auditor

## Following release — Jinhak connector activation

- capability audit 결과에 따라 API/export/report/license implementation 선택
- parser library 연결
- one-tap authenticated sync

## Following release — Hub merge/presentation

- 6장 dashboard
- provider comparison
- snapshot trend
- source-aware decision support

---

# Definition of Done — Full Automation

완전 자동화 완료 판정은 다음을 모두 만족해야 한다.

1. 사용자가 `통합 동기화 시작` 1회만 누른다.
2. 유효한 로그인 세션은 자동 재사용한다.
3. 세션 만료 시 로그인 외 페이지 조작을 요구하지 않는다.
4. 어디가 전국 공식 baseline이 entity plan으로 자동 갱신된다.
5. 사용자 성적 기반 공식/계산 점수가 자동 갱신된다.
6. 진학사 prediction/report data가 **authorized connector**로 자동 동기화된다.
7. 모든 provider data가 canonical identity로 연결된다.
8. prediction과 historical actual이 절대 섞이지 않는다.
9. 한 페이지 오류/timeout/OOM이 전체 sync를 죽이지 않는다.
10. process death 후 자동 재개한다.
11. 완료 후 Hub가 자동 갱신된다.
12. provider별 페이지를 사용자가 직접 눌러 다닐 필요가 없다.

이 12개를 모두 통과하기 전에는 '완전 자동화 완료'라고 표시하지 않는다.
