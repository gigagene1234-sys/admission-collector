from pathlib import Path

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
MODEL = ROOT / 'app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt'
TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/hub/HubDashboardModelTest.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {n}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

# Preconditions: build only from the verified v0.10.4 product source.
for token in [
    'private const val VERSION = "0.10.4"',
    'private const val BUILD_CODE = 110040',
    'private fun runLocalRebindOnly(trigger: String)',
    'private fun refreshHubState(sessionId: String?, supplied: JSONObject? = null)',
    'private fun startPreferredHubCollection()',
    'private lateinit var hubRecoveryButton: Button',
]:
    if token not in main:
        raise SystemExit('v0.10.4 MainActivity precondition failed: ' + token)
if 'versionCode = 110040' not in gradle or 'versionName = "0.10.4"' not in gradle:
    raise SystemExit('v0.10.4 Gradle precondition failed')
if 'Admission Hub v0.10.4 Local Rebind Continuity' not in manifest:
    raise SystemExit('v0.10.4 manifest precondition failed')

MODEL.parent.mkdir(parents=True, exist_ok=True)
TEST.parent.mkdir(parents=True, exist_ok=True)

MODEL.write_text(r'''package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject

/**
 * Pure presentation model for the six-application Hub dashboard.
 *
 * It never mutates collection data or canonical bindings. The dashboard is a view over
 * persisted canonical evidence and sync state, so process recreation cannot make the UI
 * silently invent progress or provider semantics.
 */
object HubDashboardModel {
    const val SCHEMA_VERSION = 1
    const val SLOT_COUNT = 6

    fun build(canonicalHub: JSONObject, syncStatus: JSONObject, runtime: JSONObject = JSONObject()): JSONObject {
        val graph = canonicalHub.optJSONArray("candidateGraph") ?: JSONArray()
        val slots = canonicalHub.optJSONArray("slots") ?: JSONArray()
        val audit = canonicalHub.optJSONObject("qualityAudit") ?: JSONObject()
        val auditSlots = audit.optJSONObject("sixSlots") ?: JSONObject()

        val byIdentity = linkedMapOf<String, JSONObject>()
        for (i in 0 until graph.length()) {
            val item = graph.optJSONObject(i) ?: continue
            val identity = item.optString("applicationIdentityKey")
            if (identity.isNotBlank()) byIdentity[identity] = item
        }

        val cards = JSONArray()
        for (slot in 1..SLOT_COUNT) {
            val slotRow = slots.optJSONObject(slot - 1)
            val occupied = slotRow?.optBoolean("occupied", false) == true
            val identity = slotRow?.optString("applicationIdentityKey").orEmpty()
            val candidate = if (identity.isBlank()) null else byIdentity[identity]
            cards.put(buildCard(slot, occupied, slotRow, candidate))
        }

        val sync = buildSync(syncStatus, runtime)
        val selected = auditSlots.optInt("selected", cards.countOccupied())
        val resolvable = auditSlots.optInt("resolvable", cards.countResolvable())
        val accepted = auditSlots.optInt("accepted", cards.countQuality("accepted"))
        val provisional = auditSlots.optInt("provisional", cards.countQuality("provisional"))
        val providerOnly = auditSlots.optInt("providerOnly", cards.countQuality("provider-only"))
        val fullCoverage = auditSlots.optInt("fullCoreCoverage", cards.countFullCoverage())

        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
            .put("cards", cards)
            .put("sync", sync)
            .put("summary", JSONObject()
                .put("selected", selected)
                .put("resolvable", resolvable)
                .put("accepted", accepted)
                .put("provisional", provisional)
                .put("providerOnly", providerOnly)
                .put("fullCoreCoverage", fullCoverage)
                .put("hubReady", audit.optBoolean("hubReady", false))
                .put("publishState", audit.optString("publishState", "WAITING_FOR_USER_SELECTION"))
                .put("candidateCount", audit.optInt("candidateCount", graph.length())))
    }

    private fun buildCard(slot: Int, occupied: Boolean, slotRow: JSONObject?, candidate: JSONObject?): JSONObject {
        if (!occupied) {
            return JSONObject()
                .put("slot", slot)
                .put("occupied", false)
                .put("resolvable", false)
                .put("title", "$slot. 비어 있음")
                .put("qualityState", "empty")
                .put("qualityLabel", "지원안 미선택")
                .put("coverageCount", 0)
                .put("coverageComplete", false)
        }
        if (candidate == null) {
            return JSONObject()
                .put("slot", slot)
                .put("occupied", true)
                .put("resolvable", false)
                .put("applicationIdentityKey", slotRow?.optString("applicationIdentityKey").orEmpty())
                .put("title", "$slot. ${slotRow?.optString("displayLabel", "연결 확인 필요")}")
                .put("qualityState", "stale")
                .put("qualityLabel", "canonical 연결 복구 필요")
                .put("coverageCount", 0)
                .put("coverageComplete", false)
        }

        val coverage = candidate.optJSONObject("coverage") ?: JSONObject()
        val binding = candidate.optJSONObject("adigaBinding") ?: JSONObject()
        val university = candidate.nullableString("university")
        val department = candidate.nullableString("department")
        val admission = candidate.nullableString("admission")
        val campus = candidate.nullableString("campus")
        val capacity = if (candidate.has("capacity") && !candidate.isNull("capacity")) candidate.optInt("capacity", -1).takeIf { it >= 0 } else null
        val quality = candidate.optString("qualityState", candidate.optString("adigaBindingQuality", "unknown"))
        return JSONObject()
            .put("slot", slot)
            .put("occupied", true)
            .put("resolvable", true)
            .put("applicationIdentityKey", candidate.optString("applicationIdentityKey"))
            .put("canonicalApplicationId", candidate.optString("canonicalApplicationId"))
            .put("university", university ?: JSONObject.NULL)
            .put("department", department ?: JSONObject.NULL)
            .put("admission", admission ?: JSONObject.NULL)
            .put("campus", campus ?: JSONObject.NULL)
            .put("capacity", capacity ?: JSONObject.NULL)
            .put("title", listOfNotNull(university, department).joinToString(" · ").ifBlank { "$slot. 지원안" })
            .put("subtitle", listOfNotNull(admission, campus?.let { "[$it]" }).joinToString(" · "))
            .put("qualityState", quality)
            .put("qualityLabel", qualityLabel(quality))
            .put("coverageCount", coverage.optInt("coveredCount", 0))
            .put("coverageComplete", coverage.optBoolean("complete", false))
            .put("missingLanes", coverage.optJSONArray("missing") ?: JSONArray())
            .put("updatedAt", candidate.optString("updatedAt"))
            .put("officialStructuralCurrent", binding.optInt("officialStructuralCurrent", 0))
            .put("officialRowBoundCurrent", binding.optInt("officialRowBoundCurrent", 0))
            .put("officialTableSegmentCurrent", binding.optInt("officialTableSegmentCurrent", 0))
            .put("adigaMatchCount", candidate.optInt("adigaMatchCount", 0))
    }

    private fun buildSync(syncStatus: JSONObject, runtime: JSONObject): JSONObject {
        val persistedStatus = syncStatus.optString("status", "unknown")
        val persistedPhase = syncStatus.optString("phase", "idle")
        val requiresUserAction = syncStatus.optBoolean("requiresUserAction", false)
        val runtimeRunning = runtime.optBoolean("running", false)
        val runtimePhase = runtime.optString("phase", persistedPhase)
        val loginRequired = runtime.optBoolean("loginRequired", false)
        val loginChecking = runtime.optBoolean("loginChecking", false)
        val recovering = runtime.optBoolean("recovering", false)

        val state = when {
            loginRequired -> "USER_LOGIN_REQUIRED"
            loginChecking -> "LOGIN_CHECK"
            recovering -> "RECOVERING"
            runtimeRunning && runtimePhase == "adiga" -> "SYNCING_ADIGA"
            runtimeRunning && runtimePhase == "jinhak" -> "SYNCING_JINHAK"
            runtimeRunning -> "SYNCING"
            requiresUserAction -> "USER_ACTION_REQUIRED"
            persistedStatus == "completed" && syncStatus.optString("completionReason").contains("error", ignoreCase = true) -> "COMPLETE_WITH_WARNINGS"
            persistedStatus == "completed" -> "COMPLETE"
            persistedStatus == "running" -> when (persistedPhase) {
                "adiga" -> "SYNCING_ADIGA"
                "jinhak" -> "SYNCING_JINHAK"
                else -> "SYNCING"
            }
            else -> "IDLE"
        }

        val mission = runtime.optJSONObject("mission")
            ?: syncStatus.optJSONObject("jinhakDiagnosticsSummary")?.optJSONObject("missionTargetLedger")
            ?: JSONObject()
        val totalTargets = mission.optInt("targets", 0)
        val confirmed = mission.optInt("confirmed", mission.optJSONObject("states")?.optInt("confirmed", 0) ?: 0)
        val outstanding = mission.optInt("outstanding", 0)
        val progressText = when {
            totalTargets > 0 -> "$confirmed/$totalTargets 완료${if (outstanding > 0) " · $outstanding 남음" else ""}"
            state == "COMPLETE" || state == "COMPLETE_WITH_WARNINGS" -> "수집 완료"
            else -> "진행 수치 대기"
        }
        return JSONObject()
            .put("state", state)
            .put("stateLabel", syncStateLabel(state))
            .put("phase", if (runtimeRunning) runtimePhase else persistedPhase)
            .put("progressText", progressText)
            .put("targets", totalTargets)
            .put("confirmed", confirmed)
            .put("outstanding", outstanding)
            .put("updatedAt", syncStatus.optString("updatedAt"))
            .put("completionReason", syncStatus.optString("completionReason"))
            .put("lastProgressAgeSeconds", runtime.optLong("lastProgressAgeSeconds", -1L))
    }

    fun qualityLabel(state: String): String = when (state) {
        "accepted" -> "공식 전형 연결 확인"
        "provisional" -> "공식 전형 연결 확인 필요"
        "provider-only" -> "진학사 중심 · 공식 결합 없음"
        "incomplete" -> "수집 보강 필요"
        "stale" -> "canonical 연결 복구 필요"
        "empty" -> "지원안 미선택"
        else -> "데이터 품질 확인 필요"
    }

    fun syncStateLabel(state: String): String = when (state) {
        "USER_LOGIN_REQUIRED" -> "로그인 필요"
        "LOGIN_CHECK" -> "로그인 확인 중"
        "RECOVERING" -> "복구 중"
        "SYNCING_ADIGA" -> "어디가 공식정보 수집 중"
        "SYNCING_JINHAK" -> "진학사 정보 수집 중"
        "SYNCING" -> "통합 수집 중"
        "USER_ACTION_REQUIRED" -> "사용자 조치 필요"
        "COMPLETE_WITH_WARNINGS" -> "완료 · 일부 오류 있음"
        "COMPLETE" -> "완료"
        else -> "대기"
    }

    private fun JSONObject.nullableString(key: String): String? =
        if (!has(key) || isNull(key)) null else optString(key).trim().takeIf { it.isNotBlank() && it != "null" }

    private fun JSONArray.countOccupied(): Int = (0 until length()).count { optJSONObject(it)?.optBoolean("occupied", false) == true }
    private fun JSONArray.countResolvable(): Int = (0 until length()).count { optJSONObject(it)?.optBoolean("resolvable", false) == true }
    private fun JSONArray.countFullCoverage(): Int = (0 until length()).count { optJSONObject(it)?.optBoolean("coverageComplete", false) == true }
    private fun JSONArray.countQuality(state: String): Int = (0 until length()).count { optJSONObject(it)?.optString("qualityState") == state }
}
''')

