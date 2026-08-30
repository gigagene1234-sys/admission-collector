# Admission Hub Site Structure Audit — 2026-08-31

이 문서는 Admission Hub 다음 버전 구현 전에 대입정보포털 어디가와 진학사의 실제 공개 사이트 구조를 직접 탐색하여 정리한 구조 감사 결과다. 앱 버전 업데이트보다 이 문서를 우선 기준으로 사용한다.

## 1. 핵심 결론

1. **어디가**는 대학/학과/전형/성적분석이 비교적 명확한 메뉴와 학년도 파라미터로 분리된 구조다. 대학 상세는 `searchSyr`와 `unvCd`로 결정되는 안정적인 URL 구조가 확인되므로, 현재 Local-First 수집기를 링크 무차별 탐색보다 **ID/학년도 기반 deterministic collector**로 발전시키는 것이 맞다.
2. **진학사**는 한 사이트가 아니라 다음 계층이 함께 존재한다.
   - `www.jinhak.com`: 현대식 고3/N수 수시·정시 UI, 대학검색, 추천대학, 합격예측, 저장소, 공공 대학정보
   - `hijinhak.jinhak.com`: 일부 성적/합격예측 legacy 서비스
   - `tong.jinhak.com`: 진학통/합격통 학생관리 프로그램
   - `member.jinhak.com`: 로그인/회원 계층
3. 진학사 수시 대학검색은 공개 문구로 서비스 DB에 대한 **사람에 의한 수집 및 프로그램에 의한 주기적 수집 이용**을 금지하고 있다. 따라서 보호된 합격예측 DB를 전국 단위 WebView crawler로 자동 수집하는 방식은 production 완전자동화 경로로 채택하지 않는다.
4. 사용 편의성을 낮추는 것이 목표가 아니다. 최종 UX 목표는 여전히 **한 번 시작 → 인증이 필요할 때만 로그인 → 나머지는 자동 → 통합 결과 생성**이다. 이를 위해 Jinhak adapter는 crawler가 아니라 **Authorized Data Connector**로 설계하고, 공식 API/export/report/license가 확보되는 순간 UI를 다시 설계하지 않고 완전자동화할 수 있게 한다.
5. 진학사의 공개 대학정보 페이지는 구조 파악과 canonical mapping에 매우 유용하다. 다만 공개라는 이유만으로 주기 자동수집 권한이 있다고 해석하지 않는다.

## 2. 어디가 실제 구조

### 2.1 사이트맵 기준 주요 기능군

공식 사이트맵에서 확인되는 기능군:

- 대학정보
- 학과정보
- 전형정보
- 지도검색
- 학생부성적분석
- 수능성적분석
- 대학별성적분석(수시/정시)
- 대학별 대입특징
- 대학별 입시가이드
- 전형 평가기준 및 전년도 결과공개
- 관심대학/전형/진로
- 학생부/수능 성적관리

따라서 Hub의 Adiga provider는 최소 다음 sub-collector로 분리한다.

- `UniversityCatalogCollector`
- `DepartmentCatalogCollector`
- `AdmissionCatalogCollector`
- `UniversityDetailCollector`
- `HistoricalResultCollector`
- `ScoreAnalysisCollector` (authenticated, user-specific)

### 2.2 대학 상세 URL 구조

확인된 대표 구조:

`/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr=2027&unvCd=<ID>`

주요 식별자:

- `searchSyr`: 학년도
- `unvCd`: 대학 코드

대학 상세 화면 안에 다음 탭이 확인된다.

- 대학소개
- 설치학과
- 모집인원
- 평가기준 및 입시결과
- 대입특징 및 입시가이드

평가기준/결과에는 2027 주요사항과 2026 전형결과가 함께 노출되는 구조가 존재한다. 따라서 `current admission`과 `historical actual`을 DOM 위치가 아니라 **표시 학년도/섹션 의미**로 분리해야 한다.

### 2.3 대학검색/학과검색 구조

대학정보/학과정보 검색 화면은 2027/2026 학년도 선택과 지역, 대학유형, 전형유형 등의 필터를 제공한다. 따라서 전국 coverage는 화면의 next-page 클릭을 반복하기보다:

1. list endpoint/페이지에서 canonical ID 목록 확보
2. `(year, entity-id)` Cartesian plan 생성
3. SQLite checkpoint로 완료/오류 관리
4. 상세 페이지 deterministic fetch

방식으로 전환한다.

### 2.4 성적분석 구조

공식 메인 안내는:

