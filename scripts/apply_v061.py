from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# ---- MainActivity: one unified session orchestrates Adiga then user-viewed Jinhak pages. ----
for p in MAIN_FILES:
    m = p.read_text()

    m = m.replace(
        '    private lateinit var diagnosticButton: Button\n',
        '    private lateinit var diagnosticButton: Button\n    private lateinit var unifiedButton: Button\n',
        1,
    )

    state_anchor = '    private var lastJinhakDigest = JSONObject()\n'
    state_block = '''    private var lastJinhakDigest = JSONObject()\n    private var unifiedSessionId: String? = null\n    private var unifiedRunning = false\n    private var unifiedPhase = "idle"\n    private var unifiedPendingAdigaStart = false\n    private var unifiedJinhakAutoCapture = false\n    private val unifiedJinhakCapturedPages = linkedSetOf<String>()\n    private var unifiedAutoCaptureScheduled = false\n'''
    if state_anchor not in m:
        raise SystemExit(f'unified state anchor missing: {p}')
    m = m.replace(state_anchor, state_block, 1)

    m = m.replace('private const val VERSION = "0.6.0"', 'private const val VERSION = "0.6.1"', 1)
    m = m.replace('private const val BUILD_CODE = 10600', 'private const val BUILD_CODE = 10610', 1)

    # Prominent unified button. Existing per-provider controls are retained for diagnostics/manual recovery.
    actions3_old = '''        diagnosticButton = Button(this).apply {\n            text = "진학사 전체 분석 전송"\n            setOnClickListener {\n                if (provider == ProviderId.JINHAK) sendLatestJinhakAnalysisDigest() else sendLatestLocalDiagnostic(manual = true)\n            }\n        }\n        actions3.addView(diagnosticButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n'''
    actions3_new = '''        unifiedButton = Button(this).apply {\n            text = "두 사이트 통합 수집 시작"\n            setOnClickListener {\n                if (unifiedRunning) finishUnifiedCollection("user-finish") else startUnifiedCollection()\n            }\n        }\n        diagnosticButton = Button(this).apply {\n            text = "진학사 전체 분석 전송"\n            setOnClickListener {\n                if (provider == ProviderId.JINHAK) sendLatestJinhakAnalysisDigest() else sendLatestLocalDiagnostic(manual = true)\n            }\n        }\n        actions3.addView(unifiedButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n        actions3.addView(diagnosticButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))\n'''
    if actions3_old not in m:
        raise SystemExit(f'actions3 anchor missing: {p}')
    m = m.replace(actions3_old, actions3_new, 1)

    # A unified run owns provider switching; manual tabs cannot accidentally interrupt an active phase.
    open_anchor = '''    private fun openProvider(which: ProviderId) {\n        if (batchRunning) stopBatch("서비스 전환")\n'''
    open_new = '''    private fun openProvider(which: ProviderId) {\n        if (unifiedRunning) {\n            Toast.makeText(this, "통합 수집 중에는 서비스 전환을 수집 엔진이 관리합니다.", Toast.LENGTH_SHORT).show()\n            return\n        }\n        if (batchRunning) stopBatch("서비스 전환")\n'''
    if open_anchor not in m:
        raise SystemExit(f'openProvider anchor missing: {p}')
    m = m.replace(open_anchor, open_new, 1)

    # On page completion, start Adiga automatically and auto-capture each unique Jinhak page the user opens.
    page_finished_anchor = '''            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                if (batchRunning && !batchPausedForLogin) {\n'''
    page_finished_new = '''            override fun onPageFinished(view: WebView, url: String) {\n                CookieManager.getInstance().flush()\n                if (unifiedRunning && unifiedPhase == "adiga" && unifiedPendingAdigaStart && provider == ProviderId.ADIGA && !batchRunning) {\n                    unifiedPendingAdigaStart = false\n                    handler.postDelayed({\n                        if (unifiedRunning && unifiedPhase == "adiga" && !batchRunning) startBatch()\n                    }, 350L)\n                    return\n                }\n                if (!batchRunning && unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK && unifiedJinhakAutoCapture) {\n                    scheduleUnifiedJinhakAutoCapture(url)\n                }\n                if (batchRunning && !batchPausedForLogin) {\n'''
    if page_finished_anchor not in m:
        raise SystemExit(f'onPageFinished anchor missing: {p}')
    m = m.replace(page_finished_anchor, page_finished_new, 1)

    # Manual Adiga recovery can stay suspended, but the explicitly requested unified run may resume incomplete checkpoints.
    m = m.replace(
        'if (provider == ProviderId.ADIGA && ADIGA_RETRY_SUSPENDED) {',
        'if (provider == ProviderId.ADIGA && ADIGA_RETRY_SUSPENDED && !unifiedRunning) {',
        1,
    )

    # Link the Adiga local run into the unified session as soon as batch starts.
    adiga_begin = '''            localRunId = localStore.beginOrResume(provider.wireName, VERSION)\n            status.text = "Local-First 수집 시작: Cloudflare 호출 없음 / run ${localRunId?.take(8)}…"\n'''
    adiga_begin_new = '''            localRunId = localStore.beginOrResume(provider.wireName, VERSION)\n            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->\n                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, provider.wireName, runId) }\n            }\n            status.text = if (unifiedRunning) {\n                "통합 수집 1/2 · 어디가 Local-First 수집 시작 / run ${localRunId?.take(8)}…"\n            } else {\n                "Local-First 수집 시작: Cloudflare 호출 없음 / run ${localRunId?.take(8)}…"\n            }\n'''
    if adiga_begin not in m:
        raise SystemExit(f'Adiga begin anchor missing: {p}')
    m = m.replace(adiga_begin, adiga_begin_new, 1)

    # Persist every Jinhak full-screen digest under the same unified session.
    digest_anchor = '''                lastJinhakDigest = buildJinhakDigest(snapshot, records, runId, collectedAt)\n'''
    digest_new = '''                lastJinhakDigest = buildJinhakDigest(snapshot, records, runId, collectedAt)\n                if (unifiedRunning && unifiedPhase == "jinhak") {\n                    unifiedSessionId?.let { sessionId ->\n                        localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId)\n                        val localPageKey = RecordUtils.sha256(canonicalizeBatchUrl(snapshot.optString("url")))\n                        localStore.storeUnifiedAnalysisCapture(\n                            sessionId = sessionId,\n                            provider = ProviderId.JINHAK.wireName,\n                            pageKey = localPageKey,\n                            pageType = snapshot.optString("providerPageType"),\n                            payload = lastJinhakDigest\n                        )\n                        localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)\n                        unifiedJinhakCapturedPages.add(localPageKey)\n                        // The bundle is already privacy-sanitized by buildJinhakDigest.\n                        // One explicit unified-session start authorizes these user-viewed page captures.\n                        cloudOffload.sendDiagnostic(\n                            "jinhak", VERSION,\n                            JSONObject(lastJinhakDigest.toString())\n                                .put("trigger", "unified-user-viewed-page")\n                                .put("unifiedSessionId", sessionId)\n                        ) { }\n                    }\n                }\n'''
    if digest_anchor not in m:
        raise SystemExit(f'Jinhak digest anchor missing: {p}')
    m = m.replace(digest_anchor, digest_new, 1)

    # Transition from the fully resumable official baseline to interactive Jinhak auto-capture.
    finish_anchor = '''        status.text = when {\n            LOCAL_FIRST_BETA && effectiveReason == "completed-with-local-errors" ->\n                "Local-First 1차 순회 종료: 미해결 오류는 로컬에 저장됨 / 다음 실행에서 해당 지점만 재개합니다."\n            LOCAL_FIRST_BETA && effectiveReason == "completed" ->\n                "어디가 로컬 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 재시도 $batchPaginationRetries / 로컬 레코드 ${localRunId?.let { localStore.stats(it).optInt("records") } ?: batchRecords.length()}"\n            effectiveReason == "cloud-verification-failed" ->\n                "로컬 수집 종료: Cloud 최종 완결성 확인 실패 / 서버 run은 닫지 않고 유지합니다."\n            batchCloudPagesDeferred > 0 ->\n                "수집 종료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 전체 완료로 확정하지 않습니다."\n            else ->\n                "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"\n        }\n'''
    finish_new = finish_anchor + '''        if (unifiedRunning && unifiedPhase == "adiga" && provider == ProviderId.ADIGA) {\n            val sessionId = unifiedSessionId\n            if (sessionId != null) {\n                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.ADIGA.wireName, runId) }\n                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$effectiveReason")\n            }\n            handler.postDelayed({ transitionUnifiedToJinhak(effectiveReason) }, 350L)\n        }\n'''
    if finish_anchor not in m:
        raise SystemExit(f'finishBatch status anchor missing: {p}')
    m = m.replace(finish_anchor, finish_new, 1)

    # Unified orchestration helpers are inserted immediately before the existing per-provider startBatch.
    start_batch_marker = '    private fun startBatch() {\n'
    unified_functions = r'''    private fun startUnifiedCollection() {
        if (batchRunning) {
            Toast.makeText(this, "현재 개별 수집을 먼저 종료한 뒤 통합 수집을 시작하세요.", Toast.LENGTH_LONG).show()
            return
        }
        val sessionId = localStore.beginOrResumeUnifiedSession(VERSION)
        unifiedSessionId = sessionId
        unifiedRunning = true
        unifiedPhase = "adiga"
        unifiedPendingAdigaStart = true
        unifiedJinhakAutoCapture = false
        unifiedJinhakCapturedPages.clear()
        unifiedAutoCaptureScheduled = false
        unifiedButton.text = "통합 수집 종료"
        localStore.updateUnifiedSession(sessionId, "adiga", "running", "user-start")

        provider = ProviderId.ADIGA
        localRunId = localStore.beginOrResume(ProviderId.ADIGA.wireName, VERSION)
        localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.ADIGA.wireName, runId) }
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        batchButton.text = "어디가 통합 수집 준비"
        diagnosticButton.text = "어디가 진단 로그 전송"
        status.text = "통합 수집 1/2 · 어디가 전국 공식 입시정보 resume/audit 준비 중…"

        val seed = ProviderRegistry.adapter(ProviderId.ADIGA).seedUrls().firstOrNull()
        if (seed.isNullOrBlank()) {
            finishUnifiedCollection("adiga-seed-missing")
            return
        }
        webView.loadUrl(seed)
    }

    private fun transitionUnifiedToJinhak(adigaReason: String) {
        if (!unifiedRunning || unifiedPhase != "adiga") return
        val sessionId = unifiedSessionId ?: return
        unifiedPhase = "jinhak"
        unifiedPendingAdigaStart = false
        unifiedJinhakAutoCapture = true
        unifiedAutoCaptureScheduled = false
        unifiedJinhakCapturedPages.clear()

        provider = ProviderId.JINHAK
        localRunId = localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
        localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }
        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$adigaReason")
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        batchButton.text = "현재 진학사 화면 전체 분석·누적"
        diagnosticButton.text = "진학사 전체 분석 전송"
        unifiedButton.text = "통합 수집 종료"
        status.text = "통합 수집 2/2 · 진학사 단계: 로그인 후 필요한 화면을 열기만 하면 자동 분석·누적됩니다."
        webView.loadUrl(ProviderId.JINHAK.homeUrl)
    }

    private fun scheduleUnifiedJinhakAutoCapture(url: String) {
        if (!unifiedRunning || unifiedPhase != "jinhak" || provider != ProviderId.JINHAK || !unifiedJinhakAutoCapture) return
        if (unifiedAutoCaptureScheduled) return
        val canonical = canonicalizeBatchUrl(url)
        if (canonical.isBlank()) return
        val pageKey = RecordUtils.sha256(canonical)
        if (unifiedJinhakCapturedPages.contains(pageKey)) return
        unifiedAutoCaptureScheduled = true
        handler.postDelayed({
            unifiedAutoCaptureScheduled = false
            if (!unifiedRunning || unifiedPhase != "jinhak" || provider != ProviderId.JINHAK) return@postDelayed
            checkSessionState { needsLogin, _ ->
                if (needsLogin) {
                    status.text = "통합 수집 2/2 · 진학사 로그인 후 페이지를 열면 자동 수집을 재개합니다."
                    return@checkSessionState
                }
                if (!unifiedJinhakCapturedPages.add(pageKey)) return@checkSessionState
                collectCurrentPage()
            }
        }, 900L)
    }

    private fun finishUnifiedCollection(reason: String) {
        val sessionId = unifiedSessionId ?: localStore.latestUnifiedSession()
        val wasBatchRunning = batchRunning
        unifiedRunning = false
        unifiedJinhakAutoCapture = false
        unifiedPendingAdigaStart = false
        unifiedAutoCaptureScheduled = false
        unifiedPhase = "completed"
        if (wasBatchRunning) stopBatch("unified-$reason")

        if (sessionId == null) {
            unifiedButton.text = "두 사이트 통합 수집 시작"
            status.text = "종료할 통합 수집 세션이 없습니다."
            return
        }
        localStore.updateUnifiedSession(sessionId, "completed", "completed", reason)
        val export = localStore.buildUnifiedExport(sessionId)
        lastJson = export.toString(2)
        showPreview(lastJson)
        unifiedButton.text = "두 사이트 통합 수집 시작"
        val summary = localStore.unifiedStatus(sessionId)
        cloudOffload.sendDiagnostic(
            "unified", VERSION,
            JSONObject(summary.toString())
                .put("trigger", "unified-finish")
                .put("containsRawAdmissionRecords", false)
        ) { }
        status.text = "통합 수집 종료 · 어디가/진학사 데이터가 하나의 세션으로 연결되었습니다. JSON 저장으로 통합 결과를 내보낼 수 있습니다."
    }

'''
    if start_batch_marker not in m:
        raise SystemExit(f'startBatch marker missing: {p}')
    m = m.replace(start_batch_marker, unified_functions + start_batch_marker, 1)

    p.write_text(m)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')

