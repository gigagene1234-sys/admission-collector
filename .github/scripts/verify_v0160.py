from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text()

main = read('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
manifest = read('app/src/main/AndroidManifest.xml')
gradle = read('app/build.gradle.kts')
dashboard = read('app/src/main/java/com/admissionhub/collector/hub/AdmissionDashboardActivity.kt')
excel = read('app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt')
complete = read('app/src/main/java/com/admissionhub/collector/score/StudentScoreDocumentCompleteness.kt')
score = read('app/src/main/java/com/admissionhub/collector/score/OfficialUniversityScoreCalculator.kt')
materializer = read('app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt')
fence = read('app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt')

assert 'versionCode = 116000' in gradle
assert 'versionName = "0.16.0"' in gradle
assert 'private const val VERSION = "0.16.0"' in main
assert 'private const val BUILD_CODE = 116000' in main
assert 'Admission Hub v0.16.0 Official Dashboard' in manifest
assert '.hub.AdmissionDashboardActivity' in manifest

# Dashboard is a real first-class screen and exposes each evidence layer separately.
assert 'text = "전체 대시보드"' in main
assert 'AdmissionDashboardActivity::class.java' in main
for token in ['conversionLabel', 'officialOutcomeLabel', 'predictionLabel', 'decisionLabel']:
    assert token in dashboard
assert '공식 환산·입결 다시 계산' in dashboard
assert 'probabilityInferred=false' in dashboard

# Official Adiga materialization cannot be hidden behind a Jinhak login failure.
assert 'AdigaAutoScoreMaterializer.materializeSelected(localStore, latest)' in main
assert 'latestUnifiedSession()' in main
assert 'AdigaFullEvidenceRescan.scanSelected(store, sessionId, selectedCandidates)' in materializer
assert 'candidateMetadataFallbackOnly' in materializer
assert '.put("slotsMutated", false)' in materializer
assert '.put("historicalBindingRelaxed", false)' in materializer
assert '.put("probabilityInferred", false)' in materializer

# Correctly recognized school exports can be structurally verified without inventing rows/grades.
assert 'object StudentScoreDocumentCompleteness' in complete
assert 'setOf("1-1", "1-2", "2-1", "2-2", "3-1")' in complete
assert '.put("inferredGrades", false)' in complete
assert '.put("inferredSubjects", false)' in complete
assert 'StudentScoreDocumentCompleteness.assess(chosen)' in excel
assert 'documentCompletenessVerified' in excel
assert 'profile.optBoolean("documentCompletenessVerified", false)' in score
assert 'completeTranscriptConfirmedByUser' in score

# Jinhak loop breaker applies to transition/preflight states, not only an active batch.
assert 'MAX_JINHAK_REAUTH_CYCLES = 3' in main
assert 'batchRunning || unifiedRunning || jinhakTransitionAuthGateActive || startupLoginPreflightActive' in main
assert 'jinhak-reauth-circuit-open' in main
assert 'finishBatch("jinhak-reauth-circuit-open")' in main

# Lower-grade product routes remain fenced from the high3 collector.
for token in ['/jh/high1/', '/jh/high2/', '/jh/high12/']:
    assert token in fence
assert 'JinhakGradeRouteFence' in main

print('v0.16.0 product contracts verified')
