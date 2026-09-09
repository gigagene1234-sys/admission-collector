from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
SANDBOX = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakStrictHigh3Sandbox.kt"
GRADE = ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakGradeRouteFence.kt"
GRADLE = ROOT / "app/build.gradle.kts"
MANIFEST = ROOT / "app/src/main/AndroidManifest.xml"

main = MAIN.read_text()
sandbox = SANDBOX.read_text()
grade = GRADE.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

required = [
    ('versionCode = 117500', gradle),
    ('versionName = "0.17.5"', gradle),
    ('Admission Hub v0.17.5 Runtime-Stable High3 Sandbox', manifest),
    ('const val SCHEMA_VERSION = 3', sandbox),
    ('fun isBenignSameDocumentHistoryAlias(url: String): Boolean', sandbox),
    ('path == "/jh/search"', sandbox),
    ('private const val JINHAK_SNAPSHOT_OVERLAP_RETRY_MS = 800L', main),
    ('private const val JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS = 5_000L', main),
    ('v0175-session-preserving-block:', main),
    ('jinhak-v0175-benign-spa-history-alias', main),
    ('.put("v0175BlockedRoutesPreserveUserSession", true)', main),
    ('.put("v0175SpaHistoryBlankNeutralization", false)', main),
    ('.put("v0175SnapshotOverlapRetryMs", JINHAK_SNAPSHOT_OVERLAP_RETRY_MS)', main),
    ('.put("v0175RendererCrashCooldownMs", JINHAK_FIRST_RENDERER_CRASH_COOLDOWN_MS)', main),
    ('user-owned-session-explicit-high3-runtime-stable-v0175', main),
    ('MAX_DECODE_ROUNDS = 12', grade),
]
for needle, text in required:
    if needle not in text:
        raise SystemExit(f'missing required contract: {needle}')

# The network/main-frame sandbox remains fail-closed: /jh/search is only a same-document alias,
# never a promoted collector destination.
if 'fun allowsCollectorNavigation(url: String): Boolean = decision(url) == MainFrameDecision.ALLOW_HIGH3' not in sandbox:
    raise SystemExit('collector navigation was broadened outside ALLOW_HIGH3')
if 'if (JinhakHigh3AuthRoute.isGenericProductLogin(url)) return MainFrameDecision.BLOCK_GENERIC_LOGIN' not in sandbox:
    raise SystemExit('generic login router is no longer blocked')
if 'if (JinhakGradeRouteFence.isBlockedLowerGrade(url)) return MainFrameDecision.BLOCK_LOWER_GRADE' not in sandbox:
    raise SystemExit('lower-grade main-frame block missing')

# Route rejection must not be coupled to auth/session mutation or batch pausing anymore.
m = re.search(
    r'private fun blockJinhakV0174MainFrame\(.*?\n    \}\n\n    private fun loadMainUrl',
    main,
    re.S,
)
if not m:
    raise SystemExit('strict block function not found')
block = m.group(0)
for forbidden in [
    'jinhakUserSessionConfirmed = false',
    'jinhakAuthVerifiedForBatch = false',
    'batchPausedForLogin = true',
    'batchCover.visibility = View.GONE',
    'slowLaneHost.visibility = View.GONE',
]:
    if forbidden in block:
        raise SystemExit(f'route block still mutates runtime/auth state: {forbidden}')

# SPA history rejection must not destroy the current high3 document.
h = re.search(
    r'override fun doUpdateVisitedHistory\(.*?\n            \}\n\n            override fun onPageStarted',
    main,
    re.S,
)
if not h:
    raise SystemExit('history callback not found')
history = h.group(0)
if 'loadMainUrl("about:blank", "spa-history-neutralize")' in history:
    raise SystemExit('destructive SPA history blank neutralization still present')
if 'isBenignSameDocumentHistoryAlias(url)' not in history:
    raise SystemExit('benign SPA alias handling missing')

# Evidence-safe admission semantics are unchanged.
if '.put("probabilityInferred", false)' not in main:
    raise SystemExit('probabilityInferred=false safeguard missing')
if 'credentialExported' not in main or 'sessionSecretExported' not in main:
    raise SystemExit('credential/session export diagnostics missing')

print('v0.17.5 source contracts verified')