# ---- Local DB v3: link provider runs and persist sanitized Jinhak page analyses. ----
s = STORE.read_text()
s = s.replace('    2\n) {', '    3\n) {', 1)

create_index_anchor = '''        db.execSQL("CREATE INDEX idx_records_run_year ON records(run_id,year)")\n    }\n'''
create_tables = '''        db.execSQL("CREATE INDEX idx_records_run_year ON records(run_id,year)")\n        db.execSQL("""\n            CREATE TABLE unified_sessions(\n              session_id TEXT PRIMARY KEY,\n              collector_version TEXT NOT NULL,\n              status TEXT NOT NULL,\n              phase TEXT NOT NULL,\n              adiga_run_id TEXT,\n              jinhak_run_id TEXT,\n              completion_reason TEXT,\n              started_at TEXT NOT NULL,\n              updated_at TEXT NOT NULL\n            )\n        """.trimIndent())\n        db.execSQL("""\n            CREATE TABLE unified_analysis_captures(\n              session_id TEXT NOT NULL,\n              capture_id TEXT NOT NULL,\n              provider TEXT NOT NULL,\n              page_key TEXT NOT NULL,\n              page_type TEXT,\n              payload_json TEXT NOT NULL,\n              captured_at TEXT NOT NULL,\n              PRIMARY KEY(session_id,capture_id)\n            )\n        """.trimIndent())\n        db.execSQL("CREATE INDEX idx_unified_sessions_status ON unified_sessions(status,updated_at)")\n        db.execSQL("CREATE UNIQUE INDEX idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")\n    }\n'''
if create_index_anchor not in s:
    raise SystemExit('LocalStore onCreate anchor missing')