TEST.write_text(r'''package com.admissionhub.collector.hub

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class HubDashboardModelTest {
    @Test
    fun buildsSixResolvableCardsWithoutChangingQualitySemantics() {
        val graph = JSONArray()
        val slots = JSONArray()
        for (i in 1..6) {
            val identity = "id-$i"
            graph.put(JSONObject()
                .put("applicationIdentityKey", identity)
                .put("canonicalApplicationId", "app-$i")
                .put("university", "대학$i")
                .put("department", "학과$i")
                .put("admission", "전형$i")
                .put("capacity", 10 + i)
                .put("qualityState", if (i == 1) "accepted" else "provisional")
                .put("coverage", JSONObject().put("coveredCount", 5).put("complete", true).put("missing", JSONArray()))
                .put("adigaBinding", JSONObject().put("officialStructuralCurrent", if (i == 1) 1 else 0)))
            slots.put(JSONObject().put("slot", i).put("occupied", true).put("applicationIdentityKey", identity).put("displayLabel", "대학$i 학과$i"))
        }
        val canonical = JSONObject()
            .put("candidateGraph", graph)
            .put("slots", slots)
            .put("qualityAudit", JSONObject()
                .put("candidateCount", 27)
                .put("hubReady", true)
                .put("publishState", "READY_WITH_WARNINGS")
                .put("sixSlots", JSONObject()
                    .put("selected", 6).put("resolvable", 6).put("accepted", 1)
                    .put("provisional", 5).put("providerOnly", 0).put("fullCoreCoverage", 6)))
        val model = HubDashboardModel.build(canonical, JSONObject().put("status", "completed").put("phase", "completed"))
        assertEquals(6, model.getJSONArray("cards").length())
        assertEquals(6, model.getJSONObject("summary").getInt("resolvable"))
        assertEquals(1, model.getJSONObject("summary").getInt("accepted"))
        assertEquals("공식 전형 연결 확인", model.getJSONArray("cards").getJSONObject(0).getString("qualityLabel"))
        assertEquals("공식 전형 연결 확인 필요", model.getJSONArray("cards").getJSONObject(1).getString("qualityLabel"))
        assertTrue(model.getJSONArray("cards").getJSONObject(5).getBoolean("coverageComplete"))
    }

    @Test
    fun preservesStaleSlotInsteadOfInventingCandidate() {
        val canonical = JSONObject()
            .put("candidateGraph", JSONArray())
            .put("slots", JSONArray().put(JSONObject()
                .put("slot", 1).put("occupied", true).put("applicationIdentityKey", "missing").put("displayLabel", "과거 지원안")))
            .put("qualityAudit", JSONObject())
        val card = HubDashboardModel.build(canonical, JSONObject()).getJSONArray("cards").getJSONObject(0)
        assertTrue(card.getBoolean("occupied"))
        assertFalse(card.getBoolean("resolvable"))
        assertEquals("stale", card.getString("qualityState"))
    }

    @Test
    fun runtimeLoginAndRecoveryOverridePersistedCompleteState() {
        val canonical = JSONObject().put("candidateGraph", JSONArray()).put("slots", JSONArray()).put("qualityAudit", JSONObject())
        val persisted = JSONObject().put("status", "completed").put("phase", "completed")
        val login = HubDashboardModel.build(canonical, persisted, JSONObject().put("running", true).put("loginRequired", true))
        assertEquals("USER_LOGIN_REQUIRED", login.getJSONObject("sync").getString("state"))
        val recovery = HubDashboardModel.build(canonical, persisted, JSONObject().put("running", true).put("recovering", true))
        assertEquals("RECOVERING", recovery.getJSONObject("sync").getString("state"))
    }

    @Test
    fun jinhakMissionProgressIsExposed() {
        val canonical = JSONObject().put("candidateGraph", JSONArray()).put("slots", JSONArray()).put("qualityAudit", JSONObject())
        val runtime = JSONObject()
            .put("running", true)
            .put("phase", "jinhak")
            .put("mission", JSONObject().put("targets", 27).put("confirmed", 20).put("outstanding", 7))
        val sync = HubDashboardModel.build(canonical, JSONObject().put("status", "running").put("phase", "jinhak"), runtime).getJSONObject("sync")
        assertEquals("SYNCING_JINHAK", sync.getString("state"))
        assertEquals("20/27 완료 · 7 남음", sync.getString("progressText"))
    }
}
''')

