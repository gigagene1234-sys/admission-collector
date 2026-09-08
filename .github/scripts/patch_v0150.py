from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 occurrence, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str, flags=0) -> str:
    rx = re.compile(pattern, flags)
    out, count = rx.subn(lambda _m: repl, text, count=1)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 regex occurrence, found {count}")
    return out


# ---------------------------------------------------------------------------
# MainActivity: provider-independent automatic unified run + automatic score/outcome materialization.
# ---------------------------------------------------------------------------
main_path = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
main = main_path.read_text()
main = replace_once(
    main,
    "import com.admissionhub.collector.score.ScoreReviewUi\n",
    "import com.admissionhub.collector.score.ScoreReviewUi\nimport com.admissionhub.collector.score.AdigaAutoScoreMaterializer\n",
    "main import"
)
main = replace_once(main, 'private const val VERSION = "0.14.2"', 'private const val VERSION = "0.15.0"', "main version")
main = replace_once(main, "private const val BUILD_CODE = 114200", "private const val BUILD_CODE = 115000", "main build")
main = replace_once(main, "private const val ADIGA_RETRY_SUSPENDED = true", "private const val ADIGA_RETRY_SUSPENDED = false", "adiga retry")

main = regex_once(
    main,
    r'''    private fun startUnifiedCollection\(\) \{.*?\n    \}\n\n    private fun startUnifiedCollectionAuthenticated\(\) \{''',
    '''    private fun startUnifiedCollection() {
        // v0.15: Jinhak authentication must never block the public official Adiga crawl.
        // Both provider leases are restored up front, but each provider verifies its own session
        // only when that provider actually needs protected content. One user action drives the
        // full Adiga -> Jinhak pipeline; no provider switch or separate login diagnostic is needed.
        startUnifiedCollectionAuthenticated()
    }

    private fun startUnifiedCollectionAuthenticated() {''',
    "provider-independent unified bootstrap",
    flags=re.S
)

needle = '''        val sessionId = localStore.beginOrResumeUnifiedSession(VERSION)
        unifiedSessionId = sessionId
'''
replacement = '''        // Restore both domain leases at the same bootstrap point. WebView CookieManager is
        // domain-scoped, so restoring Jinhak readiness does not require navigating away from Adiga.
        // A restored lease is NOT treated as proof of server authentication; the Jinhak transition
        // gate below still verifies a real protected route and uses saved credentials only if needed.
        val restoredAdiga = runCatching { sessionVault.restore(ProviderId.ADIGA.wireName) }.getOrNull()
        val restoredJinhak = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
        startupLoginAdigaRestoredLease = restoredAdiga?.restored == true
        startupLoginJinhakRestoredLease = restoredJinhak?.restored == true
        startupLoginAdigaAuthenticated = false
        startupLoginJinhakAuthenticated = false
        startupLoginPreflightActive = false
        startupLoginPreflightVerified = false
        startupLoginStage = "provider-independent-auto"
        CookieManager.getInstance().flush()

        val sessionId = localStore.beginOrResumeUnifiedSession(VERSION)
        unifiedSessionId = sessionId
'''
main = replace_once(main, needle, replacement, "dual lease bootstrap")

main = replace_once(
    main,
    'localStore.updateUnifiedSession(sessionId, "adiga", "running", "user-start")',
    'localStore.updateUnifiedSession(sessionId, "adiga", "running", "provider-independent-auto-start")',
    "unified start reason"
)
main = replace_once(
    main,
    '''                .put("collectorVersion", VERSION)
                .put("loginPreflight", JSONObject()''',
    '''                .put("collectorVersion", VERSION)
                .put("providerIndependentAuto", true)
                .put("adigaBlockedByJinhakAuth", false)
                .put("bothProviderLeasesRestoredAtBootstrap", true)
                .put("loginPreflight", JSONObject()''',
    "precheck auto metadata"
)
main = replace_once(
    main,
    'status.text = "통합 수집 1/2 · 어디가 전국 공식 입시정보 resume/audit 준비 중…"',
    'status.text = "통합 자동수집 1/2 · 어디가 공식 기준·과거 입결을 먼저 수집합니다. 진학사 인증은 이 단계를 막지 않고 다음 단계에서 자동 복구합니다."',
    "adiga status"
)
main = replace_once(
    main,
    'status.text = "통합 수집 2/2 · 진학사 보호 경로 인증을 다시 확인한 뒤 저장대학 미션을 시작합니다."',
    'status.text = "통합 자동수집 2/2 · 진학사 보호 경로를 자동 검증하고, 필요할 때만 기기 저장 계정으로 로그인한 뒤 6장 미션을 계속합니다."',
    "jinhak status"
)

