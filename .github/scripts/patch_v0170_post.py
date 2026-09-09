from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()


def replace_once(old: str, new: str, label: str):
    global text
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one old token, found {count}")
    text = text.replace(old, new, 1)


# No Jinhak code path may synthesize a login URL. This compatibility accessor returns a protected
# high3 route and lets the Jinhak server redirect naturally when authentication is actually needed.
replace_once(
    '        ProviderId.JINHAK -> JinhakHigh3AuthRoute.canonicalLoginUrl(currentBatchTarget)\n',
    '        ProviderId.JINHAK -> JinhakHigh3AuthRoute.sanitizeReturnTarget(currentBatchTarget)\n',
    'providerLoginUrl Jinhak branch',
)

# Do not inspect the Jinhak login DOM at all. The URL/navigation event itself is the only signal.
old_schedule_head = '''    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
        if (which == ProviderId.JINHAK && jinhakLowerGradeLoginFenceLatched) return
        val generation = ++credentialLoginSurfaceGeneration
'''
new_schedule_head = '''    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
        if (which == ProviderId.JINHAK) {
            val current = webView.url.orEmpty()
            if (JinhakHigh3AuthRoute.isMemberLoginSurface(current) || JinhakHigh3AuthRoute.isGenericProductLogin(current)) {
                markJinhakDirectAuthWait("v0170-url-login-surface:$reason", current)
            }
            return
        }
        val generation = ++credentialLoginSurfaceGeneration
'''
replace_once(old_schedule_head, new_schedule_head, 'scheduleLoginSurfaceDetection Jinhak DOM bypass')

# Jinhak keepalive must not click or inspect session-extension UI. Cookie persistence is left to
# WebView/CookieManager and real protected requests.
replace_once(
    '                if (!(provider == ProviderId.JINHAK && jinhakV0167AuthWaitActive)) attemptSessionExtension()\n',
    '                if (provider != ProviderId.JINHAK) attemptSessionExtension()\n',
    'Jinhak session extension bypass',
)

# A successful high3 route event is not a credential/auth proof and must not copy Jinhak session
# material into the Collector session vault. Existing WebView cookies remain untouched.
old_capture = '''            val current = webView.url.orEmpty()
            if (current.isNotBlank()) runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, current, VERSION) }
'''
new_capture = '''            val current = webView.url.orEmpty()
            // v0.17.0 keeps Jinhak session ownership inside WebView/CookieManager only.
            if (current.isNotBlank()) CookieManager.getInstance().flush()
'''
replace_once(old_capture, new_capture, 'Jinhak session vault capture removal')

MAIN.write_text(text)
print('v0.17.0 post patch applied: no canonical login accessor, no Jinhak DOM login detection, no Jinhak session-extension clicks, no session-vault capture')
