# 진학사 수집·분석 아키텍처 실패 원인 분석 — 2026-08-30

## 0. 목적과 판정 원칙

이 문서는 단일 오류 로그를 설명하는 문서가 아니다. Admission Collector의 진학사 기능을 다음 여섯 층으로 나누어, 현재 실제로 가능한 활동과 불가능한 활동, 이미 해결된 문제, 아직 해결되지 않은 문제, 향후 확장 전에 반드시 고쳐야 할 구조적 위험을 구분한다.

1. 브라우저/세션 및 페이지 렌더링
2. 페이지 분류와 DOM 카드 경계 탐색
3. 대학·학과·전형 문맥 결합과 지표 추출
4. Local-First 저장·중복제거·시계열·데이터 무결성
5. 진단·검증·빌드·배포 체계
6. 진학사 서비스 이용 범위와 최종 데이터 소스 역할

판정은 `검증됨`, `부분 검증`, `미구현`, `가설`로 나눈다. 가설은 원인으로 확정하지 않는다.

---

## 1. 현재 결론 요약

### 1.1 실제로 검증된 정상 기능

- Android WebView에서 진학사에 로그인한 상태로 페이지를 렌더링하고 현재 페이지를 분석할 수 있다.
- 앱 업데이트 설치 후 기존 WebView 세션과 Local SQLite를 유지할 수 있다.
- 수시저장소 페이지를 `jinhak-early-storage`로 구분한다.
- 수시저장소에서 칸수와 경쟁률 등 예측 지표를 읽을 수 있다.
- v0.5.4 이후 예측 지표가 포함된 DOM 후보를 중복 카드 폭증 없이 카드 단위로 크게 압축할 수 있다.
- v0.5.6에서 요약 카드와 상세 카드의 중복을 줄여 36개 구조화 레코드를 30개로 정리했다.
- v0.5.6에서 최종 30개 레코드 모두에 대학 문맥을 결합했다.
- 구조화된 진단만 `jinhak-diagnostic`으로 보내고, 원문 DOM·쿠키·로그인 자격증명·URL을 진단에서 제외하는 경로가 실제 기기→Worker→GitHub Actions까지 동작한다.
- 2027 예측 레코드는 `observedAt`을 가지며 과거입결과 `dataScope`를 분리하도록 설계되어 있다.
- Cloudflare를 대량수집 루프에 사용하지 않는 Local-First 기본 방향이 유지된다.

### 1.2 현재 핵심 미해결 문제

- JinhakAdapter는 아직 `supportsBatchCrawl=false`, `isBatchNavigable=false`이다. 즉 전국 자동 순회기는 구현되지 않았다.
- v0.5.6 기준 대학은 30/30 결합됐으나 학과는 9/30, 전형은 24/30, 대학+학과+전형 모두 결합된 레코드는 7/30이다.
- 학과 근접 문맥 탐색이 실제 DOM에서 한 건도 성공하지 않았다(`departmentContextRoots=0`).
- 기존 v0.5.0~v0.5.6에서 생성한 오탐/저신뢰 레코드가 같은 Jinhak 로컬 run에 누적될 수 있으며, 현재 schema는 개별 레코드의 파서 버전과 품질 상태를 별도 컬럼으로 보존하지 않는다.
- 진학사 대학명·학과명·전형명과 어디가의 정규화된 이름을 안정적으로 연결할 canonical ID 계층이 없다.
- 실제합격자리포트를 인식하는 분류는 있으나, 진학사 실제합격자 데이터 전용 구조 파서는 아직 완결 검증되지 않았다.
- Jinhak의 hidden table을 함께 캡처하는 방식은 로드된 탭을 얻는 장점이 있지만, 활성 탭/숨은 탭/연도 문맥이 섞일 가능성을 별도로 검증하지 않았다.

---

## 2. 버전별 실패와 해결의 의미

