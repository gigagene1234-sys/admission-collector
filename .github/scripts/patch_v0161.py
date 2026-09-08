from pathlib import Path

# 1) Existing imported profiles: re-assess completeness dynamically so v0.15/v0.16 stored data can calculate.
p=Path('app/src/main/java/com/admissionhub/collector/score/OfficialUniversityScoreCalculator.kt')
s=p.read_text()
old='''        val transcriptComplete = profile.optBoolean("completeTranscriptConfirmedByUser", false) || profile.optBoolean("documentCompletenessVerified", false)
        if (!transcriptComplete) return hold(base, "transcript-not-confirmed-complete", "가져온 과목·학기가 판단에 필요한 학생부 전체를 포함하는지 확인이 필요합니다.")'''
new='''        val structuralCompleteness = StudentScoreDocumentCompleteness.assess(profile)
        val transcriptComplete = profile.optBoolean("completeTranscriptConfirmedByUser", false) ||
            profile.optBoolean("documentCompletenessVerified", false) ||
            structuralCompleteness.optBoolean("verified", false)
        base.put("documentCompleteness", structuralCompleteness)
            .put("documentCompletenessVerifiedAtCalculation", structuralCompleteness.optBoolean("verified", false))
        if (!transcriptComplete) return hold(base, "transcript-not-confirmed-complete", "가져온 과목·학기가 판단에 필요한 학생부 전체를 포함하는지 확인이 필요합니다.")'''
if old not in s: raise SystemExit('calculator completeness anchor missing')
s=s.replace(old,new,1)
p.write_text(s)

# 2) MainActivity: same-URL DOM product fence + v0.16.1 metadata.
p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()
s=s.replace('private const val VERSION = "0.16.0"','private const val VERSION = "0.16.1"',1)
s=s.replace('private const val BUILD_CODE = 116000','private const val BUILD_CODE = 116100',1)

# Runtime counter.
anchor='''    private var jinhakLoginRecoveryFenceTrips = 0
'''
if anchor not in s: raise SystemExit('counter anchor missing')
s=s.replace(anchor, anchor + '''    private var jinhakDomProductFenceInstalls = 0
    private var jinhakDomProductFenceCorrections = 0
    private var jinhakDomLowerGradeBlocks = 0
''',1)

# Install the DOM fence before any login-surface detection on every finished Jinhak page.
old='''            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                // v0.9.5: never navigate to login proactively. Probe the rendered DOM after
                // every navigation and auto-login only when an actual login surface is visible.
                scheduleLoginSurfaceDetection(provider, "page-finished")'''
new='''            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                if (provider == ProviderId.JINHAK) installJinhakHigh3DomProductFence("page-finished")
                // Probe only after the high3 DOM product fence is armed. Jinhak's login page can
                // switch the product context without changing /jh/member/login, so URL-only fencing
                // is insufficient on real devices.
                scheduleLoginSurfaceDetection(provider, "page-finished")'''
if old not in s: raise SystemExit('page-finished anchor missing')
s=s.replace(old,new,1)

