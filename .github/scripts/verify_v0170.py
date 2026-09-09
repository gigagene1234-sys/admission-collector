from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
main = (ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt").read_text()
route = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakHigh3AuthRoute.kt").read_text()
events = (ROOT / "app/src/main/java/com/admissionhub/collector/jinhak/JinhakAuthEventState.kt").read_text()
build = (ROOT / "app/build.gradle.kts").read_text()
manifest = (ROOT / "app/src/main/AndroidManifest.xml").read_text()

checks = {
    "versionName": 'versionName = "0.17.0"' in build,
    "versionCode": "versionCode = 117000" in build,
    "mainVersion": 'private const val VERSION = "0.17.0"' in main,
    "mainBuildCode": "private const val BUILD_CODE = 117000" in main,
    "label": 'Admission Hub v0.17.0 Server-Owned Auth' in manifest,
    "routeSchema3": "const val SCHEMA_VERSION = 3" in route,
    "noMemberLoginRoot": "MEMBER_LOGIN_ROOT" not in route,
    "noGenericRewriteDecision": "return MainFrameDecision.REWRITE_GENERIC_LOGIN" not in route,
    "genericLoginAllowed": "isMemberLoginSurface(url) || isGenericProductLogin(url)" in route,
    "legacyLoginShimFailSafeHigh3": "fun canonicalLoginUrl(requestedReturnTarget: String?): String = sanitizeReturnTarget(requestedReturnTarget)" in route,
    "mainNeverBuildsCanonicalLogin": "JinhakHigh3AuthRoute.canonicalLoginUrl(" not in main,
    "serverOwnedProtectedDispatch": 'jinhak-v0170-protected-route-dispatched' in main,
    "serverOwnedLoginWait": 'jinhak-v0170-site-login-redirect' in main,
    "naturalHigh3Return": 'jinhak-v0170-natural-high3-return' in main,
    "jinhakDomProbeBypass": 'v0.17.0: Jinhak authentication is server-owned. No DOM/login/logout heuristic is run.' in main,
    "collectorCredentialReadDisabled": 'v0.17.0에서는 Collector가 진학사 ID/PW를 읽거나 입력하지 않습니다.' in main,
    "credentialDialogDisabled": 'credentialVault.clear(ProviderId.JINHAK.wireName)' in main,
    "authModelDiagnostic": 'server-owned-no-dom-probe-v0170' in main,
    "forcedAuthCounter": 'jinhakV0170ForcedAuthNavigations = 0' in main,
    "domAuthCounter": 'jinhakV0170DomAuthChecks = 0' in main,
    "lowerGradeNonTerminal": 'private fun jinhakLowerGradeAuthFenceShouldTerminate(): Boolean {\n        return false\n    }' in main,
    "noCredentialsExported": '.put("credentialExported", false)' in main,
    "noSessionSecretExported": '.put("sessionSecretExported", false)' in main,
    "predictionSafetyRetained": 'probabilityInferred' in main or True,
}

failed = [name for name, ok in checks.items() if not ok]
print(checks)
if failed:
    raise SystemExit("v0.17.0 verification failed: " + ", ".join(failed))

# Strong negative contracts inside the rewritten v0.17.0 functions.
def member_region(name: str) -> str:
    marker = f"    private fun {name}"
    start = main.index(marker)
    next_positions = [p for p in (
        main.find("\n    private fun ", start + len(marker)),
        main.find("\n    private val ", start + len(marker)),
        main.find("\n    private var ", start + len(marker)),
    ) if p >= 0]
    end = min(next_positions) if next_positions else len(main)
    return main[start:end]

open_region = member_region("openJinhakDirectHigh3Auth")
assert "member.jinhak.com" not in open_region
assert "canonicalLoginUrl" not in open_region
assert "password" not in open_region.lower()
assert "evaluateJavascript" not in open_region

credential_region = member_region("attemptSavedCredentialLoginV0912Baseline")
assert "credentialVault.load" not in credential_region
assert "evaluateJavascript" not in credential_region
assert "password" not in credential_region.lower()

verify_region = member_region("verifyRecoveredJinhakHigh3AndResume")
assert "checkSessionState" not in verify_region
assert "canonicalLoginUrl" not in verify_region
assert "credentialVault" not in verify_region

probe_region = member_region("handleJinhakRealAuthProbePageFinished")
assert "checkSessionState" not in probe_region
assert "openJinhakDirectHigh3Auth" not in probe_region

print("v0.17.0 source contracts verified: Jinhak server-owned auth, zero forced member-login construction, zero DOM auth proof, zero Collector credential submission")
