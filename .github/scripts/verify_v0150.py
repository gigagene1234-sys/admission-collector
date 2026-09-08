from pathlib import Path
import re

root = Path('app/src/main/java/com/admissionhub/collector')
main = (root / 'MainActivity.kt').read_text()
credential = (root / 'session/CredentialVault.kt').read_text()
session = (root / 'session/SecureSessionVault.kt').read_text()
unified_excel = (root / 'score/UnifiedExcelScoreActivity.kt').read_text()
recognizer = (root / 'score/KoreanTranscriptAutoRecognizer.kt').read_text()
materializer = (root / 'score/AdigaAutoScoreMaterializer.kt').read_text()
official_evidence = (root / 'canonical/AdigaOfficialAdmissionEvidence.kt').read_text()
historical = (root / 'canonical/AdigaHistoricalOutcomeExtractor.kt').read_text()
hub = (root / 'hub/HubDashboardModel.kt').read_text()
coverage = (root / 'jinhak/JinhakMissionCoverageLedger.kt').read_text()
calc = (root / 'score/OfficialUniversityScoreCalculator.kt').read_text()
manifest = Path('app/src/main/AndroidManifest.xml').read_text()
build = Path('app/build.gradle.kts').read_text()

# Product identity.
assert 'private const val VERSION = "0.15.0"' in main
assert 'private const val BUILD_CODE = 115000' in main
assert 'private const val ADIGA_RETRY_SUSPENDED = false' in main
assert 'versionCode = 115000' in build and 'versionName = "0.15.0"' in build
assert 'Admission Hub v0.15.0 Dual Auto' in manifest

# One user action must start the official Adiga lane without a Jinhak preflight gate.
start = main.split('private fun startUnifiedCollection() {', 1)[1].split('private fun startUnifiedCollectionAuthenticated()', 1)[0]
assert 'startUnifiedCollectionAuthenticated()' in start
assert 'startJinhakRealAuthProbe' not in start
assert 'startupLoginPreflightVerified' not in start
for required in [
    'providerIndependentAuto', 'adigaBlockedByJinhakAuth',
    'bothProviderLeasesRestoreAttemptedAtBootstrap',
    'adigaLeaseRestoredAtBootstrap', 'jinhakLeaseRestoredAtBootstrap',
    'sessionVault.restore(ProviderId.ADIGA.wireName)',
    'sessionVault.restore(ProviderId.JINHAK.wireName)',
    'transitionUnifiedToJinhak', 'jinhakTransitionAuthGateActive = true',
    'attemptSavedCredentialLogin(ProviderId.JINHAK',
]:
    assert required in main, 'Missing provider-independent automatic flow: ' + required
assert '.put("adigaBlockedByJinhakAuth", false)' in main

# Official score/outcome materialization must run independent of Excel and then re-index after final merge.
for required in [
    'materializeOfficialScoreAndOutcomeEvidence(sessionId, "adiga-finish:',
    'materializeOfficialScoreAndOutcomeEvidence(sessionId, "unified-final-merge")',
    'AdigaAutoScoreMaterializer.materializeSelected',
    'historicalOutcomeIndexingRunsWithoutStudentProfile',
    'ADIGA_SCORE_OUTCOME_MATERIALIZATION', 'FINAL_SCORE_OUTCOME_REINDEX'
]:
    assert required in main, 'Missing automatic official materialization: ' + required

# Current official scoring scope can be verified from separately verified official components only
# when the deterministic official calculator itself succeeds. Historical result binding stays strict.
assert 'conversionIdentityBinding = directIdentityBinding || scoringScopeBinding' in materializer
assert 'scoringScopeBinding = verified && official.optBoolean("currentComponentsVerified", false)' in materializer
assert '.put("historicalBindingRelaxed", false)' in materializer
assert 'evidence.optString("admissionMatch") != "exact"' in materializer
assert 'evidence.optString("departmentMatch") !in setOf("exact", "suffix-equivalent")' in materializer
assert 'headersVerified' in materializer

# Same-row historical extraction is allowed only after explicit official cut-table header proof.
for required in [
    'fun extractSameRow(', 'bindingMethod = "same-official-table-same-row"',
    '"모집인원"', '"경쟁률"', 'has50 && has70', 'bindingInferred',
    'if (!hasCapacity || !hasCompetition || !hasCut || (!hasConverted && !hasGrade)) return null'
]:
    assert required in historical, 'Missing historical safety contract: ' + required
assert 'departmentQuality in setOf("exact", "suffix-equivalent") && admissionQuality == "exact"' in official_evidence
assert 'AdigaHistoricalOutcomeExtractor.extractSameRow' in official_evidence

# Excel must support both legacy XLS and XLSX and two automatic recognition modes.
for required in [
    'LegacyXlsStudentScoreImport.looksLikeXls', 'LegacyXlsStudentScoreImport.parse',
    'XlsxStudentScoreImport.parse', 'KoreanTranscriptAutoRecognizer.recognizeBest',
    'strict == null && structural == null', '저장 + 6장 통합 분석'
]:
    assert required in unified_excel, 'Missing unified Excel behavior: ' + required
for required in [
    'explicit-korean-transcript-sections', 'explicitStructureOnly',
    'detectYearMarker', 'detectSemesterMarker', 'StudentScoreImport.parse',
    'sectionMarkers == 0 && !hasDedicatedYearSemester'
]:
    assert required in recognizer, 'Missing structural transcript recognizer safety: ' + required
# Blank grade must remain blank/null; automatic recognizer must not assert completeness.
assert '.put("completeTranscriptConfirmedByUser", complete)' in (root / 'score/StudentScoreImport.kt').read_text()
assert re.search(r'StudentScoreImport\.parse\([\s\S]{0,800}?admissionYear,\s*false\s*\)', recognizer), 'Structural recognizer must pass complete=false'
assert 'grade.isBlank()' in recognizer

# Dashboard separates official component verification from strict same-row/direct binding.
assert 'officialCurrentComponentsVerified' in hub
assert 'directOfficialApplicationBindings' in hub
assert '공식 구성요소 ' in main and '동일행 직접결합 ' in main

# Preserve evidence-safety semantics and provider trust separation.
assert '"university-result"' in coverage
core_fragment = coverage.split('val CORE_LANES = listOf(', 1)[1].split(')', 1)[0]
assert '"university-result"' in core_fragment
assert 'probabilityInferred' in materializer and '.put("probabilityInferred", false)' in materializer
assert 'holistic-not-quantitative' in calc
assert '2027 && university.contains("우송")' in calc
assert '2027 && university.contains("한밭")' in calc

# Credentials remain device-only; background build/release never gets website credentials.
for required in ['AndroidKeyStore', 'AES/GCM/NoPadding', 'fun save(', 'fun load(']:
    assert required in credential
for forbidden in ['cloudOffload', 'INSERT INTO', 'CookieManager']:
    assert forbidden not in credential, 'Credential vault crossed trust boundary: ' + forbidden
assert 'admission_auth_lease_metadata_v4' in session
for forbidden in ['getCookie(', 'setCookie(', 'cookieHeader', 'password: String']:
    assert forbidden not in session, 'Session metadata copied secret material: ' + forbidden

print('v0.15.0 automatic dual-provider orchestration, official score/outcome linking, and transcript Excel contracts passed')
