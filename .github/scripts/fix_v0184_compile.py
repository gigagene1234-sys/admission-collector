from pathlib import Path

p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
text = p.read_text()
old = '                        attemptV0180JinhakAuthAutofill(jinhakV0180AuthGeneration, 0)'
new = '                        // v0.18.4: legacy authWebView is inactive; same-surface autofill runs only in webView.\n                        jinhakV0168LegacyNavigationSuppressions += 1'
if old in text:
    text = text.replace(old, new, 1)
elif 'legacy authWebView is inactive; same-surface autofill runs only in webView' not in text:
    raise SystemExit('legacy auth autofill call not found and no v0.18.4 repair marker present')
p.write_text(text)
print('v0.18.4 compile residue fixed')