| 버전 | 관측된 문제 | 해결/변화 | 남긴 교훈 |
|---|---|---|---|
| v0.5.0 | 실제 수시저장소 화면을 수능최저 페이지로 오분류. `7칸`, `6.48`은 추출됐지만 `천안공과대학` 등 잘못된 문맥 결합 | 페이지 분류 우선순위 수정 | 지표 추출 성공과 레코드 정합성은 별개이다 |
| v0.5.1 | 예측 페이지로 분류됐지만 `면접(20)대학`, `서류 평가 전형` 같은 문맥 오탐 | 일반적인 대학/전형 추론을 보수화 | 불확실하면 null이 오탐보다 낫다 |
| v0.5.2 | 대학 null은 안전해졌지만 학과/전형 오염 지속 | selected UI 문맥을 우선 활용 | 페이지 전체 문맥은 다중 카드 페이지에서 위험하다 |
| v0.5.3 | 사용자 설명을 반영해 수시저장소 전용 파서 도입. 111 후보→101 레코드로 과다 중복 | 카드 단위 수집으로 구조 전환 | 페이지 전체가 아니라 반복 구조를 먼저 분리해야 한다 |
| v0.5.4 | 503 metric seed→471 candidate root→42 unique root→36 record. 중복 급감, 대학명은 모두 null | 카드 root 점수화·중첩 제거 | 구조 경계 탐색 자체는 유효해졌다 |
| v0.5.5 | 대학 31/36 결합. 하지만 `닫기7칸건국대`처럼 UI 텍스트가 대학명에 포함 | 인접/상위 대학 문맥 탐색 도입 | context binding은 가능하지만 정규화 계층이 필요하다 |
| v0.5.6 | 대학 30/30 정상 정규화, 레코드 30개로 요약 중복 제거. 학과는 9/30로 부족 | 대학명 정제, summary-only 제거, 학과 근접 탐색 | 대학과 학과가 DOM에서 같은 구조 계층에 있지 않음을 시사한다 |
| v0.5.7 | 학과가 실제 DOM에서 어디에 있는지 개인정보 없는 관계정보로 확인하기 위한 probe 추가 | 아직 실기기 전송 전 | 다음 규칙은 추측이 아니라 구조 증거를 보고 결정한다 |

### 해결된 문제의 공통 패턴

문제가 잘 해결된 경우는 정규식을 늘렸을 때가 아니라, **오류의 추상화 수준을 올렸을 때**였다. 예를 들어 v0.5.0~0.5.2의 오탐은 정규식 한두 개의 문제가 아니라 페이지 전체를 단일 모집단위로 간주한 데이터 모델 오류였고, 수시저장소 카드 모델로 전환한 뒤에야 개선됐다. v0.5.3의 중복도 값 추출 문제가 아니라 DOM 경계 문제였고, root score와 중첩 제거를 도입한 v0.5.4에서 크게 줄었다.

따라서 이후에도 “못 읽은 문자열을 더 넓은 정규식으로 찾기”보다 **페이지 타입→반복 구조→엔티티 문맥→지표** 순으로 구조를 분리해야 한다.

---

## 3. 수시저장소 학과 결합 실패의 원인 분석

### 확인된 사실

- v0.5.6 최종 레코드 30개 중 대학 30개, 학과 9개, 전형 24개가 결합됐다.
- SnapshotScript의 `departmentContextFor`는 card root, 속성, 앞쪽 sibling, 제한된 ancestor를 탐색하지만 `departmentContextRoots=0`이었다.
- 같은 화면에서 대학 문맥 탐색은 성공했다.
- 카드 자체 안에 학과 문자열이 있었던 일부 항목은 정상 결합됐다.

### [추측/가설] 원인 A — 카드 경계 점수와 엔티티 경계가 서로 다른 계층을 최적화한다

현재 `rootScore`는 대학명 존재를 크게 가산하고 학과명도 가산한다. 대학명을 포함하는 더 큰 부모 컨테이너가 높은 점수를 받아 선택되면, 그 안에 여러 학과가 함께 포함될 수 있다. 이 경우 대학은 유일하므로 안전하게 결합되지만 학과는 복수 후보가 되어 `departmentContextFor`가 의도적으로 포기할 수 있다. 이는 `대학 30/30 + 학과 9/30` 패턴과 일치한다. 정확한 DOM 구조는 v0.5.7 probe 결과가 오기 전에는 확정할 수 없다.

