# Admission Hub Observation Preservation Policy — 2026-08-31

이 문서는 Admission Hub의 수집·구조화·분석 과정에서 **현재 파서가 활용하지 못하는 정보를 곧바로 '불필요한 정보'로 정의하지 않기 위한 강제 설계 원칙**이다.

특히 진학사는 동일하거나 유사한 화면이라도 로그인 상태, 관찰 시점, 선택된 대학/모집단위/전형, 합격예측 갱신 상태, 탭/필터/지원상태에 따라 노출 정보가 달라질 수 있으므로 observation-first 방식으로 처리한다.

## 1. Core rule

**불필요한 계산과 불필요한 데이터는 구분한다.**

- 계산량·DOM 탐색량·중복 파싱은 줄여도 된다.
- 현재 구조화하지 못한 정보라는 이유로 수집 증거를 폐기하지 않는다.
- '현재 Hub 화면에 표시하지 않는다'와 '가치가 없다'를 동일시하지 않는다.
- 미분류 정보는 `unknown` 또는 `potential-value` 상태로 보존한다.
- 새로운 parser가 생기면 과거 observation을 다시 처리할 수 있어야 한다.

## 2. Three-layer model

### Layer A — Observation Evidence

사이트에서 실제 관찰된 내용을 최소한의 변형만 거쳐 보존한다.

예시 필드:

- `observationId`
- `provider`
- `observedAt`
- `effectiveAcademicYear` if explicit
- `safeRouteKey` / provider entity ID
- `pageTypeGuess`
- `pageTypeConfidence`
- `authStateClass`
- `selectedContext` (대학/학과/전형/탭/필터가 명시적으로 확인되는 경우)
- 구조화 가능한 tables/cards/labels/visible text의 privacy-sanitized representation
- content fingerprint
- parser/capture version

Layer A는 parser 성공 여부와 독립적이다.

### Layer B — Structured Provider Records

Layer A에서 확실히 해석 가능한 항목만 구조화한다.

- 대학
- 캠퍼스
- 모집단위
- 전형
- 학년도
- 모집인원
- 경쟁률
- 공식 입시결과
- 합격예측
- 모의지원
- 환산점수
- 수능최저
- provider historical case

불확실한 필드는 null + confidence/provenance로 남긴다.

### Layer C — Hub Derived Analysis

사용자 편의용 계산·랭킹·추천·비교·요약은 Layer B 위에서 수행한다.

이 계층은 언제든 다시 계산할 수 있으므로 성능 최적화 대상이 될 수 있다.

## 3. Jinhak-specific rule

진학사는 **viewpoint-dependent / time-dependent provider**로 취급한다.

같은 route라도 다음이 달라지면 별도 observation 가치가 있을 수 있다.

- 관찰 시각
- 로그인 여부
- 저장소/지원 상태
- 선택 대학
- 선택 학과/모집단위
- 선택 전형
- 성적 입력 상태
- 합격예측 업데이트 상태
- 모의지원 집계 시점
- 활성 탭/리포트 종류
- provider가 표시한 갱신 시각

따라서 dedupe는 URL 단독으로 하지 않는다.

권장 content identity:

`provider + safeRouteKey + explicitContext + contentFingerprint + providerUpdatedAt/observedAt bucket`

URL이 같아도 내용 fingerprint가 달라지면 새 observation으로 취급한다.

## 4. What may be discarded

다음은 정보 가치 판정이 아니라 안전/중복/기계적 잡음 제거 기준으로만 버릴 수 있다.

1. password, cookie, session token, CSRF, CAPTCHA, 인증 비밀값
2. 개인정보 정책상 저장하면 안 되는 민감한 form value
3. script/style/font/binary asset 자체
4. analytics/tracking identifier
5. 동일 observation 안에서 완전히 동일한 반복 navigation chrome
6. 동일 context + 동일 content fingerprint의 byte-equivalent duplicate
7. 사이트 정책/권한상 저장할 수 없는 원본 데이터

단순히 다음 이유로는 버리지 않는다.

- 현재 parser가 모름
- 현재 대시보드에 사용하지 않음
- `jinhak-other`로 분류됨
- 한 번만 관찰됨
- 현재 지원 대학과 직접 관련 없어 보임
- 현 버전의 분석 점수에 기여하지 않음

## 5. Reprocessing requirement

Observation Evidence는 parser version과 분리하여 저장한다.

새 parser/분류기가 배포되면:

`stored observation -> new parser -> new structured records`

재방문 없이 재처리할 수 있어야 한다.

기존 structured record를 덮어쓰기보다:

- source observation ID
- parser version
- generatedAt
- supersedes/replaces 관계

를 남긴다.

## 6. Performance strategy

성능은 데이터 폐기가 아니라 다음 순서로 최적화한다.

1. DOM 탐색 범위 제한
2. 반복 계산 캐시
3. exact duplicate fingerprint 제거
4. navigation chrome dictionary/reference화
5. SQLite streaming/paging
6. observation payload compression
7. derived analysis lazy computation
8. UI용 materialized view

'메모리가 부족하므로 미분류 정보를 버린다'는 해결책은 사용하지 않는다.

## 7. Diagnostics vs local evidence

Cloud diagnostic과 로컬 evidence는 구분한다.

- Cloud: privacy-minimized metadata, counts, parser quality, safe labels only
- Local: 허용 범위 내 privacy-sanitized observation evidence
- raw authenticated DOM, credential, cookie, session token은 업로드하지 않는다.

## 8. Quality metrics

향후 coverage는 단순 `structuredRecords` 수만 보지 않는다.

최소 다음을 함께 측정한다.

- observations captured
- observations classified
- observations structured
- observations unknown/potential-value
- observations exact-duplicate suppressed
- page/report type coverage
- context-bound coverage
- reprocessable observation coverage

`unknown` 비율이 높으면 '불필요한 페이지가 많다'가 아니라 **분류기/파서가 아직 충분히 이해하지 못한 상태**로 해석한다.

## 9. Release gate

새 수집기/파서가 다음 중 하나를 하면 release 차단 사유다.

- `jinhak-other`라는 이유만으로 observation 삭제
- URL-only dedupe로 서로 다른 시점/상태의 화면 합침
- parser 실패 시 evidence 폐기
- 구조화 성공 레코드만 보존하고 원 관찰 provenance 제거
- derived analysis 결과로 provider raw semantics를 대체

## 10. Definition

Admission Hub에서 '불필요한 정보'라는 표현은 기본적으로 사용하지 않는다.

대신 다음 상태로 구분한다.

- `structured-useful-now`
- `structured-reference`
- `unknown-potential-value`
- `exact-duplicate`
- `ui-noise`
- `privacy-redacted`
- `storage-prohibited`

이 중 자동 폐기 가능한 것은 `exact-duplicate`, `ui-noise`, `privacy-redacted` 대상 원문, `storage-prohibited` 데이터뿐이다.
