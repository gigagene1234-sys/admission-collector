# Jinhak Collection Plan — Revised 2026-08-31

## 0. Architecture decision

Admission Hub의 **최종 사용자 경험 목표는 완전 자동화**다.

최종 UX:

`통합 동기화 시작 1회 -> 필요한 경우 로그인 1회 -> 자동 수집/동기화 -> canonical merge -> Hub 갱신`

사용자가 진학사 페이지를 하나씩 직접 열어야 하는 방식은 최종 제품의 acceptance 조건이 아니다.

다만 2026-08-31 실제 사이트 구조를 다시 조사한 결과, 진학사 수시 대학검색/결제안내에는 서비스 DB에 대해 **사람에 의한 수집 및 프로그램에 의한 주기적 수집 이용을 금지**하는 문구가 명시되어 있다. 따라서 v0.6.6처럼 WebView가 보호된 진학사 사이트를 무차별적으로 순회하는 crawler는 완전 자동화의 본체로 사용하지 않는다.

대신 Hub는 `JinhakAuthorizedConnector`를 중심으로 설계한다. 공식 API/export/report/license/허용 채널이 확인되는 즉시 UI 재설계 없이 진학사도 완전 자동 동기화할 수 있도록 한다.

또한 **현재 parser가 이해하지 못하거나 현재 기능에서 사용하지 않는 진학사 정보도 곧바로 불필요하다고 판정하지 않는다.** 진학사는 관람 시점, 로그인 상태, 저장소/지원 상태, 선택 대학·학과·전형, 성적 입력 상태, 리포트 갱신 시점에 따라 동일 경로에서도 노출 정보가 달라질 수 있기 때문이다. 계산량을 줄이는 것과 관찰 정보를 폐기하는 것은 분리한다.

Observation 보존 정책:

- `OBSERVATION_PRESERVATION_POLICY.md`

상세 구조 감사:

- `SITE_STRUCTURE_AUDIT_2026-08-31.md`

전체 자동화 로드맵:

- `ADMISSION_HUB_FULL_AUTOMATION_ROADMAP.md`

## 1. Final goal

Admission Hub의 전국 공통 입시정보는 **어디가와 대학 공식 출처를 기준 데이터**로 구축한다.

진학사는 별도 provider semantics를 유지한다.

- 현재 합격예측
- 모의지원
- 실제합격자 리포트
- 추천대학
- 대학별 환산점수/등급
- 수능최저
- provider historical case
- 현재 parser가 아직 구조화하지 못한 provider observation

진학사 prediction은 공식 historical actual을 절대 덮어쓰지 않는다.

## 2. Verified Jinhak topology

2026-08-31 공개 사이트에서 다음 구조를 확인했다.

### Modern high3/N수 UI

- `/jh/high3/early/four-year-university/search` — 수시 대학검색
- `/jh/high3/early/four-year-university/recommend-university` — 추천대학
- `/jh/high3/early/four-year-university/university-major-predict` — 대학·학과별 합격예측
- `/jh/high3/early/four-year-university/curation` — 큐레이션
- `/jh/high3/early/four-year-university/library` — 수시 저장소

추천대학/대학학과별 합격예측/저장소는 비로그인 상태에서 `member.jinhak.com` 로그인으로 redirect되는 것이 확인됐다.

### Public university info

- `/jh/high3/univ-major/univ-info/univ-search`
- `/jh/high3/univ-major/univ-info/univ-search/detail?Flag=<n>&UnivCode=<ID>`

확인된 provider IDs:

- 국립한밭대학교 `3004`
- 우송대학교 `3011`
- 국립한국교통대학교 `3015`
- 충남대학교 `1140`

대학 상세에는 최근 3년 경쟁률, 전형/모집단위별 3개년 경쟁률, 합격자 평균점수, 모집요강/입시결과 자료 등이 존재한다.

### Other domains

- `hijinhak.jinhak.com` — legacy 합격예측/성적 서비스 일부
- `tong.jinhak.com` — 진학통/합격통 학생관리 프로그램
- `member.jinhak.com` — login/member

## 3. Official Jinhak user flow

2027 수시 이용가이드 기준:

1. 성적입력
   - 학생부
   - 모평
2. 성적분석
   - 학생부 교과분석
   - 내성적대 지원경향
   - 수능최저
3. 모의지원
   - 대학검색
   - 추천대학
   - 대학·학과별 합격예측
   - 큐레이션
4. 합격예측 리포트
   - 수시 저장소

리포트:

- 모의지원 리포트
- 합격예측 리포트
- 실제합격자 리포트

이 구조가 Jinhak connector state graph의 기준이다.

## 4. Data layers

### 4.1 Official nationwide baseline

주 데이터 소스:

- 대학 공식 자료
- 어디가

포함:

