from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
BUILD = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and text.count(new) == 1:
        return text
    raise SystemExit(f"{label}: expected one old token, found {count}")


def replace_member(text: str, name: str, replacement: str) -> str:
    marker = f"    private fun {name}"
    start = text.find(marker)
    if start < 0:
        if replacement.strip() in text:
            return text
        raise SystemExit(f"member not found: {name}")
    tail = text[start + len(marker):]
    match = re.search(r"\n    (?:private|protected|public|internal|override)\s+(?:fun|val|var|class|object)\b", tail)
    if not match:
        raise SystemExit(f"next top-level member not found after: {name}")
    end = start + len(marker) + match.start()
    return text[:start] + replacement.rstrip() + text[end:]


# Version metadata.
build = BUILD.read_text()
build = replace_once(build, "versionCode = 116900", "versionCode = 117000", "versionCode")
build = replace_once(build, 'versionName = "0.16.9"', 'versionName = "0.17.0"', "versionName")
BUILD.write_text(build)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Hub v0.16.9 Event-Driven High3 Auth"',
    'android:label="Admission Hub v0.17.0 Server-Owned Auth"',
    "manifest label",
)
MANIFEST.write_text(manifest)

text = MAIN.read_text()
text = replace_once(text, 'private const val VERSION = "0.16.9"', 'private const val VERSION = "0.17.0"', "VERSION")
text = replace_once(text, 'private const val BUILD_CODE = 116900', 'private const val BUILD_CODE = 117000', "BUILD_CODE")

# v0.17.0 proof counters. Forced auth and DOM auth checks are deliberately zero-only counters.
anchor = "    private var jinhakV0168LegacyNavigationSuppressions = 0\n"
addition = anchor + (
    "    private var jinhakV0170ServerLoginRedirects = 0\n"
    "    private var jinhakV0170NaturalHigh3Returns = 0\n"
    "    private var jinhakV0170ProtectedMissionStarts = 0\n"
    "    private var jinhakV0170ForcedAuthNavigations = 0\n"
    "    private var jinhakV0170DomAuthChecks = 0\n"
)
if "private var jinhakV0170ServerLoginRedirects" not in text:
    if text.count(anchor) != 1:
        raise SystemExit("v0170 counter anchor missing or duplicated")
    text = text.replace(anchor, addition, 1)

reset_anchor = "        jinhakV0168LegacyNavigationSuppressions = 0\n"
reset_addition = reset_anchor + (
    "        jinhakV0170ServerLoginRedirects = 0\n"
    "        jinhakV0170NaturalHigh3Returns = 0\n"
    "        jinhakV0170ProtectedMissionStarts = 0\n"
    "        jinhakV0170ForcedAuthNavigations = 0\n"
    "        jinhakV0170DomAuthChecks = 0\n"
)
if "        jinhakV0170ServerLoginRedirects = 0" not in text:
    if text.count(reset_anchor) != 1:
        raise SystemExit("v0170 reset anchor missing or duplicated")
    text = text.replace(reset_anchor, reset_addition, 1)

# The generic session detector remains for Adiga only. Jinhak never evaluates DOM/login/logout controls.
check_anchor = '    private fun checkSessionState(callback: ((Boolean, Boolean) -> Unit)? = null) {\n        val js = """\n'
check_new = (
    '    private fun checkSessionState(callback: ((Boolean, Boolean) -> Unit)? = null) {\n'
    '        if (provider == ProviderId.JINHAK) {\n'
    '            // v0.17.0: Jinhak authentication is server-owned. No DOM/login/logout heuristic is run.\n'
    '            callback?.invoke(false, true)\n'
    '            return\n'
    '        }\n'
    '        val js = """\n'
)
if check_new not in text:
    if text.count(check_anchor) != 1:
        raise SystemExit("checkSessionState anchor missing")
    text = text.replace(check_anchor, check_new, 1)

