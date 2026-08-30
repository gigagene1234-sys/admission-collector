#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt"
JINHAK = ROOT / "app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt"

source = SNAPSHOT.read_text(encoding="utf-8")
match = re.search(
    r'fun\s+build\(\)\s*:\s*String\s*=\s*"""\n(?P<js>.*)\n\s*"""\.trimIndent\(\)',
    source,
    flags=re.S,
)
if not match:
    raise SystemExit("Could not locate SnapshotScript.build() raw JavaScript string")

js = match.group("js")
if "${" in js:
    raise SystemExit("Unexpected Kotlin interpolation marker inside SnapshotScript JavaScript")

with tempfile.NamedTemporaryFile("w", suffix=".js", encoding="utf-8", delete=False) as handle:
    handle.write(js)
    js_path = Path(handle.name)

try:
    subprocess.run(["node", "--check", str(js_path)], check=True)
finally:
    js_path.unlink(missing_ok=True)

jinhak = JINHAK.read_text(encoding="utf-8")
required = [
    "override val supportsBatchCrawl = false",
    "override fun isBatchNavigable(url: String): Boolean = false",
]
for marker in required:
    if marker not in jinhak:
        raise SystemExit(
            "Jinhak automated batch navigation changed without an explicit architecture/service-boundary review: "
            + marker
        )

print("Embedded SnapshotScript JavaScript syntax: OK")
print("Jinhak unattended batch navigation remains disabled: OK")
