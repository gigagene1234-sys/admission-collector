from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "app/src/main/java/com/admissionhub/collector/competition/CompetitionBrowserCollector.kt"
text = path.read_text()
old = "if (!destroyed && running && generation == pageGeneration) {\n                onStatus(\"경쟁률 수집 · ${target.university} 페이지 시간 초과\")"
new = "if (!destroyed && running && generation == pageGeneration && challengeDialog == null) {\n                onStatus(\"경쟁률 수집 · ${target.university} 페이지 시간 초과\")"
if new in text:
    print("timeout guard already applied")
elif old in text:
    path.write_text(text.replace(old, new, 1))
    print("timeout guard applied")
else:
    raise SystemExit("page timeout anchor not found")
