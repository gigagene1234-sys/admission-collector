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
      var currentHost=String(location.hostname||'').toLowerCase();
      var targetHost=String(u.hostname||'').toLowerCase();
      var currentJinhak=(currentHost==='jinhak.com'||/\.jinhak\.com$/.test(currentHost));
      var targetJinhak=(targetHost==='jinhak.com'||/\.jinhak\.com$/.test(targetHost));
      if(u.origin!==location.origin && !(currentJinhak&&targetJinhak)) return '';
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

  var selectionContext=[];
  var selectedNodes=document.querySelectorAll('select option:checked,[aria-selected=true],.selected,.active,[class*=selected],[class*=active]');
  for(var si=0;si<selectedNodes.length && selectionContext.length<80;si++){
    var se=selectedNodes[si];
    if(se.tagName!=='OPTION' && !visible(se)) continue;
    var st=safeCloneText(se,500);
    if(st.length>=2 && admissionTerms.test(st) && !forbidden.test(st) && !loginSensitive.test(st)) selectionContext.push(st);
  }

  var jinhakCards=[];
  var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0};
  var isJinhakHost=/(^|\.)jinhak\.com$/i.test(location.hostname);
  var jinhakBarSignals=(bodyText.match(/[0-9]{1,2}\s*칸/g)||[]).length;
  var jinhakDeepPage=isJinhakHost && (
    /(?:storage|save|predict|prediction|sapplysample|admitreport|resultreport|score|calc|report)/i.test(location.href) ||
    jinhakBarSignals>=2 ||
    /(?:내\s*순위|예상\s*(?:합격선|컷)|모의지원자\s*수|지원판정|합격안정성)/i.test(bodyText)
  );
  if(jinhakDeepPage){
    var metricRx=/(?:[0-9]{1,2}\s*칸|합격(?:률|확률|가능성)|경쟁률|모의지원|합격예측|지원판정|내\s*순위|모집인원)/i;
    var primaryRx=/(?:[0-9]{1,2}\s*칸|합격(?:률|확률|가능성)|합격예측|지원판정|내\s*순위|예상\s*(?:합격선|컷))/i;
    var exactUniRx=/(?:[가-힣A-Za-z0-9·.()\-]{2,35}(?:대학교|교육대학교|과학기술원))/i;
    var deptRx=/(?:학과|학부|전공|모집단위|자율전공)/i;
    var admissionRx=/(?:지역인재|학생부교과|학생부종합|교과|종합|면접|자기추천|창의인재|학교장추천|고른기회)/i;
    var semanticRx=/(?:^|\s)(?:card|item|result|apply|support|save|univ|college|row)(?:\s|$)/i;
    var metricNodes=document.querySelectorAll('span,em,strong,b,p,td,th,li,div');
    var roots=[];
    function structuredCardText(el,maxLen){
      if(!el) return '';
      var clone=el.cloneNode(true);
      var rm=clone.querySelectorAll('script,style,noscript,template,input,textarea,select,option,form,[type=hidden],[hidden],[aria-hidden=true]');
      for(var ri=0;ri<rm.length;ri++) rm[ri].remove();
      var raw=String(clone.innerText||clone.textContent||'');
      var lines=raw.split(/\n+/).map(function(v){return cleanText(v);}).filter(function(v){return v.length>0;});
      var t=lines.join(' | ').replace(/[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/ig,'[redacted-email]');
      return t.slice(0,maxLen||5000);
    }
    function rootScore(el,text){
      var hits=(text.match(/(?:[0-9]{1,2}\s*칸|합격(?:률|확률|가능성)|경쟁률|모의지원|합격예측|지원판정|내\s*순위|모집인원)/ig)||[]).length;
      var meta=cleanText((el.tagName||'')+' '+(el.id||'')+' '+(el.className||''));
      var score=0;
      if(exactUniRx.test(text)) score+=20;
      if(deptRx.test(text)) score+=12;
      if(admissionRx.test(text)) score+=4;
      if(primaryRx.test(text)) score+=8;
      if(/^(TR|LI|ARTICLE)$/i.test(el.tagName||'')||semanticRx.test(meta)) score+=8;
      if(hits<=4) score+=6; else score-=(hits-4)*7;
      score-=Math.floor(text.length/700);
      return score;
    }
    function overlapIndex(el){
      for(var oi=0;oi<roots.length;oi++){
        var other=roots[oi].el;
        if(other===el||other.contains(el)||el.contains(other)) return oi;
      }
      return -1;
    }
    for(var ji=0;ji<metricNodes.length&&roots.length<120&&jinhakCardStats.metricSeeds<650;ji++){
      var mn=metricNodes[ji];
      if(!visible(mn)) continue;
      var seed=structuredCardText(mn,420);
      if(!metricRx.test(seed)) continue;
      jinhakCardStats.metricSeeds++;
      var cur=mn,bestEl=null,bestText='',bestScore=-9999;
      for(var depth=0;cur&&depth<12;depth++,cur=cur.parentElement){
        if(!visible(cur)) continue;
        var candidate=structuredCardText(cur,5000);
        if(candidate.length<18||candidate.length>4800||!metricRx.test(candidate)) continue;
        if(!(exactUniRx.test(candidate)||deptRx.test(candidate)||admissionRx.test(candidate))) continue;
        var score=rootScore(cur,candidate);
        if(score>bestScore){bestScore=score;bestEl=cur;bestText=candidate;}
      }
      if(!bestEl||bestScore<2) continue;
      jinhakCardStats.candidateRoots++;
      var overlap=overlapIndex(bestEl);
      if(overlap>=0){if(bestScore>roots[overlap].score) roots[overlap]={el:bestEl,text:bestText,score:bestScore};}
      else roots.push({el:bestEl,text:bestText,score:bestScore});
    }
    function explicitUniversityNames(text){
      text=cleanText(text);
      var names=[];
      var full=/([가-힣A-Za-z0-9·.()\-]{2,35}(?:대학교|교육대학교|과학기술원)(?:\[[^\]]{1,12}\])?)/ig;
      var fm;
      while((fm=full.exec(text))!==null){
        var fv=cleanText(fm[1]);
        if(fv && names.indexOf(fv)<0) names.push(fv);
      }
      // Jinhak sometimes renders a university as a short name such as "한밭대".
      // Accept only a concise, explicit token and reject generic college abbreviations.
      var short=/(?:^|[\s|])([가-힣A-Za-z0-9·.()\-]{2,24}대)(?=$|[\s|\[\](),·/])/g;
      var sm;
      var shortNoise=/^(?:공대|의대|법대|상대|교대|사범대|간호대|약대|치대|한의대|철도대)$/;
      while((sm=short.exec(text))!==null){
        var sv=cleanText(sm[1]);
        if(!sv||shortNoise.test(sv)||/(지원|합격|예측|전형|모집|학부|학과)/.test(sv)) continue;
        if(names.indexOf(sv)<0) names.push(sv);
      }
      return names;
    }
    function cleanDepartmentName(value){
      var v=cleanText(value);
      if(!v) return '';
      v=v.replace(/^(?:(?:닫기|열기|보기|상세|선택|삭제)\s*)+/,'');
      v=v.replace(/^(?:지역인재교과|지역인재종합|교과일반|교과중심|자기추천|창의인재\(면접형\)|교과면접|학생부교과|학생부종합|지역인재|학교장추천|고른기회)\s*/,'');
      if(v.length<2||v.length>55) return '';
      if(/(?:등급|경쟁률|합격|예측|지원판정|모집인원|[0-9]{1,2}\s*칸)/.test(v)) return '';
      if(!/(?:학과|학부|전공|자율전공)$/.test(v)) return '';
      return v;
    }
    function explicitDepartmentNames(text){
      text=String(text||'');
      var names=[];
      var parts=text.split('|');
      for(var di=0;di<parts.length;di++){
        var part=cleanText(parts[di]);
        var dm=part.match(/([가-힣A-Za-z0-9·.()&・\- ]{2,48}(?:학과|학부|전공|자율전공))/g)||[];
        for(var dj=0;dj<dm.length;dj++){
          var dv=cleanDepartmentName(dm[dj]);
          if(dv&&names.indexOf(dv)<0) names.push(dv);
        }
      }
      return names;
    }
    function departmentContextFor(el,rootText){
      var direct=explicitDepartmentNames(rootText);
      if(direct.length===1) return {name:direct[0],source:'card-root',depth:0};
      var cur=el;
      for(var depth=0;cur&&depth<8;depth++,cur=cur.parentElement){
        var attrs=cleanText((cur.getAttribute&&cur.getAttribute('aria-label')||'')+' '+(cur.getAttribute&&cur.getAttribute('title')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-dept-name')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-department-name')||''));
        var an=explicitDepartmentNames(attrs);
        if(an.length===1) return {name:an[0],source:'ancestor-attribute',depth:depth};
      }
      return {name:'',source:'missing',depth:-1};
    }

    function universityContextFor(el,rootText){
      var direct=explicitUniversityNames(rootText);
      if(direct.length===1) return {name:direct[0],source:'card-root',depth:0};
      var cur=el;
      for(var depth=0;cur&&depth<9;depth++){
        var attrs=cleanText((cur.getAttribute&&cur.getAttribute('aria-label')||'')+' '+(cur.getAttribute&&cur.getAttribute('title')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-univ-name')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-university-name')||''));
        var an=explicitUniversityNames(attrs);
        if(an.length===1) return {name:an[0],source:'ancestor-attribute',depth:depth};

        var prev=cur.previousElementSibling;
        for(var pi=0;prev&&pi<6;pi++,prev=prev.previousElementSibling){
          if(!visible(prev)) continue;
          var pt=structuredCardText(prev,1000);
          var pn=explicitUniversityNames(pt);
          var pm=cleanText((prev.tagName||'')+' '+(prev.id||'')+' '+(prev.className||''));
          if(pn.length===1 && (pt.length<=260 || /title|tit|name|univ|college|header|head/i.test(pm))){
            return {name:pn[0],source:'preceding-sibling',depth:depth};
          }
          if(depth===0 && primaryRx.test(pt)) break;
        }

        var next=cur.nextElementSibling;
        for(var ni=0;next&&ni<3;ni++,next=next.nextElementSibling){
          if(!visible(next)) continue;
          var nt=structuredCardText(next,700);
          if(primaryRx.test(nt)) break;
          var nn=explicitUniversityNames(nt);
          var nm=cleanText((next.tagName||'')+' '+(next.id||'')+' '+(next.className||''));
          if(nn.length===1 && (nt.length<=180 || /title|tit|name|univ|college|header|head/i.test(nm))){
            return {name:nn[0],source:'following-sibling',depth:depth};
          }
        }

        var parent=cur.parentElement;
        if(!parent) break;
        var parentText=structuredCardText(parent,10000);
        var parentNames=explicitUniversityNames(parentText);
        if(parentNames.length===1){
          return {name:parentNames[0],source:'ancestor-unique',depth:depth+1};
        }
        cur=parent;
      }
      return {name:'',source:'missing',depth:-1};
    }
    for(var jr=0;jr<roots.length&&jinhakCards.length<120;jr++){
      var entry=roots[jr];
      if(!primaryRx.test(entry.text)) continue;
      var universityCtx=universityContextFor(entry.el,entry.text);
      var departmentCtx=departmentContextFor(entry.el,entry.text);
      if(universityCtx.name){
        jinhakCardStats.universityBoundRoots++;
        if(universityCtx.source!=='card-root') jinhakCardStats.universityContextRoots++;
      }else{
        jinhakCardStats.universityMissingRoots++;
      }
      if(departmentCtx.name){
        jinhakCardStats.departmentBoundRoots++;
        if(departmentCtx.source!=='card-root') jinhakCardStats.departmentContextRoots++;
      }else{
        jinhakCardStats.departmentMissingRoots++;
      }
      jinhakCards.push({
        text:entry.text,
        score:entry.score,
        rootTag:String(entry.el.tagName||'').slice(0,20),
        primaryPrediction:true,
        university:universityCtx.name,
        universitySource:universityCtx.source,
        universityDepth:universityCtx.depth,
        department:departmentCtx.name,
        departmentSource:departmentCtx.source,
        departmentDepth:departmentCtx.depth
      });
    }
    jinhakCardStats.uniqueRoots=jinhakCards.length;
  }

  var tables=[];
  var captureHiddenDetail=(isJinhakHost&&jinhakDeepPage) || /\/(?:ucp\/uvt\/uni\/univDetailSelection|uct\/acd\/ade\/criteriaAndResultPopup)\.do$/i.test(location.pathname);
  var maxCapturedTables=(isJinhakHost&&!jinhakDeepPage)?24:120;
  var maxCapturedRows=(isJinhakHost&&!jinhakDeepPage)?100:250;
  var tableNodes=document.querySelectorAll('table,[role=table]');
  for(var ti=0;ti<tableNodes.length && tables.length<maxCapturedTables;ti++){
    var table=tableNodes[ti];
    if(!captureHiddenDetail && !visible(table)) continue;
    var rows=[];
    var trNodes=table.querySelectorAll('tr,[role=row]');
    for(var ri=0;ri<trNodes.length && rows.length<maxCapturedRows;ri++){
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
  var maxCapturedBlocks=(isJinhakHost&&!jinhakDeepPage)?100:300;
  var blockNodes=document.querySelectorAll('article,.card,.item,.result,.list-item,.tbl_row,[class*=result],[class*=admission],[class*=score],[class*=grade],[class*=competition],[class*=apply],dl,section');
  for(var bi=0;bi<blockNodes.length && blocks.length<maxCapturedBlocks;bi++){
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
  var agentActions=[];
  var linkNodes=document.querySelectorAll('a,button,[role=button],[onclick],[data-href],[data-url],[data-link],[data-path]');
  var seenNav={};
  var seenRes={};
  var seenPageAction={};
  var seenAgentAction={};
  var currentParts=location.pathname.split('/').filter(Boolean);
  var prefix=currentParts.slice(0,2).join('/');
  var scriptCandidates=0;
  var paginationAllowed=/\/(?:ucp\/uvt\/uni\/univView|ucp\/cls\/uni\/classUnivView|ucp\/prc\/uni\/admssUnivView|sco\/agu\/univScoScaAnlsView|uct\/acd\/adc\/characteristicsView|uct\/acd\/ueg\/univEtenGuideView|uct\/acd\/ade\/criteriaAndResultView|uct\/acd\/dia\/disabledAdmssView)\.do$/i.test(location.pathname);
  var maxNavigationScan=(isJinhakHost&&!jinhakDeepPage)?1800:5000;
  for(var li=0;li<linkNodes.length&&li<maxNavigationScan;li++){
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

    if(isJinhakHost && agentActions.length<160){
      var agentBlocked=/(원서\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)/i;
      var agentAllowed=/(상세|보기|조회|검색|리포트|대학\s*정보|전형\s*정보|학과\s*정보|합격\s*예측|모의\s*지원|수시\s*저장소|정시\s*저장소|추천\s*대학|성적\s*분석|다음|더보기|결과|탭)/i;
      var role=cleanText(a.getAttribute('role')||'');
      var dynamicControl=!route || role==='tab' || a.tagName==='BUTTON';
      if(dynamicControl && label && !agentBlocked.test(label+' '+meta2) && agentAllowed.test(label)){
        var ak=li+'|'+label+'|'+String(a.tagName||'')+'|'+role;
        if(!seenAgentAction[ak]){
          agentActions.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:role==='tab'?'tab-navigation':'read-navigation'});
          seenAgentAction[ak]=1;
        }
      }
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
    var ch=String(location.hostname||'').toLowerCase();
    var rh=String(ru.hostname||'').toLowerCase();
    var sameJinhakProvider=(ch==='jinhak.com'||/\.jinhak\.com$/.test(ch)) && (rh==='jinhak.com'||/\.jinhak\.com$/.test(rh));
    if(ru.origin!==location.origin && !sameJinhakProvider) continue;
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
    discovery:{navigationLinks:nav.length,resourceLinks:resources.length,scriptRoutes:scriptCandidates,pageActions:pageActions.length,agentActions:agentActions.length,jinhakDeepPage:jinhakDeepPage},
    context:context,
    selectionContext:selectionContext,
    jinhakCards:jinhakCards,
    jinhakCardStats:jinhakCardStats,
    tables:tables,
    blocks:blocks,
    navigationLinks:nav,
    pageActions:pageActions,
    agentActions:agentActions,
    resourceLinks:resources
  });
})();
    """.trimIndent()
}
