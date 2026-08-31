# Admission Collector Version Update Review Protocol

Status: mandatory release process for the 08 Admission Collector / Admission Hub project.

## Principle

A version number increase is not treated as completion by itself. Every release cycle must include evidence from an actual run, interpretation of that evidence, a concrete improvement plan, and verification that the next release implemented the agreed changes.

## Required cycle for every version

### 1. Result analysis
Analyze the exported run artifact and record at minimum:
- collector version and session completion state
- elapsed time
- provider record counts
- page / report type distribution
- observation count and unknown-potential-value count
- completed / error / unresolved documents
- navigation-state uniqueness and repeated-state churn when available
- recordType / dataScope / confidence distribution
- target evidence-lane coverage: saved application, current prediction, mock support, actual admit, university result, score analysis, strategy
- binding completeness for university / recruitment unit / admission identity
- metric semantic correctness, not merely metric presence

### 2. Interpretation
Explain what the numbers mean. Distinguish:
- more data from more useful data
- successful page visits from successful mission completion
- historical/reference evidence from current prediction evidence
- parser coverage gaps from genuinely useless content
- exact duplicates from time/state-distinct observations

Do not call unknown/unparsed observations unnecessary. Preserve the Observation Evidence policy.

### 3. Improvement diagnosis
For every material problem, state:
- observed symptom
- evidence supporting the symptom
- likely structural cause
- risk if left unchanged
- preferred structural fix

Avoid one-off regex patches when the problem is a navigation, identity, state-machine, or semantic-model issue.

### 4. Next-version change specification
Before implementation, present the next version plan with:
- changes to navigation / mission planning
- parser changes
- semantic field changes
- observation/reprocessing changes
- performance/reliability changes
- diagnostics and release-gate changes
- explicit non-goals / preserved invariants

### 5. Implementation mapping
After implementation, map every proposed change to the concrete source file/function/schema/workflow that changed. If a proposed item was not implemented, state that explicitly.

### 6. Verification
A release is not considered verified until:
- CI/build/signature checks pass
- static safety/parser invariants pass
- APK version metadata is confirmed
- actual-device run artifact is analyzed when the change affects navigation, WebView state, authentication, or live parsing

## Mandatory comparison rule

Where a previous comparable run exists, show deltas rather than standalone counts. A regression in a higher-value evidence lane cannot be hidden by an increase in total pages or total records.

## Jinhak-specific evaluation order

Evaluate Jinhak in this order:
1. saved applications discovered
2. application identity binding quality
3. current prediction evidence
4. mock-support report evidence
5. actual-admit evidence
6. university historical/result evidence
7. score/minimum evidence
8. strategy evidence linked to the relevant university/admission/application
9. general editorial/reference coverage
10. media or low-priority browsing

Page-count growth in items 9-10 does not compensate for regressions in items 1-8.

## Required final report format

Every release review must contain these sections:
1. `결과 분석`
2. `결과 해석`
3. `문제와 원인`
4. `개선 방안`
5. `다음 버전 변경 명세`
6. `업데이트 반영 체크리스트`
7. `검증 결과 / 남은 미검증 항목`