# Version bump.
main = replace_once(main, 'private const val VERSION = "0.10.4"', 'private const val VERSION = "0.11.0"', 'main version')
main = replace_once(main, 'private const val BUILD_CODE = 110040', 'private const val BUILD_CODE = 111000', 'main build code')
gradle = replace_once(gradle, 'versionCode = 110040', 'versionCode = 111000', 'gradle version code')
gradle = replace_once(gradle, 'versionName = "0.10.4"', 'versionName = "0.11.0"', 'gradle version name')
manifest = replace_once(manifest,
    'Admission Hub v0.10.4 Local Rebind Continuity',
    'Admission Hub v0.11 Six-Card Dashboard',
    'manifest label')

# Imports and fields.
main = replace_once(main,
    'import android.widget.FrameLayout\n',
    'import android.widget.FrameLayout\nimport android.widget.HorizontalScrollView\n',
    'HorizontalScrollView import')
main = replace_once(main,
    'import com.admissionhub.collector.local.LocalCollectorStore\n',
    'import com.admissionhub.collector.local.LocalCollectorStore\nimport com.admissionhub.collector.hub.HubDashboardModel\n',
    'dashboard model import')
main = replace_once(main,
    '    private lateinit var hubRecoveryButton: Button\n',
    '''    private lateinit var hubRecoveryButton: Button
    private lateinit var hubDashboardStatus: TextView
    private lateinit var hubDashboardScroll: HorizontalScrollView
    private val hubDashboardCards = mutableListOf<TextView>()
    private var hubDashboardLastModel = JSONObject()
''',
    'dashboard fields')

