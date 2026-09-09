from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
POLICY = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakUserSessionPolicy.kt"
BUILD = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count == 1:
        return text.replace(old, new, 1)
    if count == 0 and new in text:
        return text
    raise SystemExit(f"{label}: expected one old token, found {count}")


def replace_member(text: str, name: str, replacement: str) -> str:
    marker = f"    private fun {name}"
    start = text.find(marker)
    if start < 0:
        if replacement.strip() in text:
            return text
        raise SystemExit(f"member missing: {name}")
    search_start = start + len(marker)
    candidates = []
    for token in ["\n    private fun ", "\n    private val ", "\n    private var ", "\n    private data class ", "\n    private class ", "\n    private object "]:
        idx = text.find(token, search_start)
        if idx >= 0:
            candidates.append(idx)
    end = min(candidates) if candidates else len(text)
    return text[:start] + replacement.rstrip() + "\n" + text[end + (1 if end < len(text) else 0):]


# -----------------------------------------------------------------------------
# Metadata
# -----------------------------------------------------------------------------
build = BUILD.read_text()
build = replace_once(build, "versionCode = 117200", "versionCode = 117300", "versionCode")
build = replace_once(build, 'versionName = "0.17.2"', 'versionName = "0.17.3"', "versionName")
BUILD.write_text(build)

manifest = MANIFEST.read_text()
manifest = replace_once(
    manifest,
    'android:label="Admission Hub v0.17.2 Bootstrap-Safe Jinhak Session"',
    'android:label="Admission Hub v0.17.3 Natural High3 Handoff"',
    "manifest label",
)
MANIFEST.write_text(manifest)

# -----------------------------------------------------------------------------
# Pure user-session handoff policy. The screen recording showed that an app-side
# confirmation can happen while the visible page is still /jh/member/login and
# that a late login onPageFinished callback can arrive after the visible WebView
# has already reached high3. These are navigation-state races, not credentials.
# -----------------------------------------------------------------------------
policy = POLICY.read_text()
policy = policy.replace("const val SCHEMA_VERSION = 1", "const val SCHEMA_VERSION = 2")
insert_after = '''    enum class NavigationDecision {
        ALLOW_ASSUMING_USER_LOGIN,
        PAUSE_FOR_USER_SESSION,
        DROP_LOWER_GRADE
    }
'''
policy_extra = insert_after + '''
    enum class ConfirmationDecision {
        ARM_AFTER_SITE_LOGIN,
        ACTIVATE_CURRENT_HIGH3,
        WAIT_FOR_HIGH3
    }

    fun isLoginSurface(url: String): Boolean =
        JinhakHigh3AuthRoute.isMemberLoginSurface(url) || JinhakHigh3AuthRoute.isGenericProductLogin(url)

    fun confirmationDecision(url: String): ConfirmationDecision = when {
        JinhakGradeRouteFence.isBlockedLowerGrade(url) -> ConfirmationDecision.WAIT_FOR_HIGH3
        isLoginSurface(url) -> ConfirmationDecision.ARM_AFTER_SITE_LOGIN
        JinhakGradeRouteFence.isHigh3(url) -> ConfirmationDecision.ACTIVATE_CURRENT_HIGH3
        else -> ConfirmationDecision.WAIT_FOR_HIGH3
    }

    fun shouldIgnoreStaleLoginCallback(callbackUrl: String, currentVisibleUrl: String): Boolean {
        if (!isLoginSurface(callbackUrl)) return false
        if (isLoginSurface(currentVisibleUrl)) return false
        return JinhakGradeRouteFence.isHigh3(currentVisibleUrl)
    }
'''
if "enum class ConfirmationDecision" not in policy:
    policy = replace_once(policy, insert_after, policy_extra, "policy confirmation decisions")
POLICY.write_text(policy)

# -----------------------------------------------------------------------------
# MainActivity: no synthetic post-login bootstrap. The user's site login must
# naturally hand the visible WebView to a stable high3 route. A login callback
# whose callback URL is stale relative to a currently-visible high3 route is
# ignored. If a real login surface later returns, collection pauses and arms a
# new natural handoff rather than bouncing back to /search.
# -----------------------------------------------------------------------------
text = MAIN.read_text()
text = replace_once(text, 'private const val VERSION = "0.17.2"', 'private const val VERSION = "0.17.3"', "VERSION")
text = replace_once(text, 'private const val BUILD_CODE = 117200', 'private const val BUILD_CODE = 117300', "BUILD_CODE")

