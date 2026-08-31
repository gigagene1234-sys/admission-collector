from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
text = path.read_text()
bad = 'Regex("(학과\\s*심층분석|대학\\s*심층분석|대학학과\\s*심층분석|지도로\\s*보는\\s*대학|대학교\\s*지도|캠퍼스맵)")'
good = 'Regex("(학과\\\\s*심층분석|대학\\\\s*심층분석|대학학과\\\\s*심층분석|지도로\\\\s*보는\\\\s*대학|대학교\\\\s*지도|캠퍼스맵)")'
if bad not in text:
    raise SystemExit('post-v0.7.1 editorial regex escape anchor not found')
text = text.replace(bad, good, 1)
path.write_text(text)
print('Fixed generated Kotlin regex escaping for v0.8.0 post-v0.7.1 quality patch')
