from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()

# Any remaining generic provider-lease restoration site must explicitly exclude Jinhak.
pattern = re.compile(r'(?m)^(\s*)val\s+(\w+)\s*=\s*runCatching\s*\{\s*sessionVault\.restore\(which\.wireName\)\s*\}\.getOrNull\(\)\s*$')

def repl(match: re.Match) -> str:
    indent, name = match.group(1), match.group(2)
    return f'{indent}val {name} = if (which == ProviderId.JINHAK) null else runCatching {{ sessionVault.restore(which.wireName) }}.getOrNull()'

text, count = pattern.subn(repl, text)
print(f'v0.17.1 post patch: guarded {count} remaining generic sessionVault.restore(which) site(s)')

# Defensive source-level contract: direct Jinhak restore/capture must not survive.
text = text.replace(
    'runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()',
    'null as SecureSessionVault.SessionLeaseSummary?'
)
text = text.replace(
    'runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }',
    'runCatching { null } // v0.17.1 Jinhak lease capture disabled'
)

# patch_v0171.py originally injected the generic-provider guard into the older
# attemptSavedCredentialLoginV0912Baseline overload because their names share a prefix.
# Make the baseline itself a pure user-session handoff and keep all credential-vault/DOM work out.
baseline_pattern = re.compile(
    r'    private fun attemptSavedCredentialLoginV0912Baseline\(reason: String\) \{.*?\n    \}\n(?=    private fun attemptSavedCredentialLogin\(which: ProviderId, reason: String\) \{)',
    re.S,
)
baseline_replacement = '''    private fun attemptSavedCredentialLoginV0912Baseline(reason: String) {
        if (provider != ProviderId.JINHAK) return
        enterJinhakUserSessionGate("saved-credential-login-disabled:$reason")
    }
'''
text, baseline_count = baseline_pattern.subn(baseline_replacement, text, count=1)
if baseline_count != 1 and baseline_replacement not in text:
    raise SystemExit(f'failed to replace Jinhak baseline credential function: {baseline_count}')

# Ensure the real generic function has an explicit Jinhak return before any credentialVault read.
actual_signature = '    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {\n'
actual_guard = actual_signature + '''        if (which == ProviderId.JINHAK) {
            if (provider == ProviderId.JINHAK) enterJinhakUserSessionGate("saved-credential-login-disabled:$reason")
            return
        }
'''
if actual_guard not in text:
    if text.count(actual_signature) != 1:
        raise SystemExit('generic attemptSavedCredentialLogin signature missing/duplicated')
    text = text.replace(actual_signature, actual_guard, 1)

MAIN.write_text(text)
print('v0.17.1 post patch: credential baseline is user-session-only and generic Jinhak credential path returns before vault access')