s = s.replace(create_index_anchor, create_tables, 1)

upgrade_anchor = '''        if (oldVersion < 2) {\n            val additions = listOf(\n                "capture_version TEXT",\n                "data_scope TEXT",\n                "observed_at TEXT",\n                "quality_state TEXT",\n                "provider_entity_id TEXT",\n                "canonical_university_id TEXT",\n                "canonical_department_id TEXT",\n                "canonical_admission_id TEXT",\n                "application_identity_key TEXT"\n            )\n            for (column in additions) db.execSQL("ALTER TABLE records ADD COLUMN $column")\n            db.execSQL("CREATE INDEX IF NOT EXISTS idx_records_run_quality ON records(run_id,quality_state)")\n            db.execSQL("CREATE INDEX IF NOT EXISTS idx_records_application_identity ON records(run_id,application_identity_key)")\n        }\n    }\n'''
upgrade_new = upgrade_anchor[:-6] + '''        if (oldVersion < 3) {\n            db.execSQL("""\n                CREATE TABLE IF NOT EXISTS unified_sessions(\n                  session_id TEXT PRIMARY KEY,\n                  collector_version TEXT NOT NULL,\n                  status TEXT NOT NULL,\n                  phase TEXT NOT NULL,\n                  adiga_run_id TEXT,\n                  jinhak_run_id TEXT,\n                  completion_reason TEXT,\n                  started_at TEXT NOT NULL,\n                  updated_at TEXT NOT NULL\n                )\n            """.trimIndent())\n            db.execSQL("""\n                CREATE TABLE IF NOT EXISTS unified_analysis_captures(\n                  session_id TEXT NOT NULL,\n                  capture_id TEXT NOT NULL,\n                  provider TEXT NOT NULL,\n                  page_key TEXT NOT NULL,\n                  page_type TEXT,\n                  payload_json TEXT NOT NULL,\n                  captured_at TEXT NOT NULL,\n                  PRIMARY KEY(session_id,capture_id)\n                )\n            """.trimIndent())\n            db.execSQL("CREATE INDEX IF NOT EXISTS idx_unified_sessions_status ON unified_sessions(status,updated_at)")\n            db.execSQL("CREATE UNIQUE INDEX IF NOT EXISTS idx_unified_capture_page ON unified_analysis_captures(session_id,provider,page_key)")\n        }\n    }\n'''
if upgrade_anchor not in s:
    raise SystemExit('LocalStore onUpgrade anchor missing')
