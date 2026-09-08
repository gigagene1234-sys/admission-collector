from pathlib import Path
p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()
old='''        private const val JINHAK_LOGIN_RECOVERY_TIMEOUT_MS = 60_000L
        private const val MAX_JINHAK_LOGIN_RECOVERY_POLLS = 40
'''
new='''        private const val JINHAK_LOGIN_RECOVERY_TIMEOUT_MS = 60_000L
        private const val MAX_JINHAK_LOGIN_RECOVERY_POLLS = 40
        private const val MAX_JINHAK_REAUTH_CYCLES = 3
'''
if s.count(old)!=1: raise SystemExit('constant anchor mismatch')
s=s.replace(old,new,1)
old2='''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val currentUrl = if (::webView.isInitialized) webView.url.orEmpty() else ""
'''
new2='''    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        if (batchRunning && jinhakReauthCycles >= MAX_JINHAK_REAUTH_CYCLES) {
            jinhakLoginRecoveryFenceTrips += 1
            batchErrors.put(JSONObject()
                .put("type", "jinhak-reauth-circuit-open")
                .put("reason", reason.take(80))
                .put("reauthCycles", jinhakReauthCycles)
                .put("maxReauthCycles", MAX_JINHAK_REAUTH_CYCLES)
                .put("lowerGradeNavigationsBlocked", jinhakLowerGradeNavigationsBlocked))
            recordRuntimeEvent("jinhak-reauth-circuit-open", JSONObject()
                .put("reason", reason.take(80))
                .put("reauthCycles", jinhakReauthCycles)
                .put("maxReauthCycles", MAX_JINHAK_REAUTH_CYCLES))
            status.text = "진학사 재인증 반복 상한 도달 · 무한 로그인 재시도를 중단하고 어디가 공식자료를 보존합니다."
            finishBatch("jinhak-reauth-circuit-open")
            return
        }
        val currentUrl = if (::webView.isInitialized) webView.url.orEmpty() else ""
'''
if s.count(old2)!=1: raise SystemExit('schedule anchor mismatch')
s=s.replace(old2,new2,1)
p.write_text(s)
print('v0.15.1 reauth circuit breaker applied')
