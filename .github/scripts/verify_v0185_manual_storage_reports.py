from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
adapter = (ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()
nav = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt").read_text()
policy = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakManualStorageReportPolicy.kt").read_text()
gradle = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()

required = {
    "version": 'versionName = "0.18.5"' in gradle and 'versionCode = 118500' in gradle,
    "label": 'Admission Hub v0.18.5 Manual Storage Reports' in manifest,
    "policy-import": 'JinhakManualStorageReportPolicy' in main,
    "no-auth-webview-config": 'configureWebView()\n        configureDedicatedJinhakAuthWebView()' not in main,
    "no-auth-webview-instance": 'authWebView = WebView(this)\n        authHost = FrameLayout(this).apply' not in main,
    "manual-entry-gate": 'JinhakManualStorageReportPolicy.isStorageEntry(current)' in main,
    "auto-start-on-storage": '수시 저장소 확인 · 리포트 탐색 시작' in main,
    "no-jinhak-credential-dialog": 'Admission Hub는 진학사 ID/PW·로그인 세션·인증 상태를 저장하거나 판정하지 않습니다.' in main,
    "manual-unified-handoff": 'navigationModel", "application-card-report-only"' in main,
    "manual-diagnostics": 'JINHAK_MANUAL_STORAGE_REPORT_DIAGNOSTICS' in main,
    "adapter-scope": 'JinhakManualStorageReportPolicy.isAllowedMissionUrl(url)' in adapter,
    "storage-policy": 'const val STORAGE_PATH = "/jh/high3/early/four-year-university/library"' in policy,
    "report-policy": 'const val REPORT_PREFIX = "/jh/high3/early/four-year-university/report/"' in policy,
    "auth-disabled": 'const val AUTO_LOGIN = false' in policy and 'const val APP_SESSION_RESTORE = false' in policy and 'const val AUTH_PROOF_CACHE = false' in policy,
    "generic-crawl-disabled": 'const val GENERIC_SITE_CRAWL = false' in policy,
    "navigator-policy": 'JinhakManualStorageReportPolicy.shouldPromoteAction' in nav,
    "navigator-no-generic-labels": '추천\\s*대학' not in nav and '입시\\s*전략' not in nav and '입시\\s*지식' not in nav,
    "report-candidates-active": 'val rawMissionCandidates = JinhakAgentNavigator.candidates(snapshot)' in main,
    "legacy-empty-candidate-gate-removed": 'if (JinhakStorageCompetitionPolicy.ENABLED) emptyList() else JinhakAgentNavigator.candidates(snapshot)' not in main,
    "generic-link-expansion-off": 'var jinhakExpandOutgoingLinks = !jinhakManualReportScope' in main and 'if (JinhakManualStorageReportPolicy.ENABLED) false else jinhakExpandedNavigationStates.add' in main,
    "report-agent-actions-on": 'var jinhakAllowAgentAction = true' in main,
    "legacy-storage-watch-not-authoritative": 'Manual-storage report mode is mission-driven' in main,
    "no-auth-inference": 'callback?.invoke(false, false)' in main and 'callback?.invoke(false, true)' not in main,
    "auth-proof-cleared": 'private fun clearJinhakLegacyAuthState()' in main and '.remove("jinhakAuthProofCollectorVersion")' in main,
    "no-auth-proof-on-create": 'restoreJinhakAuthProofCheckpoint("activity-create")' not in main,
    "no-jinhak-session-keepalive": 'no Jinhak session keep-alive, measurement, or auth diagnostic exists' in main,
    "route-only-batch-guard": 'private fun continueBatchAfterRenderedLoginGuard(url: String, attempt: Int)' in main and 'if (JinhakManualStorageReportPolicy.isAllowedMissionUrl(current)) {\n                scheduleBatchSnapshot()' in main and 'stopBatch("jinhak-left-manual-storage-report-scope")' in main,
    "auth-probe-ui-removed": 'text = "진학사 직접 탐색 안내"' in main,
    "runtime-auth-proof-not-persisted": '.remove("jinhakRealAuthProbeVerifiedAtMs")' in main and '.remove("jinhakAuthProofSafePath")' in main,
    "no-authenticated-evidence-label": 'authStateClass = "authenticated"' not in main,
}

failed = [name for name, ok in required.items() if not ok]
print({"checks": len(required), "failed": failed})
if failed:
    raise SystemExit("v0.18.5 contract verification failed: " + ", ".join(failed))
