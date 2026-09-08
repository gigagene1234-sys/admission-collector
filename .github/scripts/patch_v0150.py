from pathlib import Path
import re

ROOT = Path('.')

def read(path):
    return (ROOT / path).read_text()

def write(path, text):
    (ROOT / path).write_text(text)

def replace_once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing patch anchor: {label}')
    if text.count(old) != 1:
        raise SystemExit(f'non-unique patch anchor {label}: {text.count(old)}')
    return text.replace(old, new, 1)

# --- MainActivity: v0.15.0 means one automatic dual-provider flow, no six-complete startup skip.
p = 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
s = read(p)
s = replace_once(s, 'import com.admissionhub.collector.score.ScoreReviewUi\n', 'import com.admissionhub.collector.score.ScoreReviewUi\nimport com.admissionhub.collector.score.AdigaAutoScoreMaterializer\n', 'MainActivity score import')
s = replace_once(s, 'private const val VERSION = "0.14.2"\n        private const val BUILD_CODE = 114200', 'private const val VERSION = "0.15.0"\n        private const val BUILD_CODE = 115000', 'MainActivity version')
old_startup = '''        // On app launch, six-slot Hub state is authoritative. Never silently spend another
        // full 27-target run when the user has already fixed their six applications.
        when {
            selectedSixRecoveryNeeded() -> startSelectedSixRecovery()
            selectedSixAlreadyComplete() -> {
                rebuildCanonicalHubFromLatestSessionIfReady("launch-six-complete")
                openProvider(ProviderId.JINHAK)
                status.text = "선택한 6장의 핵심 coverage가 완료되어 앱 시작 시 전체 재수집을 생략했습니다. 필요할 때 통합 수집 버튼으로 갱신하세요."
            }
            isFreshJinhakRealAuthProbe() -> startAutomaticLoginAndCollectionSequence("app-launch-restored-real-auth")
            else -> startJinhakRealAuthProbe(autoContinue = true, trigger = "app-launch")
        }'''
new_startup = '''        // v0.15.0: app launch always enters one dual-provider preflight. Existing WebView sessions
        // are reused, but six-card coverage never suppresses Adiga/Jinhak freshness collection.
        when {
            unifiedRunning || batchRunning || startupLoginPreflightActive -> Unit
            else -> startAutomaticLoginAndCollectionSequence("app-launch-v0150-full-auto")
        }'''
s = replace_once(s, old_startup, new_startup, 'startup auto flow')
old_pref = '''    private fun startPreferredHubCollection() {
        if (selectedSixRecoveryNeeded()) {
            startSelectedSixRecovery()
        } else {
            startUnifiedCollection()
        }
    }'''
new_pref = '''    private fun startPreferredHubCollection() {
        if (unifiedRunning || batchRunning || startupLoginPreflightActive) return
        // One button now owns both provider authentication checks and both provider collections.
        // Selected-six recovery is performed by the resulting canonical/evidence materialization,
        // not as a substitute for collecting a provider.
        startupLoginPreflightVerified = false
        startAutomaticLoginAndCollectionSequence("manual-v0150-full-auto")
    }'''
s = replace_once(s, old_pref, new_pref, 'preferred full auto flow')
s = replace_once(s, 'text = "통합 동기화 시작"', 'text = "어디가 + 진학사 자동 수집"', 'primary unified label')
s = s.replace('unifiedButton.text = "통합 동기화 시작"', 'unifiedButton.text = "어디가 + 진학사 자동 수집"')
# Materialize official links/scores at finalization, after current provider work has been stopped.
anchor = '            val hubAudit = summary.optJSONObject("canonicalHub")?.optJSONObject("qualityAudit") ?: JSONObject()'
materialize = '''            if (sessionId != null) {
                runCatching { localStore.rebuildCanonicalApplicationGraph(sessionId) }
                runCatching { AdigaAutoScoreMaterializer.materializeSelected(localStore, sessionId) }
                refreshHubDashboardFromStore("unified-finish-v0150-materialized")
            }
            val hubAudit = summary.optJSONObject("canonicalHub")?.optJSONObject("qualityAudit") ?: JSONObject()'''