### [추측/가설] 원인 B — 학과 라벨이 카드의 부모/형제가 아니라 별도 컬럼 또는 반복 table/grid에 있다

진학사 화면이 데스크톱형 그리드 구조라면 대학/학과/전형이 카드의 상위 요소가 아니라 같은 행의 별도 cell, CSS grid 형제 또는 고정 헤더와 값 영역으로 분리됐을 수 있다. 현재 탐색은 `previousElementSibling`과 ancestor 중심이라 이 경우 놓칠 수 있다. v0.5.7은 relation/depth/distance를 기록해 이 가설을 검증한다.

### [추측/가설] 원인 C — 학과명이 select/option 또는 숨김 컨트롤에만 존재한다

SnapshotScript의 `safeCloneText`는 input/select/option/form을 제거한다. 개인정보·폼 노이즈 제거에는 유효하지만, 학과명이 선택 컨트롤의 option에만 있으면 카드 텍스트에는 남지 않는다. `selectionContext`는 별도로 캡처하지만 카드별 binding에는 직접 쓰지 않는다. v0.5.7 probe에서 후보 자체가 거의 나오지 않으면 이 원인을 우선 확인해야 한다.

### [추측/가설] 원인 D — 텍스트 정규화가 구체적 모집단위를 더 짧은 일반 토큰으로 축소한다

GenericAdmissionParser의 `bestDepartment`는 여러 후보 중 짧은 문자열을 우선할 수 있다. `자율전공`과 `철도대학자율전공학부`가 동시에 있으면 짧은 일반명칭이 선택될 위험이 있다. 수시저장소 전용 파서에서는 DOM 구조와 explicit field를 우선하고 Generic parser는 fallback으로 제한해야 한다.

---

## 4. 데이터 무결성: 현재 가장 큰 비가시적 위험

### 4.1 하나의 Jinhak run에 여러 베타 파서 세대가 혼재할 수 있다

`LocalCollectorStore.beginOrResume()`는 동일 provider의 최신 `collecting/stopped/incomplete` run을 버전과 무관하게 재사용하고, run의 `collector_version`을 새 버전으로 덮어쓴다. 현재 Jinhak의 단일 화면 분석은 run을 종료·격리하지 않는다.

그 결과 v0.5.0에서 생성한 `천안공과대학`, v0.5.1의 `면접(20)대학`, 이후의 정상 레코드가 fingerprint가 다르면 같은 run 안에 동시에 존재할 수 있다. 또한 run의 `collector_version`은 최신값으로 갱신되므로 개별 레코드가 어느 파서 버전에서 생성됐는지 DB 컬럼만으로 추적할 수 없다.

이 문제는 Hub 병합 전에 반드시 해결해야 한다. **파서가 좋아졌다는 사실과 로컬 DB가 깨끗하다는 사실은 동일하지 않다.**

### 4.2 권장 schema v2

다음 필드를 레코드 수준에서 명시적으로 저장한다.

- `capture_version`
- `data_scope`
- `observed_at`
- `quality_state` = accepted / provisional / rejected / superseded
- `provider_entity_id`
- `canonical_university_id`
- `canonical_department_id`
- `canonical_admission_id`
- `application_identity_key` (예측 시계열용)

그리고 v0.5.x 베타 Jinhak run은 삭제하지 않고 `legacy-beta/quarantined`로 보존하며, 정식 parser acceptance 이후 새 clean run을 시작해야 한다. 어디가 DB는 건드리지 않는다.

### 4.3 `storeRecords()`의 저장 개수 의미

현재 `CONFLICT_REPLACE`를 사용하며 insert가 -1이 아니면 `stored`를 증가시킨다. 따라서 UI의 “이번 저장 N개”는 엄밀하게 “새 unique record N개”라고 단정할 수 없다. 새 레코드 / 동일 fingerprint 갱신 / superseded 레코드를 분리해 카운트해야 한다.

### 4.4 전국 규모에서 `loadRecords()` 전체 메모리 로드는 위험

