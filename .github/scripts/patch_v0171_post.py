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

MAIN.write_text(text)