- current admissions
- historical official results
- 모집단위/전형/모집인원
- 지원자격
- 수능최저
- 전형방법
- 일정
- 사용자 대학별 환산결과

### 4.2 Jinhak provider layer

source semantics를 유지한다.

- `jinhak-current-prediction`
- `jinhak-mock-support`
- `jinhak-provider-historical-case`
- `jinhak-score-calculation`
- `jinhak-sat-minimum`
- `jinhak-public-reference`

모든 변동값은 `observedAt`을 가진다.

### 4.3 Observation Evidence layer

Structured provider record보다 앞에 `Observation Evidence` 계층을 둔다.

진학사 관찰 화면은 다음 중 하나로 처리한다.

- `structured-useful-now`
- `structured-reference`
- `unknown-potential-value`
- `exact-duplicate`
- `ui-noise`
- `privacy-redacted`
- `storage-prohibited`

`unknown-potential-value`는 삭제 상태가 아니다. 현 parser가 아직 이해하지 못했다는 뜻이며 향후 재처리 대상이다.

같은 URL이라도 다음 context가 달라지면 별도 observation 가치가 있을 수 있다.

- observedAt
- auth state
- 선택 대학
- 선택 모집단위/학과
- 선택 전형
- 저장/지원 상태
- 입력된 성적 상태
- 활성 탭
- 리포트 종류
- provider update state

따라서 URL-only dedupe는 금지한다.

## 5. Prediction semantics

예측 데이터는 historical actual과 분리한다.

- stability bars / 칸수
- prediction label
- 합격률/합격가능성(명시된 경우만)
- 모의지원자 수/경쟁률
- 분석대상자
- 내 순위
- 예상 합격선
- 충원 관련 예측값
- 대학별 환산점수/등급
- 관측시각

진학사 공식 가이드상 합격예측 리포트는 실시간이 아니라 provider 업데이트 시점에 따라 변경될 수 있으므로 snapshot history를 유지한다.

최신 snapshot 하나만 남기고 과거 observation을 덮어쓰지 않는다.

## 6. Automation strategy

### 6.1 Do not lower user convenience

최종 제품에서는 페이지별 manual collection을 요구하지 않는다.

현재 user-view capture는 **fallback/diagnostic**일 뿐 최종 UX가 아니다.

### 6.2 JinhakAuthorizedConnector

아래 인터페이스를 아키텍처 중심으로 둔다.

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

### 6.3 Authorized acquisition priority

1. official API
2. official CSV/XLSX/JSON export
3. officially allowed PDF/report output import
4. license/partner data channel
5. user-view capture fallback

공개 정보만으로 현재 API/구조화 export 존재 여부는 확인할 수 없다.

### 6.4 Next capability probe

다음 구현 단계에서는 protected DB를 crawl하지 않고 로그인된 UI에서 다음 **공식 출력 기능 metadata**를 탐지한다.

- download
- Excel/CSV
- export
- PDF
- print/report
- email report
- save

버튼 label, safe path, action type만 기록한다. raw protected DOM/credentials/session token은 업로드하지 않는다.

### 6.5 Preserve observations before optimization

수집·분석 비용을 줄일 때 우선순위는 다음과 같다.

1. 반복 DOM 계산 제거
2. exact duplicate fingerprint 억제
3. navigation chrome reference화
4. SQLite paging/streaming
5. observation compression
6. derived analysis lazy computation

다음 방식은 금지한다.

- `jinhak-other`라서 observation 삭제
- 현 지원대학과 직접 관련 없어 보여서 삭제
- 현재 parser가 쓸 필드가 없어서 삭제
- 동일 URL이라서 시점/상태가 다른 snapshot 병합

## 7. Safety, integrity and service-boundary rules

- Android WebView owns authenticated rendering.
- password를 앱 DB에 저장하지 않는다.
- cookies/session tokens/CSRF/CAPTCHA data를 diagnostic으로 업로드하지 않는다.
- raw authenticated DOM을 Cloud diagnostic으로 보내지 않는다.
- CAPTCHA/session/authentication bypass를 구현하지 않는다.
- submission/payment/delete/account-change actions를 자동 수행하지 않는다.
- 계정 공유를 전제로 설계하지 않는다.
- 대학/학과/전형 context는 같은 모집단위 구조에서 확인된 경우만 결합한다.
- uncertain context는 null + low/raw confidence로 남긴다.
- 2027 prediction을 2027 actual result로 표기하지 않는다.
- Jinhak protected database의 unattended/periodic mass WebView crawl은 구현하지 않는다.
- hidden endpoint를 직접 호출하여 UI/정책을 우회하지 않는다.
- 저장이 허용되지 않는 원본은 observation evidence에도 보존하지 않는다.

이 제한은 **자동화 목표를 포기하는 것이 아니라 자동화 acquisition channel을 올바르게 선택하기 위한 것**이다.

