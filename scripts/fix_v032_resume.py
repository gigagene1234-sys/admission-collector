from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATHS = [
    ROOT / "MainActivity.kt",
    ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt",
]

bad = 'status.text = "Cloud resume 계획 확인 중: $batchCloudPlansPending개 목록"'
good = 'status.text = "Cloud resume 계획 확인 중: ${batchCloudPlansPending}개 목록"'

for path in PATHS:
    text = path.read_text(encoding="utf-8")
    if bad in text:
        text = text.replace(bad, good, 1)
        path.write_text(text, encoding="utf-8")
        print(f"fixed: {path.relative_to(ROOT)}")
    elif good in text:
        print(f"already fixed: {path.relative_to(ROOT)}")
    else:
        raise SystemExit(f"resume status interpolation anchor missing: {path.relative_to(ROOT)}")

if PATHS[0].read_text(encoding="utf-8") != PATHS[1].read_text(encoding="utf-8"):
    raise SystemExit("root and nested MainActivity.kt diverged after resume interpolation fix")
