from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()


def replace_idempotent(old: str, new: str, label: str) -> None:
    global text
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit(f"{label}: anchor missing")


CLEAR_FUNC = '''    private fun clearJinhakLegacyAuthState() {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        prefs.edit()
            .remove("jinhakAuthProofCollectorVersion")
            .remove("jinhakRealAuthProbeResult")
            .remove("jinhakRealAuthProbeVerifiedAtMs")
            .remove("jinhakLastCoreVerifiedAtMs")
            .remove("jinhakLastAuthEvidence")
            .remove("jinhakAuthProofSafePath")
            .apply()
        jinhakAuthVerifiedForBatch = false
        jinhakV0182ProtectedSessionVerified = false
        jinhakUserSessionConfirmed = false
        jinhakTransitionAuthGateActive = false
        jinhakRealAuthProbeActive = false
        jinhakRealAuthResumeGatePending = false
        jinhakLastCoreVerifiedAtMs = 0L
        jinhakRealAuthProbeVerifiedAtMs = 0L
        jinhakLastAuthEvidence = "manual-browser-no-auth-inference"
    }'''

# Earlier retry runs could apply the auth-proof replacement twice. Normalize the source to one
# cleanup function so this script is safe to replay after CI commits product source back to branch.
while (CLEAR_FUNC + "\n\n" + CLEAR_FUNC) in text:
    text = text.replace(CLEAR_FUNC + "\n\n" + CLEAR_FUNC, CLEAR_FUNC, 1)
if text.count("private fun clearJinhakLegacyAuthState()") != 1:
    raise SystemExit("expected exactly one clearJinhakLegacyAuthState definition")

current_old = '''                val safeRouteKey = runtimeSafePath(snapshot.optString("url"))
                val explicitContext = ObservationEvidence.explicitContextFromDigest(lastJinhakDigest)
                val sessionObj = snapshot.optJSONObject("session") ?: JSONObject()
                val authStateClass = when {
                    sessionObj.optBoolean("needsLogin", false) -> "auth-required"
                    sessionObj.optBoolean("authenticated", false) -> "authenticated"
                    else -> "unknown"
                }
                val observationId = localStore.storeObservationEvidence('''
current_new = '''                val safeRouteKey = runtimeSafePath(snapshot.optString("url"))
                val explicitContext = ObservationEvidence.explicitContextFromDigest(lastJinhakDigest)
                val authStateClass = "user-viewed-no-auth-inference"
                val observationId = localStore.storeObservationEvidence('''
replace_idempotent(current_old, current_new, "current-page-auth-metadata")

batch_old = '''                    val batchPageType = snapshot.optString("providerPageType")
                    val batchSession = snapshot.optJSONObject("session") ?: JSONObject()
                    val batchAuthState = when {
                        batchSession.optBoolean("needsLogin", false) -> "auth-required"
                        batchSession.optBoolean("authenticated", false) -> "authenticated"
                        else -> "unknown"
                    }
                    localStore.storeObservationEvidence('''
batch_new = '''                    val batchPageType = snapshot.optString("providerPageType")
                    val batchAuthState = "user-viewed-no-auth-inference"
                    localStore.storeObservationEvidence('''
replace_idempotent(batch_old, batch_new, "batch-auth-metadata")

# Switching to Jinhak must not flush/restore/categorize its session. Browser/provider cookies are
# deliberately left alone because the user owns the manual login session.
open_old = '''        provider = which
        localRunId = localStore.latestResumableRun(which.wireName)
        CookieManager.getInstance().flush()
        val restoredLease = if (which == ProviderId.JINHAK) null else runCatching { sessionVault.restore(which.wireName) }.getOrNull()
        sessionState.text = if (restoredLease?.restored == true) {
            "● 암호화 세션 lease 복구 · ${restoredLease.leaseId.take(8)}…"
        } else "세션 상태 확인 중"'''
open_new = '''        provider = which
        localRunId = localStore.latestResumableRun(which.wireName)
        val restoredLease = if (which == ProviderId.JINHAK) null else runCatching { sessionVault.restore(which.wireName) }.getOrNull()
        if (which != ProviderId.JINHAK) CookieManager.getInstance().flush()
        sessionState.text = if (which == ProviderId.JINHAK) {
            "○ 직접 로그인 · 수시 저장소로 이동"
        } else if (restoredLease?.restored == true) {
            "● 암호화 세션 lease 복구 · ${restoredLease.leaseId.take(8)}…"
        } else "세션 상태 확인 중"'''
replace_idempotent(open_old, open_new, "openProvider-session")

if '"진학사 observation-first 모드 · active ${capabilities.active.size} / discoverable ${capabilities.discoverable.size} · 분류 여부와 무관하게 증거 보존"' in text:
    text = text.replace(
        '"진학사 observation-first 모드 · active ${capabilities.active.size} / discoverable ${capabilities.discoverable.size} · 분류 여부와 무관하게 증거 보존"',
        '"진학사 직접 탐색 모드 · 로그인 후 수시 저장소까지 이동하면 대학·학과별 리포트 탐색을 자동 시작"',
        1,
    )
if 'ProviderId.JINHAK -> "진학사 에이전트 자동 수집"' in text:
    text = text.replace(
        'ProviderId.JINHAK -> "진학사 에이전트 자동 수집"',
        'ProviderId.JINHAK -> "수시 저장소에서 리포트 탐색"',
        1,
    )

refresh_old = '''    private fun refreshSessionOrOpenLogin() {
        checkSessionState { needsLogin, authenticated ->'''
