from pathlib import Path
p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()
old='''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n                runtimeLastSafePath = runtimeSafePath(url)\n                if (provider == ProviderId.JINHAK) {\n                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url)) {'''
new='''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {\n                runtimeLastSafePath = runtimeSafePath(url)\n                if (provider == ProviderId.JINHAK) {\n                    if (JinhakDedicatedAuthPolicy.isLoginSurface(url) == true) {'''
if s.count(old)!=1:
    raise SystemExit(f'expected one page-started hook, got {s.count(old)}')
p.write_text(s.replace(old,new,1))
print('v0.18.2 page-started hook disambiguated')