# Persisted dashboard refresh ticker. It is intentionally read-only.
main = replace_once(main,
    '    private val handler = Handler(Looper.getMainLooper())\n',
    '''    private val handler = Handler(Looper.getMainLooper())
    private val hubDashboardTicker = object : Runnable {
        override fun run() {
            if (::hubDashboardStatus.isInitialized && !isFinishing) {
                refreshHubDashboardFromStore("ticker")
                handler.postDelayed(this, if (unifiedRunning || batchRunning || startupLoginPreflightActive) 2_000L else 7_500L)
            }
        }
    }
''',
    'dashboard ticker')

# Add dashboard UI immediately after the existing six-slot controls.
ui_anchor = '''        hubRow.addView(hubState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hubRow.addView(hubManageButton)
        hubRow.addView(hubRecoveryButton)

        status = TextView(this).apply {
'''
ui_insert = '''        hubRow.addView(hubState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hubRow.addView(hubManageButton)
        hubRow.addView(hubRecoveryButton)

        hubDashboardStatus = TextView(this).apply {
            text = "대시보드 상태를 불러오는 중…"
            textSize = 16f
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnClickListener { refreshHubDashboardFromStore("manual-banner-refresh") }
        }
        val dashboardCardRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.TOP
            setPadding(dp(4), dp(4), dp(4), dp(4))
        }
        hubDashboardCards.clear()
        repeat(6) { index ->
            val card = TextView(this).apply {
                text = "${index + 1}. 지원안 데이터 준비 중"
                textSize = 15f
                gravity = Gravity.TOP
                minHeight = dp(150)
                setPadding(dp(14), dp(12), dp(14), dp(12))
                setLineSpacing(0f, 1.12f)
                isClickable = true
                isFocusable = true
                setBackgroundColor(android.graphics.Color.rgb(246, 246, 246))
                setOnClickListener { showHubDashboardCard(index + 1) }
            }
            hubDashboardCards.add(card)
            dashboardCardRow.addView(card, LinearLayout.LayoutParams(dp(292), LinearLayout.LayoutParams.WRAP_CONTENT).apply {
                setMargins(dp(4), dp(2), dp(4), dp(6))
            })
        }
        hubDashboardScroll = HorizontalScrollView(this).apply {
            isHorizontalScrollBarEnabled = true
            addView(dashboardCardRow)
        }

        status = TextView(this).apply {
'''
main = replace_once(main, ui_anchor, ui_insert, 'dashboard UI')