state_anchor = '''    private val jinhakV0172DeferredProtectedTargets = linkedSetOf<String>()
'''
state_new = state_anchor + '''    private var jinhakV0173ResumeArmed = false
    private var jinhakV0173LoginSurfaceArmRequests = 0
    private var jinhakV0173NaturalHigh3Resumes = 0
    private var jinhakV0173StaleLoginCallbacksIgnored = 0
    private var jinhakV0173High3StabilityRejects = 0
    private var jinhakV0173High3StabilityGeneration = 0
    private var jinhakV0173ActualLoginReturns = 0
'''
if "jinhakV0173ResumeArmed" not in text:
    text = replace_once(text, state_anchor, state_new, "v0173 state")

# v0.17.2 set a synthetic /search target at transition. v0.17.3 starts with no
# collector-owned Jinhak target; the visible site decides where login returns.
old_transition_target = '''        currentBatchTarget = canonicalizeBatchUrl(JinhakSiteTopology.userSessionBootstrapUrl())
        jinhakV0172DeferredProtectedTargets.clear()
        jinhakV0172BootstrapStarts = 0
        jinhakV0172ProtectedRetryDeferrals = 0
        jinhakV0172LoginRedirectLoopBreaks = 0
        enterJinhakUserSessionGate("unified-transition")
'''
new_transition_target = '''        currentBatchTarget = null
        jinhakV0172DeferredProtectedTargets.clear()
        jinhakV0172BootstrapStarts = 0
        jinhakV0172ProtectedRetryDeferrals = 0
        jinhakV0172LoginRedirectLoopBreaks = 0
        jinhakV0173ResumeArmed = false
        jinhakV0173LoginSurfaceArmRequests = 0
        jinhakV0173NaturalHigh3Resumes = 0
        jinhakV0173StaleLoginCallbacksIgnored = 0
        jinhakV0173High3StabilityRejects = 0
        jinhakV0173High3StabilityGeneration = 0
        jinhakV0173ActualLoginReturns = 0
        enterJinhakUserSessionGate("unified-transition")
'''
text = replace_once(text, old_transition_target, new_transition_target, "transition no synthetic target")

