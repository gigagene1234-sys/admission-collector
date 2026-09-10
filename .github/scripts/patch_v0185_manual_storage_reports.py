from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
ADAPTER = ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    return text.replace(old, new, 1)


def regex_once(text: str, pattern: str, repl: str, label: str) -> str:
    out, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one regex match, found {count}")
    return out


main = MAIN.read_text()
main = replace_once(
    main,
    "import com.admissionhub.collector.jinhak.JinhakSingleSurfaceStoragePolicy\n",
    "import com.admissionhub.collector.jinhak.JinhakSingleSurfaceStoragePolicy\nimport com.admissionhub.collector.jinhak.JinhakManualStorageReportPolicy\n",
    "manual-policy-import",
)

# Do not initialize the legacy dedicated auth WebView. It may remain as dead compatibility source,
# but it has no instance, no foreground surface, and no active runtime path in v0.18.5.
main = replace_once(
    main,
    "        configureWebView()\n        configureDedicatedJinhakAuthWebView()\n        initializeProcessResumeJournal()",
    "        configureWebView()\n        initializeProcessResumeJournal()",
    "disable-auth-webview-config",
)
main = replace_once(
    main,
    '''        authWebView = WebView(this)\n        authHost = FrameLayout(this).apply {\n            visibility = View.GONE\n            setBackgroundColor(android.graphics.Color.WHITE)\n            addView(authWebView, FrameLayout.LayoutParams(\n                FrameLayout.LayoutParams.MATCH_PARENT,\n                FrameLayout.LayoutParams.MATCH_PARENT\n            ))\n        }''',
    '''        // v0.18.5: no application-owned Jinhak authentication surface exists.\n        // The user browses/logs in directly in the main WebView.\n        authHost = FrameLayout(this).apply {\n            visibility = View.GONE\n        }''',
    "remove-auth-webview-instance",
)

main = replace_once(
    main,
    '''        jinhakSessionConfirmButton = Button(this).apply {\n            text = "진학사 고3 전용 진입 / 현재 고3 탐색 시작"\n            setOnClickListener { confirmJinhakUserSessionAndResume("dashboard-browser-button") }\n        }''',
    '''        jinhakSessionConfirmButton = Button(this).apply {\n            text = "수시 저장소에서 리포트 탐색 시작"\n            setOnClickListener { startBatch() }\n        }''',
    "manual-storage-button",
)

# Jinhak credentials are no longer collected or stored by Admission Hub.
main = replace_once(
    main,
    "    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {\n        if (credentialAutoLoginInFlight) return",
    '''    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {\n        if (which == ProviderId.JINHAK) {\n            credentialVault.clear(ProviderId.JINHAK.wireName)\n            sessionState.text = "○ 진학사 로그인은 사이트에서 직접 진행"\n            status.text = "Admission Hub는 진학사 ID/PW·로그인 세션·인증 상태를 저장하거나 판정하지 않습니다. 아래 사이트에서 직접 로그인한 뒤 수시 저장소까지 이동하세요."\n            return\n        }\n        if (credentialAutoLoginInFlight) return''',
    "disable-jinhak-credential-dialog",
)

# Launch never starts a Jinhak auth probe. The browser is handed to the user.
main = regex_once(
    main,
    r"    private fun startLaunchAwareCollection\(\) \{.*?\n    \}\n\n    private fun startPreferredHubCollection",
    '''    private fun startLaunchAwareCollection() {\n        provider = ProviderId.JINHAK\n        credentialVault.clear(ProviderId.JINHAK.wireName)\n        startupLoginPreflightActive = false\n        startupLoginPreflightVerified = false\n        jinhakTransitionAuthGateActive = false\n        jinhakUserSessionConfirmed = false\n        jinhakAuthVerifiedForBatch = false\n        jinhakV0182ProtectedSessionVerified = false\n        currentBatchTarget = null\n        sessionState.text = "○ 진학사 직접 탐색 대기"\n        status.text = "진학사 사이트에서 직접 로그인하고 수시 저장소까지 이동하세요. 저장소가 실제 화면에 열리면 각 대학·학과 카드의 리포트부터 자동 탐색을 시작합니다."\n    }\n\n    private fun startPreferredHubCollection''',
    "manual-launch",
)