s = replace_once(s, anchor, materialize, 'finish materialization')
# Dashboard language: distinguish official identity verification from strict same-row binding.
s = replace_once(s,
'''            append("공식연결 ").append(summary.optInt("accepted", 0)).append("/6")
            val provisional = summary.optInt("provisional", 0)
            val providerOnly = summary.optInt("providerOnly", 0)
            if (provisional > 0) append(" · 확인필요 ").append(provisional)
            if (providerOnly > 0) append(" · 공식결합없음 ").append(providerOnly)''',
'''            append("공식확인 ").append(summary.optInt("officialVerified", 0)).append("/6")
            append(" · 직접결합 ").append(summary.optInt("directOfficialBound", 0)).append("/6")
            val provisional = summary.optInt("provisional", 0)
            val providerOnly = summary.optInt("providerOnly", 0)
            if (provisional > 0) append(" · 구조확인 ").append(provisional)
            if (providerOnly > 0) append(" · 공식근거부족 ").append(providerOnly)''', 'dashboard official labels')
write(p, s)

# --- Score materializer: refresh full-local official binding before calculating or storing outcomes.
p = 'app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt'
s = read(p)
s = replace_once(s, 'import com.admissionhub.collector.canonical.AdigaFullEvidenceRescan\n', 'import com.admissionhub.collector.canonical.AdigaFullEvidenceRescan\nimport com.admissionhub.collector.canonical.OfficialEvidenceAutoLinker\n', 'materializer import')
old = '''        if (sessionId.isBlank()) return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("error", "missing-session")
        val candidates = store.loadCanonicalApplicationCandidates(sessionId)'''
new = '''        if (sessionId.isBlank()) return JSONObject().put("schemaVersion", SCHEMA_VERSION).put("error", "missing-session")
        val relink = OfficialEvidenceAutoLinker.relinkSelected(store, sessionId)
        val candidates = store.loadCanonicalApplicationCandidates(sessionId)'''
s = replace_once(s, old, new, 'materializer autolink')
s = replace_once(s, '.put("fullAdigaRecordsScanned", fullRescan.optInt("recordsScanned"))\n            .put("results", results)', '.put("fullAdigaRecordsScanned", fullRescan.optInt("recordsScanned"))\n            .put("officialAutoRelink", relink)\n            .put("results", results)', 'materializer result relink')
write(p, s)

# --- Hub model: current official component verification is visible even when same-row binding is absent.
p = 'app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt'
s = read(p)
old_counts = '''        val accepted = auditSlots.optInt("accepted", cards.countQuality("accepted"))
        val provisional = auditSlots.optInt("provisional", cards.countQuality("provisional"))
        val providerOnly = auditSlots.optInt("providerOnly", cards.countQuality("provider-only"))'''
new_counts = '''        val directOfficialBound = cards.countDirectOfficialBound()
        val officialVerified = cards.countOfficialVerified()
        val accepted = maxOf(auditSlots.optInt("accepted", 0), directOfficialBound)
        val provisional = maxOf(auditSlots.optInt("provisional", 0), (officialVerified - directOfficialBound).coerceAtLeast(0))
        val providerOnly = maxOf(auditSlots.optInt("providerOnly", 0), (selected - officialVerified).coerceAtLeast(0))'''
s = replace_once(s, old_counts, new_counts, 'Hub official counts')
s = replace_once(s, '.put("providerOnly", providerOnly)\n                .put("fullCoreCoverage", fullCoverage)', '.put("providerOnly", providerOnly)\n                .put("officialVerified", officialVerified)\n                .put("directOfficialBound", directOfficialBound)\n                .put("fullCoreCoverage", fullCoverage)', 'Hub summary official counts')
helper_anchor = '''    private fun JSONObject.nullableString(key: String): String? ='''
helpers = '''    private fun JSONArray.countOfficialVerified(): Int = (0 until length()).count { i ->
        val card = optJSONObject(i) ?: return@count false
        if (!card.optBoolean("occupied", false)) return@count false
        val official = card.optJSONObject("officialEvidence") ?: return@count false
        official.optBoolean("currentComponentsVerified", false) || official.optInt("currentApplicationBoundCount", 0) > 0
    }

    private fun JSONArray.countDirectOfficialBound(): Int = (0 until length()).count { i ->
        val card = optJSONObject(i) ?: return@count false
        if (!card.optBoolean("occupied", false)) return@count false
        (card.optJSONObject("officialEvidence") ?: JSONObject()).optInt("currentApplicationBoundCount", 0) > 0
    }

    private fun JSONObject.nullableString(key: String): String? ='''