# Compatibility-named function now means: open only a real protected high3 mission route.
text = replace_member(text, "openJinhakDirectHigh3Auth", '''    private fun openJinhakDirectHigh3Auth(reason: String, requestedTarget: String?) {
        if (provider != ProviderId.JINHAK) return
        val current = webView.url.orEmpty()
        if (JinhakGradeRouteFence.isBlockedLowerGrade(current)) {
            hardBlockJinhakLowerGradeNavigation("v0170-protected-start-lower-grade:$reason", current)
            return
        }
        if (JinhakHigh3AuthRoute.isMemberLoginSurface(current) || JinhakHigh3AuthRoute.isGenericProductLogin(current)) {
            markJinhakDirectAuthWait("v0170-site-login-already-visible:$reason", current)
            return
        }
        val target = JinhakHigh3AuthRoute.sanitizeReturnTarget(
            requestedTarget?.takeIf { it.isNotBlank() } ?: currentBatchTarget
        )
        if (target.isBlank() || JinhakGradeRouteFence.isBlockedLowerGrade(target)) return
        jinhakV0170ProtectedMissionStarts += 1
        jinhakV0167AuthWaitActive = false
        jinhakV0167AuthReturnTarget = target
        jinhakCoreBootstrapState = "v0170-protected-route-dispatched"
        jinhakLastAuthEvidence = "server-owned-auth-no-probe"
        sessionState.text = "● 진학사 보호경로 요청 · 인증 판단은 사이트에 위임"
        status.text = "Collector는 로그인 페이지를 만들거나 열지 않습니다. 보호경로를 요청하고 진학사 서버의 응답만 따릅니다."
        recordRuntimeEvent(
            "jinhak-v0170-protected-route-dispatched",
            JSONObject()
                .put("reason", reason.take(80))
                .put("targetSafePath", runtimeSafePath(target))
                .put("forcedAuthNavigation", false)
                .put("domAuthCheck", false)
                .put("credentialRead", false)
        )
        webView.visibility = View.VISIBLE
        webView.loadUrl(target)
        persistJinhakAuthDiagnostics("v0170-protected-route-dispatched")
    }''')

# A site-owned login redirect pauses exactly the active mission. No rewrite, auto-submit or polling.
text = replace_member(text, "markJinhakDirectAuthWait", '''    private fun markJinhakDirectAuthWait(reason: String, url: String) {
        if (provider != ProviderId.JINHAK) return
        val siteLogin = JinhakHigh3AuthRoute.isMemberLoginSurface(url) || JinhakHigh3AuthRoute.isGenericProductLogin(url)
        if (!siteLogin) return
        if (!jinhakV0167AuthWaitActive) jinhakV0167AuthWaitEntries += 1
        else jinhakV0167AuthWaitDuplicateSuppressions += 1
        jinhakV0167AuthWaitActive = true
        jinhakV0170ServerLoginRedirects += 1
        val returnTarget = JinhakHigh3AuthRoute.returnUrl(url)
        if (!returnTarget.isNullOrBlank() && JinhakHigh3AuthRoute.isAllowedHigh3Target(returnTarget)) {
            jinhakV0167AuthReturnTarget = returnTarget
        }
        jinhakAuthVerifiedForBatch = false
        if (batchRunning) batchPausedForLogin = true
        jinhakCoreBootstrapState = "v0170-waiting-for-site-login"
        jinhakLastAuthEvidence = "server-login-redirect-visible"
        sessionState.text = "○ 진학사 사이트 로그인 대기"
        status.text = "진학사 서버가 로그인 화면으로 이동시켰습니다. Collector는 주소를 바꾸거나 입력·제출·인증 판정을 하지 않습니다. 사이트가 high3로 자연 복귀하면 같은 mission을 이어갑니다."
        webView.visibility = View.VISIBLE
        recordRuntimeEvent(
            "jinhak-v0170-site-login-redirect",
            JSONObject()
                .put("reason", reason.take(80))
                .put("loginSafePath", runtimeSafePath(url))
                .put("pausedTargetSafePath", runtimeSafePath(currentBatchTarget))
                .put("forcedAuthNavigation", false)
                .put("credentialRead", false)
                .put("credentialSubmitted", false)
                .put("polling", false)
        )
        persistJinhakAuthDiagnostics("v0170-site-login-redirect")
    }''')

# Login/lower-grade fences are never allowed to terminal-stop the whole Jinhak batch in v0.17.0.
text = replace_member(text, "jinhakLowerGradeAuthFenceShouldTerminate", '''    private fun jinhakLowerGradeAuthFenceShouldTerminate(): Boolean {
        return false
    }''')

# Login compatibility is now a passive server redirect observer only.
text = replace_member(text, "handleJinhakV0912AuthCompatibilityPage", '''    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return false
        return when (JinhakHigh3AuthRoute.decision(url)) {
            JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE -> {
                hardBlockJinhakLowerGradeNavigation("v0170-lower-grade-drop", url)
                true
            }
            JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_CANONICAL_AUTH -> {
                markJinhakDirectAuthWait("v0170-site-login-visible", url)
                true
            }
            JinhakHigh3AuthRoute.MainFrameDecision.REWRITE_GENERIC_LOGIN -> {
                // Unreachable under JinhakHigh3AuthRoute schema 3; fail passive if encountered.
                markJinhakDirectAuthWait("v0170-legacy-generic-login", url)
                true
            }
            else -> false
        }
    }''')