# onPageFinished: no auth/session inference. Storage visibility is the only start gate.
main = regex_once(
    main,
    r'''                CookieManager\.getInstance\(\)\.flush\(\)\n                if \(provider == ProviderId\.JINHAK\) \{.*?\n                \} else \{\n                    scheduleLoginSurfaceDetection\(provider, "page-finished"\)\n                \}\n                if \(jinhakRealAuthProbeActive && provider == ProviderId\.JINHAK\) \{''',
    '''                if (provider != ProviderId.JINHAK) CookieManager.getInstance().flush()\n                if (provider == ProviderId.JINHAK) {\n                    val current = webView.url.orEmpty()\n                    credentialVault.clear(ProviderId.JINHAK.wireName)\n                    jinhakTransitionAuthGateActive = false\n                    jinhakUserSessionConfirmed = false\n                    jinhakAuthVerifiedForBatch = false\n                    jinhakV0182ProtectedSessionVerified = false\n                    jinhakLastCoreVerifiedAtMs = 0L\n                    jinhakLastAuthEvidence = "manual-browser-no-auth-inference"\n\n                    if (!batchRunning) {\n                        if (JinhakManualStorageReportPolicy.isStorageEntry(current)) {\n                            batchPausedForLogin = false\n                            jinhakCoreBootstrapState = "manual-storage-visible"\n                            sessionState.text = "● 수시 저장소 확인 · 리포트 탐색 시작"\n                            status.text = "수시 저장소가 확인되었습니다. 같은 대학·학과 카드에 결합된 리포트만 순차 탐색합니다."\n                            handler.postDelayed({\n                                if (provider == ProviderId.JINHAK && !batchRunning && JinhakManualStorageReportPolicy.isStorageEntry(webView.url)) startBatch()\n                            }, 250L)\n                        } else {\n                            sessionState.text = "○ 진학사 직접 탐색"\n                            status.text = "직접 로그인한 뒤 수시 저장소까지 이동하세요. Admission Hub는 로그인·세션을 건드리지 않습니다."\n                        }\n                        return\n                    }\n\n                    if (!JinhakManualStorageReportPolicy.isAllowedMissionUrl(current)) {\n                        batchPausedForLogin = false\n                        sessionState.text = "○ 리포트 탐색 정지 · 수시 저장소 재진입 필요"\n                        status.text = "수시 저장소/지원 리포트 범위를 벗어났습니다. 로그인 처리는 하지 않습니다. 수시 저장소로 직접 돌아오면 다시 시작합니다."\n                        stopBatch("jinhak-left-manual-storage-report-scope")\n                        return\n                    }\n                } else {\n                    scheduleLoginSurfaceDetection(provider, "page-finished")\n                }\n                if (jinhakRealAuthProbeActive && provider == ProviderId.JINHAK) {''',
    "manual-page-finished",
)

# Batch start uses the visible storage page, not any login/session/auth-proof flags.
main = regex_once(
    main,
    r'''    private fun startBatch\(\) \{\n        if \(provider == ProviderId\.JINHAK\) \{.*?\n        \}\n        if \(startupLoginPreflightActive\) \{''',
    '''    private fun startBatch() {\n        if (provider == ProviderId.JINHAK) {\n            activateV0181PinnedSixFocus("manual-storage-start")\n            val current = webView.url.orEmpty()\n            if (!JinhakManualStorageReportPolicy.isStorageEntry(current)) {\n                batchPausedForLogin = false\n                sessionState.text = "○ 수시 저장소 직접 진입 필요"\n                status.text = "진학사 로그인은 직접 진행하세요. 수시 저장소 페이지가 열린 뒤에만 대학·학과별 리포트 탐색을 시작합니다."\n                Toast.makeText(this, "수시 저장소까지 직접 이동해주세요.", Toast.LENGTH_LONG).show()\n                return\n            }\n            credentialVault.clear(ProviderId.JINHAK.wireName)\n            startupLoginPreflightActive = false\n            startupLoginPreflightVerified = false\n            jinhakTransitionAuthGateActive = false\n            jinhakUserSessionConfirmed = false\n            jinhakAuthVerifiedForBatch = false\n            jinhakV0182ProtectedSessionVerified = false\n            jinhakCoreBootstrapState = "manual-storage-ready"\n            jinhakLastAuthEvidence = "manual-storage-visible-no-auth-inference"\n            jinhakLastCoreVerifiedAtMs = 0L\n            currentBatchTarget = canonicalizeBatchUrl(current)\n        }\n        if (provider != ProviderId.JINHAK && startupLoginPreflightActive) {''',
    "manual-start-batch",
)

