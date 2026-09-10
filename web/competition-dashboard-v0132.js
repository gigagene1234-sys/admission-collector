const $=id=>document.getElementById(id);
const BASE='/api/worker';
const ORDER=['knut','woosong','hanbat','hannam','koreatech','kongju'];
const STORE='admissionCompetitionInterestsV0132';
const MAX_PER_UNIVERSITY=4;
let statusData={targets:[]};
let latestData={targets:[]};
let decoratedById={};
let selectedId='woosong';
let autoRefresh=true;
let timer=null;
let interests=loadInterests();

function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function num(v){return Number.isFinite(Number(v))?Number(v).toLocaleString('ko-KR'):'—';}
function ratio(v){return Number.isFinite(Number(v))?Number(v).toFixed(2)+':1':'—';}
function time(v){if(!v)return'—';const d=new Date(v);return Number.isNaN(d.getTime())?String(v):d.toLocaleString('ko-KR',{timeZone:'Asia/Seoul',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'});}
function loadInterests(){try{const x=JSON.parse(localStorage.getItem(STORE)||'{}');return x&&typeof x==='object'?x:{};}catch{return {};}}
function saveInterests(){localStorage.setItem(STORE,JSON.stringify(interests));}
function interestList(id){return Array.isArray(interests[id])?interests[id]:[];}
function totalInterests(){return Object.values(interests).reduce((n,a)=>n+(Array.isArray(a)?a.length:0),0);}
function latestFor(id){return (latestData.targets||[]).find(x=>x.targetId===id)||{targetId:id,snapshot:null,rows:[]};}
function statusFor(id){return (statusData.targets||[]).find(x=>x.targetId===id)||null;}
async function api(action){const r=await fetch(BASE+'?action='+encodeURIComponent(action),{headers:{Accept:'application/json'},cache:'no-store'});let body={};try{body=await r.json();}catch{}if(!r.ok)throw new Error(body.error||('HTTP '+r.status));return body;}
function closeEnough(a,b){return Number.isFinite(Number(a))&&Number.isFinite(Number(b))&&Math.abs(Number(a)-Number(b))<=0.015;}
function isSubtotal(r){return /소계/.test(String(r?.department||''));}
function isTotal(r){return /^(?:총계|소계|정원내 소계|정원외 소계)$/.test(String(r?.department||'').trim());}
function rowKey(r){return `${r._application||r.admission||''}¦${r.department||''}`;}

// Uway competition pages place a compact per-admission overview before detailed rows.
// Detailed blocks terminate in a subtotal whose quota/applicants/ratio match the overview row.
// Restore only a DISPLAY admission label from that structural match; never mutate source rows.
function decorateRows(sourceRows){
  const rows=(sourceRows||[]).map((r,i)=>({...r,_index:i,_application:null,_aggregate:false}));
  const subtotals=[];
  rows.forEach((r,i)=>{if(isSubtotal(r))subtotals.push(i);});
  let blockStart=null;
  for(const end of subtotals){
    const subtotal=rows[end];
    let matched=-1;
    const searchEnd=blockStart==null?end:blockStart;
    for(let i=0;i<searchEnd;i++){
      const r=rows[i];
      if(isTotal(r))continue;
      if(Number(r.quota)===Number(subtotal.quota)&&Number(r.applicants)===Number(subtotal.applicants)&&closeEnough(r.ratio,subtotal.ratio))matched=i;
    }
    if(blockStart==null)blockStart=matched>=0?matched+1:0;
    let label=null;
    matched=-1;
    for(let i=0;i<blockStart;i++){
      const r=rows[i];
      if(isTotal(r))continue;
      if(Number(r.quota)===Number(subtotal.quota)&&Number(r.applicants)===Number(subtotal.applicants)&&closeEnough(r.ratio,subtotal.ratio)){
        matched=i;
        label=String(r.department||'').trim()||null;
      }
    }
    if(label){for(let i=blockStart;i<=end;i++)rows[i]._application=label;}
    rows[end]._aggregate=true;
    blockStart=end+1;
  }
  const detail=new Set();
  rows.forEach((r,i)=>{if(r._application&&!isTotal(r))detail.add(i);});
  rows.forEach((r,i)=>{if(!detail.has(i)||isTotal(r))r._aggregate=true;});
  return rows;
}

function rebuildDecorated(){decoratedById={};for(const id of ORDER)decoratedById[id]=decorateRows(latestFor(id).rows||[]);}
function state(status,latest){if(status?.lastError)return['오류','bad'];if(latest?.snapshot)return['스냅샷 확보','ok'];if(status?.requiresUserBrowser)return['브라우저 관측 대기','wait'];return['수집 대기','info'];}
function currentInterestRow(id,item){return (decoratedById[id]||[]).find(r=>!r._aggregate&&rowKey(r)===item.key)||null;}

function addInterest(index){
  const r=(decoratedById[selectedId]||[])[index];
  if(!r||r._aggregate||!r._application)return;
  const list=interestList(selectedId),key=rowKey(r);
  if(list.some(x=>x.key===key)||list.length>=MAX_PER_UNIVERSITY)return;
  list.push({key,application:r._application,department:r.department,quota:r.quota,applicants:r.applicants,ratio:r.ratio,savedAt:new Date().toISOString()});
  interests[selectedId]=list;saveInterests();renderAll();
}
function removeInterest(key){interests[selectedId]=interestList(selectedId).filter(x=>x.key!==key);if(!interests[selectedId].length)delete interests[selectedId];saveInterests();renderAll();}

function renderSummary(){
  const ready=(latestData.targets||[]).filter(x=>x.snapshot).length;
  const errors=(statusData.targets||[]).filter(x=>x.lastError).length;
  $('summaryBadge').textContent=errors?`오류 ${errors}개`:`${ready}/6 스냅샷 확보 · 관심 ${totalInterests()}개`;
  $('summaryBadge').className='badge '+(errors?'bad':ready===6?'ok':'info');
}
function renderCards(){
  const root=$('targets');
  const statuses=[...(statusData.targets||[])].sort((a,b)=>ORDER.indexOf(a.targetId)-ORDER.indexOf(b.targetId));
  if(!statuses.length){root.innerHTML='<div class="empty wide">수집 상태를 불러오지 못했습니다.</div>';return;}
  root.innerHTML=statuses.map(s=>{
    const latest=latestFor(s.targetId),rows=latest.rows||[],snap=latest.snapshot,st=state(s,latest),count=interestList(s.targetId).length;
    const mode=s.requiresUserBrowser?'Android WebView 관측':'서버 공개페이지 수집';
    return `<article class="card target ${selectedId===s.targetId?'selected':''}" data-id="${esc(s.targetId)}">
      <div class="target-head"><div><h3>${esc(s.university)}</h3><div class="sub">${esc(s.provider)}</div></div><span class="badge ${st[1]}">${st[0]}</span></div>
      <div class="target-meta"><div class="metric"><span>최신 전체 행</span><b>${snap?num(rows.length):'—'}</b></div><div class="metric"><span>관심 원서</span><b>${count} / 4</b></div><div class="metric"><span>갱신 주기</span><b>${num(s.refreshMinutes)}분</b></div><div class="metric"><span>원문 기준</span><b>${esc(time(s.lastSourceUpdatedAt||snap?.source_updated_at))}</b></div></div>
      <div class="source-line"><span class="badge source">${esc(s.provider)}</span><span class="sub">${mode}</span></div>
    </article>`;
  }).join('');
  root.querySelectorAll('.target').forEach(el=>el.onclick=()=>{selectedId=el.dataset.id;$('searchBox').value='';$('admissionFilter').value='';renderAll();});
}
function renderInterests(){
  const s=statusFor(selectedId),latest=latestFor(selectedId),list=interestList(selectedId);
  $('interestTitle').textContent=(s?.university||latest.university||'대학')+' · 관심 원서';
  $('interestCount').textContent=list.length+' / 4';
  $('interestList').innerHTML=list.length?list.map(item=>{
    const cur=currentInterestRow(selectedId,item);
    return `<div class="interest-item"><span class="badge source">${esc(item.application)}</span><h4>${esc(item.department)}</h4><div class="sub">저장 당시 ${ratio(item.ratio)} · 현재 ${cur?ratio(cur.ratio):'—'}</div><div class="sub" style="margin-top:4px">현재 ${cur?num(cur.quota):'—'}명 모집 / ${cur?num(cur.applicants):'—'}명 지원</div><div class="interest-actions"><button class="btn" data-remove="${esc(item.key)}">삭제</button></div></div>`;
  }).join(''):'<div class="empty wide">아래 전체 경쟁률에서 관심 전형·학과를 저장하세요.</div>';
  $('interestList').querySelectorAll('[data-remove]').forEach(b=>b.onclick=()=>removeInterest(b.dataset.remove));
}
function renderTable(){
  const s=statusFor(selectedId),latest=latestFor(selectedId),snap=latest.snapshot,rows=decoratedById[selectedId]||[];
  $('tableTitle').textContent=(s?.university||latest.university||'대학')+' · 최신 경쟁률 전체';
  $('tableMeta').textContent=snap?`스냅샷 #${snap.id} · 수집 ${time(snap.collected_at)} · 원문 ${time(snap.source_updated_at)} · ${s?.provider||snap.provider||'출처 미상'}`:(s?.requiresUserBrowser?'아직 Android WebView 공개표 관측 스냅샷이 없습니다.':'아직 저장된 경쟁률 스냅샷이 없습니다.');
  const applications=[...new Set(rows.map(r=>r._application).filter(Boolean))];
  const select=$('admissionFilter'),old=select.value;
  select.innerHTML='<option value="">전체 전형</option>'+applications.map(a=>`<option value="${esc(a)}">${esc(a)}</option>`).join('');
  if(applications.includes(old))select.value=old;
  const q=$('searchBox').value.trim().toLowerCase(),f=select.value,kind=$('kindFilter').value;
  const filtered=rows.filter(r=>(!f||r._application===f)&&(!q||[r._application,r.admission,r.department].some(v=>String(v||'').toLowerCase().includes(q)))&&(!kind||(kind==='detail'?!r._aggregate:r._aggregate)));
  $('rowBadge').textContent=(q||f||kind?filtered.length+' / ':'')+rows.length+'행';
  if(!snap||!rows.length){$('tableArea').innerHTML=`<div class="empty">${s?.requiresUserBrowser?'사용자 브라우저 관측 대기 중입니다.':'표시할 최신 경쟁률 행이 없습니다.'}</div>`;return;}
  $('tableArea').innerHTML=`<table class="data-table"><thead><tr><th>#</th><th>구분</th><th>전형</th><th>모집단위 / 학과</th><th style="text-align:right">모집인원</th><th style="text-align:right">지원인원</th><th style="text-align:right">경쟁률</th><th>관심 원서</th></tr></thead><tbody>${filtered.map(r=>{
    const key=rowKey(r),saved=interestList(selectedId).some(x=>x.key===key),full=interestList(selectedId).length>=MAX_PER_UNIVERSITY&&!saved,canSave=!r._aggregate&&!!r._application;
    return `<tr class="${r._aggregate?'aggregate':saved?'saved-row':''}"><td>${num(r.row_ordinal||r._index+1)}</td><td><span class="kind">${r._aggregate?'합계/요약':'모집단위'}</span></td><td>${esc(r._application||r.admission||'—')}</td><td>${esc(r.department||'—')}</td><td class="num">${num(r.quota)}</td><td class="num">${num(r.applicants)}</td><td class="num"><strong>${ratio(r.ratio)}</strong></td><td>${canSave?`<button class="btn ${saved?'saved':'save'}" data-add="${r._index}" ${saved||full?'disabled':''}>${saved?'저장됨':full?'4개 저장 완료':'관심 원서 저장'}</button>`:'—'}</td></tr>`;
  }).join('')}</tbody></table>`;
  $('tableArea').querySelectorAll('[data-add]').forEach(b=>b.onclick=()=>addInterest(Number(b.dataset.add)));
}
function renderAll(){renderSummary();renderCards();renderInterests();renderTable();}

async function refresh(){
  const btn=$('refreshBtn');btn.disabled=true;btn.textContent='불러오는 중';
  try{
    const [health,status,latest]=await Promise.all([api('health'),api('competition_status'),api('competition_latest')]);
    statusData=status;latestData=latest;rebuildDecorated();
    $('healthText').textContent='API 연결 정상';$('healthBadge').className='badge ok';$('healthDot').className='dot on';
    if(!statusFor(selectedId)&&statusData.targets?.length)selectedId=statusData.targets[0].targetId;
    renderAll();
  }catch(error){
    $('healthText').textContent='API 연결 오류';$('healthBadge').className='badge bad';$('healthDot').className='dot';$('summaryBadge').textContent='API 확인 필요';$('summaryBadge').className='badge bad';console.error(error);
  }finally{btn.disabled=false;btn.textContent='지금 새로고침';}
}
$('refreshBtn').onclick=refresh;
$('searchBox').oninput=renderTable;
$('admissionFilter').onchange=renderTable;
$('kindFilter').onchange=renderTable;
$('autoBtn').onclick=()=>{autoRefresh=!autoRefresh;$('autoBtn').textContent='자동갱신 60초 · '+(autoRefresh?'ON':'OFF');if(timer)clearInterval(timer);timer=autoRefresh?setInterval(refresh,60000):null;};
refresh();
timer=setInterval(refresh,60000);