# Inject helper before credential auto-login function.
anchor='''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
'''
if anchor not in s: raise SystemExit('credential function anchor missing')
helper=r'''    private fun installJinhakHigh3DomProductFence(reason: String) {
        if (provider != ProviderId.JINHAK || !::webView.isInitialized) return
        val js = """
            (function(){
              try{
                function norm(v){return (v||'').toString().toLowerCase().replace(/\\s+/g,'').replace(/[·ㆍ・\\/,._-]/g,'');}
                function label(el){return ((el&&(el.innerText||el.textContent||el.value||el.getAttribute&&el.getAttribute('aria-label')))||'').toString();}
                function low(el){var n=norm(label(el));return n==='고12'||n==='고1~2'||n.indexOf('고1고2')>=0||n.indexOf('고12학년')>=0;}
                function high(el){var n=norm(label(el));return n.indexOf('고3')>=0&&(n.indexOf('n수')>=0||n.indexOf('재수')>=0||n==='고3');}
                function active(el){if(!el)return false;var a=(el.getAttribute&&el.getAttribute('aria-selected'))||'';var c=(el.className||'').toString().toLowerCase();return a==='true'||/(^|\\s)(active|on|selected|current)(\\s|$)/.test(c);}
                function all(){return Array.from(document.querySelectorAll('a,button,[role=tab],[role=button],li,span,div')).filter(function(el){var n=norm(label(el));return n.indexOf('고3')>=0||n.indexOf('고1')>=0||n.indexOf('고2')>=0;});}
                function enforce(source){
                  var els=all(), h=els.find(high), l=els.find(low), now=Date.now();
                  var lowActive=!!(l&&active(l)); var highActive=!!(h&&active(h));
                  if(h&&l&&(lowActive||!highActive)&&(!window.__admissionHigh3LastClick||now-window.__admissionHigh3LastClick>1200)){
                    window.__admissionHigh3LastClick=now; try{h.click();}catch(e){}
                    return {corrected:true,source:source,high:label(h).trim(),low:label(l).trim(),lowActive:lowActive,highActive:highActive};
                  }
                  return {corrected:false,source:source,high:!!h,low:!!l,lowActive:lowActive,highActive:highActive};
                }
                if(!window.__admissionHigh3FenceInstalled){
                  window.__admissionHigh3FenceInstalled=true;
                  document.addEventListener('click',function(ev){
                    try{var t=ev.target&&ev.target.closest?ev.target.closest('a,button,[role=tab],[role=button],li,span,div'):ev.target;if(t&&low(t)){ev.preventDefault();ev.stopPropagation();if(ev.stopImmediatePropagation)ev.stopImmediatePropagation();window.__admissionLowerGradeBlocked=(window.__admissionLowerGradeBlocked||0)+1;setTimeout(function(){enforce('blocked-click');},0);}}catch(e){}
                  },true);
                  try{new MutationObserver(function(){enforce('mutation');}).observe(document.documentElement||document,{subtree:true,childList:true,attributes:true,attributeFilter:['class','aria-selected']});}catch(e){}
                }
                var out=enforce('install'); out.installed=true; out.blocked=window.__admissionLowerGradeBlocked||0; return JSON.stringify(out);
              }catch(e){return JSON.stringify({installed:false,error:String(e)});}
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { raw ->
            jinhakDomProductFenceInstalls += 1
            val decoded = runCatching { JSONTokener(raw).nextValue() as? String }.getOrNull().orEmpty()
            val result = runCatching { JSONObject(decoded) }.getOrDefault(JSONObject())
            val blocked = result.optInt("blocked", 0)
            if (blocked > jinhakDomLowerGradeBlocks) jinhakDomLowerGradeBlocks = blocked
            if (result.optBoolean("corrected", false)) {
                jinhakDomProductFenceCorrections += 1
                recordRuntimeEvent("jinhak-high3-dom-product-corrected", JSONObject(result.toString()).put("reason", reason))
                status.text = "진학사 고1·2 제품 전환을 차단하고 고3·N수 컨텍스트를 복구했습니다."
            }
        }
    }

'''
s=s.replace(anchor,helper+anchor,1)

# Guard at the beginning of each saved-credential login attempt too.
old='''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        val now = System.currentTimeMillis()
'''
new='''    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        if (which == ProviderId.JINHAK) installJinhakHigh3DomProductFence("credential:$reason")
        val now = System.currentTimeMillis()
'''
if old not in s: raise SystemExit('credential pre-fence anchor missing')
s=s.replace(old,new,1)

# Diagnostics include the same-URL product fence evidence.
needle='''.put("jinhakLoginRecoveryFenceTrips", jinhakLoginRecoveryFenceTrips)'''
if needle in s:
    s=s.replace(needle, needle+'''
                    .put("jinhakDomProductFenceInstalls", jinhakDomProductFenceInstalls)
                    .put("jinhakDomProductFenceCorrections", jinhakDomProductFenceCorrections)
                    .put("jinhakDomLowerGradeBlocks", jinhakDomLowerGradeBlocks)''',1)

p.write_text(s)

# 3) Manifest/Gradle metadata.
p=Path('app/src/main/AndroidManifest.xml')
s=p.read_text().replace('Admission Hub v0.16.0 Official Dashboard','Admission Hub v0.16.1 High3 DOM Fence',1)
p.write_text(s)
p=Path('app/build.gradle.kts')
s=p.read_text().replace('versionCode = 116000','versionCode = 116100',1).replace('versionName = "0.16.0"','versionName = "0.16.1"',1)
p.write_text(s)
print('v0.16.1 device evidence patch applied')
