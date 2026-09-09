from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"

main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

# Version metadata.
gradle = gradle.replace('versionCode = 117400', 'versionCode = 117500')
gradle = gradle.replace('versionName = "0.17.4"', 'versionName = "0.17.5"')
manifest = manifest.replace(
    'android:label="Admission Hub v0.17.4 Strict High3 Sandbox"',
    'android:label="Admission Hub v0.17.5 Runtime-Stable High3 Sandbox"'
)

# Real-device evidence from v0.17.4 showed 150 snapshot-overlap deferrals and two renderer
# crash cooldowns. Back off the retry loop so WebView gets a larger single-flight window.
if 'private const val JINHAK_SNAPSHOT_OVERLAP_RETRY_MS = 400L' not in main:
    raise SystemExit('expected v0.17.4 snapshot overlap constant not found')
main = main.replace(
    'private const val JINHAK_SNAPSHOT_OVERLAP_RETRY_MS = 400L',
    'private const val JINHAK_SNAPSHOT_OVERLAP_RETRY_MS = 800L'
)
if 'private const val JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS = 2_000L' not in main:
    raise SystemExit('expected v0.17.4 renderer cooldown constant not found')
main = main.replace(
    'private const val JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS = 2_000L',
    'private const val JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS = 5_000L'
)

# Core v0.17.5 fix: a rejected route is a transport/security event, not authentication
# evidence. v0.17.4 cleared userSession/authVerified and paused the batch on every strict
# block, which made benign internal redirects repeatedly stop a valid high3 mission.
block_pattern = re.compile(
    r'    private fun blockJinhakV0174MainFrame\(source: String, target: String, decision: JinhakStrictHigh3Sandbox\.MainFrameDecision\) \{.*?\n    \}\n\n    private fun loadMainUrl',
    re.S,
)
block_replacement = '''    private fun blockJinhakV0174MainFrame(source: String, target: String, decision: JinhakStrictHigh3Sandbox.MainFrameDecision) {
        if (provider != ProviderId.JINHAK) return
        noteJinhakV0174Decision(source, target, decision)

        // v0.17.5: strict route rejection and authentication are independent state machines.
        // Dropping high1/high2/shared/generic/external routes must not manufacture a logout,
        // erase an explicitly confirmed high3 session, or pause an otherwise healthy batch.
        currentBatchTarget = currentBatchTarget?.takeIf { JinhakStrictHigh3Sandbox.allowsCollectorNavigation(it) }
        if (::sessionState.isInitialized) {
            sessionState.text = if (jinhakUserSessionConfirmed || jinhakAuthVerifiedForBatch) {
                "● 고3 세션 유지 · 비허용 이동만 차단"
            } else {
                "○ 고3 전용 샌드박스 · 비허용 이동 차단"
            }
        }
        if (::status.isInitialized) {
            status.text = "비허용 경로만 차단했습니다. 이 차단만으로 로그인 상태를 변경하거나 실행을 멈추지 않습니다."
        }
        persistJinhakAuthDiagnostics("v0175-session-preserving-block:$source")
    }

    private fun loadMainUrl'''
main, count = block_pattern.subn(block_replacement, main, count=1)
if count != 1:
    raise SystemExit(f'failed to replace strict block function: {count}')

# v0.17.4 blanked the WebView after a same-document SPA history rewrite such as /jh/search.
# That destroyed the active DOM and fed the auth-pause loop. Keep network/main-frame policy
# fail-closed, but ignore the exact benign history alias only after explicit high3 confirmation.
history_pattern = re.compile(
    r'            override fun doUpdateVisitedHistory\(view: WebView, url: String, isReload: Boolean\) \{.*?\n            \}\n\n            override fun onPageStarted',
    re.S,
)
history_replacement = '''            override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean) {
                super.doUpdateVisitedHistory(view, url, isReload)
                if (provider != ProviderId.JINHAK) return
                if (jinhakUserSessionConfirmed && JinhakStrictHigh3Sandbox.isBenignSameDocumentHistoryAlias(url)) {
                    recordRuntimeEvent(
                        "jinhak-v0175-benign-spa-history-alias",
                        JSONObject()
                            .put("safePath", runtimeSafePath(url))
                            .put("batchRunning", batchRunning)
                            .put("batchPausedForLogin", batchPausedForLogin),
                        synchronous = false
                    )
                    persistJinhakAuthDiagnostics("v0175-benign-spa-history-alias")
                    return
                }
                val decision = JinhakStrictHigh3Sandbox.decision(url)
                val allowed = decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_HIGH3 ||
                    decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_MEMBER_LOGIN ||
                    decision == JinhakStrictHigh3Sandbox.MainFrameDecision.ALLOW_BLANK
                if (allowed) return
                jinhakV0174HistoryBlocks += 1
                runCatching { view.stopLoading() }
                blockJinhakV0174MainFrame("spa-history", url, decision)
                // Deliberately do not navigate to about:blank. A blocked history mutation is not
                // allowed to tear down the already loaded high3 document or fabricate auth loss.
            }

            override fun onPageStarted'''
main, count = history_pattern.subn(history_replacement, main, count=1)
if count != 1:
    raise SystemExit(f'failed to replace doUpdateVisitedHistory: {count}')

# Diagnostics make the new runtime contract visible in the exported JSON.
main = main.replace(
    '.put("jinhakAuthModel", "user-owned-session-explicit-high3-strict-sandbox-v0174")',
    '.put("jinhakAuthModel", "user-owned-session-explicit-high3-runtime-stable-v0175")'
)
needle = '.put("v0174StrictHigh3Sandbox", true)'
if main.count(needle) < 1:
    raise SystemExit('v0.17.4 diagnostic marker not found')
main = main.replace(
    needle,
    needle + '\n                    .put("v0175BlockedRoutesPreserveUserSession", true)\n                    .put("v0175SpaHistoryBlankNeutralization", false)\n                    .put("v0175SnapshotOverlapRetryMs", JINHAK_SNAPSHOT_OVERLAP_RETRY_MS)\n                    .put("v0175RendererCrashCooldownMs", JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS)'
)

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('Applied v0.17.5 runtime stability + session-preservation patch')