# Helpers are inserted before the legacy v0.17.2 breaker.
break_marker = '''    private fun breakJinhakLoginRedirectLoopAfterUserConfirmation(reason: String): Boolean {
'''
if "private fun isJinhakV0173StaleLoginCallback" not in text:
    helpers = '''    private fun isJinhakV0173StaleLoginCallback(callbackUrl: String, source: String): Boolean {
        if (provider != ProviderId.JINHAK || !::webView.isInitialized) return false
        val current = webView.url.orEmpty()
        if (!JinhakUserSessionPolicy.shouldIgnoreStaleLoginCallback(callbackUrl, current)) return false
        jinhakV0173StaleLoginCallbacksIgnored += 1
        recordRuntimeEvent(
            "jinhak-v0173-stale-login-callback-ignored",
            JSONObject()
                .put("source", source.take(80))
                .put("callbackSafePath", runtimeSafePath(callbackUrl))
                .put("currentSafePath", runtimeSafePath(current))
                .put("currentHigh3Visible", true)
                .put("collectorNavigation", false)
        )
        persistJinhakAuthDiagnostics("v0173-stale-login-callback:$source")
        return true
    }

    private fun armJinhakV0173NaturalHigh3Resume(reason: String, countUserArm: Boolean = false) {
        if (provider != ProviderId.JINHAK) return
        jinhakV0173ResumeArmed = true
        if (countUserArm) jinhakV0173LoginSurfaceArmRequests += 1
        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        if (batchRunning) batchPausedForLogin = true
        jinhakTransitionAuthGateActive = false
        jinhakCoreBootstrapState = "v0173-natural-high3-handoff-armed"
        jinhakLastAuthEvidence = "waiting-for-user-site-login-natural-high3-return"
        jinhakLastCoreVerifiedAtMs = 0L
        ++jinhakV0173High3StabilityGeneration
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
        if (::slowLaneHost.isInitialized) slowLaneHost.visibility = View.GONE
        if (::webView.isInitialized) webView.visibility = View.VISIBLE
        if (::jinhakSessionConfirmButton.isInitialized) {
            jinhakSessionConfirmButton.isEnabled = true
            jinhakSessionConfirmButton.text = "사이트 로그인 후 고3 화면 자동 재개 대기"
        }
        if (::sessionState.isInitialized) sessionState.text = "○ 진학사 사이트 로그인 완료 후 자연 복귀 대기"
        if (::status.isInitialized) status.text = "현재 로그인 화면에서는 앱이 어떤 주소도 열지 않습니다. 진학사 사이트의 로그인 절차를 완료하세요. 사이트가 고3 화면으로 자연 복귀하고 잠시 안정되면 현재 화면 그대로 수집을 재개합니다."
        recordRuntimeEvent(
            "jinhak-v0173-natural-high3-resume-armed",
            JSONObject()
                .put("reason", reason.take(100))
                .put("safePath", runtimeSafePath(webView.url))
                .put("countUserArm", countUserArm)
                .put("collectorNavigation", false)
                .put("collectorVerifiedLogin", false)
        )
        persistJinhakAuthDiagnostics("v0173-resume-armed:$reason")
    }

    private fun scheduleJinhakV0173StableHigh3Handoff(rawUrl: String, reason: String) {
        if (provider != ProviderId.JINHAK || !jinhakV0173ResumeArmed) return
        if (!JinhakGradeRouteFence.isHigh3(rawUrl) || JinhakUserSessionPolicy.isLoginSurface(rawUrl)) return
        val expected = canonicalizeBatchUrl(rawUrl)
        if (expected.isBlank()) return
        val generation = ++jinhakV0173High3StabilityGeneration
        handler.postDelayed({
            if (provider != ProviderId.JINHAK || !jinhakV0173ResumeArmed || generation != jinhakV0173High3StabilityGeneration) return@postDelayed
            val current = webView.url.orEmpty()
            val currentCanonical = canonicalizeBatchUrl(current)
            val stable = currentCanonical == expected && JinhakGradeRouteFence.isHigh3(current) && !JinhakUserSessionPolicy.isLoginSurface(current)
            if (!stable) {
                jinhakV0173High3StabilityRejects += 1
                persistJinhakAuthDiagnostics("v0173-high3-stability-rejected:$reason")
                return@postDelayed
            }
            activateJinhakV0173StableHigh3(reason, current)
        }, 900L)
    }

    private fun activateJinhakV0173StableHigh3(reason: String, rawUrl: String) {
        if (provider != ProviderId.JINHAK || !jinhakV0173ResumeArmed) return
        if (!JinhakGradeRouteFence.isHigh3(rawUrl) || JinhakUserSessionPolicy.isLoginSurface(rawUrl)) return
        val current = canonicalizeBatchUrl(rawUrl)
        if (current.isBlank()) return
        val wasPaused = batchRunning && batchPausedForLogin
        jinhakV0173ResumeArmed = false
        jinhakUserSessionConfirmed = true
        jinhakUserSessionConfirmations += 1
        jinhakAuthVerifiedForBatch = true // compatibility flag == user's stable high3 assertion only
        jinhakV0173NaturalHigh3Resumes += 1
        batchPausedForLogin = false
        jinhakTransitionAuthGateActive = false
        jinhakCoreBootstrapState = "v0173-stable-natural-high3-active"
        jinhakLastAuthEvidence = "user-site-login-natural-high3-stable-no-app-auth-verification"
        jinhakLastCoreVerifiedAtMs = 0L
        currentBatchTarget = current
        if (::jinhakSessionConfirmButton.isInitialized) jinhakSessionConfirmButton.text = "고3 화면 연결됨 · 필요 시 다시 대기"
        if (::sessionState.isInitialized) sessionState.text = "● 사용자 사이트 로그인 → 고3 화면 자연 연결"
        if (::status.isInitialized) status.text = "진학사 사이트가 고3 화면으로 자연 복귀한 상태가 안정적으로 유지되어 현재 화면에서 수집을 재개합니다. 앱이 로그인 주소나 고3 시작 주소를 강제로 열지 않았습니다."
        recordRuntimeEvent(
            "jinhak-v0173-natural-high3-resumed",
            JSONObject()
                .put("reason", reason.take(100))
                .put("safePath", runtimeSafePath(current))
                .put("stabilityMs", 900)
                .put("collectorNavigation", false)
                .put("collectorVerifiedLogin", false)
        )
        persistJinhakAuthDiagnostics("v0173-natural-high3-resumed:$reason")

        when {
            startupLoginPreflightActive -> {
                startupLoginJinhakAuthenticated = true
                startupLoginPreflightActive = false
                startupLoginPreflightVerified = true
                startupLoginVerifiedAtMs = System.currentTimeMillis()
                startupLoginStage = "jinhak-user-natural-high3"
                startupLoginPollGeneration += 1
                handler.postDelayed({ if (!unifiedRunning && !batchRunning && jinhakUserSessionConfirmed) startUnifiedCollectionAuthenticated() }, 120L)
            }
            unifiedRunning && unifiedPhase == "jinhak" && !batchRunning -> {
                unifiedPendingJinhakStart = false
                handler.postDelayed({ if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning && jinhakUserSessionConfirmed) startBatch() }, 120L)
            }
            wasPaused && batchRunning -> {
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || !jinhakUserSessionConfirmed) return@postDelayed
                    currentBatchTarget = canonicalizeBatchUrl(webView.url.orEmpty())
                    collectCurrentPage()
                }, 120L)
            }
        }
    }

'''
    text = replace_once(text, break_marker, helpers + break_marker, "insert v0173 helpers")

