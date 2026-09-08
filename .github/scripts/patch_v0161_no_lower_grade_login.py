from pathlib import Path

p = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s = p.read_text()

# 1) Hide the WebView as soon as Jinhak collection/auth enters the shared login route. This prevents
# a transient 고1·2 product surface from being shown before the high3 DOM fence has verified context.
old = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {'''
new = '''            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                if (jinhakHigh3FenceActive() && provider == ProviderId.JINHAK && isProviderLoginUrl(ProviderId.JINHAK, url)) {
                    view.visibility = View.INVISIBLE
                    status.text = "진학사 고3·N수 로그인 컨텍스트 확인 중 · 고1·2 화면은 표시하지 않습니다."
                }
                if (jinhakHigh3FenceActive() && JinhakGradeRouteFence.isBlockedLowerGrade(url)) {'''
if old not in s:
    raise SystemExit('onPageStarted anchor mismatch')
s = s.replace(old, new, 1)

# 2) Lower-grade product controls are one-way fenced: suppress them immediately, force high3 when
# necessary, and return an explicit safeHigh3 bit to Kotlin. A plain shared login page with no grade
# controls is treated as a neutral authentication surface, not as a lower-grade product.
old = '''                function enforce(source){
                  var els=all(), h=els.find(high), l=els.find(low), now=Date.now();
                  var lowActive=!!(l&&active(l)); var highActive=!!(h&&active(h));
                  if(h&&l&&(lowActive||!highActive)&&(!window.__admissionHigh3LastClick||now-window.__admissionHigh3LastClick>1200)){
                    window.__admissionHigh3LastClick=now; try{h.click();}catch(e){}
                    return {corrected:true,source:source,high:label(h).trim(),low:label(l).trim(),lowActive:lowActive,highActive:highActive};
                  }
                  return {corrected:false,source:source,high:!!h,low:!!l,lowActive:lowActive,highActive:highActive};
                }'''
new = '''                function enforce(source){
                  var els=all(), h=els.find(high), l=els.find(low), now=Date.now();
                  var lowActive=!!(l&&active(l)); var highActive=!!(h&&active(h));
                  if(l){
                    try{l.style.setProperty('display','none','important');}catch(e){}
                    try{l.setAttribute('aria-hidden','true');l.setAttribute('tabindex','-1');}catch(e){}
                  }
                  if(h&&l&&(lowActive||!highActive)&&(!window.__admissionHigh3LastClick||now-window.__admissionHigh3LastClick>1200)){
                    window.__admissionHigh3LastClick=now; try{h.click();}catch(e){}
                    return {corrected:true,safeHigh3:false,source:source,highFound:true,lowFound:true,lowActive:lowActive,highActive:highActive};
                  }
                  var safeHigh3=!l || (!!h&&highActive&&!lowActive);
                  return {corrected:false,safeHigh3:safeHigh3,source:source,highFound:!!h,lowFound:!!l,lowActive:lowActive,highActive:highActive};
                }'''
if old not in s:
    raise SystemExit('DOM enforce anchor mismatch')
s = s.replace(old, new, 1)

# 3) Fail closed while a lower-grade product context is unresolved. Reveal the shared login only
# after it is neutral/high3-safe; after forcing high3, re-check shortly rather than flashing the
# previous lower-grade surface.
old = '''            val blocked = result.optInt("blocked", 0)
            if (blocked > jinhakDomLowerGradeBlocks) jinhakDomLowerGradeBlocks = blocked
            if (result.optBoolean("corrected", false)) {
                jinhakDomProductFenceCorrections += 1
                recordRuntimeEvent("jinhak-high3-dom-product-corrected", JSONObject(result.toString()).put("reason", reason))
                status.text = "진학사 고1·2 제품 전환을 차단하고 고3·N수 컨텍스트를 복구했습니다."
            }
        }
    }'''
new = '''            val blocked = result.optInt("blocked", 0)
            if (blocked > jinhakDomLowerGradeBlocks) jinhakDomLowerGradeBlocks = blocked
            val corrected = result.optBoolean("corrected", false)
            val currentUrl = webView.url.orEmpty()
            if (corrected) {
                jinhakDomProductFenceCorrections += 1
                webView.visibility = View.INVISIBLE
                recordRuntimeEvent("jinhak-high3-dom-product-corrected", JSONObject(result.toString()).put("reason", reason))
                status.text = "진학사 고1·2 컨텍스트를 표시하지 않고 고3·N수로 전환 확인 중입니다."
                handler.postDelayed({
                    if (provider == ProviderId.JINHAK && jinhakHigh3FenceActive()) {
                        installJinhakHigh3DomProductFence("post-correction-confirm")
                    }
                }, 350L)
            } else if (isProviderLoginUrl(ProviderId.JINHAK, currentUrl)) {
                if (result.optBoolean("safeHigh3", false)) {
                    webView.visibility = View.VISIBLE
                    status.text = "진학사 고3·N수 로그인 컨텍스트 확인 완료 · 자동 로그인을 계속합니다."
                } else {
                    webView.visibility = View.INVISIBLE
                    status.text = "진학사 고1·2 로그인 컨텍스트 차단 · 고3·N수 확인 전에는 로그인 화면을 표시하지 않습니다."
                    handler.postDelayed({
                        if (provider == ProviderId.JINHAK && jinhakHigh3FenceActive() && isProviderLoginUrl(ProviderId.JINHAK, webView.url.orEmpty())) {
                            installJinhakHigh3DomProductFence("unsafe-login-recheck")
                        }
                    }, 500L)
                }
            } else if (!JinhakGradeRouteFence.isBlockedLowerGrade(currentUrl)) {
                webView.visibility = View.VISIBLE
            }
        }
    }'''
if old not in s:
    raise SystemExit('DOM callback anchor mismatch')
s = s.replace(old, new, 1)

# 4) Credential preflight must never expose the lower-grade selector either. It can only choose
# high3; lower-grade remains hidden and non-interactive.
old = '''                var phigh=pels.find(function(el){var n=pnorm(plabel(el));return n.indexOf('고3')>=0&&(n.indexOf('n수')>=0||n.indexOf('재수')>=0||n==='고3');});
                var plow=pels.find(function(el){var n=pnorm(plabel(el));return n==='고12'||n==='고1~2'||n.indexOf('고1고2')>=0||n.indexOf('고12학년')>=0;});
                var pnow=Date.now(), plast=0;'''
new = '''                var phigh=pels.find(function(el){var n=pnorm(plabel(el));return n.indexOf('고3')>=0&&(n.indexOf('n수')>=0||n.indexOf('재수')>=0||n==='고3');});
                var plow=pels.find(function(el){var n=pnorm(plabel(el));return n==='고12'||n==='고1~2'||n.indexOf('고1고2')>=0||n.indexOf('고12학년')>=0;});
                if(plow){try{plow.style.setProperty('display','none','important');plow.setAttribute('aria-hidden','true');plow.setAttribute('tabindex','-1');}catch(e){}}
                var pnow=Date.now(), plast=0;'''
if old not in s:
    raise SystemExit('credential preflight anchor mismatch')
s = s.replace(old, new, 1)

p.write_text(s)
print('v0.16.1 no-lower-grade-login fence applied')
