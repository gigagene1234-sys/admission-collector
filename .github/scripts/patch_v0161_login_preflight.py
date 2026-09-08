from pathlib import Path
p=Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
s=p.read_text()
old='''        val userJson = JSONObject.quote(credential.username)
        val passJson = JSONObject.quote(credential.password)
        val js = """
            (function(){
              try{
                function visible(el){'''
new='''        val userJson = JSONObject.quote(credential.username)
        val passJson = JSONObject.quote(credential.password)
        val js = """
            (function(){
              try{
                // Real-device evidence: Jinhak can switch from 고3/N수 to 고1·2 while staying on
                // the same /jh/member/login URL. Force the product context immediately before any
                // credential submission. sessionStorage keeps a short guard across same-tab reloads.
                function pnorm(v){return (v||'').toString().toLowerCase().replace(/\\s+/g,'').replace(/[·ㆍ・\\/,._-]/g,'');}
                function plabel(el){return ((el&&(el.innerText||el.textContent||el.value||el.getAttribute&&el.getAttribute('aria-label')))||'').toString();}
                var pels=[];try{pels=Array.from(document.querySelectorAll('a,button,[role=tab],[role=button]'));}catch(e){}
                var phigh=pels.find(function(el){var n=pnorm(plabel(el));return n.indexOf('고3')>=0&&(n.indexOf('n수')>=0||n.indexOf('재수')>=0||n==='고3');});
                var plow=pels.find(function(el){var n=pnorm(plabel(el));return n==='고12'||n==='고1~2'||n.indexOf('고1고2')>=0||n.indexOf('고12학년')>=0;});
                var pnow=Date.now(), plast=0;try{plast=Number(sessionStorage.getItem('__admissionHigh3CredentialReadyAt')||0);}catch(e){}
                if(phigh&&plow&&(!plast||pnow-plast>3000)){
                  try{sessionStorage.setItem('__admissionHigh3CredentialReadyAt',String(pnow));}catch(e){}
                  try{phigh.click();}catch(e){}
                  return JSON.stringify({submitted:false,productContextCorrected:true,reason:'high3-product-preflight'});
                }
                function visible(el){'''
if old not in s: raise SystemExit('credential JS anchor mismatch')
s=s.replace(old,new,1)

old2='''            if (result.optBoolean("submitted", false)) {
                credentialAutoLoginSubmissions += 1'''
new2='''            if (result.optBoolean("productContextCorrected", false)) {
                credentialAutoLoginLastResult = "high3-product-preflight"
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                jinhakDomProductFenceCorrections += 1
                status.text = "진학사 고3·N수 컨텍스트를 고정한 뒤 자동 로그인을 계속합니다."
                handler.postDelayed({
                    if (provider == which && credentialVault.has(which.wireName)) {
                        attemptSavedCredentialLogin(which, "high3-product-preflight")
                    }
                }, 900L)
            } else if (result.optBoolean("submitted", false)) {
                credentialAutoLoginSubmissions += 1'''
if old2 not in s: raise SystemExit('credential callback anchor mismatch')
s=s.replace(old2,new2,1)
p.write_text(s)
print('v0.16.1 synchronous high3 login preflight applied')