# A real visible return to login after a previously active session pauses and arms.
# It never loads /search or any other synthetic route.
text = replace_member(text, "breakJinhakLoginRedirectLoopAfterUserConfirmation", '''    private fun breakJinhakLoginRedirectLoopAfterUserConfirmation(reason: String): Boolean {
        if (provider != ProviderId.JINHAK || !jinhakUserSessionConfirmed) return false
        val visibleUrl = webView.url.orEmpty()
        if (!JinhakUserSessionPolicy.isLoginSurface(visibleUrl)) return false

        val deferred = currentBatchTarget
            ?.takeIf { it.isNotBlank() && isProviderUrl(it) && !JinhakUserSessionPolicy.isLoginSurface(it) }
            ?.let { canonicalizeBatchUrl(it) }
        if (deferred != null) {
            if (jinhakV0172DeferredProtectedTargets.add(deferred)) jinhakV0172ProtectedRetryDeferrals += 1
            batchVisited.add(deferred)
            batchQueued.remove(deferred)
        }
        currentBatchTarget = null
        jinhakV0173ActualLoginReturns += 1
        jinhakV0172LoginRedirectLoopBreaks += 1
        armJinhakV0173NaturalHigh3Resume("actual-login-return:$reason", countUserArm = false)
        recordRuntimeEvent(
            "jinhak-v0173-actual-login-return-paused",
            JSONObject()
                .put("reason", reason.take(100))
                .put("visibleSafePath", runtimeSafePath(visibleUrl))
                .put("deferredTargetSafePath", runtimeSafePath(deferred))
                .put("automaticBootstrapNavigation", false)
                .put("userConfirmationRevokedBecauseLoginActuallyVisible", true)
        )
        persistJinhakAuthDiagnostics("v0173-actual-login-return:$reason")
        return true
    }''')