1. 학생부/수능/모의 성적 입력
2. 대학/학과/전형 선택
3. 성적분석 결과/대학별 내 점수 확인

순서를 명시한다. 또한 2027 수시 대학별 점수산출 서비스가 별도로 운영되고 있다.

따라서 Hub는 공식정보 수집과 사용자 성적산출을 같은 crawler로 취급하지 않고 다음으로 분리한다.

- Official baseline: 비로그인 또는 일반 공개 정보
- User score analysis: WebView session 내 authenticated workflow

### 2.5 세션/장애 대응

어디가 UI에는 자동 로그아웃 연장 팝업이 존재한다. 기존 앱의 세션 연장/JS dialog 처리 방향은 유지하되 provider state machine에 명시적으로 포함한다.

`AUTHENTICATED -> SESSION_EXPIRING -> EXTEND -> AUTHENTICATED`

페이지 오류는 `retry -> quarantine -> next`로 처리하고 수집 전체를 중단하지 않는다.

### 2.6 권리/출처

어디가 저작권 정책은 웹문서·첨부파일·DB정보가 저작권법으로 보호되며 무단 변경·복제·배포 등을 제한한다고 안내한다. Hub는 다음을 기본 규칙으로 둔다.

- 원문 전체 재배포가 아니라 구조화된 사실/사용자용 분석 중심
- source URL/source provider/source year 보존
- 외부 공개 Hub 기능으로 확장할 때 이용허락 범위 재검토
- 대학 공식 출처와 교차검증 가능하도록 provenance 유지

## 3. 진학사 실제 구조

### 3.1 공식 수시 사용자 흐름

진학사 2027 수시 이용가이드가 제시하는 실제 구조:

1. 성적입력
   - 학생부 입력
   - 모평 입력
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

리포트 유형:

- 모의지원 리포트
- 합격예측 리포트
- 실제합격자 리포트

이 순서가 Hub의 Jinhak state graph 기준이 되어야 한다.

### 3.2 공개 route topology

확인된 현대식 경로:

- 대학검색
  - `/jh/high3/early/four-year-university/search`
- 추천대학
  - `/jh/high3/early/four-year-university/recommend-university`
- 대학·학과별 합격예측
  - `/jh/high3/early/four-year-university/university-major-predict`
- 큐레이션
  - `/jh/high3/early/four-year-university/curation`
- 수시 저장소
  - `/jh/high3/early/four-year-university/library`

로그아웃 상태에서 추천대학, 대학·학과별 합격예측, 저장소는 `member.jinhak.com` 로그인으로 redirect되는 것이 확인된다.

### 3.3 대학정보 public route

대학검색:

`/jh/high3/univ-major/univ-info/univ-search`

상세:

`/jh/high3/univ-major/univ-info/univ-search/detail?Flag=<n>&UnivCode=<ID>`

실제 확인된 코드 예:

- 국립한밭대학교 `UnivCode=3004`
- 우송대학교 `UnivCode=3011`
- 국립한국교통대학교 `UnivCode=3015`
- 충남대학교 `UnivCode=1140`

대학 상세에는 다음이 존재한다.

- 기본 대학정보
- 모집요강/입시결과/기출문제 자료
- 최근 3년간 경쟁률
- 2026 수시/정시 경쟁률 TOP
- 2026 수시 합격자 평균점수
- 설치학과 경쟁률: 전형/모집단위 × 2026/2025/2024
- 합격후기

v0.6.6에서 `jinhak-other`로 잘못 분류했던 페이지가 바로 이 구조다.

### 3.4 protected prediction semantics

공식 가이드에 따르면 다음 값은 서로 다른 의미를 가진다.

- 합격안정성 칸수
- 합격예측 결과
- 모의지원자
- 분석대상자
- 대학별 환산점수
- 내 순위
- 예상 합격선
- 실제지원 희망대학

합격예측 리포트는 실시간이 아니라 업데이트 주기에 따라 변경될 수 있다. 모의지원 리포트는 더 실시간에 가까운 성격이다. Hub schema는 `observedAt`, `providerUpdateType`, `dataScope`를 유지해야 한다.

### 3.5 Jinhak service boundary

수시 대학검색과 결제안내 페이지에서 확인되는 공개 문구:

- 계정은 1인 1아이디 원칙
- DB는 저작권법에 의해 보호됨
- **사람에 의한 수집 및 프로그램에 의한 주기적 수집 이용 금지**
- 무단전재/배포/데이터 조작 금지
- 비정상 이용 시 자동 차단 또는 법적 조치 가능

