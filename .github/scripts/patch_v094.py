from pathlib import Path

MAIN=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
CLOUD=Path('app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt')
GRADLE=Path('app/build.gradle.kts')
MANIFEST=Path('app/src/main/AndroidManifest.xml')

def rep(text,old,new,label):
    if old not in text:
        if new in text: return text
        raise SystemExit(label+' anchor not found')
    return text.replace(old,new,1)

main=MAIN.read_text(); cloud=CLOUD.read_text(); gradle=GRADLE.read_text(); manifest=MANIFEST.read_text()
main=rep(main,'        private const val VERSION = "0.9.3"\n        private const val BUILD_CODE = 10930\n','        private const val VERSION = "0.9.4"\n        private const val BUILD_CODE = 10940\n','main version')
gradle=rep(gradle,'        versionCode = 10930\n        versionName = "0.9.3"\n','        versionCode = 10940\n        versionName = "0.9.4"\n','gradle version')
manifest=rep(manifest,'android:label="Admission Collector v0.9.3 Local Credential Auto Login"','android:label="Admission Collector v0.9.4 Auth Guard Web Bridge"','manifest label')

# Explicit 3-state auth policy: ambiguous != logged out.
main=rep(main,
'''            if (authenticated) {
                onStartupProviderAuthenticated(expectedProvider, generation)
                return@checkSessionState
            }
            if (credentialVault.has(expectedProvider.wireName)) {
''',
'''            if (authenticated) {
                onStartupProviderAuthenticated(expectedProvider, generation)
                return@checkSessionState
            }
            // v0.9.4: an indeterminate DOM/auth check must never be treated as logout.
            // Preserve the user's current page unless the adapter explicitly sees a login-required state.
            if (!needsLogin) {
                sessionState.text = "△ ${expectedProvider.displayName} 로그인 상태 확인 중 · 현재 화면 유지"
                status.text = "${expectedProvider.displayName} 로그인 여부가 아직 확정되지 않았습니다. 현재 화면을 유지하고 다시 확인합니다. 로그인 필요가 명시적으로 감지될 때만 자동 로그인합니다."
                scheduleStartupLoginPoll(expectedProvider, generation)
                return@checkSessionState
            }
            if (credentialVault.has(expectedProvider.wireName)) {
''','three-state auth guard')

# Add one-tap live website bridge next to the credential settings.
main=rep(main,
'''        val sessionButton = Button(this).apply {
            text = "계정 자동로그인 설정"
            setOnClickListener { showCredentialDialog(provider, continueAfterSave = false) }
        }
        sessionRow.addView(sessionState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        sessionRow.addView(sessionButton)
''',
'''        val sessionButton = Button(this).apply {
            text = "계정 자동로그인 설정"
            setOnClickListener { showCredentialDialog(provider, continueAfterSave = false) }
        }
        val liveWebButton = Button(this).apply {
            text = "Live 웹"
            setOnClickListener {
                val target = cloudOffload.liveDashboardUrl()
                if (target == null) {
                    Toast.makeText(this@MainActivity, "Cloudflare 수집 토큰을 먼저 한 번 설정해주세요.", Toast.LENGTH_LONG).show()
                    cloudOffload.showSettingsDialog(this@MainActivity)
                } else {
                    runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(target))) }
                        .onFailure { Toast.makeText(this@MainActivity, "웹 대시보드를 열 수 없습니다.", Toast.LENGTH_LONG).show() }
                }
            }
        }
        sessionRow.addView(sessionState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        sessionRow.addView(sessionButton)
        sessionRow.addView(liveWebButton)
''','live web button')

# Correct legacy telemetry now that credentials can intentionally exist locally.
main=main.replace('.put("passwordStored", false).put("sessionSecretStoredLocally", true).put("sessionSecretExported", false)', '.put("credentialStoredLocally", credentialVault.has(expectedProvider.wireName)).put("credentialExported", false).put("sessionSecretStoredLocally", true).put("sessionSecretExported", false)')
main=main.replace('.put("passwordStored", false)\n                .put("sessionSecretStoredLocally", true)', '.put("credentialStoredLocally", credentialVault.has(ProviderId.ADIGA.wireName) || credentialVault.has(ProviderId.JINHAK.wireName))\n                .put("credentialExported", false)\n                .put("sessionSecretStoredLocally", true)')

# Cloud token is passed only in the URL fragment; fragments are not included in the HTTP request.
cloud=rep(cloud,'import android.content.Context\n','import android.content.Context\nimport android.net.Uri\n','cloud Uri import')
marker='    fun snapshotStatus(): JSONObject = JSONObject()\n'
helper='''    fun liveDashboardUrl(baseUrl: String = "https://admission-collector-live.vercel.app"): String? {
        val secret = token().trim()
        if (secret.isBlank()) return null
        return baseUrl.trimEnd('/') + "/#token=" + Uri.encode(secret)
    }

'''
if helper not in cloud:
    if marker not in cloud: raise SystemExit('cloud dashboard marker not found')
    cloud=cloud.replace(marker,helper+marker,1)

MAIN.write_text(main); CLOUD.write_text(cloud); GRADLE.write_text(gradle); MANIFEST.write_text(manifest)
print('v0.9.4 auth guard + web bridge patch applied')
