from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, got {count}: {old[:160]!r}")
    p.write_text(text.replace(old, new, 1))


def patch_if_needed() -> None:
    gradle = Path("app/build.gradle.kts")
    if 'versionName = "0.18.4"' in gradle.read_text():
        print("v0.18.4 product source already applied")
        return

    replace_once(
        "app/build.gradle.kts",
        '        versionCode = 118300\n        versionName = "0.18.3"',
        '        versionCode = 118400\n        versionName = "0.18.4"'
    )

    manifest = Path("app/src/main/AndroidManifest.xml")
    m = manifest.read_text()
    m = m.replace(
        'android:label="Admission Hub v0.18.3 Storage Competition Watch"',
        'android:label="Admission Hub v0.18.4 Native Jinhak Bridge + Adiga Audit"'
    )
    m = m.replace(
        '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />\n',
        '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_DATA_SYNC" />\n\n'
        '    <queries>\n'
        '        <package android:name="com.jinhak.jinhakmobile.android" />\n'
        '    </queries>\n'
    )
    m = m.replace(
        '        <service\n            android:name=".CollectionKeepAliveService"\n            android:exported="false"\n            android:foregroundServiceType="dataSync" />',
        '        <service\n            android:name=".CollectionKeepAliveService"\n            android:exported="false"\n            android:foregroundServiceType="dataSync" />\n'
        '        <service\n'
        '            android:name=".jinhak.JinhakNativeBridgeAccessibilityService"\n'
        '            android:permission="android.permission.BIND_ACCESSIBILITY_SERVICE"\n'
        '            android:exported="false">\n'
        '            <intent-filter>\n'
        '                <action android:name="android.accessibilityservice.AccessibilityService" />\n'
        '            </intent-filter>\n'
        '            <meta-data\n'
        '                android:name="android.accessibilityservice"\n'
        '                android:resource="@xml/jinhak_native_bridge_accessibility" />\n'
        '        </service>'
    )
    manifest.write_text(m)

    path = "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
    p = Path(path)
    text = p.read_text()
    text = text.replace(
        'import com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\n',
        'import com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\nimport com.admissionhub.collector.jinhak.JinhakNativeAppBridge\n'
    )
    text = text.replace(
        '    private var batchPageCount = 0\n    private var batchPaginationRetries = 0',
        '    private var batchPageCount = 0\n'
        '    private var adigaV0184KnownPagesAtStart = 0\n'
        '    private var adigaV0184CompletedPagesAtStart = 0\n'
        '    private var adigaV0184ErrorPagesAtStart = 0\n'
        '    private var adigaV0184KnownDocumentsAtStart = 0\n'
        '    private var adigaV0184CompletedDocumentsAtStart = 0\n'
        '    private var adigaV0184UnresolvedAtStart = 0\n'
        '    private var batchPaginationRetries = 0'
    )
    text = text.replace(
        '        private const val VERSION = "0.18.3"\n        private const val BUILD_CODE = 118300',
        '        private const val VERSION = "0.18.4"\n        private const val BUILD_CODE = 118400'
    )

    old_button = '''        jinhakSessionConfirmButton = Button(this).apply {
            text = "진학사 고3 전용 진입 / 현재 고3 탐색 시작"
            setOnClickListener { confirmJinhakUserSessionAndResume("dashboard-browser-button") }
        }
        hubAdvancedToggle = Button(this).apply { text = "고급 도구" }
'''
    new_button = '''        jinhakSessionConfirmButton = Button(this).apply {
            text = "진학사 고3 전용 진입 / 현재 고3 탐색 시작"
            setOnClickListener { confirmJinhakUserSessionAndResume("dashboard-browser-button") }
        }
        val nativeJinhakRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            addView(Button(this@MainActivity).apply {
                text = "진학사 앱 열기 (로그인 우회)"
                setOnClickListener { launchV0184NativeJinhakBridge() }
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
            addView(Button(this@MainActivity).apply {
                text = "진학사 앱 저장소 관측 가져오기"
                setOnClickListener { importV0184NativeJinhakObservation(showToast = true) }
            }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        }
        hubAdvancedToggle = Button(this).apply { text = "고급 도구" }
'''
    if old_button not in text:
        raise SystemExit("MainActivity: native button anchor missing")
    text = text.replace(old_button, new_button, 1)
    text = text.replace(
        '        root.addView(jinhakSessionConfirmButton, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))\n',
        '        root.addView(jinhakSessionConfirmButton, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))\n'
        '        root.addView(nativeJinhakRow, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))\n'
    )

    helper_anchor = '    private fun dp(value: Int): Int = (value * resources.displayMetrics.density).toInt()\n'
    helpers = r'''    private fun launchV0184NativeJinhakBridge() {
        val bridge = JinhakNativeAppBridge.status(this)
        if (!bridge.serviceEnabled) {
            Toast.makeText(this, "진학사 앱 관측 기능은 사용자가 접근성 설정에서 직접 허용해야 합니다. 설정 후 다시 눌러주세요.", Toast.LENGTH_LONG).show()
            startActivity(JinhakNativeAppBridge.accessibilitySettingsIntent())
            return
        }
        if (!bridge.appInstalled) {
            Toast.makeText(this, "지원하는 진학사 앱 패키지를 이 기기에서 찾지 못했습니다. WebView 수시저장소 방식은 계속 사용할 수 있습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val opened = JinhakNativeAppBridge.launchOfficialApp(this)
        status.text = if (opened) {
            "진학사 공식 앱을 열었습니다. 앱에서 수시 저장소를 표시하면 비밀번호/입력칸을 제외한 화면 텍스트만 기기 내부에 관측합니다."
        } else {
            "진학사 앱 실행에 실패했습니다. WebView 수시저장소 방식으로 계속할 수 있습니다."
        }
    }

    private fun importV0184NativeJinhakObservation(showToast: Boolean): Boolean {
        if (!::localStore.isInitialized) return false
        val latest = JinhakNativeAppBridge.latest(this) ?: run {
            if (showToast) Toast.makeText(this, "진학사 앱에서 수시 저장소 화면이 아직 관측되지 않았습니다.", Toast.LENGTH_LONG).show()
            return false
        }
        val observedAtMs = latest.optLong("observedAtMs", 0L)
        val now = System.currentTimeMillis()
        if (observedAtMs <= 0L || now - observedAtMs !in 0..JinhakNativeAppBridge.MAX_OBSERVATION_AGE_MS) {
            if (showToast) Toast.makeText(this, "최근 진학사 앱 수시 저장소 관측이 없습니다. 앱에서 저장소를 다시 열어주세요.", Toast.LENGTH_LONG).show()
            return false
        }
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        val prior = prefs.getLong("v0184NativeJinhakImportedAtMs", 0L)
        if (observedAtMs <= prior) {
            if (showToast) Toast.makeText(this, "이 진학사 앱 관측은 이미 가져왔습니다.", Toast.LENGTH_SHORT).show()
            return false
        }
        val runId = localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
        val sessionId = unifiedSessionId ?: localStore.latestUnifiedSession()
        val evidence = JSONObject(latest.toString())
            .put("importedAt", Instant.now().toString())
            .put("captureVersion", VERSION)
            .put("nativeBridgeReadOnly", true)
            .put("credentialCaptured", false)
            .put("cookieCaptured", false)
            .put("sessionSecretCaptured", false)
            .put("officialEvidence", false)
            .put("probabilityInferred", false)
        val observationId = localStore.storeObservationEvidence(
            sessionId = sessionId,
            runId = runId,
            provider = ProviderId.JINHAK.wireName,
            safeRouteKey = "native-app://jinhak/susi-storage",
            pageTypeGuess = "jinhak-native-early-storage",
            pageTypeConfidence = 0.80,
            authStateClass = "native-app-user-session",
            explicitContext = JSONObject().put("scope", "susi-saved-application-visible-text"),
            evidence = evidence,
            captureVersion = VERSION
        )
        sessionId?.let { sid ->
            localStore.storeUnifiedAnalysisCapture(
                sessionId = sid,
                provider = ProviderId.JINHAK.wireName,
                pageKey = RecordUtils.sha256("native-jinhak-storage|$observedAtMs"),
                pageType = "jinhak-native-early-storage",
                payload = evidence.put("observationId", observationId)
            )
            localStore.recordSyncState(
                sid,
                "JINHAK_NATIVE_APP_OBSERVATION",
                ProviderId.JINHAK.wireName,
                JSONObject()
                    .put("observedAtMs", observedAtMs)
                    .put("competitionReadings", latest.optJSONArray("competitionReadings")?.length() ?: 0)
                    .put("sourceClass", "jinhak-user-viewed-native-app")
                    .put("officialEvidence", false)
                    .put("probabilityInferred", false),
                false,
                updateOrchestrator = false
            )
        }
        prefs.edit().putLong("v0184NativeJinhakImportedAtMs", observedAtMs).apply()
        val readings = latest.optJSONArray("competitionReadings") ?: JSONArray()
        lastJson = JSONObject()
            .put("collectorVersion", VERSION)
            .put("type", "jinhak-native-app-storage-observation")
            .put("sourceClass", "jinhak-user-viewed-native-app")
            .put("observedAtMs", observedAtMs)
            .put("competitionReadings", readings)
            .put("observationId", observationId)
            .put("sameCardIdentityVerified", false)
            .put("officialEvidence", false)
            .put("probabilityInferred", false)
            .toString(2)
        showPreview(lastJson)
        status.text = "진학사 앱 수시 저장소 관측 가져오기 완료 · 경쟁률 표현 ${readings.length()}개 · 대학/전형 동일카드 결합 전에는 현재 경쟁률로 승격하지 않습니다."
        if (showToast) Toast.makeText(this, "진학사 앱 관측을 가져왔습니다.", Toast.LENGTH_SHORT).show()
        return true
    }

    private fun adigaV0184CompletionStatus(reason: String): String {
        val stats = localRunId?.let { localStore.stats(it) } ?: JSONObject()
        val completedNow = stats.optInt("completedPages", 0)
        val knownNow = stats.optInt("pages", 0)
        val newCompleted = (completedNow - adigaV0184CompletedPagesAtStart).coerceAtLeast(0)
        val unresolvedNow = localRunId?.let { localStore.unresolvedCount(it) } ?: 0
        return "어디가 ${if (reason == "completed") "완료" else "1차 순회 종료"}: 이번 실행 스냅샷 $batchPageCount회 · 시작 시 이미 완료 ${adigaV0184CompletedPagesAtStart}/${adigaV0184KnownPagesAtStart}쪽 · 이번 새 완료 ${newCompleted}쪽 · 현재 누적 ${completedNow}/${knownNow}쪽 · 미해결 $unresolvedNow · '페이지 수'와 '이번 실행 시도'는 서로 다른 누적/세션 지표입니다."
    }

'''
    if helper_anchor not in text:
        raise SystemExit("MainActivity: dp helper anchor missing")
    text = text.replace(helper_anchor, helpers + helper_anchor, 1)

    # Import a newly observed official-app storage screen automatically when the user returns.
    if "override fun onResume()" not in text:
        on_resume = '''    override fun onResume() {
        super.onResume()
        handler.postDelayed({
            if (::localStore.isInitialized && !isFinishing) importV0184NativeJinhakObservation(showToast = false)
        }, 250L)
    }

'''
        text = text.replace(helper_anchor, on_resume + helper_anchor, 1)

    # Explicitly reset the Adiga run-vs-local-resume diagnostics per batch.
    text = text.replace(
        '        batchPageCount = 0\n        batchPaginationRetries = 0',
        '        batchPageCount = 0\n'
        '        adigaV0184KnownPagesAtStart = 0\n'
        '        adigaV0184CompletedPagesAtStart = 0\n'
        '        adigaV0184ErrorPagesAtStart = 0\n'
        '        adigaV0184KnownDocumentsAtStart = 0\n'
        '        adigaV0184CompletedDocumentsAtStart = 0\n'
        '        adigaV0184UnresolvedAtStart = 0\n'
        '        batchPaginationRetries = 0',
        1
    )

    adiga_anchor = '''        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            localRunId = localStore.beginOrResume(provider.wireName, VERSION)
            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
'''
    adiga_new = '''        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            localRunId = localStore.beginOrResume(provider.wireName, VERSION)
            localRunId?.let { runId ->
                val startStats = localStore.stats(runId)
                adigaV0184KnownPagesAtStart = startStats.optInt("pages", 0)
                adigaV0184CompletedPagesAtStart = startStats.optInt("completedPages", 0)
                adigaV0184ErrorPagesAtStart = startStats.optInt("errorPages", 0)
                adigaV0184KnownDocumentsAtStart = startStats.optInt("documents", 0)
                adigaV0184CompletedDocumentsAtStart = startStats.optInt("completedDocuments", 0)
                adigaV0184UnresolvedAtStart = localStore.unresolvedCount(runId)
                recordRuntimeEvent("adiga-v0184-local-resume-baseline", JSONObject()
                    .put("attemptModel", "session-snapshot-attempts-vs-persisted-local-resume")
                    .put("pagesKnownAtStart", adigaV0184KnownPagesAtStart)
                    .put("pagesCompletedAtStart", adigaV0184CompletedPagesAtStart)
                    .put("errorPagesAtStart", adigaV0184ErrorPagesAtStart)
                    .put("documentsKnownAtStart", adigaV0184KnownDocumentsAtStart)
                    .put("documentsCompletedAtStart", adigaV0184CompletedDocumentsAtStart)
                    .put("unresolvedAtStart", adigaV0184UnresolvedAtStart))
            }
            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
'''
    if adiga_anchor not in text:
        raise SystemExit("MainActivity: Adiga local-first anchor missing")
    text = text.replace(adiga_anchor, adiga_new, 1)

    text = text.replace(
        '            LOCAL_FIRST_BETA && effectiveReason == "completed-with-local-errors" ->\n                "Local-First 1차 순회 종료: 미해결 오류는 로컬에 저장됨 / 다음 실행에서 해당 지점만 재개합니다."\n            LOCAL_FIRST_BETA && effectiveReason == "completed" ->\n                "어디가 로컬 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 재시도 $batchPaginationRetries / 로컬 레코드 ${localRunId?.let { localStore.stats(it).optInt("records") } ?: batchRecords.length()}"',
        '            LOCAL_FIRST_BETA && provider == ProviderId.ADIGA && effectiveReason == "completed-with-local-errors" ->\n                adigaV0184CompletionStatus(effectiveReason)\n            LOCAL_FIRST_BETA && provider == ProviderId.ADIGA && effectiveReason == "completed" ->\n                adigaV0184CompletionStatus(effectiveReason)'
    )

    text = text.replace(
        '                .put("attemptedPages", batchPageCount)\n                .put("successfulPages", batchSnapshots.length())',
        '                .put("attemptedPages", batchPageCount)\n'
        '                .put("attemptedPagesMeaning", "current-process-snapshot-attempts-not-total-known-pages")\n'
        '                .put("adigaAttemptModel", if (provider == ProviderId.ADIGA) "session-snapshot-attempts-vs-persisted-local-resume-v0184" else JSONObject.NULL)\n'
        '                .put("adigaPagesKnownAtStart", if (provider == ProviderId.ADIGA) adigaV0184KnownPagesAtStart else JSONObject.NULL)\n'
        '                .put("adigaPagesCompletedAtStart", if (provider == ProviderId.ADIGA) adigaV0184CompletedPagesAtStart else JSONObject.NULL)\n'
        '                .put("adigaErrorPagesAtStart", if (provider == ProviderId.ADIGA) adigaV0184ErrorPagesAtStart else JSONObject.NULL)\n'
        '                .put("adigaDocumentsKnownAtStart", if (provider == ProviderId.ADIGA) adigaV0184KnownDocumentsAtStart else JSONObject.NULL)\n'
        '                .put("adigaDocumentsCompletedAtStart", if (provider == ProviderId.ADIGA) adigaV0184CompletedDocumentsAtStart else JSONObject.NULL)\n'
        '                .put("adigaUnresolvedAtStart", if (provider == ProviderId.ADIGA) adigaV0184UnresolvedAtStart else JSONObject.NULL)\n'
        '                .put("adigaNewCompletedPagesThisRun", if (provider == ProviderId.ADIGA) (localStats.optInt("completedPages", 0) - adigaV0184CompletedPagesAtStart).coerceAtLeast(0) else JSONObject.NULL)\n'
        '                .put("successfulPages", batchSnapshots.length())',
        1
    )

    p.write_text(text)
    print("v0.18.4 native Jinhak bridge + Adiga audit patch applied")


if __name__ == "__main__":
    patch_if_needed()