# Confirmation button is now an arm/observe control on login. It never triggers a
# loadUrl. If already on high3, it still waits for 900ms route stability.
text = replace_member(text, "confirmJinhakUserSessionAndResume", '''    private fun confirmJinhakUserSessionAndResume(reason: String) {
        if (provider != ProviderId.JINHAK) {
            Toast.makeText(this, "진학사 화면에서만 사용할 수 있습니다.", Toast.LENGTH_SHORT).show()
            return
        }
        val current = webView.url.orEmpty()
        when (JinhakUserSessionPolicy.confirmationDecision(current)) {
            JinhakUserSessionPolicy.ConfirmationDecision.ARM_AFTER_SITE_LOGIN -> {
                armJinhakV0173NaturalHigh3Resume("user-button-on-login:$reason", countUserArm = true)
                return
            }
            JinhakUserSessionPolicy.ConfirmationDecision.WAIT_FOR_HIGH3 -> {
                armJinhakV0173NaturalHigh3Resume("user-button-wait-high3:$reason", countUserArm = true)
                return
            }
            JinhakUserSessionPolicy.ConfirmationDecision.ACTIVATE_CURRENT_HIGH3 -> {
                jinhakV0173ResumeArmed = true
                if (::status.isInitialized) status.text = "현재 고3 화면이 실제로 유지되는지 잠시 확인한 뒤, 화면 이동 없이 그대로 수집을 재개합니다."
                scheduleJinhakV0173StableHigh3Handoff(current, "user-button-high3:$reason")
            }
        }
    }''')

# Late onPageFinished(login) must not override a high3 page that is already the
# current visible main frame. High3 while armed schedules a stability handoff.
text = replace_member(text, "handleJinhakV0912AuthCompatibilityPage", '''    private fun handleJinhakV0912AuthCompatibilityPage(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return false
        if (isJinhakV0173StaleLoginCallback(url, "auth-compat-page-finished")) return true
        return when (JinhakUserSessionPolicy.decision(url)) {
            JinhakUserSessionPolicy.NavigationDecision.DROP_LOWER_GRADE -> {
                hardBlockJinhakLowerGradeNavigation("v0173-lower-grade-drop", url)
                true
            }
            JinhakUserSessionPolicy.NavigationDecision.PAUSE_FOR_USER_SESSION -> {
                enterJinhakUserSessionGate("v0173-login-surface")
                true
            }
            JinhakUserSessionPolicy.NavigationDecision.ALLOW_ASSUMING_USER_LOGIN -> {
                if (jinhakV0173ResumeArmed && JinhakGradeRouteFence.isHigh3(url)) {
                    scheduleJinhakV0173StableHigh3Handoff(url, "page-finished")
                }
                false
            }
        }
    }''')

text = replace_member(text, "markJinhakDirectAuthWait", '''    private fun markJinhakDirectAuthWait(reason: String, url: String) {
        if (provider != ProviderId.JINHAK) return
        if (isJinhakV0173StaleLoginCallback(url, "direct-auth-wait:$reason")) return
        jinhakV0170ServerLoginRedirects += 1
        enterJinhakUserSessionGate("site-login-surface:$reason")
    }''')

text = replace_member(text, "handleJinhakTransitionAuthGate", '''    private fun handleJinhakTransitionAuthGate(url: String) {
        if (provider != ProviderId.JINHAK) return
        if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) {
            hardBlockJinhakLowerGradeNavigation("v0173-transition-lower-grade", url)
            return
        }
        if (isJinhakV0173StaleLoginCallback(url, "transition-auth-gate")) return
        if (JinhakUserSessionPolicy.isLoginSurface(url)) {
            enterJinhakUserSessionGate("transition-login-surface")
        } else if (jinhakV0173ResumeArmed && JinhakGradeRouteFence.isHigh3(url)) {
            scheduleJinhakV0173StableHigh3Handoff(url, "transition-high3")
        }
    }''')

# When entering the normal gate before any stable high3 handoff, arm natural resume
# if a login surface is actually visible. This preserves the browser/site as owner.
old_gate_reset = '''        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        jinhakTransitionAuthGateActive = false
        jinhakCoreBootstrapState = "v0171-user-session-gate"
'''
new_gate_reset = '''        jinhakUserSessionConfirmed = false
        jinhakAuthVerifiedForBatch = false
        if (::webView.isInitialized && JinhakUserSessionPolicy.isLoginSurface(webView.url.orEmpty())) jinhakV0173ResumeArmed = true
        jinhakTransitionAuthGateActive = false
        jinhakCoreBootstrapState = "v0173-user-session-gate"
'''
text = replace_once(text, old_gate_reset, new_gate_reset, "gate arms visible login")