# A natural high3 navigation is sufficient to resume transport; no logout-control DOM proof is used.
text = replace_member(text, "verifyRecoveredJinhakHigh3AndResume", '''    private fun verifyRecoveredJinhakHigh3AndResume(url: String): Boolean {
        if (provider != ProviderId.JINHAK || !JinhakGradeRouteFence.isHigh3(url)) return false
        val owned = jinhakAuthCompatibilityWindowActive() || batchPausedForLogin || jinhakTransitionAuthGateActive ||
            startupLoginPreflightActive || jinhakV0167AuthWaitActive || jinhakRealAuthProbeActive
        if (!owned) return false
        jinhakV0170NaturalHigh3Returns += 1
        jinhakV0912ProtectedCoreVerified += 1
        jinhakV0167AuthExitsToHigh3 += 1
        jinhakV0167AuthWaitActive = false
        jinhakV0167AuthReturnTarget = ""
        credentialAwaitingLoginExitProvider = null
        jinhakLowerGradeHigh3RecoverySuccesses += 1
        jinhakLowerGradeRecoveryInFlight = false
        jinhakLowerGradeManualGateActive = false
        jinhakLowerGradeLoginFenceLatched = false
        // Compatibility flag for downstream collection gates: means "high3 route reached", not DOM-auth proof.
        jinhakAuthVerifiedForBatch = true
        jinhakReauthCycles = 0
        jinhakCoreBootstrapState = "v0170-high3-reached-server-owned"
        jinhakLastAuthEvidence = "natural-high3-navigation-no-dom-proof"
        jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
        recordRuntimeEvent(
            "jinhak-v0170-natural-high3-return",
            JSONObject()
                .put("count", jinhakV0170NaturalHigh3Returns)
                .put("safePath", runtimeSafePath(url))
                .put("domAuthCheck", false)
                .put("forcedAuthNavigation", false)
                .put("batchPausedForLogin", batchPausedForLogin)
        )
        sessionState.text = "● 진학사 high3 도달 · 수집 재개"
        when {
            batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth("v0170-natural-high3-return")
            jinhakRealAuthProbeActive -> finishJinhakRealAuthProbe("v0170-high3-reached", success = true)
            unifiedRunning && unifiedPhase == "jinhak" && jinhakTransitionAuthGateActive && !batchRunning -> {
                jinhakTransitionAuthGateActive = false
                unifiedPendingJinhakStart = false
                status.text = "진학사 high3 도달 · 별도 인증 검사 없이 수집을 시작합니다."
                handler.postDelayed({
                    if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
                }, 120L)
            }
            startupLoginPreflightActive -> onStartupProviderAuthenticated(ProviderId.JINHAK, startupLoginPollGeneration)
            else -> status.text = "진학사 high3 보호경로를 유지합니다."
        }
        persistJinhakAuthDiagnostics("v0170-natural-high3-return")
        return true
    }''')

# Jinhak Collector-side credential storage/autofill is disabled. Website/Samsung Pass remains external.
text = replace_member(text, "attemptSavedCredentialLoginV0912Baseline", '''    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {
        if (provider != ProviderId.JINHAK) return
        credentialAutoLoginSuppressedNoCredential += 1
        val current = webView.url.orEmpty()
        if (JinhakHigh3AuthRoute.isMemberLoginSurface(current) || JinhakHigh3AuthRoute.isGenericProductLogin(current)) {
            markJinhakDirectAuthWait("v0170-collector-credential-disabled:$reason", current)
        }
        status.text = "v0.17.0에서는 Collector가 진학사 ID/PW를 읽거나 입력하지 않습니다. 필요한 경우 사이트 자체 로그인/Samsung Pass만 사용합니다."
        persistJinhakAuthDiagnostics("v0170-collector-credential-disabled")
    }''')