# Mount the dashboard before the collector browser/status area.
main = replace_once(main,
    '''        root.addView(actions3)
        root.addView(hubRow)
        root.addView(status)
''',
    '''        root.addView(actions3)
        root.addView(hubRow)
        root.addView(hubDashboardStatus)
        root.addView(hubDashboardScroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(status)
''',
    'dashboard mount')

# Dashboard renderer and detail dialog.
method_anchor = '''    private fun canonicalHubSessionId(): String? =
'''
methods = r'''    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()

    private fun runtimeHubDashboardState(): JSONObject {
        val now = System.currentTimeMillis()
        val lastProgressAgeSeconds = if (jinhakLastMeaningfulProgressAtMs > 0L) {
            ((now - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L) / 1000L)
        } else -1L
        return JSONObject()
            .put("running", unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive)
            .put("phase", unifiedPhase)
            .put("loginRequired", batchPausedForLogin)
            .put("loginChecking", startupLoginPreflightActive || jinhakTransitionAuthGateActive)
            .put("recovering", runtimeRendererRecovering || selectedSixRecoveryMode || jinhakMissionCells.summary().optString("supervisorState") == "RECOVERING")
            .put("provider", provider.wireName)
            .put("mission", jinhakMissionTargetLedger.summary())
            .put("lastProgressAgeSeconds", lastProgressAgeSeconds)
    }

    private fun refreshHubDashboardFromStore(trigger: String) {
        if (!::hubDashboardStatus.isInitialized || !::localStore.isInitialized) return
        val canonicalSession = canonicalHubSessionId()
        if (canonicalSession.isNullOrBlank()) {
            renderHubDashboard(HubDashboardModel.build(JSONObject(), JSONObject(), runtimeHubDashboardState()))
            return
        }
        val canonical = runCatching { localStore.canonicalHubSummary(canonicalSession) }.getOrDefault(JSONObject())
        val syncSession = if (unifiedRunning && !unifiedSessionId.isNullOrBlank()) unifiedSessionId else canonicalSession
        val sync = runCatching { localStore.unifiedStatus(syncSession ?: canonicalSession) }.getOrDefault(JSONObject())
        val model = HubDashboardModel.build(canonical, sync, runtimeHubDashboardState())
        hubDashboardLastModel = model
        renderHubDashboard(model)
        if (trigger != "ticker") {
            recordRuntimeEvent("hub-dashboard-refresh", JSONObject()
                .put("trigger", trigger.take(80))
                .put("canonicalSessionId", canonicalSession)
                .put("syncState", model.optJSONObject("sync")?.optString("state")))
        }
    }

    private fun renderHubDashboard(model: JSONObject) {
        hubDashboardLastModel = model
        val sync = model.optJSONObject("sync") ?: JSONObject()
        val summary = model.optJSONObject("summary") ?: JSONObject()
        val age = sync.optLong("lastProgressAgeSeconds", -1L)
        val ageText = if (age >= 0 && age < 86_400) " · 마지막 진행 ${age}초 전" else ""
        val qualityText = buildString {
            append("공식연결 ").append(summary.optInt("accepted", 0)).append("/6")
            val provisional = summary.optInt("provisional", 0)
            val providerOnly = summary.optInt("providerOnly", 0)
            if (provisional > 0) append(" · 확인필요 ").append(provisional)
            if (providerOnly > 0) append(" · 공식결합없음 ").append(providerOnly)
        }
        hubDashboardStatus.text = "${sync.optString("stateLabel", "대기")} · ${sync.optString("progressText", "진행 수치 대기")}$ageText\n지원 6장 ${summary.optInt("resolvable", 0)}/6 · 핵심자료 ${summary.optInt("fullCoreCoverage", 0)}/6 · $qualityText"

        val cards = model.optJSONArray("cards") ?: JSONArray()
        for (index in hubDashboardCards.indices) {
            val view = hubDashboardCards[index]
            val card = cards.optJSONObject(index) ?: JSONObject().put("slot", index + 1).put("occupied", false)
            val occupied = card.optBoolean("occupied", false)
            val resolvable = card.optBoolean("resolvable", false)
            view.text = when {
                !occupied -> "${index + 1}. — 비어 있음 —\n\n지원 6장 관리에서 선택"
                !resolvable -> "${index + 1}. ${card.optString("title", "연결 확인 필요")}\n\ncanonical 연결 복구 필요"
                else -> {
                    val university = card.optString("university").takeIf { it.isNotBlank() && it != "null" }.orEmpty()
                    val department = card.optString("department").takeIf { it.isNotBlank() && it != "null" }.orEmpty()
                    val subtitle = card.optString("subtitle")
                    val capacity = if (card.has("capacity") && !card.isNull("capacity")) "모집 ${card.optInt("capacity")}명" else "모집인원 미확인"
                    val coverage = "Jinhak 핵심 ${card.optInt("coverageCount", 0)}/5"
                    val official = card.optString("qualityLabel", "데이터 품질 확인 필요")
                    "${index + 1}. $university\n$department\n$subtitle\n\n$capacity · $coverage\n$official"
                }
            }
        }
    }

    private fun showHubDashboardCard(slot: Int) {
        if (slot !in 1..6) return
        if (hubDashboardLastModel.length() == 0) refreshHubDashboardFromStore("card-open")
        val card = hubDashboardLastModel.optJSONArray("cards")?.optJSONObject(slot - 1)
        if (card == null || !card.optBoolean("occupied", false)) {
            Toast.makeText(this, "$slot 번 슬롯은 비어 있습니다.", Toast.LENGTH_SHORT).show()
            return
        }
        val missing = card.optJSONArray("missingLanes") ?: JSONArray()
        val missingText = if (missing.length() == 0) "없음" else (0 until missing.length()).joinToString(", ") { missing.optString(it) }
        val message = buildString {
            append(card.optString("university", "미확인")).append('\n')
            append(card.optString("department", "미확인")).append('\n')
            val admission = card.optString("admission").takeIf { it.isNotBlank() && it != "null" }
            val campus = card.optString("campus").takeIf { it.isNotBlank() && it != "null" }
            if (admission != null) append("전형: ").append(admission).append('\n')
            if (campus != null) append("캠퍼스: ").append(campus).append('\n')
            if (card.has("capacity") && !card.isNull("capacity")) append("모집인원: ").append(card.optInt("capacity")).append("명\n")
            append("\n데이터 품질: ").append(card.optString("qualityLabel")).append('\n')
            append("Jinhak 핵심 coverage: ").append(card.optInt("coverageCount", 0)).append("/5\n")
            append("누락 lane: ").append(missingText).append('\n')
            append("Adiga 구조적 현재연도 근거: ").append(card.optInt("officialStructuralCurrent", 0)).append("건\n")
            append("Adiga 같은 행 근거: ").append(card.optInt("officialRowBoundCurrent", 0)).append("건\n")
            append("Adiga 명시적 표 구간 근거: ").append(card.optInt("officialTableSegmentCurrent", 0)).append("건\n")
            val updated = card.optString("updatedAt")
            if (updated.isNotBlank()) append("마지막 canonical 갱신: ").append(updated)
        }
        AlertDialog.Builder(this)
            .setTitle("지원 $slot 상세")
            .setMessage(message)
            .setPositiveButton("확인", null)
            .show()
    }

'''
main = replace_once(main, method_anchor, methods + method_anchor, 'dashboard methods')