# Unified handoff waits at Jinhak; user enters storage manually. No auth gate/probe/autofill.
main = regex_once(
    main,
    r'''    private fun transitionUnifiedToJinhak\(adigaReason: String\) \{.*?\n    \}\n\n    private fun jinhakTargetAuthRedirectKey''',
    '''    private fun transitionUnifiedToJinhak(adigaReason: String) {\n        if (!unifiedRunning || unifiedPhase != "adiga") return\n        val sessionId = unifiedSessionId ?: return\n        unifiedPhase = "jinhak"\n        unifiedPendingAdigaStart = false\n        unifiedPendingJinhakStart = false\n        unifiedJinhakAutoCapture = false\n        unifiedAutoCaptureScheduled = false\n        provider = ProviderId.JINHAK\n        credentialVault.clear(ProviderId.JINHAK.wireName)\n        jinhakTransitionAuthGateActive = false\n        jinhakUserSessionConfirmed = false\n        jinhakAuthVerifiedForBatch = false\n        jinhakV0182ProtectedSessionVerified = false\n        jinhakCoreBootstrapState = "manual-storage-wait"\n        jinhakLastAuthEvidence = "manual-browser-no-auth-inference"\n        jinhakLastCoreVerifiedAtMs = 0L\n        currentBatchTarget = null\n        localRunId = localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)\n        localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }\n        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$adigaReason")\n        localStore.recordSyncState(\n            sessionId,\n            UnifiedSyncState.JINHAK_USER_SESSION_MISSION.name,\n            ProviderId.JINHAK.wireName,\n            JSONObject()\n                .put("authOwnership", JinhakManualStorageReportPolicy.AUTH_OWNERSHIP)\n                .put("autoLogin", false)\n                .put("sessionRestore", false)\n                .put("authProofCache", false)\n                .put("startGate", "visible-susi-storage")\n                .put("navigationModel", "application-card-report-only")\n                .put("genericSiteCrawl", false),\n            true,\n            false\n        )\n        persistRuntimeCheckpoint(forceResume = true)\n        batchButton.text = "수시 저장소에서 리포트 탐색"\n        diagnosticButton.text = "진학사 분석 전송"\n        unifiedButton.text = "통합 수집 종료"\n        sessionState.text = "○ 진학사 수시 저장소 직접 진입 대기"\n        status.text = "어디가 수집은 끝났습니다. 이제 진학사에 직접 로그인하고 수시 저장소까지 이동하세요. 저장소가 열리면 각 대학·학과의 리포트 탐색을 자동 시작합니다."\n    }\n\n    private fun jinhakTargetAuthRedirectKey''',
    "manual-unified-transition",
)

# Auth diagnostics are replaced with navigation-scope diagnostics only.
main = regex_once(
    main,
    r'''    private fun persistJinhakAuthDiagnostics\(trigger: String\) \{.*?\n    \}\n\n    private fun isJinhakPostMissionClosureReady''',
    '''    private fun persistJinhakAuthDiagnostics(trigger: String) {\n        val sessionId = unifiedSessionId ?: return\n        if (provider != ProviderId.JINHAK && unifiedPhase != "jinhak") return\n        runCatching {\n            localStore.recordSyncState(\n                sessionId,\n                "JINHAK_MANUAL_STORAGE_REPORT_DIAGNOSTICS",\n                ProviderId.JINHAK.wireName,\n                JSONObject()\n                    .put("trigger", trigger.take(80))\n                    .put("safePath", runtimeSafePath(webView.url))\n                    .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget))\n                    .put("storageVisible", JinhakManualStorageReportPolicy.isStorageEntry(webView.url))\n                    .put("reportVisible", JinhakManualStorageReportPolicy.isReportUrl(webView.url))\n                    .put("batchRunning", batchRunning)\n                    .put("authOwnership", JinhakManualStorageReportPolicy.AUTH_OWNERSHIP)\n                    .put("autoLogin", false)\n                    .put("credentialStorage", false)\n                    .put("sessionRestore", false)\n                    .put("authProofCache", false)\n                    .put("genericSiteCrawl", false)\n                    .put("missionTargets", jinhakMissionTargetLedger.summary())\n                    .put("missionActionsExecuted", jinhakMissionActionsExecuted)\n                    .put("genericActionsExecuted", jinhakGenericActionsExecuted)\n                    .put("credentialsExported", false)\n                    .put("cookiesExported", false)\n                    .put("sessionSecretsExported", false),\n                false,\n                false\n            )\n        }\n    }\n\n    private fun isJinhakPostMissionClosureReady''',
    "strip-auth-diagnostics",
)