# Materialize official score/outcome evidence immediately when Adiga ends, even with no student profile.
adiga_finish_needle = '''            if (sessionId != null) {
                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.ADIGA.wireName, runId) }
                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$effectiveReason")
            }
'''
adiga_finish_replacement = '''            if (sessionId != null) {
                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.ADIGA.wireName, runId) }
                materializeOfficialScoreAndOutcomeEvidence(sessionId, "adiga-finish:$effectiveReason")
                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$effectiveReason")
            }
'''
main = replace_once(main, adiga_finish_needle, adiga_finish_replacement, "adiga finish materialize")

# Add a bounded evidence materializer helper before transition.
transition_marker = '''    private fun transitionUnifiedToJinhak(adigaReason: String) {
'''
materializer_helper = '''    private fun materializeOfficialScoreAndOutcomeEvidence(sessionId: String, trigger: String): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("error", "missing-session")
        val canonical = runCatching { localStore.rebuildCanonicalApplicationGraph(sessionId) }
            .getOrElse { localStore.canonicalHubSummary(sessionId) }
        val result = runCatching {
            AdigaAutoScoreMaterializer.materializeSelected(localStore, sessionId, localStore.currentStudentScoreProfile())
        }.getOrElse { error ->
            JSONObject()
                .put("schemaVersion", 1)
                .put("error", "materialization-failed")
                .put("exceptionClass", error.javaClass.name.take(120))
                .put("probabilityInferred", false)
        }
        localStore.recordSyncState(
            sessionId,
            "ADIGA_SCORE_OUTCOME_MATERIALIZATION",
            ProviderId.ADIGA.wireName,
            JSONObject()
                .put("trigger", trigger.take(120))
                .put("candidateCount", canonical.optJSONArray("candidateGraph")?.length() ?: 0)
                .put("studentProfileStatus", localStore.currentStudentScoreProfile().optString("status", "NOT_IMPORTED"))
                .put("materialization", result)
                .put("historicalOutcomeIndexingRunsWithoutStudentProfile", true)
                .put("probabilityInferred", false),
            false,
            false
        )
        refreshHubDashboardFromStore("official-materialization")
        return result
    }

'''
main = replace_once(main, transition_marker, materializer_helper + transition_marker, "insert materializer helper")

# Re-run materialization after Jinhak identities have been canonically merged. This is the point at
# which the selected-six identity keys and the freshly collected Adiga evidence can be joined.
final_merge_needle = '''            val canonicalSummary = localStore.rebuildCanonicalApplicationGraph(sessionId)
            if (selectedSixRecoveryMode || selectedSixRecoverySessionId == sessionId) {
'''
final_merge_replacement = '''            val canonicalSummary = localStore.rebuildCanonicalApplicationGraph(sessionId)
            val finalOfficialMaterialization = materializeOfficialScoreAndOutcomeEvidence(sessionId, "unified-final-merge")
            localStore.recordSyncState(
                sessionId,
                "FINAL_SCORE_OUTCOME_REINDEX",
                ProviderId.ADIGA.wireName,
                JSONObject()
                    .put("materialization", finalOfficialMaterialization)
                    .put("scoreDecisionSummary", localStore.scoreDecisionSummary(sessionId).optJSONObject("summary") ?: JSONObject())
                    .put("probabilityInferred", false),
                false,
                false
            )
            if (selectedSixRecoveryMode || selectedSixRecoverySessionId == sessionId) {
'''
main = replace_once(main, final_merge_needle, final_merge_replacement, "final official reindex")

# Do not present the strict same-row acceptance count as if it were the only official-link state.
main = replace_once(
    main,
    'append("공식연결 ").append(summary.optInt("accepted", 0)).append("/6")',
    'append("공식 구성요소 ").append(summary.optInt("officialCurrentComponentsVerified", 0)).append("/6 · 동일행 직접결합 ").append(summary.optInt("accepted", 0)).append("/6")',
    "hub official status wording"
)

# Make the primary button describe what it now does. Preserve old text in diagnostic/fallback paths.
main = main.replace('"통합 동기화 시작"', '"통합 자동수집 시작"')
main_path.write_text(main)

