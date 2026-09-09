from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
TOPOLOGY = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakSiteTopology.kt"
BUILD = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and new in text:
        return text
    raise SystemExit(f"{label}: expected one old token, found {count}")


def replace_all(text: str, old: str, new: str, label: str, min_count: int = 1) -> str:
    count = text.count(old)
    if count == 0 and new in text:
        return text
    if count < min_count:
        raise SystemExit(f"{label}: expected at least {min_count}, found {count}")
    return text.replace(old, new)

# -----------------------------------------------------------------------------
# Metadata
# -----------------------------------------------------------------------------
build = BUILD.read_text()
build = replace_once(build, "versionCode = 117100", "versionCode = 117200", "versionCode")
build = replace_once(build, 'versionName = "0.17.1"', 'versionName = "0.17.2"', "versionName")
BUILD.write_text(build)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Hub v0.17.1 User-Owned Jinhak Session"',
    'android:label="Admission Hub v0.17.2 Bootstrap-Safe Jinhak Session"',
    "manifest label",
)
MANIFEST.write_text(manifest)

# -----------------------------------------------------------------------------
# Jinhak topology: the public/current high3 search page is a bootstrap surface.
# Protected report/library routes stay protected mission targets and are not used
# as the first post-confirmation navigation anymore.
# -----------------------------------------------------------------------------
topo = TOPOLOGY.read_text()
old_seeds = '''    fun missionSeeds(): List<String> = listOf(
        "$ROOT/jh/high3/early/four-year-university/library",
        "$ROOT/jh/high3/early/four-year-university/university-major-predict",
        "$ROOT/jh/high3/early/four-year-university/search",
        "$ROOT/jh/high3/univ-major/univ-info/univ-search",
        "$ROOT/jh/high3/ipsi-analysis/ipsi-strategy"
    )
'''
new_seeds = '''    fun userSessionBootstrapUrl(): String = "$ROOT/jh/high3/early/four-year-university/search"

    fun protectedCoreProbeUrl(): String = "$ROOT/jh/high3/early/four-year-university/library"

    fun isUserSessionBootstrapUrl(url: String): Boolean {
        val path = runCatching { URI(url).path?.lowercase().orEmpty() }.getOrDefault("")
        return path.trimEnd('/') == "/jh/high3/early/four-year-university/search"
    }

    fun missionSeeds(): List<String> = listOf(
        userSessionBootstrapUrl(),
        protectedCoreProbeUrl(),
        "$ROOT/jh/high3/early/four-year-university/university-major-predict",
        "$ROOT/jh/high3/univ-major/univ-info/univ-search",
        "$ROOT/jh/high3/ipsi-analysis/ipsi-strategy"
    )
'''
topo = replace_once(topo, old_seeds, new_seeds, "Jinhak mission bootstrap/seeds")

old_priority = '''    fun priority(url: String, label: String = ""): Int {
        val lane = lane(url, label)
        var score = lane.basePriority
'''
new_priority = '''    fun priority(url: String, label: String = ""): Int {
        val lane = lane(url, label)
        var score = lane.basePriority
        if (isUserSessionBootstrapUrl(url)) score = maxOf(score, 86)
'''
topo = replace_once(topo, old_priority, new_priority, "bootstrap priority")

old_default = '''    fun isDefaultSusiCoreTraversalUrl(url: String, label: String = ""): Boolean = when (lane(url, label)) {
'''
new_default = '''    fun isDefaultSusiCoreTraversalUrl(url: String, label: String = ""): Boolean {
        if (isUserSessionBootstrapUrl(url)) return true
        return when (lane(url, label)) {
'''
topo = replace_once(topo, old_default, new_default, "bootstrap default traversal open")
old_default_end = '''        JinhakMissionLane.MEDIA,
        JinhakMissionLane.UNKNOWN -> false
    }

    fun shouldExpandEditorial'''
