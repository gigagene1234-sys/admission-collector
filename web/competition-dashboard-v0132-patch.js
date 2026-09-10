if(typeof CompetitionRowNormalizer!=='undefined'&&CompetitionRowNormalizer.decorateRows){
  decorateRows=CompetitionRowNormalizer.decorateRows;
  if(typeof rebuildDecorated==='function')rebuildDecorated();
  if(typeof renderAll==='function'&&statusData&&Array.isArray(statusData.targets)&&statusData.targets.length)renderAll();
}
