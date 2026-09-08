from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text()

main = read('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
gradle = read('app/build.gradle.kts')
manifest = read('app/src/main/AndroidManifest.xml')
score = read('app/src/main/java/com/admissionhub/collector/score/OfficialUniversityScoreCalculator.kt')
complete = read('app/src/main/java/com/admissionhub/collector/score/StudentScoreDocumentCompleteness.kt')
materializer = read('app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt')
published = read('app/src/main/java/com/admissionhub/collector/score/OfficialPublishedOutcomeFallback.kt')
dashboard = read('app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt')
fence = read('app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt')

assert 'versionCode = 116100' in gradle
assert 'versionName = "0.16.1"' in gradle
assert 'private const val VERSION = "0.16.1"' in main
assert 'private const val BUILD_CODE = 116100' in main
assert 'Admission Hub v0.16.1 High3 DOM Fence' in manifest

# Existing v0.15/v0.16 transcript profiles must be reassessed at calculation time.
assert 'StudentScoreDocumentCompleteness.assess(profile)' in score
assert 'documentCompletenessVerifiedAtCalculation' in score
assert 'profile.optBoolean("completeTranscriptConfirmedByUser", false)' in score
assert 'profile.optBoolean("documentCompletenessVerified", false)' in score
assert 'setOf("1-1", "1-2", "2-1", "2-2", "3-1")' in complete
assert '.put("inferredGrades", false)' in complete
assert '.put("inferredSubjects", false)' in complete

# Same-URL Jinhak product switching observed on the real device is fenced in the DOM and directly
# before credentials are submitted. URL-only high1/high2/high12 fencing remains as a second layer.
assert 'installJinhakHigh3DomProductFence("page-finished")' in main
assert 'installJinhakHigh3DomProductFence("credential:$reason")' in main
assert '__admissionHigh3FenceInstalled' in main
assert '__admissionHigh3CredentialReadyAt' in main
assert 'productContextCorrected:true' in main
assert 'credentialAutoLoginLastResult = "high3-product-preflight"' in main
assert 'attemptSavedCredentialLogin(which, "high3-product-preflight")' in main
assert 'MAX_JINHAK_REAUTH_CYCLES = 3' in main
assert 'batchRunning || unifiedRunning || jinhakTransitionAuthGateActive || startupLoginPreflightActive' in main
for token in ['/jh/high1/', '/jh/high2/', '/jh/high12/']:
    assert token in fence

# Official fallback may only use pinned, explicit official publications; Jinhak data is never
# promoted to official baseline. Existing strict Adiga rescan remains first.
assert 'AdigaFullEvidenceRescan.scanSelected(store, sessionId, selectedCandidates)' in materializer
assert 'OfficialPublishedOutcomeFallback.materializeMissing(store, sessionId, selectedCandidates)' in materializer
assert 'object OfficialPublishedOutcomeFallback' in published
assert 'officialSourcesOnly' in published
assert '.put("jinhakPromoted", false)' in published
assert '.put("historicalBindingRelaxed", false)' in published
assert '.put("slotsMutated", false)' in published
assert '.put("probabilityInferred", false)' in published
for token in [
    'https://ent.wsu.ac.kr/site/ent/popup/2026susi.pdf',
    'unvCd=0000034',
    'unvCd=0000039',
    '철도차량시스템학과',
    '철도차량시스템공학과',
    '반도체시스템공학과'
]:
    assert token in published
assert 'officially-suppressed' in published
assert 'new-program-no-prior-result' in published
assert '대학 공식 비공개' in dashboard
assert '전년도 수치 없음' in dashboard

# Safety contracts remain intact.
assert '.put("historicalBindingRelaxed", false)' in materializer
assert '.put("slotsMutated", false)' in materializer
assert '.put("probabilityInferred", false)' in materializer

print('v0.16.1 product contracts verified')