s = replace_once(s, helper_anchor, helpers, 'Hub count helpers')
write(p, s)

# --- Excel: standard mapping first, flexible repeated-header/section fallback second; recognized rows are saved immediately as a draft.
p = 'app/src/main/java/com/admissionhub/collector/score/UnifiedExcelScoreActivity.kt'
s = read(p)
s = replace_once(s, '                autoRecognize(workbook)\n', '''                runCatching { autoRecognize(workbook) }.getOrElse {
                    val defaultYear = sessionId?.let { id -> store.loadCanonicalApplicationCandidates(id).optJSONObject(0)?.optInt("academicYear") }
                        ?.takeIf { y -> y in 2000..2100 } ?: 2027
                    FlexibleTranscriptExtractor.extract(workbook, defaultYear, false, fileName, sourceFormat)
                }
''', 'Excel flexible fallback')
s = replace_once(s, 'result.onSuccess { profile -> parsedProfile = profile; renderEditable(profile) }', 'result.onSuccess { profile -> parsedProfile = profile; persistDraft(profile); renderEditable(profile) }', 'Excel draft on recognition')
render_anchor = '    private fun renderEditable(profile: JSONObject) {'
persist = '''    private fun persistDraft(profile: JSONObject) {
        // Successful recognition is already an input operation. Save it immediately so returning to
        // the Hub never shows 0 courses merely because the user has not scrolled to the final button.
        runCatching {
            profile.put("completeTranscriptConfirmedByUser", false)
                .put("importState", "AUTO_RECOGNIZED_DRAFT")
            store.saveStudentScoreImport(profile)
            sessionId?.takeIf { it.isNotBlank() }?.let { sid ->
                runCatching { store.rebuildCanonicalApplicationGraph(sid) }
                runCatching { AdigaAutoScoreMaterializer.materializeSelected(store, sid, profile) }
            }
        }
    }

    private fun renderEditable(profile: JSONObject) {'''
s = replace_once(s, render_anchor, persist, 'Excel persist draft')
s = replace_once(s, 'info("아래 인식값 자체가 입력값입니다. 틀린 셀만 바로 수정한 뒤 맨 아래의 ‘저장 + 6장 통합 분석’을 누르세요.")', 'info("인식된 과목은 이미 학생부 입력 초안으로 저장되었습니다. 틀린 셀만 수정하고, 전체 과목 누락 여부를 확인한 뒤 ‘저장 + 6장 통합 분석’을 누르세요.")', 'Excel wording')
write(p, s)

# --- XLS/XLSX aliases: cover common school-export labels.
p = 'app/src/main/java/com/admissionhub/collector/score/XlsxStudentScoreImport.kt'
s = read(p)
s = s.replace('setOf("학년", "gradeyear", "year")', 'setOf("학년", "학년도", "학년학기", "gradeyear", "year")')
s = s.replace('setOf("학기", "semester", "term")', 'setOf("학기", "학년학기", "semester", "term")')
s = s.replace('setOf("과목", "과목명", "교과목", "교과목명", "subject")', 'setOf("과목", "과목명", "교과목", "교과목명", "과목명칭", "subject")')
s = s.replace('setOf("등급", "석차등급", "내신등급", "grade")', 'setOf("등급", "석차등급", "석차 등급", "내신등급", "등급(석차)", "grade")')
s = s.replace('setOf("학점", "이수단위", "단위수", "이수학점", "credits", "credit")', 'setOf("학점", "이수단위", "단위수", "단위 수", "이수학점", "이수 학점", "credits", "credit")')
s = s.replace('setOf("성취도", "성취수준", "achievement")', 'setOf("성취도", "성취수준", "성취 수준", "성취도(수강자수)", "achievement")')
write(p, s)

# --- Android product identity.
p = 'app/build.gradle.kts'
s = read(p)
s = replace_once(s, 'versionCode = 114200', 'versionCode = 115000', 'gradle version code')
s = replace_once(s, 'versionName = "0.14.2"', 'versionName = "0.15.0"', 'gradle version name')
write(p, s)

p = 'app/src/main/AndroidManifest.xml'
s = read(p)
s = replace_once(s, 'android:label="Admission Hub v0.14.2 Unified Auto"', 'android:label="Admission Hub v0.15.0 Full Auto Evidence"', 'manifest label')
write(p, s)

print('v0.15.0 source patch applied')
