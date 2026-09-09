from pathlib import Path
import runpy

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
ADAPTER = ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt"
GRADE = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt"
AUTH = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakHigh3AuthRoute.kt"
LEGACY_PATCH = Path(__file__).with_name("patch_v0174_final.py")

main = MAIN.read_text()
adapter = ADAPTER.read_text()
grade = GRADE.read_text()
auth = AUTH.read_text()

already_final = all([
    'private fun loadMainUrl(target: String, source: String = "app-load")' in main,
    'override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean)' in main,
    'if (provider == ProviderId.JINHAK) {\n            if (webView.canGoBack()) safeJinhakV0174Back()' in main,
    'const val SCHEMA_VERSION = 5' in grade,
    'MAX_DECODE_ROUNDS = 12' in grade,
    'const val SCHEMA_VERSION = 4' in auth,
    'MAX_DECODE_ROUNDS = 12' in auth,
    'Regex("""\\.(?:jpg|jpeg|png|gif|webp|svg|ico|css|js|map|woff2?|ttf|eot|zip|hwp|hwpx|pdf)$"""' in adapter,
])

if already_final:
    # Critical idempotence invariant: never rewrite the raw WebView calls inside the
    # central loader itself. The old one-shot patch intentionally performed a global
    # replacement only while introducing the loader for the first time.
    print("v0.17.4 final product source already hardened; patch is a verified no-op")
else:
    runpy.run_path(str(LEGACY_PATCH), run_name="__main__")