## 8. Parser library

지원 대상:

1. 수시 저장소
2. 추천대학
3. 대학검색
4. 대학·학과별 합격예측
5. 모의지원 리포트
6. 합격예측 리포트
7. 실제합격자 리포트
8. 수능최저
9. 성적산출
10. 대학정보/3개년 경쟁률

GenericAdmissionParser는 fallback으로 제한한다.

Cross-card department inheritance는 금지한다.

Parser가 이해하지 못한 observation은 `unknown-potential-value`로 남기고 parser coverage의 입력으로 사용한다.

새 parser가 배포되면 기존 observation을 다시 처리할 수 있어야 하며, 사이트 재방문이 필수여서는 안 된다.

## 9. Canonical identity

다음 entity를 분리한다.

- University
- Campus
- RecruitmentUnit
- AdmissionTrack
- AcademicYear
- ProviderEntity

provider labels는 alias로 canonical entity에 연결한다.

학년도별 명칭 변경/통폐합을 지원한다.

Observation identity와 canonical entity identity는 별개로 관리한다. 같은 모집단위라도 관찰시점이 다른 prediction snapshot은 별도 observation이다.

## 10. Sequential gates

### Gate A — Site topology audit [DONE]

`SITE_STRUCTURE_AUDIT_2026-08-31.md`

### Gate B — Provider capability architecture

- ProviderCapability model
- UnifiedSyncSession
- JinhakAuthorizedConnector interface
- Observation Evidence store/reprocessing contract

### Gate C — Local DB/canonical graph

- capture_version
- data_scope
- observed_at
- quality_state
- canonical IDs
- provider IDs
- observation ID/content fingerprint
- streaming/paging

### Gate D — Adiga deterministic sync

전국 공식 baseline을 entity ID/year plan으로 자동 갱신한다.

기존 완료 페이지를 무작정 재수집하지 않는다.

### Gate E — Jinhak capability discovery

실제 계정 UI에서 official export/report/API 단서를 안전하게 탐지한다.

동시에 현재 parser가 이해하지 못한 화면도 observation coverage로 기록한다.

### Gate F — Authorization resolution

다음 중 하나를 확보한다.

- documented API
- supported export/import
- license/partnership
- explicit permission
- policy상 허용되는 report/output import

### Gate G — Authorized connector implementation

Gate F 결과에 맞춰 API/export/report connector를 구현한다.

### Gate H — One-tap Jinhak sync

로그인 세션이 유효하면 page-by-page 사용자 조작 없이 provider sync를 끝낸다.

### Gate I — Hub integration

- official-current-admission
- official-historical-result
- jinhak-current-prediction
- jinhak-provider-historical-case
- user-calculated-score
- hub-derived-analysis

을 한 모집단위 화면에서 의미를 분리해 표시한다.

표시에 쓰이지 않는 observation은 재처리 가능한 provenance 계층에 남는다.

## 11. Definition of Done — Jinhak automation

진학사 자동화 완료라고 부르려면:

1. 통합 sync 한 번으로 시작
2. 기존 로그인 세션 자동 재사용
3. 만료 시 로그인만 요구
4. page-by-page 사용자 클릭 0회
5. authorized connector를 통한 prediction/report sync
6. observedAt snapshot history
7. parser quality audit
8. canonical merge
9. process death 자동 복구
10. Hub 자동 갱신
11. 현재 parser가 이해하지 못한 허용 범위 내 observation을 임의 폐기하지 않고 재처리 가능하게 보존

을 모두 통과해야 한다.

그 전에는 '완전 자동화 완료'라고 표시하지 않는다.

## 12. Engineering quality gates

- one canonical Android source tree
- version-specific Python string patching을 일반 release path에서 제거
- CI가 generated source를 main에 다시 쓰지 않도록 정리
- SnapshotScript syntax test
- parser fixtures
- bounded retry
- content identity proof
- signing secret와 ingest token 분리
- runtime event와 diagnostic 분리
- streaming export 유지
- OOM regression test 유지
- URL-only dedupe 금지
- unknown observation 재처리 테스트
- parser version과 observation capture version 분리

## Reference

- `OBSERVATION_PRESERVATION_POLICY.md`
- `SITE_STRUCTURE_AUDIT_2026-08-31.md`
- `ADMISSION_HUB_FULL_AUTOMATION_ROADMAP.md`
- `JINHAK_ARCHITECTURE_FAILURE_ANALYSIS_2026-08-30.md`

Public references checked 2026-08-31:

- https://www.jinhak.com/jh/high3/early/manual
- https://www.jinhak.com/jh/high3/early/four-year-university/search
- https://www.jinhak.com/jh/high3/univ-major/univ-info/univ-search
- https://www.jinhak.com/Tong/Index.aspx