현재는 한 run의 모든 JSON을 메모리에 로드한다. 레코드가 수만~수십만 건으로 늘어나는 구조에서는 cursor 기반 스트리밍 export와 증분 동기화가 필요하다.

---

## 5. 엔티티 정규화와 어디가 병합 문제

진학사에서는 `국립한밭대`, 어디가에서는 `국립한밭대학교[본교]`처럼 이름 표현이 다를 수 있다. 이름 문자열만으로 Hub에서 join하면 다음 문제가 생긴다.

- 약칭/정식명칭 차이
- 본교/분교/캠퍼스 차이
- 학과 개편·통합·신설
- 전형명의 연도별 변경
- `자율전공`, `자율전공학부`, `철도대학자유전공학부`처럼 계층이 다른 이름

따라서 raw provider label과 canonical identity를 분리해야 한다. 가능하다면 진학사 화면에서 노출되는 비민감 내부 대학/모집단위 ID를 로컬에서 allowlist 방식으로 보존하고, 없다면 `대학+캠퍼스+학년도+모집단위+전형`을 정규화한 별도 매핑 테이블을 둔다. `sourcePage`에서 query를 모두 제거하는 현재 방식은 URL query에 비민감 모집단위 ID가 있는 경우 identity 정보를 잃을 수 있으므로, 민감 파라미터 차단과 비민감 ID allowlist를 구분할 필요가 있다.

---

## 6. 예측 데이터의 시간 의미

진학사 공식 이용가이드는 수시 과정이 `성적입력 → 성적분석 → 모의지원 → 합격예측리포트(수시 저장소)`로 구성된다고 설명한다. 또한 합격예측 결과는 모의지원·과거 입시결과·실제합격자 데이터 등을 바탕으로 한 진학사 기준 결과이며, 수시 저장소의 실제지원 희망대학을 중심으로 분석된다.

정시 공식 가이드에서는 합격예측 리포트가 모의지원 리포트와 달리 실시간이 아니라 주기적으로 업데이트된다고 명시한다. 따라서 향후 snapshot 정책은 무조건 짧은 주기로 페이지를 재수집하는 방식이 아니라 **사용자가 실제로 확인할 때 + 진학사가 명시한 업데이트 시점 이후**를 중심으로 해야 한다.

예측값은 반드시 다음과 분리한다.

- `current-prediction`: 칸수, 진학사 판정, 모의지원 경쟁률, 내 순위 등 변동 데이터
- `historical-provider-case`: 진학사가 수집한 과거 실제합격자 사례
- `historical-official-result`: 어디가/대학 공식 발표 기반 입결

진학사의 실제합격자리포트는 공식 안내상 과거 3개년도 합격자 점수 분포와 나의 위치 등을 제공한다. 이 자료를 어디가의 공식 50/70% 입결과 같은 의미의 데이터로 합치면 안 된다.

---

## 7. 전국 자동수집 목표에 대한 중요한 운영 제약

진학사 현재 수시 대학검색 페이지의 유의사항에는 서비스 데이터가 저작권법상 보호되는 DB이며, **사람에 의한 수집 및 프로그램에 의한 주기적 수집 이용을 금지**한다고 명시되어 있다. 또한 비정상적 이용은 차단 또는 법적 조치 대상이 될 수 있다고 안내한다.

따라서 기존 `JINHAK_COLLECTION_PLAN.md`의 “진학사를 어디가와 동일하게 전국 자동 순회” 계획은 그대로 실행하면 안 된다.

### 수정된 역할 분담

- 전국 공통 입시정보의 완전성 기준: 어디가 + 각 대학 공식 모집요강/입시결과
- 진학사 고유 가치: 사용자가 정상적으로 열람하는 대학검색/수시저장소/합격예측/모의지원/실제합격자리포트의 **사용자 주도 로컬 구조화 분석**
- 진학사 전국 규모 데이터가 꼭 필요할 경우: 진학사가 명시적으로 허용한 API/내보내기/라이선스/제휴 경로가 확인될 때만 자동 대량수집을 검토
- CAPTCHA 우회, 세션 우회, 비정상 요청, unattended periodic crawl은 설계 범위에서 제외