s = s.replace(upgrade_anchor, upgrade_new, 1)

# Insert unified session APIs before the existing beginOrResume provider-run function.
api_marker = '    fun beginOrResume(provider: String, collectorVersion: String): String {\n'
unified_api = r'''    fun beginOrResumeUnifiedSession(collectorVersion: String): String {
        val db = writableDatabase
        val existing = db.rawQuery(
            "SELECT session_id FROM unified_sessions WHERE status='running' ORDER BY updated_at DESC LIMIT 1",
            emptyArray()
        ).use { c -> if (c.moveToFirst()) c.getString(0) else null }
        val now = Instant.now().toString()
        if (!existing.isNullOrBlank()) {
            val cv = ContentValues().apply {
                put("collector_version", collectorVersion)
                put("status", "running")
                put("updated_at", now)
            }
            db.update("unified_sessions", cv, "session_id=?", arrayOf(existing))
            return existing
        }
        val sessionId = UUID.randomUUID().toString()
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("collector_version", collectorVersion)
            put("status", "running")
            put("phase", "adiga")
            putNull("adiga_run_id")
            putNull("jinhak_run_id")
            putNull("completion_reason")
            put("started_at", now)
            put("updated_at", now)
        }
        db.insertOrThrow("unified_sessions", null, cv)
        return sessionId
    }

    fun latestUnifiedSession(): String? = readableDatabase.rawQuery(
        "SELECT session_id FROM unified_sessions ORDER BY updated_at DESC LIMIT 1",
        emptyArray()
    ).use { c -> if (c.moveToFirst()) c.getString(0) else null }

    fun attachUnifiedProviderRun(sessionId: String, provider: String, runId: String) {
        val column = when (provider) {
            "adiga" -> "adiga_run_id"
            "jinhak" -> "jinhak_run_id"
            else -> return
        }
        val cv = ContentValues().apply {
            put(column, runId)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("unified_sessions", cv, "session_id=?", arrayOf(sessionId))
    }

    fun updateUnifiedSession(sessionId: String, phase: String, status: String, reason: String?) {
        val cv = ContentValues().apply {
            put("phase", phase)
            put("status", status)
            if (reason == null) putNull("completion_reason") else put("completion_reason", reason)
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.update("unified_sessions", cv, "session_id=?", arrayOf(sessionId))
    }

    fun storeUnifiedAnalysisCapture(
        sessionId: String,
        provider: String,
        pageKey: String,
        pageType: String?,
        payload: JSONObject
    ) {
        if (sessionId.isBlank() || provider.isBlank() || pageKey.isBlank()) return
        val now = Instant.now().toString()
        val captureId = RecordUtils.sha256("$sessionId|$provider|$pageKey")
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            put("capture_id", captureId)
            put("provider", provider)
            put("page_key", pageKey)
            put("page_type", pageType)
            put("payload_json", payload.toString())
            put("captured_at", now)
        }
        writableDatabase.insertWithOnConflict(
            "unified_analysis_captures", null, cv, SQLiteDatabase.CONFLICT_REPLACE
        )
        writableDatabase.execSQL(
            "UPDATE unified_sessions SET updated_at=? WHERE session_id=?",
            arrayOf(now, sessionId)
        )
    }

    fun unifiedStatus(sessionId: String): JSONObject {
        val out = JSONObject().put("sessionId", sessionId)
        var adigaRun: String? = null
        var jinhakRun: String? = null
        readableDatabase.rawQuery(
            "SELECT collector_version,status,phase,adiga_run_id,jinhak_run_id,completion_reason,started_at,updated_at FROM unified_sessions WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c ->
            if (c.moveToFirst()) {
                out.put("collectorVersion", c.getString(0))
                    .put("status", c.getString(1))
                    .put("phase", c.getString(2))
                    .put("completionReason", if (c.isNull(5)) JSONObject.NULL else c.getString(5))
                    .put("startedAt", c.getString(6))
                    .put("updatedAt", c.getString(7))
                adigaRun = if (c.isNull(3)) null else c.getString(3)
                jinhakRun = if (c.isNull(4)) null else c.getString(4)
            }
        }
        out.put("adiga", JSONObject()
            .put("runId", adigaRun ?: JSONObject.NULL)
            .put("stats", adigaRun?.let { stats(it) } ?: JSONObject()))
        out.put("jinhak", JSONObject()
            .put("runId", jinhakRun ?: JSONObject.NULL)
            .put("stats", jinhakRun?.let { stats(it) } ?: JSONObject()))

        val pageTypes = JSONObject()
        var captures = 0
        readableDatabase.rawQuery(
            "SELECT COALESCE(page_type,'unknown'),COUNT(*) FROM unified_analysis_captures WHERE session_id=? GROUP BY COALESCE(page_type,'unknown') ORDER BY 1",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                pageTypes.put(c.getString(0), c.getInt(1))
                captures += c.getInt(1)
            }
        }
        out.put("jinhakAnalysisCaptures", captures)
            .put("jinhakPageTypes", pageTypes)
            .put("sourcePolicy", JSONObject()
                .put("adiga", "official-current-and-historical-baseline")
                .put("jinhak", "user-viewed-derived-analysis-and-prediction")
                .put("predictionIsNotHistoricalActual", true))
        return out
    }

    fun buildUnifiedExport(sessionId: String): JSONObject {
        val status = unifiedStatus(sessionId)
        val adigaRun = status.optJSONObject("adiga")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
        val jinhakRun = status.optJSONObject("jinhak")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
        val analyses = JSONArray()
        readableDatabase.rawQuery(
            "SELECT page_type,payload_json,captured_at FROM unified_analysis_captures WHERE session_id=? ORDER BY captured_at",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                val payload = runCatching { JSONObject(c.getString(1)) }.getOrNull() ?: continue
                analyses.put(JSONObject()
                    .put("pageType", if (c.isNull(0)) JSONObject.NULL else c.getString(0))
                    .put("capturedAt", c.getString(2))
                    .put("analysis", payload))
            }
        }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("type", "admission-unified-two-provider-export")
            .put("session", status)
            .put("combinationPolicy", JSONObject()
                .put("officialBaseline", "adiga")
                .put("predictionAnalysis", "jinhak")
                .put("keepProviderSemanticsSeparate", true)
                .put("doNotOverwriteHistoricalWithPrediction", true))
            .put("sources", JSONObject()
                .put("adiga", JSONObject()
                    .put("runId", adigaRun ?: JSONObject.NULL)
                    .put("records", adigaRun?.let { loadRecords(it) } ?: JSONArray()))
                .put("jinhak", JSONObject()
                    .put("runId", jinhakRun ?: JSONObject.NULL)
                    .put("records", jinhakRun?.let { loadRecords(it) } ?: JSONArray())
                    .put("pageAnalyses", analyses)))
    }

'''
if api_marker not in s:
    raise SystemExit('LocalStore API marker missing')
s = s.replace(api_marker, unified_api + api_marker, 1)
STORE.write_text(s)

# ---- Version metadata ----
g = GRADLE.read_text()
if 'versionCode = 10600' not in g or 'versionName = "0.6.0"' not in g:
    raise SystemExit('v0.6.0 Gradle anchors missing')
g = g.replace('versionCode = 10600', 'versionCode = 10610', 1)
g = g.replace('versionName = "0.6.0"', 'versionName = "0.6.1"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
if 'Admission Collector v0.6.0 Jinhak Full Screen Analyzer' not in mf:
    raise SystemExit('v0.6.0 manifest anchor missing')
mf = mf.replace(
    'Admission Collector v0.6.0 Jinhak Full Screen Analyzer',
    'Admission Collector v0.6.1 Unified Two-Site Collector',
    1,
)
MANIFEST.write_text(mf)

print('v0.6.1 unified two-provider collection patch applied')
