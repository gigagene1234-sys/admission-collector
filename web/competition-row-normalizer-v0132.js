(function(root){
  function closeEnough(a,b){return Number.isFinite(Number(a))&&Number.isFinite(Number(b))&&Math.abs(Number(a)-Number(b))<=0.015;}
  function marker(r){const d=String(r&&r.department||'').trim();return d==='총계'||/소계/.test(d);}
  function signature(r){if(r==null)return null;const q=Number(r.quota),a=Number(r.applicants),x=Number(r.ratio);return Number.isFinite(q)&&Number.isFinite(a)&&Number.isFinite(x)?`${q}|${a}|${x.toFixed(2)}`:null;}
  function decorateRows(sourceRows){
    const rows=(sourceRows||[]).map((r,i)=>({...r,_index:i,_application:null,_aggregate:true}));
    const subtotalIndexes=[];
    rows.forEach((r,i)=>{if(/소계/.test(String(r.department||'')))subtotalIndexes.push(i);});
    const detailSubtotals=subtotalIndexes.filter(end=>{
      const sig=signature(rows[end]);
      return sig&&rows.slice(0,end).some(r=>!marker(r)&&signature(r)===sig);
    });
    if(!detailSubtotals.length)return rows;

    const firstDetailSubtotal=detailSubtotals[0];
    const overviewMarkers=[];
    rows.slice(0,firstDetailSubtotal).forEach((r,i)=>{if(marker(r))overviewMarkers.push(i);});
    let blockStart=overviewMarkers.length?overviewMarkers[overviewMarkers.length-1]+1:0;
    const overview=rows.slice(0,blockStart);
    let previousOverviewIndex=-1;

    for(const end of detailSubtotals){
      if(end<blockStart)continue;
      const sig=signature(rows[end]);
      const matches=[];
      overview.forEach((r,i)=>{if(!marker(r)&&signature(r)===sig)matches.push(i);});
      const monotonic=matches.filter(i=>i>previousOverviewIndex);
      const match=monotonic.length?monotonic[0]:(matches.length===1?matches[0]:null);
      if(match==null){blockStart=end+1;continue;}
      previousOverviewIndex=match;
      const label=String(overview[match].department||'').trim();
      if(label){
        for(let i=blockStart;i<end;i++){
          rows[i]._application=label;
          rows[i]._aggregate=false;
        }
        rows[end]._application=label;
      }
      rows[end]._aggregate=true;
      blockStart=end+1;
    }
    return rows;
  }
  const api={decorateRows};
  root.CompetitionRowNormalizer=api;
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