# Initial and resumed refreshes.
main = replace_once(main,
    '        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)\n',
    '''        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)
        handler.postDelayed({ refreshHubDashboardFromStore("app-start") }, 900L)
        handler.removeCallbacks(hubDashboardTicker)
        handler.postDelayed(hubDashboardTicker, 3_500L)
''',
    'dashboard startup scheduling')
main = replace_once(main,
    '''    override fun onResume() {
        super.onResume()
        handler.removeCallbacks(sessionKeepAlive)
        handler.postDelayed(sessionKeepAlive, 45_000L)
    }
''',
    '''    override fun onResume() {
        super.onResume()
        handler.removeCallbacks(sessionKeepAlive)
        handler.postDelayed(sessionKeepAlive, 45_000L)
        handler.removeCallbacks(hubDashboardTicker)
        handler.postDelayed({ refreshHubDashboardFromStore("activity-resume") }, 250L)
        handler.postDelayed(hubDashboardTicker, 2_500L)
    }
''',
    'dashboard onResume')
main = replace_once(main,
    '''    override fun onPause() {
        persistProcessResumeJournal("onPause", synchronous = true)
        handler.removeCallbacks(sessionKeepAlive)
''',
    '''    override fun onPause() {
        persistProcessResumeJournal("onPause", synchronous = true)
        handler.removeCallbacks(hubDashboardTicker)
        handler.removeCallbacks(sessionKeepAlive)
''',
    'dashboard onPause')

