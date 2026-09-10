from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()

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
# cleanup function so the patch remains idempotent across CI-triggered commits.
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
if current_old in text:
    text = text.replace(current_old, current_new, 1)
elif current_new not in text:
    raise SystemExit("current-page auth metadata anchor missing")

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
if batch_old in text:
    text = text.replace(batch_old, batch_new, 1)
elif batch_new not in text:
    raise SystemExit("batch auth metadata anchor missing")

# Switching to Jinhak must not flush/restore/categorize its session. The provider WebView remains
# available for the user's own navigation and ordinary provider cookies remain untouched.
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
if open_old in text:
    text = text.replace(open_old, open_new, 1)
elif open_new not in text:
    raise SystemExit("openProvider session anchor missing")

text = text.replace(
    '"진학사 observation-first 모드 · active ${capabilities.active.size} / discoverable ${capabilities.discoverable.size} · 분류 여부와 무관하게 증거 보존"',
    '"진학사 직접 탐색 모드 · 로그인 후 수시 저장소까지 이동하면 대학·학과별 리포트 탐색을 자동 시작"',
    1,
)
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
if refresh_old in text:
    text = text.replace(refresh_old, refresh_new, 1)
elif refresh_new not in text:
    raise SystemExit("refresh session anchor missing")

MAIN.write_text(text)