즉 최종 Admission Hub는 전국 대학 정보의 기반을 어디가/공식 출처로 확보하고, 진학사에서만 얻을 수 있는 개인화 예측·모의지원·실제합격자 사례를 **사용자가 열람한 모집단위에 덧붙이는 overlay 구조**가 가장 안전하고 정확하다.

---

## 8. 브라우저·세션·페이지 생명주기 분석

### 정상 작동이 확인된 부분

- WebView cookie를 통한 로그인 유지
- update install 후 데이터/세션 유지
- popup child WebView를 생성하고 main WebView로 URL 전달
- foreground collection service 기반 장시간 수집 구조의 기초
- 로그인 상태 점검 및 로그인 화면 복귀 후 이어받기 구조

### 아직 검증되지 않은 부분

- Jinhak popup이 POST/`document.write`/동적 window 객체로 생성되는 경우 URL forwarding만으로 동일 내용 재현 가능한지
- 앱 background 전환 후 진학사 세션이 장시간 유지되는지
- `onPause` 시 session keepalive 중단이 장시간 작업에 어떤 영향을 주는지
- Jinhak SPA 내부 상태에서 URL은 같고 콘텐츠만 바뀌는 화면을 document checkpoint가 제대로 구분할 수 있는지
- 실제 예측 리포트 탭 전환이 history state, XHR, iframe 중 어떤 방식인지

`로그아웃` 컨트롤이 보일 때만 authenticated를 강하게 판정하는 방식은 메뉴가 접혀 있는 모바일 화면에서는 false negative를 만들 수 있다. 따라서 향후 세션 판정은 `로그인 필요 UI`, known authenticated feature availability, cookie presence의 비민감 boolean 등을 복합적으로 사용해야 한다.

---

## 9. SnapshotScript 구조의 강점과 위험

### 강점

- password/cookie/token/CSRF/CAPTCHA 관련 요소를 캡처/URL 탐색에서 차단한다.
- 이메일을 redaction한다.
- Jinhak의 hidden table도 로컬 분석 대상으로 볼 수 있어 탭을 일일이 누르지 않고 이미 로드된 정보를 얻을 가능성이 있다.
- navigation link를 안전 필터링하고, DOM card 탐색을 브라우저 렌더링 후 수행한다.

### 위험

- hidden table을 활성/비활성 상태 구분 없이 읽으면 다른 탭·연도·이전 상태가 섞일 수 있다.
- `safeCloneText`가 select/option/form을 제거하여 모집단위 label이 컨트롤에만 있으면 문맥이 손실될 수 있다.
- navigation action 필터가 `저장` 문자열을 mutation 위험어로 취급하므로, 향후 route discovery에서 이름에 `저장소`가 들어간 정상 읽기 링크까지 누락할 수 있다.
- script route parser는 `.do` 형태와 명시 URL에 강하고, extensionless SPA route나 JS state transition에는 약할 수 있다.
- 현재 card segmentation과 entity context binding이 같은 root 탐색에 강하게 결합돼 있다.

향후 구조는 `Segmenter → ContextBinder → MetricParser → Validator` 네 단계로 명시적으로 분리해야 한다.

---

## 10. 진단 파이프라인 평가

v0.4.3에서 도입한 직접 진단 방식은 매우 효과적이었다. 사용자의 JSON 파일 공유 실패를 우회했고, 실제 어디가 15개 실패 페이지 및 진학사 카드 binding 문제를 원문 DOM 없이 좁힐 수 있었다.

그러나 현재 `jinhak-diagnostic`은 Worker DB에서 `run_errors`를 진단 메시지 저장소처럼 재사용한다. 따라서 `error_count`는 진학사 파서 오류 개수가 아니라 진단 메시지 개수로 증가한다. 이 값은 운영 지표로 오해할 수 있다.

또한 diagnostic run의 run-level collector_version은 처음 만든 버전에 머물 수 있고, 실제 최신 앱 버전은 diagnostic detail 안의 `collectorVersion`을 봐야 한다. 향후에는 `diagnostics` 전용 테이블/endpoint 또는 적어도 `event_type=diagnostic`을 분리해야 한다.

