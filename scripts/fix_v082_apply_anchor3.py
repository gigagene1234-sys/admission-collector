from pathlib import Path

p = Path(__file__).resolve().parent / 'apply_v082_application_mission.py'
text = p.read_text()
old = """def once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected one anchor, found {count}')
    return text.replace(old, new, 1)
"""
new = """def once(text, old, new, label):
    count = text.count(old)
    if label == 'adapter report semantic metrics base' and count >= 1:
        return text.replace(old, new, 1)
    if label == 'adapter broad report competition' and count == 0:
        # Removed by post-integration semantic scrub using Kotlin-source semantics, not Python escaping.
        return text
    if count != 1:
        raise SystemExit(f'{label}: expected one anchor, found {count}')
    return text.replace(old, new, 1)
"""
if old not in text:
    raise SystemExit('apply_v082 once() helper anchor not found')
p.write_text(text.replace(old, new, 1))
print('Adjusted v0.8.2 patch helper for report metrics and escaped competition cleanup')