new_default_end = '''        JinhakMissionLane.MEDIA,
        JinhakMissionLane.UNKNOWN -> false
        }
    }

    fun shouldExpandEditorial'''
topo = replace_once(topo, old_default_end, new_default_end, "bootstrap default traversal close")
TOPOLOGY.write_text(topo)

# -----------------------------------------------------------------------------
# Main activity: screen-recording-derived fix.
# Facts reproduced by the recording + diagnostics:
#  1. visible login succeeds and logged-in home is shown;
#  2. user presses the v0.17.1 confirmation button;
#  3. v0.17.1 immediately replays currentBatchTarget (protected /library);
#  4. site redirects that direct protected request to /member/login;
#  5. the app revokes the user's assertion and repeats the gate.
# v0.17.2 never immediately replays the redirecting protected target and never
# revokes an already-confirmed user session merely because a route redirected.
# -----------------------------------------------------------------------------
text = MAIN.read_text()
text = replace_once(text, 'private const val VERSION = "0.17.1"', 'private const val VERSION = "0.17.2"', "VERSION")
text = replace_once(text, 'private const val BUILD_CODE = 117100', 'private const val BUILD_CODE = 117200', "BUILD_CODE")

state_anchor = '''    private var jinhakUserSessionPauses = 0
'''
state_new = state_anchor + '''    private var jinhakV0172BootstrapStarts = 0
    private var jinhakV0172ProtectedRetryDeferrals = 0
    private var jinhakV0172LoginRedirectLoopBreaks = 0
    private val jinhakV0172DeferredProtectedTargets = linkedSetOf<String>()
'''
if "jinhakV0172BootstrapStarts" not in text:
    text = replace_once(text, state_anchor, state_new, "v0172 state")

# Existing code often used missionSeeds().first as an implicit protected-core probe.
# missionSeeds now starts with the public bootstrap, so preserve those old semantics
# explicitly wherever the old first-seed shorthand remains.
text = text.replace(
    'JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()',
    'JinhakSiteTopology.protectedCoreProbeUrl()'
)
text = text.replace(
    'JinhakSiteTopology.missionSeeds().firstOrNull()?.takeIf { it.isNotBlank() }',
    'JinhakSiteTopology.protectedCoreProbeUrl().takeIf { it.isNotBlank() }'
)