# ---------------------------------------------------------------------------
# UnifiedExcelScoreActivity: strict reader + explicit section reader in one automatic path.
# ---------------------------------------------------------------------------
excel_path = ROOT / "app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt"
excel = excel_path.read_text()
excel = replace_once(
    excel,
    '''                autoRecognize(workbook)
''',
    '''                val strict = runCatching { autoRecognize(workbook) }.getOrNull()
                val structural = KoreanTranscriptAutoRecognizer.recognizeBest(
                    workbook = workbook,
                    admissionYear = sessionId?.let { id -> store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear") }
                        ?.takeIf { it in 2000..2100 } ?: 2027,
                    fileName = fileName,
                    sourceType = sourceFormat
                )
                when {
                    strict == null && structural == null -> throw IllegalArgumentException(
                        "Excel 파일은 열렸지만 학년·학기·과목 구조를 안전하게 확정하지 못했습니다."
                    )
                    strict == null -> structural!!
                    structural == null -> strict
                    structural.optInt("rowCount", 0) > strict.optInt("rowCount", 0) -> structural
                    else -> strict
                }
''',
    "excel two-pass recognition"
)
excel = replace_once(
    excel,
    '''        info("$fileName · $sourceFormat · ${profile.optString("xlsxSheetName")} · ${subjects.length()}과목 인식 · 등급 없음 ${profile.optInt("ungradedRows")}과목 · 현재 가중평균 $average")
''',
    '''        val recognitionMode = profile.optString("recognitionMode").ifBlank { "strict-column" }
        info("$fileName · $sourceFormat · ${profile.optString("xlsxSheetName")} · ${subjects.length()}과목 인식 · 등급 없음 ${profile.optInt("ungradedRows")}과목 · 현재 가중평균 $average")
        info("자동 인식 방식: $recognitionMode · 학년/학기는 파일에 명시된 열·병합·구간 표지만 사용하고 추정하지 않습니다.")
''',
    "excel recognition info"
)
excel = replace_once(
    excel,
    '''        if (!completeCheck.isChecked) info("전체 학생부 확인 체크가 꺼져 있어 대학별 자동 환산은 보수적으로 보류될 수 있습니다.")
''',
    '''        if (!completeCheck.isChecked) info("대학 환산 산식이 상위과목·이수단위를 사용하므로, 파일이 판단에 사용할 학생부 전체인지 사용자가 확인하기 전에는 환산값만 보류합니다. 공식 과거 입결 수집·연결은 이 확인과 무관하게 자동 진행됩니다.")
''',
    "excel completeness wording"
)
excel_path.write_text(excel)

# ---------------------------------------------------------------------------
# HubDashboardModel: expose separately verified current official components.
# ---------------------------------------------------------------------------
hub_path = ROOT / "app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt"
hub = hub_path.read_text()
hub = replace_once(hub, "const val SCHEMA_VERSION = 4", "const val SCHEMA_VERSION = 5", "hub schema")
hub = replace_once(
    hub,
    '''        val fullCoverage = auditSlots.optInt("fullCoreCoverage", cards.countFullCoverage())
        val scoreSummary = scoreDecisionSummary.optJSONObject("summary") ?: JSONObject()
''',
    '''        val fullCoverage = auditSlots.optInt("fullCoreCoverage", cards.countFullCoverage())
        val officialCurrentComponentsVerified = (0 until cards.length()).count { index ->
            cards.optJSONObject(index)?.optJSONObject("officialEvidence")?.optBoolean("currentComponentsVerified", false) == true
        }
        val scoreSummary = scoreDecisionSummary.optJSONObject("summary") ?: JSONObject()
''',
    "hub official component count"
)
hub = replace_once(
    hub,
    '''                .put("fullCoreCoverage", fullCoverage)
                .put("verifiedConversions", scoreSummary.optInt("verifiedConversions", 0))
''',
    '''                .put("fullCoreCoverage", fullCoverage)
                .put("officialCurrentComponentsVerified", officialCurrentComponentsVerified)
                .put("directOfficialApplicationBindings", accepted)
                .put("verifiedConversions", scoreSummary.optInt("verifiedConversions", 0))
''',
    "hub summary official fields"
)
hub_path.write_text(hub)

for path in (main_path, excel_path, hub_path):
    if "0.14.2" in path.read_text() and path == main_path:
        raise SystemExit("MainActivity still contains product version 0.14.2")

print("v0.15.0 product patch applied")