refresh_new = '''    private fun refreshSessionOrOpenLogin() {
        if (provider == ProviderId.JINHAK) {
            clearJinhakLegacyAuthState()
            sessionState.text = "○ 직접 로그인 · 수시 저장소로 이동"
            status.text = "진학사 로그인/세션 상태는 Admission Hub가 확인하지 않습니다. 직접 로그인한 뒤 수시 저장소까지 이동하세요."
            return
        }
        checkSessionState { needsLogin, authenticated ->'''
replace_idempotent(refresh_old, refresh_new, "refresh-session")

# Fatal old gate: startBatch() already accepted the visible storage page, but beginBatchNavigation()
# used to require jinhakUserSessionConfirmed again. The route is now the sole runtime gate.
begin_old = '''        if (provider == ProviderId.JINHAK) {
            val visible = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(webView.url)
            val target = JinhakStrictHigh3Sandbox.sanitizedHigh3OrNull(currentBatchTarget)
            if (!jinhakUserSessionConfirmed || visible == null) {
                batchPausedForLogin = true
                hideBatchCover()
                enterJinhakUserSessionGate("v0174-begin-navigation-visible-high3-required")
                return
            }
            currentBatchTarget = canonicalizeBatchUrl(visible)
            if (target == null || canonicalizeBatchUrl(target) == canonicalizeBatchUrl(visible)) {
                scheduleBatchSnapshot()
            } else {
                loadJinhakV0174High3Only(target, "begin-batch-navigation")
            }
            return
        }'''
begin_new = '''        if (provider == ProviderId.JINHAK) {
            val visible = canonicalizeBatchUrl(webView.url.orEmpty())
            if (!JinhakManualStorageReportPolicy.isAllowedMissionUrl(visible)) {
                batchRunning = false
                batchPausedForLogin = false
                hideBatchCover()
                stopCollectionKeepAlive()
                sessionState.text = "○ 수시 저장소 직접 진입 필요"
                status.text = "수시 저장소/지원 리포트 범위가 아닙니다. 직접 수시 저장소로 이동하면 다시 시작합니다."
                return
            }
            currentBatchTarget = visible
            scheduleBatchSnapshot()
            return
        }'''
replace_idempotent(begin_old, begin_new, "beginBatchNavigation-route-only")

# The old global “login completed -> continue” UI remains for Adiga, but for Jinhak it is only a
# convenient re-arm action from the storage page and cannot enter an auth state machine.
resume_old = '''    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK) {
            confirmJinhakUserSessionAndResume("legacy-resume-button")
            return
        }'''
resume_new = '''    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK) {
            clearJinhakLegacyAuthState()
            val current = webView.url.orEmpty()
            if (JinhakManualStorageReportPolicy.isStorageEntry(current)) {
                if (!batchRunning) startBatch() else scheduleBatchSnapshot()
            } else {
                batchPausedForLogin = false
                sessionState.text = "○ 수시 저장소 직접 진입 필요"
                status.text = "진학사 로그인/세션은 직접 관리합니다. 수시 저장소까지 이동한 뒤 다시 진행하세요."
            }
            return
        }'''
replace_idempotent(resume_old, resume_new, "resumeAfterLogin-route-only")

# Error recovery must not flush/probe Jinhak authentication. Reuse the visible report/storage route
# when it is still in scope; otherwise terminate this traversal and wait for manual storage entry.
recover_old = '''    private fun recoverCollectorSessionOrPause() {
        if (!batchRunning) return
        CookieManager.getInstance().flush()
        checkSessionState { needsLogin, authenticated ->'''
recover_new = '''    private fun recoverCollectorSessionOrPause() {
        if (!batchRunning) return
        if (provider == ProviderId.JINHAK) {
            val current = webView.url.orEmpty()
            if (JinhakManualStorageReportPolicy.isAllowedMissionUrl(current)) {
                batchPausedForLogin = false
                showBatchCover()
                scheduleBatchSnapshot()
            } else {
                batchPausedForLogin = false
                stopBatch("jinhak-recovery-outside-storage-report-scope")
                sessionState.text = "○ 수시 저장소 직접 재진입 필요"
                status.text = "진학사 세션 복구는 수행하지 않습니다. 수시 저장소로 직접 돌아오면 다시 탐색합니다."
            }
            return
        }
        CookieManager.getInstance().flush()
        checkSessionState { needsLogin, authenticated ->'''
replace_idempotent(recover_old, recover_new, "recoverCollector-route-only")

# Mission stall recovery is based on outstanding report work, not a protected-session boolean.
progress_old = '''                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS &&
                    JinhakProtectedSessionPolicy.shouldRunMissionStallFence(jinhakV0182ProtectedSessionVerified, missionTargetCount)) {'''
progress_new = '''                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS && missionTargetCount > 0) {'''
replace_idempotent(progress_old, progress_new, "progress-fence-no-auth-proof")

# Remove a harmless but misleading auth-conditioned batch state transition.
batch_core_old = '''        if (provider == ProviderId.JINHAK && jinhakAuthVerifiedForBatch) {
            jinhakCoreBootstrapState = "batch-core-start"
        }'''
batch_core_new = '''        if (provider == ProviderId.JINHAK) {
            jinhakCoreBootstrapState = "manual-storage-report-batch"
        }'''
replace_idempotent(batch_core_old, batch_core_new, "batch-core-no-auth-proof")

MAIN.write_text(text)
