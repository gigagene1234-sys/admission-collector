from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "scripts/apply_v036.py"
MAIN_FILES = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]


def prepare_patch_script() -> None:
    s = PATCH.read_text()
    old = """    if 'collectorWebView' in text:\n        raise SystemExit(f\"{path}: obsolete collectorWebView reference remains\")\n"""
    new = """    # Any residual secondary-WebView name belongs to the old v0.3.5 collector.\n    text = text.replace('collectorWebView', 'webView')\n    text = text.replace('    private var collectorStateSyncInProgress = false\\n', '')\n    text = text.replace('    private var collectorStateSyncPayload: String? = null\\n', '')\n    text = text.replace('    private var collectorStateSyncTarget: String? = null\\n', '')\n    if 'collectorWebView' in text:\n        raise SystemExit(f\"{path}: obsolete collectorWebView reference remains\")\n"""
    if old in s:
        PATCH.write_text(s.replace(old, new, 1))
    elif new not in s:
        raise SystemExit("apply_v036.py normalization marker missing")


def normalize_generated_source() -> None:
    for path in MAIN_FILES:
        s = path.read_text()

        # The final collectorWebView -> webView migration can leave two field declarations.
        field = "    private lateinit var webView: WebView\n"
        if s.count(field) > 1:
            first = s.find(field)
            s = s[: first + len(field)] + s[first + len(field) :].replace(field, "")

        # The patch template intentionally contains human-readable multiline text, but Kotlin
        # ordinary string literals need escaped newlines in generated source.
        bad_loading = '''batchCover.text = "입시정보 수집 중

페이지 렌더링은 이 화면 뒤에서 처리됩니다.
${safeDisplayUrl(url)}"'''
        good_loading = 'batchCover.text = "입시정보 수집 중\\n\\n페이지 렌더링은 이 화면 뒤에서 처리됩니다.\\n${safeDisplayUrl(url)}"'
        s = s.replace(bad_loading, good_loading)

        bad_cover = '''batchCover.text = "입시정보 수집 중

로그인된 브라우저 자체가 수집 엔진으로 동작합니다.
페이지 이동은 이 화면 뒤에서 처리됩니다."'''
        good_cover = 'batchCover.text = "입시정보 수집 중\\n\\n로그인된 브라우저 자체가 수집 엔진으로 동작합니다.\\n페이지 이동은 이 화면 뒤에서 처리됩니다."'
        s = s.replace(bad_cover, good_cover)

        path.write_text(s)


def verify_prebuild() -> None:
    a = MAIN_FILES[0].read_text()
    b = MAIN_FILES[1].read_text()
    if a != b:
        raise SystemExit("root/app MainActivity.kt mismatch")
    checks = [
        'private const val VERSION = "0.3.6"',
        'private lateinit var batchCover: TextView',
        'authenticated-webview-covered',
        'batchCloudPagesDeferred',
        'completed-with-deferred-errors',
    ]
    for item in checks:
        if item not in a:
            raise SystemExit(f"missing v0.3.6 invariant: {item}")
    if a.count("private lateinit var webView: WebView") != 1:
        raise SystemExit("expected exactly one authenticated WebView field")
    forbidden = [
        "collectorWebView",
        "synchronizeCollectorBrowserState",
        "collectorStateSyncInProgress",
        "collectorStateSyncPayload",
        "collectorStateSyncTarget",
    ]
    for item in forbidden:
        if item in a:
            raise SystemExit(f"obsolete v0.3.5 symbol remains: {item}")


if 'private const val VERSION = "0.3.6"' not in MAIN_FILES[0].read_text():
    prepare_patch_script()
    subprocess.run(["python3", str(PATCH)], cwd=ROOT, check=True)
    normalize_generated_source()
else:
    # Safe to run after persistence as a no-op/normalizer.
    normalize_generated_source()

verify_prebuild()
print("v0.3.6 authenticated single-WebView source prepared")
