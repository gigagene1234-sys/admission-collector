(function(){
  if (window.__wsuAiUiLoaded) return;
  window.__wsuAiUiLoaded = true;

  var style=document.createElement('style');
  style.textContent='.wsu-ai-open{position:fixed;right:18px;bottom:18px;z-index:120;border:0;border-radius:999px;padding:12px 16px;background:#6ba7ff;color:#fff;font-weight:900;box-shadow:0 12px 35px rgba(0,0,0,.3)}.wsu-ai-panel{position:fixed;right:18px;bottom:76px;z-index:121;width:min(430px,calc(100vw - 28px));max-height:78vh;overflow:auto;background:var(--panel,#0d1728);color:var(--text,#f5f7fb);border:1px solid var(--line,rgba(255,255,255,.12));border-radius:18px;padding:16px;box-shadow:0 20px 60px rgba(0,0,0,.38);display:none}.wsu-ai-panel.open{display:block}.wsu-ai-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start;margin-bottom:12px}.wsu-ai-head h3{margin:2px 0 0;font-size:16px}.wsu-ai-close{border:0;background:transparent;color:inherit;font-size:22px}.wsu-ai-meta{font-size:11px;color:var(--muted,#9ba9bd);margin-bottom:10px}.wsu-ai-evidence{display:grid;gap:7px;margin:8px 0 12px}.wsu-ai-evidence label{display:grid;grid-template-columns:auto 1fr;gap:8px;align-items:start;padding:9px;border:1px solid var(--line,rgba(255,255,255,.12));border-radius:12px;background:var(--panel-2,#111e32)}.wsu-ai-evidence small{display:block;color:var(--muted,#9ba9bd)}.wsu-ai-panel textarea{width:100%;min-height:84px;resize:vertical;border:1px solid var(--line,rgba(255,255,255,.12));border-radius:12px;background:var(--panel-2,#111e32);color:inherit;padding:10px}.wsu-ai-actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:10px}.wsu-ai-actions button{border:1px solid var(--line,rgba(255,255,255,.12));border-radius:11px;padding:9px 11px;background:var(--panel-3,#16243a);color:inherit;font-weight:800}.wsu-ai-actions .primary{background:#6ba7ff;color:#fff;border-color:transparent}.wsu-ai-result{margin-top:12px;display:grid;gap:9px}.wsu-ai-box{border:1px solid var(--line,rgba(255,255,255,.12));border-radius:12px;padding:10px;background:var(--panel-2,#111e32);white-space:pre-wrap}.wsu-ai-box b{display:block;margin-bottom:5px;font-size:11px;color:#8dd6c8}.wsu-ai-error{color:#ff8c8c;font-size:12px;margin-top:8px}.wsu-ai-status{font-size:11px;color:var(--muted,#9ba9bd);margin-top:8px}@media(max-width:640px){.wsu-ai-open{right:12px;bottom:12px}.wsu-ai-panel{right:7px;bottom:66px;width:calc(100vw - 14px);max-height:80vh}}';
  document.head.appendChild(style);

  var btn=document.createElement('button');
  btn.className='wsu-ai-open';
  btn.textContent='AI 답안 수정';
  document.body.appendChild(btn);

  var panel=document.createElement('section');
  panel.className='wsu-ai-panel';
  panel.innerHTML='<div class="wsu-ai-head"><div><div class="eyebrow">GLM + LLAMA REVIEW</div><h3>선택 근거로 수정안 만들기</h3></div><button class="wsu-ai-close" aria-label="닫기">×</button></div><div id="wsuAiBody"></div>';
  document.body.appendChild(panel);
  panel.querySelector('.wsu-ai-close').onclick=function(){panel.classList.remove('open');};

  var lastResult=null;
  var activeQid=null;

  function currentQid(){
    if (Number(window.__selectedQuestionId)) return Number(window.__selectedQuestionId);
    var el=document.querySelector('.question-card.open[id^="qcard-"]');
    if(el){var m=el.id.match(/qcard-(\d+)/);if(m)return Number(m[1]);}
    return null;
  }

  function safe(v){
    return String(v==null?'':v).replace(/[&<>"']/g,function(ch){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch];
    });
  }

  function recById(id){return STUDENT_RECORDS.find(function(r){return String(r.id)===String(id);});}

  function refsFor(qid){
    return (QUESTION_RECORD_MAP[qid]||[]).map(function(x){
      return {ref:x,record:recById(x.record)};
    }).filter(function(x){return x.record;});
  }

  function render(){
    activeQid=currentQid();
    var root=document.getElementById('wsuAiBody');
    lastResult=null;

    if(!activeQid){
      root.innerHTML='<div class="wsu-ai-box">먼저 왼쪽 「면접 문항」에서 수정할 질문을 선택하세요.</div>';
      return;
    }

    var q=QUESTIONS[activeQid-1];
    var refs=refsFor(activeQid);
    var savedIds=[];
    try{savedIds=JSON.parse(localStorage.getItem('wsu-ai-records-'+activeQid)||'[]');}catch(e){}
    var defaultIds=refs.filter(function(x){return x.ref.usage==='본문';}).map(function(x){return String(x.record.id);});
    var selected=savedIds.length?savedIds:defaultIds;
    var instruction=localStorage.getItem('wsu-ai-instruction-'+activeQid)||'';

    var evidenceHtml=refs.length?refs.map(function(x){
      var r=x.record;
      var checked=selected.indexOf(String(r.id))>=0?' checked':'';
      return '<label><input type="checkbox" value="'+safe(r.id)+'"'+checked+'><span><strong>'+safe(r.subject||r.title)+'</strong><small>'+safe(x.ref.usage||'후보')+' · '+safe(r.title||'')+' · '+safe(r.sourceLabel||r.sourceKind||'')+'</small></span></label>';
    }).join(''):'<div class="wsu-ai-box">이 문항에 연결된 생기부 근거가 없습니다. 현재 답안과 수정 의견만으로 첨삭합니다.</div>';

    root.innerHTML='<div class="wsu-ai-meta">Q'+activeQid+' · '+safe(q.question)+'</div>'+
      '<div><b style="font-size:12px">사용할 생기부 근거</b><div class="wsu-ai-evidence">'+evidenceHtml+'</div></div>'+
      '<div><b style="font-size:12px">수정 의견</b><textarea id="wsuAiInstruction" placeholder="예: 핵심은 유지하고 더 자연스럽게, 과장 없이 다듬어줘.">'+safe(instruction)+'</textarea></div>'+
      '<div class="wsu-ai-actions"><button class="primary" id="wsuAiGenerate">수정안 만들기</button></div>'+
      '<div id="wsuAiState" class="wsu-ai-status"></div><div id="wsuAiResult" class="wsu-ai-result"></div>';

    document.getElementById('wsuAiGenerate').onclick=generate;
  }

  async function generate(){
    var qid=activeQid||currentQid();
    if(!qid)return;
    var q=QUESTIONS[qid-1];
    var instruction=document.getElementById('wsuAiInstruction').value.trim();
    var ids=Array.prototype.slice.call(panel.querySelectorAll('.wsu-ai-evidence input[type=checkbox]:checked')).map(function(el){return String(el.value);});
    localStorage.setItem('wsu-ai-records-'+qid,JSON.stringify(ids));
    localStorage.setItem('wsu-ai-instruction-'+qid,instruction);

    var records=ids.map(recById).filter(Boolean).map(function(r){
      return {id:r.id,atlasId:r.atlasId||'',subject:r.subject||'',title:r.title||'',sourceKind:r.sourceKind||'',sourceLabel:r.sourceLabel||'',summary:r.summary||'',fullText:r.fullText||'',limits:r.limits||''};
    });

    var state=document.getElementById('wsuAiState');
    var out=document.getElementById('wsuAiResult');
    state.textContent='AI가 근거와 위험도를 확인하고 있습니다…';
    out.innerHTML='';

    try{
      var res=await fetch('/api/rewrite',{
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({
          question:{id:q.id,text:q.question,target:q.target,method:q.method,risk:q.risk},
          currentAnswer:getAnswer(q),
          userInstruction:instruction,
          records:records
        })
      });
      var data=await res.json();
      if(!res.ok) throw new Error(data.error||'수정안 생성 실패');

      lastResult=data;
      state.textContent='검토 경로: '+(data.reviewPath||[]).join(' → ')+' · 위험도 '+((data.risk&&data.risk.level)||'미표기');
      out.innerHTML='<div class="wsu-ai-box"><b>의견 검토</b>'+safe(data.assessment||'')+'</div>'+
        '<div class="wsu-ai-box"><b>주의사항</b>'+safe(data.caution||'없음')+'</div>'+
        '<div class="wsu-ai-box"><b>새 전체 답안</b>'+safe(data.revisedAnswer||'')+'</div>'+
        '<div class="wsu-ai-actions"><button class="primary" id="wsuAiApply">이 수정안 적용</button></div>';
      document.getElementById('wsuAiApply').onclick=applyResult;
    }catch(e){
      state.textContent='';
      out.innerHTML='<div class="wsu-ai-error">'+safe(e.message||e)+'</div>';
    }
  }

  function applyResult(){
    var qid=activeQid||currentQid();
    if(!qid||!lastResult||!lastResult.revisedAnswer)return;
    appState.answers[qid]=lastResult.revisedAnswer;
    saveState();
    if(typeof renderFocusedQuestion==='function' && QUESTIONS[qid-1]) renderFocusedQuestion(QUESTIONS[qid-1]);
    else if(typeof drawQuestionList==='function') drawQuestionList();
    if(typeof toast==='function') toast('AI 수정안을 현재 답안에 적용했습니다.');
    panel.classList.remove('open');
  }

  btn.onclick=function(){
    render();
    panel.classList.add('open');
  };
})();