# Do not persist or restore auth proof/session fields in mission runtime.
main = main.replace('''                .put("targetAuthRedirectEpisodeOpenKey", if (jinhakTargetAuthRedirectEpisodeOpenKey.isBlank()) JSONObject.NULL else jinhakTargetAuthRedirectEpisodeOpenKey)\n                .put("authProofCollectorVersion", VERSION)\n                .put("realAuthProbeResult", jinhakRealAuthProbeResult.take(80))\n                .put("realAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)\n                .put("lastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)\n                .put("lastAuthEvidence", jinhakLastAuthEvidence.take(80))\n                .put("authProofSafePath", runtimeSafePath(webView.url).take(300))\n                .put("credentialStored", false)\n                .put("sessionSecretStored", false)''', '''                .put("targetAuthRedirectEpisodeOpenKey", JSONObject.NULL)\n                .put("authOwnership", JinhakManualStorageReportPolicy.AUTH_OWNERSHIP)\n                .put("authStatePersisted", false)\n                .put("credentialStored", false)\n                .put("sessionSecretStored", false)''')
main = regex_once(
    main,
    r'''            if \(runtime\.optString\("authProofCollectorVersion"\) == VERSION\) \{.*?\n            \}\n''',
    '''            // v0.18.5: mission progress may be restored, authentication/session proof may not.\n            jinhakAuthVerifiedForBatch = false\n            jinhakV0182ProtectedSessionVerified = false\n            jinhakLastCoreVerifiedAtMs = 0L\n            jinhakLastAuthEvidence = "manual-browser-no-auth-inference"\n''',
    "remove-auth-proof-restore",
)

# Selected-six recovery also waits for manual storage entry instead of an auth gate.
main = replace_once(
    main,
    '''        status.text = "선택한 6장 보강도 사용자 진학사 로그인 세션만 사용합니다. 아래 사이트에서 로그인 완료 후 버튼을 누르세요."\n        enterJinhakUserSessionGate("selected-six-recovery-user-session")\n        if (!isProviderUrl(webView.url.orEmpty())) loadJinhakV0174High3Only(ProviderId.JINHAK.homeUrl, "legacy-jinhak-home-failsafe")\n        return''',
    '''        credentialVault.clear(ProviderId.JINHAK.wireName)\n        status.text = "선택 6장 보강 준비 완료. 진학사에 직접 로그인하고 수시 저장소까지 이동하면 선택 지원안의 리포트만 보강합니다."\n        sessionState.text = "○ 수시 저장소 직접 진입 대기"\n        currentBatchTarget = null\n        return''',
    "manual-selected-six-recovery",
)

MAIN.write_text(main)

adapter = ADAPTER.read_text()
adapter = replace_once(
    adapter,
    "import com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\n",
    "import com.admissionhub.collector.jinhak.JinhakStorageCompetitionPolicy\nimport com.admissionhub.collector.jinhak.JinhakManualStorageReportPolicy\n",
    "adapter-policy-import",
)
adapter = replace_once(
    adapter,
    '''    override fun isBatchNavigable(url: String): Boolean {\n        if (!accepts(url) || !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) return false\n        if (JinhakStorageCompetitionPolicy.ENABLED && !JinhakStorageCompetitionPolicy.isStorageUrl(url)) return false''',
    '''    override fun isBatchNavigable(url: String): Boolean {\n        if (!accepts(url) || !JinhakStrictHigh3Sandbox.allowsCollectorNavigation(url)) return false\n        if (JinhakManualStorageReportPolicy.ENABLED && !JinhakManualStorageReportPolicy.isAllowedMissionUrl(url)) return false''',
    "adapter-storage-report-scope",
)
ADAPTER.write_text(adapter)

gradle = GRADLE.read_text()
gradle = replace_once(gradle, 'versionCode = 118400', 'versionCode = 118500', 'version-code')
gradle = replace_once(gradle, 'versionName = "0.18.4"', 'versionName = "0.18.5"', 'version-name')
GRADLE.write_text(gradle)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Hub v0.18.4 Single Surface Storage"',
    'android:label="Admission Hub v0.18.5 Manual Storage Reports"',
    'manifest-label',
)
MANIFEST.write_text(manifest)
