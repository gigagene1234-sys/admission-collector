from pathlib import Path


def require(cond, msg):
    if not cond:
        raise SystemExit(msg)

build = Path("app/build.gradle.kts").read_text()
manifest = Path("app/src/main/AndroidManifest.xml").read_text()
main = Path("app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
policy = Path("app/src/main/java/com/admissionhub/collector/jinhak/JinhakSingleSurfaceStoragePolicy.kt").read_text()
adapter = Path("app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt").read_text()

require('versionCode = 118400' in build and 'versionName = "0.18.4"' in build, "wrong app version")
require('Admission Hub v0.18.4 Single Surface Storage' in manifest, "wrong manifest label")
require('private const val VERSION = "0.18.4"' in main and 'BUILD_CODE = 118400' in main, "wrong MainActivity version")

require('const val ENABLED = true' in policy, "single-surface policy disabled")
require('AUTH_AND_COLLECTION_SURFACE = "collector-main-webview"' in policy, "wrong Jinhak auth surface")
require('EXTERNAL_APP_SESSION_BRIDGE = false' in policy, "external app must not be treated as session bridge")
require('JinhakStorageCompetitionPolicy.isStorageUrl(url)' in policy, "storage-only gate missing")
require('JinhakDedicatedAuthPolicy.isLoginSurface(url)' in policy, "login surface gate missing")

require('V0184_SINGLE_SURFACE_STORAGE_AUTH' in main, "single-surface auth state missing")
require('beginV0184SingleSurfaceAutofill' in main, "single-surface autofill missing")
require('webView.evaluateJavascript(js)' in main, "main WebView autofill missing")
require('authHost.visibility = View.GONE' in main, "dedicated auth host not suppressed")
require('return jinhakV0174BlockedResponse("dedicated-auth-route")' not in main, "main-frame login is still blocked/rerouted")
require('startV0180DedicatedJinhakAuth("collector-navigation-login")' not in main, "navigation login still rerouted")
require('startV0180DedicatedJinhakAuth("collector-page-started-login")' not in main, "page-started login still rerouted")
require('startV0180DedicatedJinhakAuth("collector-page-finished-login")' not in main, "page-finished login still rerouted")
require('V0184_SINGLE_SURFACE_LOGIN_VISIBLE' in main and 'V0184_SINGLE_SURFACE_LOGIN_READY' in main, "single-surface login lifecycle missing")
require('if (JinhakStorageCompetitionPolicy.isStorageUrl(webView.url.orEmpty())) webView.reload()' in main, "same-surface periodic reload missing")

require('override fun seedUrls(): List<String> = listOf(JinhakSiteTopology.protectedCoreProbeUrl())' in adapter, "Jinhak seed is not storage-only")
require('JinhakStorageCompetitionPolicy.ENABLED && !JinhakStorageCompetitionPolicy.isStorageUrl(url)' in adapter, "non-storage batch navigation is not rejected")

require('adigaV0184BaselineCompletedPages' in main, "Adiga baseline counter missing")
require('이번 실행 화면시도' in main and '시작 전 누적' in main and '현재 누적' in main, "Adiga counter semantics are not visible")
require('adigaCounterSemantics' in main, "Adiga diagnostics semantics missing")
require('completedPages=persisted-run-page-rows' in main, "Adiga persisted-page explanation missing")

# Credentials or secrets must never be hardcoded into product source.
for forbidden in ["songtaeho2008", "20081115", "dbs6250767"]:
    require(forbidden not in main and forbidden not in policy and forbidden not in adapter, "credential material found in source")

print("v0.18.4 source contracts verified")