# Make local rebind and six-slot edits immediately visible without waiting for the ticker.
main = replace_once(main,
    '''        status.text = "로컬 재결합 완료 · 후보 ${audit.optInt("candidateCount", 0)} · 지원 6장 ${audit.optJSONObject("sixSlots")?.optInt("resolvable", 0) ?: 0}/6 · 사이트 재수집 없음"
    }
''',
    '''        status.text = "로컬 재결합 완료 · 후보 ${audit.optInt("candidateCount", 0)} · 지원 6장 ${audit.optJSONObject("sixSlots")?.optInt("resolvable", 0) ?: 0}/6 · 사이트 재수집 없음"
        refreshHubDashboardFromStore("local-rebind-complete")
    }
''',
    'local rebind dashboard refresh')

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

# Static postconditions.
checks = {
    'version': 'private const val VERSION = "0.11.0"' in main and 'versionName = "0.11.0"' in gradle,
    'dashboard model': MODEL.exists() and 'object HubDashboardModel' in MODEL.read_text(),
    'six card ui': 'repeat(6)' in main and 'showHubDashboardCard' in main,
    'persisted status': 'localStore.unifiedStatus' in main and 'hubDashboardTicker' in main,
    'local first preserved': 'runLocalRebindOnly' in main and 'preferLocalRebind' in main,
    'collection entry preserved': 'startPreferredHubCollection' in main,
    'privacy': 'credentialExported' in main and 'sessionSecretExported' in main,
}
failed = [k for k, v in checks.items() if not v]
if failed:
    raise SystemExit('v0.11.0 postcondition failure: ' + ', '.join(failed))
print('v0.11.0 Six-Card Dashboard patch applied')
