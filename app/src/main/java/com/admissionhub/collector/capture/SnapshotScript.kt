package com.admissionhub.collector.capture

object SnapshotScript {
    fun build(): String = """
(function(){
  function visible(el){
    if(!el) return false;
    var s=getComputedStyle(el);
    if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
    var r=el.getBoundingClientRect();
    return r.width>0 && r.height>0;
  }
  function cleanText(v){
    return String(v||'').replace(/\s+/g,' ').trim();
  }
  function safeCloneText(el,maxLen){
    if(!el) return '';
    var clone=el.cloneNode(true);
    var rm=clone.querySelectorAll('script,style,noscript,template,input,textarea,select,option,form,[type=hidden],[hidden],[aria-hidden=true]');
    for(var i=0;i<rm.length;i++) rm[i].remove();
    var t=cleanText(clone.innerText||clone.textContent||'');
    t=t.replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'[redacted-email]');
    return t.slice(0,maxLen||3000);
  }
  function unsafePseudoUrl(raw){
    raw=String(raw||'').trim();
    if(!raw || raw.length>4096) return true;
    if(/^(?:javascript:|data:|mailto:|tel:)/i.test(raw)) return true;
    if(/^[A-Za-z_$][A-Za-z0-9_$]*\s*\(/.test(raw)) return true;
    if(/^(?:return\s+false|void\s*\()/i.test(raw)) return true;
    return false;
  }
  function safeUrl(raw){
    if(unsafePseudoUrl(raw)) return '';
    try{
      var u=new URL(raw,location.href);
      if(u.protocol!=='https:' && u.protocol!=='http:') return '';
      return u.origin+u.pathname;
    }catch(e){ return ''; }
  }
  function fullNavigationUrl(raw){
    if(unsafePseudoUrl(raw)) return '';
    try{
      var u=new URL(raw,location.href);
      if(u.origin!==location.origin) return '';
      var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|sysReg|sysChg|userId|ipMac/i;
      var filtered=new URLSearchParams();
      u.searchParams.forEach(function(v,k){ if(!badKey.test(k)) filtered.append(k,v); });
      var q=filtered.toString();
      return u.origin+u.pathname+(q?'?'+q:'');
    }catch(e){ return ''; }
  }
  function safeExportUrl(raw){
    if(unsafePseudoUrl(raw)) return '';
    try{
      var u=new URL(raw,location.href);
      if(u.protocol!=='https:' && u.protocol!=='http:') return '';
      var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|preurl|returnurl|redirect|callback|sysReg|sysChg|userId|ipMac/i;
      var filtered=new URLSearchParams();
      u.searchParams.forEach(function(v,k){ if(!badKey.test(k)) filtered.append(k,v); });
      var q=filtered.toString();
      return u.origin+u.pathname+(q?'?'+q:'');
    }catch(e){ return ''; }
  }
  function routeFromScript(raw){
    raw=String(raw||'').replace(/&amp;/g,'&').trim();
    if(!raw || raw.length>4096) return '';

    // 함수 호출 전체를 URL로 해석하지 않는다. 실제 문자열 URL만 추출한다.
    var explicit=[
      /location(?:\.href)?\s*=\s*['"]([^'"]+)['"]/i,
      /location\.(?:assign|replace)\s*\(\s*['"]([^'"]+)['"]/i,
      /window\.open\s*\(\s*['"]([^'"]+)['"]/i
    ];
    for(var i=0;i<explicit.length;i++){
      var em=raw.match(explicit[i]);
      if(em && em[1]){
        var er=fullNavigationUrl(em[1]);
        if(er) return er;
      }
    }

    var quoted=/['"]((?:https?:\/\/[^'"]+|\/[^'"]+\.do(?:\?[^'"]*)?))['"]/ig;
    var m;
    while((m=quoted.exec(raw))!==null){
      var q=fullNavigationUrl(m[1]);
      if(q) return q;
    }
    return '';
  }

  function inferAcademicYear(){
    try{
      var q=new URL(location.href).searchParams.get('searchSyr');
      if(/^20[0-9]{2}$/.test(String(q||''))) return String(q);
    }catch(e){}
    var controls=document.querySelectorAll('[name=searchSyr],#searchSyr,select[name*=Syr],input[name*=Syr]');
    for(var i=0;i<controls.length;i++){
      var v=String(controls[i].value||'').trim();
      if(/^20[0-9]{2}$/.test(v)) return v;
    }
    var m=(document.body&&document.body.innerText?document.body.innerText:'').match(/(20[0-9]{2})학년도/);
    return m?m[1]:'';
  }
  function inferredUniversityDetailRoute(script){
    if(!/\/ucp\/uvt\/uni\/univView\.do$/i.test(location.pathname)) return '';
    script=String(script||'');
    var codeMatch=script.match(/\b(0[0-9]{6})\b/);
    if(!codeMatch) return '';
    var year=inferAcademicYear();
    if(!year) return '';
    return location.origin+'/ucp/uvt/uni/univDetailSelection.do?menuId=PCUVTINF2000&searchSyr='+encodeURIComponent(year)+'&unvCd='+encodeURIComponent(codeMatch[1]);
  }

  var forbidden=/password|passwd|cookie|session|token|csrf|transkey|captcha|credential|secret/i;
  var loginSensitive=/(아이디|비밀번호|로그인|로그아웃|회원정보|마이페이지|account|sign[ -]?in|sign[ -]?out)/i;
  var admissionTerms=/(대학|대학교|학과|학부|전공|모집|전형|입시|입결|성적|환산|등급|경쟁률|합격|예측|지원|교과|종합|면접|수능|최저|50%|70%|칸수|모집요강|전년도|202[0-9])/i;

  var pass=false;
  var pw=document.querySelectorAll('input[type=password]');
  for(var p=0;p<pw.length;p++){ if(visible(pw[p])) { pass=true; break; } }
  var bodyText=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,16000);
  var logoutControl=false;
  var sessionControls=document.querySelectorAll('a,button,[role=button]');
  for(var sc=0;sc<sessionControls.length;sc++){
    var sn=sessionControls[sc];
    if(!visible(sn)) continue;
    var sl=cleanText(sn.innerText||sn.textContent||sn.getAttribute('aria-label')||'');
    if(/^(로그아웃|log\s*out|sign\s*out)$/i.test(sl)){ logoutControl=true; break; }
  }
  var loginUrl=/(\/mbs\/log\/|login|signin|sign-in|member\/login|loginForm)/i.test(location.href);
  var loginRequired=/(로그인이\s*필요|로그인\s*후\s*(?:이용|사용)|로그인해\s*주세요|로그인해주세요|회원만\s*이용|서비스\s*이용을\s*위해\s*로그인)/i.test(bodyText);
  var authenticated=logoutControl;
  var titleText=cleanText(document.title||'');
  var error404=/(404\s*Not\s*Found|요청하신\s*페이지를\s*찾을\s*수\s*없|페이지를\s*찾을\s*수\s*없)/i.test(titleText+' '+bodyText);
  var serverError=/(500\s*(?:Internal\s*Server\s*Error)?|서비스\s*처리\s*중\s*오류|일시적인\s*오류가\s*발생)/i.test(titleText+' '+bodyText);
  var browserError=/(웹페이지를\s*사용할\s*수\s*없|net::ERR_|ERR_CONNECTION_|ERR_NAME_NOT_RESOLVED)/i.test(titleText+' '+bodyText);
  var pageError=error404||serverError||browserError;
  var errorType=error404?'404':(serverError?'server-error':(browserError?'browser-error':''));

  var context=[];
  var contextNodes=document.querySelectorAll('h1,h2,h3,h4,h5,h6,.title,.tit,.sub-title,.breadcrumb,.location,[class*=title],[class*=breadcrumb]');
  for(var c=0;c<contextNodes.length && context.length<80;c++){
    var ce=contextNodes[c];
    if(!visible(ce)) continue;
    var ct=safeCloneText(ce,800);
    if(ct.length>=2 && !forbidden.test(ct) && !loginSensitive.test(ct)) context.push(ct);
  }

  var tables=[];
  var captureHiddenDetail=/(^|\.)jinhak\.com$/i.test(location.hostname) || /\/(?:ucp\/uvt\/uni\/univDetailSelection|uct\/acd\/ade\/criteriaAndResultPopup)\.do$/i.test(location.pathname);
  var tableNodes=document.querySelectorAll('table,[role=table]');
  for(var ti=0;ti<tableNodes.length && tables.length<120;ti++){
    var table=tableNodes[ti];
    if(!captureHiddenDetail && !visible(table)) continue;
    var rows=[];
    var trNodes=table.querySelectorAll('tr,[role=row]');
    for(var ri=0;ri<trNodes.length && rows.length<250;ri++){
      var tr=trNodes[ri];
      if(!captureHiddenDetail && !visible(tr)) continue;
      var cells=[];
      var cellNodes=tr.querySelectorAll('th,td,[role=columnheader],[role=cell]');
      for(var ci=0;ci<cellNodes.length && cells.length<40;ci++){
        var cell=cellNodes[ci];
        if(!captureHiddenDetail && !visible(cell)) continue;
        var cellText=safeCloneText(cell,1200);
        if(cellText && !forbidden.test(cellText.substring(0,160))) cells.push(cellText);
      }
      if(cells.length>0) rows.push(cells);
    }
    if(rows.length>0){
      tables.push({caption:safeCloneText(table.querySelector('caption'),500),rows:rows});
    }
  }

  var blocks=[];
  var blockNodes=document.querySelectorAll('article,.card,.item,.result,.list-item,.tbl_row,[class*=result],[class*=admission],[class*=score],[class*=grade],[class*=competition],[class*=apply],dl,section');
  for(var bi=0;bi<blockNodes.length && blocks.length<300;bi++){
    var be=blockNodes[bi];
    if(!visible(be)) continue;
    var meta=(be.id||'')+' '+(be.className||'')+' '+(be.getAttribute('name')||'');
    if(forbidden.test(meta)) continue;
    var bt=safeCloneText(be,3000);
    if(bt.length<4 || loginSensitive.test(bt.substring(0,200))) continue;
    if(admissionTerms.test(bt)) blocks.push(bt);
  }

  var nav=[];
  var resources=[];
  var pageActions=[];
  var linkNodes=document.querySelectorAll('a,button,[role=button],[onclick],[data-href],[data-url],[data-link],[data-path]');
  var seenNav={};
  var seenRes={};
  var seenPageAction={};
  var currentParts=location.pathname.split('/').filter(Boolean);
  var prefix=currentParts.slice(0,2).join('/');
  var scriptCandidates=0;
  var paginationAllowed=/\/(?:ucp\/uvt\/uni\/univView|ucp\/cls\/uni\/classUnivView|ucp\/prc\/uni\/admssUnivView|sco\/agu\/univScoScaAnlsView|uct\/acd\/adc\/characteristicsView|uct\/acd\/ueg\/univEtenGuideView|uct\/acd\/ade\/criteriaAndResultView|uct\/acd\/dia\/disabledAdmssView)\.do$/i.test(location.pathname);
  for(var li=0;li<linkNodes.length;li++){
    var a=linkNodes[li];
    if(!visible(a)) continue;
    var href=a.getAttribute('href')||'';
    var onclick=a.getAttribute('onclick')||'';
    var dataRaw=a.getAttribute('data-href')||a.getAttribute('data-url')||a.getAttribute('data-link')||a.getAttribute('data-path')||'';
    var raw=dataRaw||href||'';
    var label=cleanText(a.innerText||a.textContent||a.getAttribute('aria-label')||a.getAttribute('title')||'').slice(0,500);
    var meta2=(a.id||'')+' '+(a.className||'')+' '+label+' '+raw+' '+onclick;
    if(/logout|signout|로그아웃|delete|withdraw|탈퇴|회원탈퇴|원서접수|결제|삭제|저장/i.test(meta2)) continue;
    if(/^mailto:/i.test(raw) || /^tel:/i.test(raw)) continue;

    var scriptText=(onclick||'')+' '+(/^javascript:/i.test(raw)?raw:'');
    if(paginationAllowed){
      var pm=scriptText.match(/\bfnSearch\s*\(\s*([0-9]{1,4})\s*\)/i);
      if(pm){
        var pageNum=parseInt(pm[1],10);
        if(pageNum>1 && pageNum<=500){
          var actionKey=fullNavigationUrl(location.href)+'|fnSearch|'+pageNum;
          if(!seenPageAction[actionKey]){
            pageActions.push({type:'fnSearch',page:pageNum,baseUrl:fullNavigationUrl(location.href)});
            seenPageAction[actionKey]=1;
          }
        }
      }
    }

    var route='';
    var directUrlish=/^(?:https?:\/\/|\/|\.\.?\/)/i.test(raw) && !/[{}();]/.test(raw);
    if(raw && directUrlish && raw!=='#') route=fullNavigationUrl(raw);
    if(!route && onclick){ route=routeFromScript(onclick); if(route) scriptCandidates++; }
    if(!route && /^javascript:/i.test(raw)){ route=routeFromScript(raw); if(route) scriptCandidates++; }
    if(!route){
      route=inferredUniversityDetailRoute(scriptText+' '+dataRaw+' '+raw);
      if(route) scriptCandidates++;
    }

    var resourceRaw=(raw && directUrlish) ? raw : (route||'');
    var exportUrl=safeExportUrl(resourceRaw);
    var u=null;
    try{ if(resourceRaw) u=new URL(resourceRaw,location.href); }catch(e){ u=null; }
    var ext=/\.(pdf|hwp|hwpx|xls|xlsx|csv|doc|docx|ppt|pptx|zip)(?:$|[?#])/i;
    if(u && ext.test(u.pathname)){
      if(exportUrl && !seenRes[exportUrl]){ resources.push({label:label,url:exportUrl}); seenRes[exportUrl]=1; }
      continue;
    }

    if(!route) continue;
    var ru;
    try{ ru=new URL(route,location.href); }catch(e2){ continue; }
    if(ru.origin!==location.origin) continue;
    var sameArea=prefix && ru.pathname.split('/').filter(Boolean).slice(0,2).join('/')===prefix;
    if(!(admissionTerms.test(label+' '+ru.pathname+' '+onclick) || sameArea)) continue;
    if(seenNav[route]) continue;
    nav.push({label:label,url:route,exportUrl:safeExportUrl(route)});
    seenNav[route]=1;
    if(nav.length>=700) break;
  }

  var totalMatch=bodyText.match(/총\s*([0-9,]+)\s*건/);
  var listTotal=totalMatch?parseInt(totalMatch[1].replace(/,/g,''),10):-1;
  var visibleDataRows=(tables.length>0 && tables[0].rows)?Math.max(0,tables[0].rows.length-1):0;

  return JSON.stringify({
    title:document.title||'',
    url:safeExportUrl(location.href),
    navigationKey:fullNavigationUrl(location.href),
    collectedAt:new Date().toISOString(),
    session:{needsLogin:(pass||loginUrl||loginRequired)&&!authenticated,authenticated:authenticated},
    pageState:{isError:pageError,errorType:errorType},
    listMeta:{totalItems:isNaN(listTotal)?-1:listTotal,visibleDataRows:visibleDataRows},
    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length},
    context:context,
    tables:tables,
    blocks:blocks,
    navigationLinks:nav,
    pageActions:pageActions,
    resourceLinks:resources
  });
})();
    """.trimIndent()
}