# Start a Jinhak batch from the stable visible high3 route, not missionSeeds()[0].
old_target_assignment = '''        currentBatchTarget = if (provider == ProviderId.JINHAK && preserveJinhakMissionState && !currentBatchTarget.isNullOrBlank()) {
            currentBatchTarget
        } else if (provider == ProviderId.JINHAK) {
            canonicalizeBatchUrl(currentAdapter().seedUrls().firstOrNull() ?: url)
        } else canonicalizeBatchUrl(url)
'''
new_target_assignment = '''        currentBatchTarget = if (provider == ProviderId.JINHAK && preserveJinhakMissionState && !currentBatchTarget.isNullOrBlank()) {
            currentBatchTarget
        } else if (provider == ProviderId.JINHAK) {
            val visible = webView.url.orEmpty().takeIf { JinhakGradeRouteFence.isHigh3(it) && !JinhakUserSessionPolicy.isLoginSurface(it) }
            canonicalizeBatchUrl(visible ?: url)
        } else canonicalizeBatchUrl(url)
'''
text = replace_once(text, old_target_assignment, new_target_assignment, "batch starts at visible high3")

# beginBatchNavigation normally reloads currentBatchTarget. For the natural high3
# handoff, process the already-visible page in place instead.
old_begin_start = '''            } else {
                val startUrl = currentBatchTarget
                if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)
                else loadNextBatchPage()
            }
'''
new_begin_start = '''            } else {
                val startUrl = currentBatchTarget
                val visible = canonicalizeBatchUrl(webView.url.orEmpty())
                if (provider == ProviderId.JINHAK && !startUrl.isNullOrBlank() &&
                    canonicalizeBatchUrl(startUrl) == visible && JinhakGradeRouteFence.isHigh3(visible) &&
                    !JinhakUserSessionPolicy.isLoginSurface(visible)) {
                    collectCurrentPage()
                } else if (!startUrl.isNullOrBlank()) {
                    webView.loadUrl(startUrl)
                } else loadNextBatchPage()
            }
'''
text = replace_once(text, old_begin_start, new_begin_start, "in-place natural high3 batch start")

# Export non-secret diagnostics. v0173AutoBootstrapNavigations is an invariant: 0.
diag_anchor = '''                    .put("v0172DeferredProtectedTargets", jinhakV0172DeferredProtectedTargets.size)
'''
diag_extra = diag_anchor + '''                    .put("v0173ResumeArmed", jinhakV0173ResumeArmed)
                    .put("v0173LoginSurfaceArmRequests", jinhakV0173LoginSurfaceArmRequests)
                    .put("v0173NaturalHigh3Resumes", jinhakV0173NaturalHigh3Resumes)
                    .put("v0173StaleLoginCallbacksIgnored", jinhakV0173StaleLoginCallbacksIgnored)
                    .put("v0173High3StabilityRejects", jinhakV0173High3StabilityRejects)
                    .put("v0173ActualLoginReturns", jinhakV0173ActualLoginReturns)
                    .put("v0173AutoBootstrapNavigations", 0)
'''
text = text.replace(diag_anchor, diag_extra)
text = text.replace('"user-owned-session-login-assumed-v0172-bootstrap-safe"', '"user-owned-session-natural-high3-handoff-v0173"')

# v0.17.3 must contain no automatic /search bootstrap load. The topology route remains
# available as a normal discovery seed later, but login handoff never calls it directly.
text = text.replace('status.text = "사용자가 로그인 완료를 확인했습니다. Collector는 별도 인증 검사 없이 현재 WebView 세션을 사용하며, 보호경로를 즉시 재생하지 않고 공개 고3 서비스 시작점에서 탐색을 시작합니다."',
                    'status.text = "진학사 사이트 로그인 이후 자연스럽게 열린 고3 화면을 그대로 사용합니다. 로그인 단계에서는 앱이 고3 시작 주소를 강제로 열지 않습니다."')

MAIN.write_text(text)
print("v0.17.3 patch applied: login-page button only arms; stable natural high3 resumes in place; stale login callbacks ignored; no synthetic post-login bootstrap")
