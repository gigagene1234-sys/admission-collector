from pathlib import Path

path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
text = path.read_text()
marker = '    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {'
assert marker in text, 'scheduleLoginSurfaceDetection marker missing'
assert 'private fun probeLoginSurface(which: ProviderId, callback: (JSONObject) -> Unit)' not in text, 'probeLoginSurface already restored'
probe = r'''    private fun probeLoginSurface(which: ProviderId, callback: (JSONObject) -> Unit) {
        if (provider != which) { callback(JSONObject().put("detected", false)); return }
        val js = """
            (function(){
              try{
                function visible(el){ if(!el) return false; var s=getComputedStyle(el); if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false; var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
                function roots(doc){ var out=[doc]; try{var all=doc.querySelectorAll('*'); for(var i=0;i<all.length;i++) if(all[i].shadowRoot) out.push(all[i].shadowRoot);}catch(e){} return out; }
                var docs=[document]; try{var fs=document.querySelectorAll('iframe,frame'); for(var f=0;f<fs.length;f++) try{if(fs[f].contentDocument) docs.push(fs[f].contentDocument);}catch(e){}}catch(e){}
                var best=null;
                for(var d=0;d<docs.length;d++){
                  var rs=roots(docs[d]);
                  for(var r=0;r<rs.length;r++){
                    var root=rs[r], passes=[]; try{passes=Array.from(root.querySelectorAll('input[type=password]')).filter(visible);}catch(e){}
                    for(var p=0;p<passes.length;p++){
                      var pass=passes[p], form=pass.form||pass.closest('form'), candidates=[];
                      var base=form||root;
                      try{candidates=Array.from(base.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                      if(!candidates.length) try{candidates=Array.from(root.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                      function score(el){ var meta=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase(); var n=0; if(/아이디|user|login|member|email|account/.test(meta)) n+=50; if(/\bid\b/.test(meta)) n+=25; if((el.autocomplete||'').toLowerCase()==='username') n+=80; if((el.type||'').toLowerCase()==='email') n+=10; if(/search|검색/.test(meta)) n-=120; if(form&&el.form===form) n+=100; return n; }
                      candidates.sort(function(a,b){return score(b)-score(a);});
                      var user=candidates[0]||null;
                      var controls=[]; try{controls=Array.from((form||root).querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                      if(!controls.length) try{controls=Array.from(root.querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                      function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\s+/g,' ').trim();}
                      var submit=controls.find(function(el){return /^(로그인|로그인하기|log\s*in|sign\s*in)$/i.test(label(el));})||null;
                      if(user){ best={user:true,pass:true,submit:!!submit,form:!!form}; break; }
                    }
                    if(best) break;
                  }
                  if(best) break;
                }
                var text=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,20000);
                var credentialError=/(아이디\s*(?:또는|나)\s*비밀번호.*(?:확인|일치|오류)|비밀번호.*일치하지|잘못된\s*비밀번호|로그인에\s*실패)/i.test(text);
                return JSON.stringify({detected:!!best,hasUser:!!(best&&best.user),hasPassword:!!(best&&best.pass),hasSubmit:!!(best&&best.submit),hasForm:!!(best&&best.form),credentialError:credentialError,urlLooksLogin:/(\/member\/login|\/mbs\/log\/|mbslogview)/i.test(location.href)});
              }catch(e){return JSON.stringify({detected:false,error:'probe-error'});}
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { encoded ->
            val obj = runCatching { JSONObject(decodeJsString(encoded)) }.getOrElse { JSONObject().put("detected", false).put("error", "decode-error") }
            if (obj.optBoolean("detected", false)) {
                credentialLoginSurfaceSeenProvider = which
                credentialLoginSurfaceSeenAtMs = System.currentTimeMillis()
            }
            callback(obj)
        }
    }

'''
text = text.replace(marker, probe + marker, 1)
path.write_text(text)
print('restored probeLoginSurface')