# Insert redirect-loop breaker before the user-session gate.
gate_marker = '''    private fun enterJinhakUserSessionGate(reason: String) {
'''
if "private fun breakJinhakLoginRedirectLoopAfterUserConfirmation" not in text:
    helper = '''    private fun breakJinhakLoginRedirectLoopAfterUserConfirmation(reason: String): Boolean {
        if (provider != ProviderId.JINHAK || !jinhakUserSessionConfirmed) return false
        val visibleUrl = webView.url.orEmpty()
        val loginSurface = isProviderLoginUrl(ProviderId.JINHAK, visibleUrl) ||
            JinhakHigh3AuthRoute.isMemberLoginSurface(visibleUrl) ||
            JinhakHigh3AuthRoute.isGenericProductLogin(visibleUrl)
        if (!loginSurface) return false

        val deferred = currentBatchTarget
            ?.takeIf { it.isNotBlank() && isProviderUrl(it) && !isProviderLoginUrl(ProviderId.JINHAK, it) }
            ?.let { canonicalizeBatchUrl(it) }
            ?.takeIf { it.isNotBlank() && !JinhakSiteTopology.isUserSessionBootstrapUrl(it) }
        if (deferred != null) {
            if (jinhakV0172DeferredProtectedTargets.add(deferred)) {
                jinhakV0172ProtectedRetryDeferrals += 1
            }
            // The queue had already dispatched this target. Treat this immediate cycle as
            // consumed so discovery cannot immediately put the same redirecting route back.
            batchVisited.add(deferred)
            batchQueued.remove(deferred)
        }
        currentBatchTarget = null
        batchPausedForLogin = false
        jinhakAuthVerifiedForBatch = true // compatibility flag == user assertion only
        jinhakV0172LoginRedirectLoopBreaks += 1
        jinhakCoreBootstrapState = "v0172-user-confirmed-bootstrap-recovery"
        jinhakLastAuthEvidence = "user-confirmed-session-authority-preserved-after-site-login-redirect"
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
        if (::slowLaneHost.isInitialized) slowLaneHost.visibility = View.GONE
        webView.visibility = View.VISIBLE
        status.text = "진학사가 보호경로를 로그인 화면으로 돌려보냈지만 사용자 로그인 확인은 취소하지 않았습니다. 같은 보호경로를 즉시 재생하지 않고 공개 고3 시작점에서 탐색을 이어갑니다."
        recordRuntimeEvent(
            "jinhak-v0172-login-redirect-loop-break",
            JSONObject()
                .put("reason", reason.take(100))
                .put("visibleSafePath", runtimeSafePath(visibleUrl))
                .put("deferredTargetSafePath", runtimeSafePath(deferred))
                .put("sessionAuthority", "user")
                .put("userConfirmationPreserved", true)
                .put("collectorVerifiedLogin", false)
                .put("protectedTargetImmediatelyReplayed", false)
        )
        persistJinhakAuthDiagnostics("v0172-login-redirect-loop-break:$reason")
        handler.postDelayed({
            if (!batchRunning || provider != ProviderId.JINHAK || !jinhakUserSessionConfirmed) return@postDelayed
            jinhakV0172BootstrapStarts += 1
            webView.loadUrl(JinhakSiteTopology.userSessionBootstrapUrl())
        }, 140L)
        return true
    }

'''
    text = replace_once(text, gate_marker, helper + gate_marker, "insert redirect-loop breaker")

# Once the user has asserted that login is complete, a site redirect must not revoke
# that user-owned assertion. It becomes a target deferral/bootstrap recovery instead.
gate_open_old = '''    private fun enterJinhakUserSessionGate(reason: String) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        jinhakUserSessionGateEntries += 1
'''
gate_open_new = '''    private fun enterJinhakUserSessionGate(reason: String) {
        if (provider != ProviderId.JINHAK) provider = ProviderId.JINHAK
        if (breakJinhakLoginRedirectLoopAfterUserConfirmation(reason)) return
        jinhakUserSessionGateEntries += 1
'''
text = replace_once(text, gate_open_old, gate_open_new, "preserve confirmed user authority")

# Screen-recording root cause: v0.17.1's paused branch reloaded currentBatchTarget.
# Replace that with a one-way bootstrap and defer the protected target that caused the pause.
old_paused = '''            wasPaused && batchRunning -> {
                val retry = currentBatchTarget
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || !jinhakUserSessionConfirmed) return@postDelayed
                    if (!retry.isNullOrBlank() && isProviderUrl(retry) && !JinhakGradeRouteFence.isBlockedLowerGrade(retry)) {
                        webView.loadUrl(retry)
                    } else {
                        loadNextBatchPage()
                    }
                }, 120L)
            }
'''
new_paused = '''            wasPaused && batchRunning -> {
                val redirectedTarget = currentBatchTarget
                    ?.takeIf { it.isNotBlank() && isProviderUrl(it) && !isProviderLoginUrl(ProviderId.JINHAK, it) }
                    ?.let { canonicalizeBatchUrl(it) }
                    ?.takeIf { it.isNotBlank() && !JinhakSiteTopology.isUserSessionBootstrapUrl(it) }
                if (redirectedTarget != null) {
                    if (jinhakV0172DeferredProtectedTargets.add(redirectedTarget)) {
                        jinhakV0172ProtectedRetryDeferrals += 1
                    }
                    batchVisited.add(redirectedTarget)
                    batchQueued.remove(redirectedTarget)
                }
                currentBatchTarget = null
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || !jinhakUserSessionConfirmed) return@postDelayed
                    jinhakV0172BootstrapStarts += 1
                    webView.loadUrl(JinhakSiteTopology.userSessionBootstrapUrl())
                }, 120L)
            }
'''
text = replace_once(text, old_paused, new_paused, "remove protected target immediate replay")

