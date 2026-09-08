from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
p = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = p.read_text()

# Remove the old generic credential script's high3-tab preflight too. It was unreachable for the
# Jinhak v0.9.12 branch, but leaving any grade-selector click/hide code in the APK violates the
# v0.16.7 architectural invariant and makes future refactors unsafe.
pattern = r'''                // Real-device evidence: Jinhak can switch from 고3/N수 to 고1·2 while staying on\n.*?                function visible\(el\)\{'''
repl = '''                function visible(el){'''
text, n = re.subn(pattern, repl, text, count=1, flags=re.S)
if n != 1:
    raise SystemExit(f"generic product preflight removal: expected 1, found {n}")

# Its callback used to handle productContextCorrected by scheduling another attempt. With the grade
# preflight removed, delete that branch rather than preserving a dormant retry state.
pattern = r'''            if \(result\.optBoolean\("productContextCorrected", false\)\) \{.*?            \} else if \(result\.optBoolean\("submitted", false\)\) \{'''
repl = '''            if (result.optBoolean("submitted", false)) {'''
text, n = re.subn(pattern, repl, text, count=1, flags=re.S)
if n != 1:
    raise SystemExit(f"productContextCorrected callback removal: expected 1, found {n}")

for forbidden in [
    "style.setProperty('display','none','important')",
    "setAttribute('aria-hidden','true')",
    "stopImmediatePropagation",
    "high3-product-preflight",
    "productContextCorrected",
]:
    if forbidden in text:
        raise SystemExit(f"grade UI residue remains: {forbidden}")

p.write_text(text)
print("v0.16.7 remaining grade UI manipulation removed")