v0.5.7 방식처럼 **오류 원인을 모를 때 최소 구조 증거를 추가하고, 충분한 증거를 얻은 뒤 probe를 제거하는 방식**을 표준으로 삼는다.

---

## 11. 빌드·개발 프로세스에서 확인된 구조적 비용

Git history를 보면 여러 버전에서 기능 논리보다 Python patch script의 문자열 anchor 불일치, Kotlin regex escape, workflow 검증 문자열 때문에 빌드가 중단됐다. 현재 방식은 버전마다 `apply_vXYZ.py`와 전용 workflow를 만들고, CI가 소스를 패치한 뒤 다시 main에 commit하는 구조다.

이 방식의 문제는 다음과 같다.

- patch anchor가 이전 소스 한 줄 변화에 쉽게 깨진다.
- workflow와 실제 source가 이중 상태를 가진다.
- CI가 source를 다시 main에 쓰므로 동시 작업 시 rebase/race 위험이 있다.
- root `MainActivity.kt`와 app package 내부 `MainActivity.kt`를 두 벌 유지하고 `cmp`로 강제 동기화한다.
- SnapshotScript의 Kotlin 컴파일은 통과해도 내부 JavaScript 문법을 별도로 실행 검증하지 않는다.
- APK signing password와 Cloud ingest token이 같은 secret에서 파생되어 보안 영역이 결합돼 있다.

### 개선 원칙

- 생성 patch 방식 종료: 실제 최종 Kotlin source를 직접 commit
- `MainActivity.kt` canonical source 하나만 유지
- 단일 reusable Android CI로 통합
- CI는 build/test만 하고 source를 자동 commit하지 않음
- SnapshotScript 내부 JS를 추출해 `node --check`
- synthetic DOM fixture 기반 parser regression test 도입
- APK signing secret과 Cloud ingest token 분리

사용자 실제 수시지원/성적 데이터는 public GitHub fixture로 저장하지 않는다. fixture는 가상 대학/가상 학과를 사용한다.

---

## 12. 어디가에서 이미 얻은 교훈을 진학사에 적용

어디가에서 해결된 문제들은 진학사 설계의 중요한 선행 실험이다.

1. **Cloud 부하 문제 → Local-First 전환**: 브라우저 렌더링/파싱/체크포인트를 기기에서 처리하고 Cloud는 작은 진단·증분 동기화만 담당해야 한다.
2. **stale AJAX page → content proof 필요**: 클릭/페이지 이동 함수가 성공했다고 해당 페이지 데이터가 바뀐 것은 아니다. requested identity와 rendered identity가 일치해야 checkpoint를 완료한다.
3. **298쪽 무한 재시도 → 중앙 circuit breaker**: 모든 retry 경로는 하나의 bounded retry 정책을 통과해야 한다.
4. **JSON 공유 실패 → privacy-safe diagnostic**: 사용자의 수동 파일 전달 대신 작은 구조 진단을 직접 읽는 것이 안정적이다.
5. **완료 상태와 완전성의 차이**: `completed` 플래그만으로 수집 완전성을 판단하지 않고 엔티티/페이지/레코드 coverage를 확인한다.
6. **지원하지 않을 대학의 복구 비용**: 데이터 수집 완전성과 실제 의사결정 가치를 구분하여, 분석 목적에 중요하지 않은 오류는 deferred 상태로 둘 수 있다.

---

## 13. 수정된 발전 계획

### Gate 0 — v0.5.7 구조 probe 완료

- 동일 수시저장소 화면에서 v0.5.7 진단 1회만 수집
- 누락 학과 카드별 `direct/previous/next/ancestor/near-child` 후보를 비교
- 실제 DOM 관계를 확인한 뒤 학과 binding rule을 한 번만 확정
- probe 데이터는 production record에 남기지 않음

### Gate 1 — 수시저장소 Parser Acceptance

통과 기준:

- 대학명 오염 0
- 다른 카드의 대학/학과/전형을 잘못 상속한 사례 0(검증 표본 기준)
- summary/detail 중복은 identity 기반으로 제거
- context가 없는 카드는 null + low/raw confidence
- 카드별 stable `applicationIdentityKey` 도입
- synthetic fixture regression test 통과