# Initial unified Jinhak handoff should point at the public service bootstrap, not /library.
text = replace_once(
    text,
    'currentBatchTarget = canonicalizeBatchUrl(JinhakSiteTopology.protectedCoreProbeUrl())\n        enterJinhakUserSessionGate("unified-transition")',
    'currentBatchTarget = canonicalizeBatchUrl(JinhakSiteTopology.userSessionBootstrapUrl())\n        jinhakV0172DeferredProtectedTargets.clear()\n        jinhakV0172BootstrapStarts = 0\n        jinhakV0172ProtectedRetryDeferrals = 0\n        jinhakV0172LoginRedirectLoopBreaks = 0\n        enterJinhakUserSessionGate("unified-transition")',
    "unified public bootstrap target",
)

# UI/status language should describe the exact route policy visible to the user.
text = text.replace(
    'status.text = "사용자가 로그인 완료를 확인했습니다. Collector는 별도 인증 검사 없이 현재 WebView 세션을 그대로 사용해 진학사 탐색을 실행합니다."',
    'status.text = "사용자가 로그인 완료를 확인했습니다. Collector는 별도 인증 검사 없이 현재 WebView 세션을 사용하며, 보호경로를 즉시 재생하지 않고 공개 고3 서비스 시작점에서 탐색을 시작합니다."'
)
text = text.replace(
    'status.text = "아래 진학사 화면에서 직접 로그인 상태를 확인하세요. 앱은 ID/PW·쿠키·로그인 여부·세션 연장을 건드리지 않습니다. 로그인 완료 후 버튼을 누르면 로그인 완료 상태라고 가정하고 탐색합니다."',
    'status.text = "아래 진학사 화면에서 직접 로그인 상태를 확인하세요. 앱은 ID/PW·쿠키·로그인 여부·세션 연장을 건드리지 않습니다. 로그인 완료 후 버튼을 누르면 공개 고3 시작점에서 탐색하며 보호경로를 즉시 재생하지 않습니다."'
)

# Update diagnostics model label and expose only counters/safe-path behavior.
text = text.replace('"user-owned-session-login-assumed-v0171"', '"user-owned-session-login-assumed-v0172-bootstrap-safe"')
diag_anchor = '''                    .put("userSessionPauses", jinhakUserSessionPauses)
'''
diag_extra = diag_anchor + '''                    .put("v0172BootstrapStarts", jinhakV0172BootstrapStarts)
                    .put("v0172ProtectedRetryDeferrals", jinhakV0172ProtectedRetryDeferrals)
                    .put("v0172LoginRedirectLoopBreaks", jinhakV0172LoginRedirectLoopBreaks)
                    .put("v0172DeferredProtectedTargets", jinhakV0172DeferredProtectedTargets.size)
'''
if 'put("v0172BootstrapStarts"' not in text:
    count = text.count(diag_anchor)
    if count < 1:
        raise SystemExit("diagnostic anchor missing")
    text = text.replace(diag_anchor, diag_extra)

# Update v0.17.1 status/runtime labels where they describe the active user-session gate.
text = text.replace('v0171-user-confirmed-login-assumed', 'v0172-user-confirmed-login-assumed')
text = text.replace('jinhak-v0171-user-session-confirmed', 'jinhak-v0172-user-session-confirmed')
text = text.replace('v0171-user-session-confirmed:', 'v0172-user-session-confirmed:')

MAIN.write_text(text)
print("v0.17.2 patch applied: public bootstrap first, no immediate protected retry, user confirmation preserved across protected-route login redirects")
