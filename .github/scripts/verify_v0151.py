from pathlib import Path


def read(path: str) -> str:
    return Path(path).read_text()

main = read("app/src/main/java/com/admissionhub/collector/MainActivity.kt")
excel = read("app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt")
wide = read("app/src/main/java/com/admissionhub/collector/score/KoreanWideSemesterTranscriptRecognizer.kt")
fence = read("app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt")
materializer = read("app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt")
gradle = read("app/build.gradle.kts")
manifest = read("app/src/main/AndroidManifest.xml")

assert 'versionCode = 115100' in gradle
assert 'versionName = "0.15.1"' in gradle
assert 'private const val VERSION = "0.15.1"' in main
assert 'private const val BUILD_CODE = 115100' in main
assert 'Admission Hub v0.15.1 Wide XLS + High3 Fence' in manifest

# Actual school XLS wide format support.
assert 'object KoreanWideSemesterTranscriptRecognizer' in wide
assert 'recognitionMode", "wide-semester-columns"' in wide
assert 'PRESERVE_NULL_ZERO_AS_NULL' in wide
assert '1학기' in wide and '2학기' in wide
assert '성취도별분포' in wide
assert 'KoreanWideSemesterTranscriptRecognizer.recognizeBest' in excel
assert 'listOfNotNull(strict, structural, wideSemester)' in excel
assert 'recognized.maxWithOrNull' in excel

# The high3 collector must never traverse the same-domain lower-grade products.
assert 'object JinhakGradeRouteFence' in fence
for token in ['/jh/high1/', '/jh/high2/', '/jh/high12/']:
    assert token in fence
assert 'JinhakGradeRouteFence.isBlockedLowerGrade(target)' in main
assert 'JinhakGradeRouteFence.isBlockedLowerGrade(url)' in main
assert 'jinhak-lower-grade-navigation-blocked' in main
assert 'jinhak-lower-grade-redirect-stopped' in main
assert 'jinhak-popup-lower-grade-navigation-blocked' in main
assert 'lowerGradeNavigationsBlocked' in main

# Reauthentication is finite even if the site keeps bouncing back to login.
assert 'private const val MAX_JINHAK_REAUTH_CYCLES = 3' in main
assert 'jinhakReauthCycles >= MAX_JINHAK_REAUTH_CYCLES' in main
assert 'jinhak-reauth-circuit-open' in main
assert 'finishBatch("jinhak-reauth-circuit-open")' in main

# Current Adiga evidence can be materialized against pinned identities even when the fresh
# Jinhak run failed before rebuilding a candidate graph. Only candidate metadata may fall back.
assert 'latestReusableCanonicalSessionId()' in materializer
assert 'candidateMetadataFallbackOnly' in materializer
assert 'AdigaFullEvidenceRescan.scanSelected(store, sessionId, selectedCandidates)' in materializer
assert '.put("slotsMutated", false)' in materializer
assert '.put("historicalBindingRelaxed", false)' in materializer
assert '.put("probabilityInferred", false)' in materializer

print("v0.15.1 product contracts verified")