따라서 다음은 release acceptance 대상이 아니다.

- 전국 protected Jinhak DB crawler
- 주기적인 unattended WebView crawl
- hidden endpoint를 직접 호출하여 UI/정책을 우회하는 수집기
- session/CAPTCHA 우회

### 3.6 공식적으로 확인되는 대안 채널

진학통/합격통 학생관리 프로그램은 다음을 공식 기능으로 안내한다.

- 학생 성적 파일/일괄 등록
- 학생 데이터 누적 저장
- 대학/학과 검색과 저장
- 추천대학
- 대학별 상세리포트
- 실제합격자 리포트
- 리포트 출력

공개 정보만으로 API 또는 구조화 export의 존재는 확인되지 않았다. 하지만 **리포트 출력/데이터 저장**이 공식 기능이므로, Jinhak 완전자동화 조사 우선순위는 crawler가 아니라 다음이다.

1. 공식 API 존재 여부
2. 공식 CSV/XLSX/JSON export 존재 여부
3. 리포트 PDF/print output의 허용된 개인 사용 import 가능 여부
4. 제휴/license 데이터 제공 가능 여부

## 4. Admission Hub 구현 원칙

### 4.1 사용자 경험 목표

최종 목표 UX:

`통합 수집 시작 1회`

-> 세션 확인
-> 필요한 provider만 로그인 요청
-> 어디가 자동 수집
-> 진학사 authorized connector 자동 동기화
-> canonical merge
-> 품질검증
-> Hub 표시

페이지별 수동 버튼은 최종 UX에 존재하지 않는다.

### 4.2 Provider capability model

각 provider adapter는 다음 capability를 선언한다.

- `PUBLIC_DETERMINISTIC_COLLECTION`
- `AUTHENTICATED_USER_WORKFLOW`
- `AUTHORIZED_EXPORT_IMPORT`
- `AUTHORIZED_API_SYNC`
- `USER_VIEW_CAPTURE_FALLBACK`

어디가:

- PUBLIC_DETERMINISTIC_COLLECTION = enabled
- AUTHENTICATED_USER_WORKFLOW = enabled

진학사:

- AUTHORIZED_EXPORT_IMPORT/API_SYNC = 목표
- USER_VIEW_CAPTURE_FALLBACK = 현재 안전 fallback
- protected periodic crawler = disabled

### 4.3 Canonical merge

Hub는 source semantics를 없애지 않는다.

- `official-current-admission`
- `official-historical-result`
- `jinhak-public-reference`
- `jinhak-current-prediction`
- `jinhak-provider-historical-case`
- `user-calculated-score`

예측은 actual을 overwrite하지 않는다.

## 5. 다음 개발 버전 전에 필요한 결정

1. Adiga crawler를 URL-discovery 중심에서 entity-ID/state-plan 중심으로 재설계한다.
2. Jinhak UI crawler는 완전자동화의 본체로 사용하지 않는다.
3. `JinhakAuthorizedConnector` 인터페이스를 먼저 만든다.
4. 진학사 공식 export/API/report 가능성을 실제 계정 화면에서 확인할 진단 기능을 만든다. 이 진단은 endpoint 호출이 아니라 UI에 나타난 download/print/export capability metadata만 기록한다.
5. Hub merge schema를 provider-neutral canonical identity로 확정한다.
6. 위 구조가 잡힌 뒤에만 다음 APK 버전을 올린다.

## 6. 검증에 사용한 공개 페이지

어디가:

- https://www.adiga.kr/cct/stp/sitemapView.do?menuId=PCCCTSTP1000
- https://www.adiga.kr/ucp/uvt/uni/univView.do?menuId=PCUVTINF2000
- https://www.adiga.kr/ucp/prc/uni/admssUnivView.do?menuId=PCPRC
- https://www.adiga.kr/mbs/cop/copyrightPolicyView.do?menuId=PCMBSCOP1000

진학사:

- https://www.jinhak.com/jh/high3/early/manual
- https://www.jinhak.com/jh/high3/early/four-year-university/search
- https://www.jinhak.com/jh/high3/univ-major/univ-info/univ-search
- https://www.jinhak.com/jh/high3/univ-major/univ-info/univ-search/detail?Flag=1&UnivCode=3004
- https://www.jinhak.com/jh/high3/univ-major/univ-info/univ-search/detail?Flag=1&UnivCode=3011
- https://www.jinhak.com/jh/high3/univ-major/univ-info/univ-search/detail?Flag=1&UnivCode=3015
- https://www.jinhak.com/Tong/Index.aspx