# Real-site diagnostic remains as a route event check only; high3 is accepted without DOM auth proof.
text = replace_member(text, "handleJinhakRealAuthProbePageFinished", '''    private fun handleJinhakRealAuthProbePageFinished(url: String) {
        if (!jinhakRealAuthProbeActive || provider != ProviderId.JINHAK) return
        jinhakV0168AuthEventsObserved += 1
        noteJinhakRealAuthProbeRoute(url, "v0170-page-finished")
        when (JinhakAuthEventState.action(url)) {
            JinhakAuthEventState.Action.DROP_REQUEST -> hardBlockJinhakLowerGradeNavigation("v0170-real-site-event", url)
            JinhakAuthEventState.Action.WAIT_FOR_SERVER_RETURN -> {
                jinhakV0168PassiveMemberWaits += 1
                markJinhakDirectAuthWait("v0170-real-site-login-wait", url)
            }
            JinhakAuthEventState.Action.VERIFY_HIGH3_SESSION -> {
                jinhakV0168High3Verifications += 1
                jinhakV0170NaturalHigh3Returns += 1
                finishJinhakRealAuthProbe("v0170-high3-reached", success = true)
            }
            JinhakAuthEventState.Action.OPEN_CANONICAL_HIGH3_AUTH_ONCE -> {
                // Legacy enum value is unreachable in schema 3. Never synthesize a login navigation.
                jinhakV0168LegacyNavigationSuppressions += 1
                persistJinhakAuthDiagnostics("v0170-forced-auth-suppressed")
            }
            JinhakAuthEventState.Action.OBSERVE_WITHOUT_NAVIGATION -> {
                jinhakV0168OtherRouteObservations += 1
                persistJinhakAuthDiagnostics("v0170-real-site-observe-other")
            }
        }
    }''')

# Suppress the Collector credential dialog for Jinhak without navigating anywhere.
old_dialog = '''        if (which == ProviderId.JINHAK) {
            startupCredentialPromptedProvider = ProviderId.JINHAK
            jinhakV0168LegacyNavigationSuppressions += 1
            val current = webView.url.orEmpty()
            if (JinhakHigh3AuthRoute.isMemberLoginSurface(current)) {
                markJinhakDirectAuthWait("collector-credential-dialog-suppressed", current)
            } else {
                openJinhakDirectHigh3Auth("collector-credential-dialog-suppressed", currentBatchTarget)
            }
            status.text = "진학사는 Collector 계정 입력창을 사용하지 않습니다. 사이트 자체 로그인/Samsung Pass/자동완성을 사용하세요."
            return
        }
'''
new_dialog = '''        if (which == ProviderId.JINHAK) {
            startupCredentialPromptedProvider = ProviderId.JINHAK
            jinhakV0168LegacyNavigationSuppressions += 1
            credentialVault.clear(ProviderId.JINHAK.wireName)
            val current = webView.url.orEmpty()
            if (JinhakHigh3AuthRoute.isMemberLoginSurface(current) || JinhakHigh3AuthRoute.isGenericProductLogin(current)) {
                markJinhakDirectAuthWait("v0170-collector-credential-dialog-disabled", current)
            }
            status.text = "v0.17.0은 진학사 Collector 계정 입력·저장을 사용하지 않습니다. 사이트 자체 로그인/Samsung Pass만 사용하세요."
            return
        }
'''
if new_dialog not in text:
    if text.count(old_dialog) != 1:
        raise SystemExit("showCredentialDialog Jinhak branch anchor missing")
    text = text.replace(old_dialog, new_dialog, 1)

# Add explicit v0.17.0 proof fields to every auth-diagnostics JSON chain that carries real probe state.
diag_anchor = '                    .put("realJinhakAuthProbeResult", jinhakRealAuthProbeResult.take(80))\n'
diag_insert = (
    '                    .put("jinhakAuthModel", "server-owned-no-dom-probe-v0170")\n'
    '                    .put("forcedAuthNavigations", jinhakV0170ForcedAuthNavigations)\n'
    '                    .put("domAuthChecks", jinhakV0170DomAuthChecks)\n'
    '                    .put("serverLoginRedirects", jinhakV0170ServerLoginRedirects)\n'
    '                    .put("naturalHigh3Returns", jinhakV0170NaturalHigh3Returns)\n'
    '                    .put("protectedMissionStarts", jinhakV0170ProtectedMissionStarts)\n'
    + diag_anchor
)
if '"jinhakAuthModel", "server-owned-no-dom-probe-v0170"' not in text:
    count = text.count(diag_anchor)
    if count < 1:
        raise SystemExit("diagnostics anchor missing")
    text = text.replace(diag_anchor, diag_insert)

MAIN.write_text(text)
print("v0.17.0 server-owned Jinhak auth patch applied")
