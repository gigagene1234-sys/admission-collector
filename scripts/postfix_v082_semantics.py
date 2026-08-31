from pathlib import Path

p = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
text = p.read_text()
lines = text.splitlines()
out = []
removed = 0
for line in lines:
    # v0.8.1 semantic bug: optional '모의지원' made plain '전년도 경쟁률' eligible for mockCompetition.
    if 'putNumber(metrics, "mockCompetition"' in line and '경쟁률' in line:
        removed += 1
        continue
    out.append(line)
if removed < 1:
    raise SystemExit('legacy broad mockCompetition assignment not found after integration')
text = '\n'.join(out) + '\n'
if '(?:모의지원\\\\s*)?경쟁률' in text:
    raise SystemExit('legacy broad competition regex remains after semantic scrub')
p.write_text(text)
print(f'Removed {removed} legacy broad mockCompetition assignment(s); explicit semantic parser remains authoritative')