### Gate 2 — Local DB v2 / 베타 오염 격리

- schema migration 구현(`onUpgrade` 포함)
- capture_version/data_scope/observed_at/quality_state/canonical IDs 추가
- 기존 Jinhak v0.5.x run은 `legacy-beta`로 격리
- clean Jinhak run 생성
- 어디가 run/records는 그대로 유지
- 신규/갱신/superseded 카운트 분리

### Gate 3 — 진학사 읽기 전용 사용자 주도 분석 확대

자동 전국 crawl이 아니라 사용자가 정상적으로 연 페이지를 대상으로:

- 대학검색 결과
- 대학·학과별 합격예측
- 수시 저장소
- 모의지원 리포트
- 합격예측 리포트
- 실제합격자리포트
- 수능최저/성적산출 관련 읽기 화면

각 page type마다 전용 parser를 두고 GenericAdmissionParser는 fallback으로 제한한다.

### Gate 4 — 공식 전국 baseline + Jinhak overlay

- 어디가 2027 모집정보 + 2026/2025 공식 입결을 nationwide baseline으로 유지
- 대학 공식 모집요강/입시결과로 보완
- Jinhak 사용자가 열람한 모집단위에 prediction/provider-case overlay 결합
- canonical identity layer를 통해 두 provider를 연결

### Gate 5 — 허용된 데이터 이동 경로가 있을 때만 확장

진학사가 명시적으로 허용한 export/API/license가 확인될 경우에만 전국 규모 Jinhak ingestion을 별도 모듈로 검토한다. 그 전에는 unattended/periodic mass collection을 구현하지 않는다.

### Gate 6 — Admission Hub 통합

Hub에서는 source semantics를 분명히 표시한다.

- 공식 모집정보/입결
- 진학사 실제합격자 사례
- 진학사 현재 합격예측
- 사용자 성적 기반 환산값

AI 분석 결과는 raw/provider data와 분리 저장한다.

### Gate 7 — 보류된 어디가 한밭대 복구

진학사 parser acceptance 이후 국립한밭대학교 자율전공학부 관련 381쪽만 targeted recovery한다. 이미 정상 확보된 다른 지원 대학 범위는 불필요하게 재수집하지 않는다.

---

## 14. 다음 개발 의사결정 규칙

- 새로운 regex를 추가하기 전에 구조 증거가 있는지 확인한다.
- “값을 읽었다”와 “값을 올바른 모집단위에 붙였다”를 별도 테스트한다.
- null보다 잘못된 결합을 더 큰 실패로 취급한다.
- parser 버전 변경 시 기존 레코드를 무조건 신뢰하지 않는다.
- prediction snapshot은 업데이트 의미가 있을 때 남기고 무의미한 고빈도 반복을 피한다.
- Jinhak protected DB의 unattended/periodic collection은 구현하지 않는다.
- official baseline과 provider-specific value를 섞지 않는다.
- 모든 장시간 작업에는 bounded retry, persisted checkpoint, content identity proof를 적용한다.
- 개발 workflow 오류와 제품 runtime 오류를 별도 분류한다.

---

## 15. 근거

### 저장소/실기기 근거

- Admission Collector v0.5.0~v0.5.6 기기 전송 진단
- `JinhakAdapter.kt`
- `SnapshotScript.kt`
- `GenericAdmissionParser.kt`
- `LocalCollectorStore.kt`
- `MainActivity.kt`
- v0.4.x~v0.5.x Git history 및 GitHub Actions 결과

### 진학사 공식 공개 근거 (2026-08-30 확인)

- 수시 합격예측 이용가이드: https://www.jinhak.com/jh/high3/early/manual
- 수시 대학검색/유의사항: https://www.jinhak.com/jh/high3/early/four-year-university/search
- 2027학년도 실제합격자 리포트 안내: https://www.jinhak.com/jh/high3/jinhak-tv/1921

본 문서에서 진학사 DOM 내부 구조에 대한 확정되지 않은 원인 설명은 `[추측/가설]`로 표시했다.
