from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / "app/src/main/java/com/admissionhub/collector/competition/CompetitionBrowserCollector.kt"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


text = PATH.read_text(encoding="utf-8")

text = replace_once(
    text,
    """                function at(a,i){return i>=0&&i<a.length?a[i]:null;}\n""",
    """                function at(a,i){return i>=0&&i<a.length?a[i]:null;}\n                function countsMatch(q,a,r){\n                  if(q===null||a===null||r===null)return true;\n                  if(q===0)return a===0&&Math.abs(r)<=0.005;\n                  return Math.abs((a/q)-r)<=0.015;\n                }\n""",
    "counts consistency helper",
)

old = """                  var admission=label(at(cells,currentHeader?currentHeader.admission:-1))||label(section);\n                  var department=label(at(cells,currentHeader?currentHeader.department:-1));\n                  var quota=integer(at(cells,currentHeader?currentHeader.quota:-1));\n                  var applicants=integer(at(cells,currentHeader?currentHeader.applicants:-1));\n                  if(!department){\n                    var texts=cells.slice(0,ri).filter(function(c){return !numeric(c);});\n                    if(texts.length)department=label(texts[texts.length-1]);\n                    if(!admission&&texts.length>1)admission=label(texts[texts.length-2]);\n                  }\n                  if(quota===null||applicants===null){\n                    var nums=cells.slice(0,ri).map(integer).filter(function(x){return x!==null;});\n                    if(nums.length>=2){if(quota===null)quota=nums[nums.length-2];if(applicants===null)applicants=nums[nums.length-1];}\n                  }\n                  if(!department&&quota===null&&applicants===null)return;\n"""
new = """                  var before=cells.slice(0,ri);\n                  var ints=[];\n                  before.forEach(function(c,i){var v=integer(c);if(v!==null)ints.push({i:i,v:v});});\n                  var quota=null,applicants=null,tail=ri;\n                  if(ints.length>=2){\n                    quota=ints[ints.length-2].v;\n                    applicants=ints[ints.length-1].v;\n                    tail=ints[ints.length-2].i;\n                  }else{\n                    quota=integer(at(cells,currentHeader?currentHeader.quota:-1));\n                    applicants=integer(at(cells,currentHeader?currentHeader.applicants:-1));\n                  }\n                  var texts=before.slice(0,tail).filter(function(c){return !numeric(c);});\n                  var department=texts.length?label(texts[texts.length-1]):label(at(cells,currentHeader?currentHeader.department:-1));\n                  var admission=label(section);\n                  var indexedAdmission=label(at(cells,currentHeader?currentHeader.admission:-1));\n                  if(indexedAdmission&&indexedAdmission!==department)admission=indexedAdmission;\n                  else if(!admission&&texts.length>1)admission=label(texts[texts.length-2]);\n                  if(!countsMatch(quota,applicants,r))return;\n                  if(!department&&quota===null&&applicants===null)return;\n"""
text = replace_once(text, old, new, "right aligned DOM parser")

old_time = """                var sourceUpdatedAt=null;\n                var dm=body.match(/(20\\d{2})\\s*[.\\/-]\\s*(\\d{1,2})\\s*[.\\/-]\\s*(\\d{1,2})[^\\d]{0,40}(\\d{1,2})\\s*:\\s*(\\d{2})/)||body.match(/(20\\d{2})\\s*년\\s*(\\d{1,2})\\s*월\\s*(\\d{1,2})\\s*일[^\\d]{0,40}(\\d{1,2})\\s*:\\s*(\\d{2})/);\n                if(dm){sourceUpdatedAt=dm[1]+'-'+String(dm[2]).padStart(2,'0')+'-'+String(dm[3]).padStart(2,'0')+'T'+String(dm[4]).padStart(2,'0')+':'+dm[5]+':00+09:00';}\n"""
new_time = """                var sourceUpdatedAt=null;\n                var datePattern='(20\\\\d{2})\\\\s*[.\\\\/-]\\\\s*(\\\\d{1,2})\\\\s*[.\\\\/-]\\\\s*(\\\\d{1,2})[^\\\\d]{0,20}(\\\\d{1,2})\\\\s*:\\\\s*(\\\\d{2})';\n                var dm=body.match(new RegExp('(?:업데이트|갱신|기준|현재)[^0-9]{0,30}'+datePattern,'i'))||body.match(new RegExp(datePattern+'[^가-힣A-Za-z0-9]{0,20}(?:업데이트|갱신|기준|현재)','i'));\n                if(dm){\n                  var offset=dm.length>6?dm.length-5:1;\n                  sourceUpdatedAt=dm[offset]+'-'+String(dm[offset+1]).padStart(2,'0')+'-'+String(dm[offset+2]).padStart(2,'0')+'T'+String(dm[offset+3]).padStart(2,'0')+':'+dm[offset+4]+':00+09:00';\n                }\n"""
text = replace_once(text, old_time, new_time, "timestamp context restriction")

PATH.write_text(text, encoding="utf-8")
print("competition browser DOM parser v3 patch applied or already present")
