package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject

object JinhakAgentNavigator {
    data class Candidate(
        val scanIndex: Int,
        val label: String,
        val tag: String,
        val kind: String,
        val missionPriority: Int,
        val contextText: String,
        val applicationContext: JinhakApplicationMission.Context?
    )

    fun candidates(snapshot: JSONObject): List<Candidate> {
        val array = snapshot.optJSONArray("agentActions") ?: JSONArray()
        val route = snapshot.optString("url")
        val out = mutableListOf<Candidate>()
        for (i in 0 until minOf(array.length(), 160)) {
            val obj = array.optJSONObject(i) ?: continue
            val scanIndex = obj.optInt("scanIndex", -1)
            val label = obj.optString("label").replace(Regex("\\s+"), " ").trim().take(120)
            val tag = obj.optString("tag").take(24)
            val kind = obj.optString("kind", "read-navigation").take(40)
            val contextText = obj.optString("contextText")
                .replace(Regex("\\s+"), " ").trim().take(2400)
            if (scanIndex < 0 || label.isBlank()) continue
            if (!isSafeReadNavigationLabel(label)) continue
            val app = JinhakApplicationMission.parseCard(contextText)
            var priority = JinhakSiteTopology.priority(route, label)
            if (app?.identityKey != null) priority += 14
            if (app != null && Regex("(리포트|실제\\s*합격자|모의\\s*지원|합격\\s*예측)").containsMatchIn(label)) priority += 8
            // v0.8.3 discovered mission-bound anchors but executed none. Prefer them over
            // generic same-page controls while preserving the same-card Gate-A identity.
            if (kind == "mission-link-navigation" && app?.identityKey != null) priority += 35
            out += Candidate(scanIndex, label, tag, kind, priority.coerceIn(0, 160), contextText, app)
        }
        return out.sortedWith(
            compareByDescending<Candidate> { it.kind == "mission-link-navigation" && it.applicationContext?.identityKey != null }
                .thenByDescending { it.applicationContext?.identityKey != null }
                .thenByDescending { it.missionPriority }
                .thenBy { it.scanIndex }
        )
    }

    fun key(safeRoute: String, candidate: Candidate): String = RecordUtils.sha256(
        listOf(
            safeRoute,
            candidate.scanIndex.toString(),
            candidate.label,
            candidate.tag,
            candidate.kind,
            candidate.missionPriority.toString(),
            candidate.applicationContext?.identityKey ?: RecordUtils.sha256(candidate.contextText.take(1200))
        ).joinToString("|")
    )

    fun executionScript(candidate: Candidate): String {
        val expected = JSONObject.quote(candidate.label)
        val university = JSONObject.quote(candidate.applicationContext?.university.orEmpty().take(80))
        val department = JSONObject.quote(candidate.applicationContext?.departmentRaw.orEmpty().take(120))
        val admission = JSONObject.quote(candidate.applicationContext?.admission.orEmpty().take(100))
        val requiresSameCard = candidate.applicationContext?.identityKey != null
        return """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0&&r.height>0;
              }
              function clean(v){return String(v||'').replace(/\s+/g,' ').trim();}
              var expected=$expected, uni=$university, dept=$department, adm=$admission;
              var requireSameCard=${if (requiresSameCard) "true" else "false"};
              var blocked=/(원서\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)/i;
              var allowed=/(실제\s*합격자|과거\s*입시결과|입시\s*결과|합격\s*예측\s*리포트|모의\s*지원\s*리포트|지원자\s*분포|대학.?학과별\s*합격\s*예측|합격\s*안정성|상세|보기|조회|검색|리포트|대학\s*정보|전형\s*정보|학과\s*정보|합격\s*예측|모의\s*지원|수시\s*저장소|정시\s*저장소|추천\s*대학|성적\s*분석|성적\s*산출|입시\s*전략|입시\s*지식|경쟁률|모집\s*요강|다음|더보기|결과|탭)/i;
              var nodes=document.querySelectorAll('a,button,[role=button],[role=tab],[onclick],[data-href],[data-url],[data-link],[data-path]');
              function labelOf(el){return clean(el&& (el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')||'')).slice(0,120);}
              function sameCard(el){
                if(!requireSameCard) return true;
                var cur=el;
                for(var d=0;cur&&d<10;d++,cur=cur.parentElement){
                  var t=clean(cur.innerText||cur.textContent||'').slice(0,6000);
                  var okUni=!uni||t.indexOf(uni)>=0;
                  var okDept=!dept||t.indexOf(dept)>=0;
                  var okAdm=!adm||t.indexOf(adm)>=0;
                  if(okUni&&okDept&&okAdm) return true;
                }
                return false;
              }
              function tryClick(el,resolution){
                if(!el) return null;
                if(!visible(el)) return {ok:false,reason:'hidden',resolution:resolution};
                var lab=labelOf(el);
                if(lab!==expected) return {ok:false,reason:'label-changed',resolution:resolution,observedLabel:lab};
                if(blocked.test(lab)||!allowed.test(lab)) return {ok:false,reason:'policy-block',resolution:resolution};
                if(!sameCard(el)) return {ok:false,reason:'same-card-context-mismatch',resolution:resolution};
                try{
                  var before=location.href;
                  el.click();
                  return {ok:true,label:lab,before:before===location.href?'same-document':'navigation-started',resolution:resolution,matchedSameCard:requireSameCard};
                }catch(e){return {ok:false,reason:'click-failed',resolution:resolution};}
              }
              var primary=tryClick(nodes[${candidate.scanIndex}], 'scan-index');
              if(primary&&primary.ok) return JSON.stringify(primary);

              // DOM order can change between snapshot and execution in the SPA. Resolve the same
              // exact label again, but only inside the already-bound application card.
              var fallbackReasons=[];
              for(var i=0;i<nodes.length;i++){
                var el=nodes[i];
                if(labelOf(el)!==expected) continue;
                var result=tryClick(el,'same-card-fallback');
                if(result&&result.ok) return JSON.stringify(result);
                if(result&&result.reason) fallbackReasons.push(result.reason);
              }
              return JSON.stringify({
                ok:false,
                reason:requireSameCard?'same-card-action-not-found':'action-not-found',
                primaryReason:primary&&primary.reason?primary.reason:'missing',
                fallbackReasons:fallbackReasons.slice(0,12)
              });
            })();
        """.trimIndent()
    }

    private fun isSafeReadNavigationLabel(label: String): Boolean {
        if (Regex("(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)", RegexOption.IGNORE_CASE).containsMatchIn(label)) return false
        return Regex(
            "(실제\\s*합격자|과거\\s*입시결과|입시\\s*결과|합격\\s*예측\\s*리포트|모의\\s*지원\\s*리포트|지원자\\s*분포|대학.?학과별\\s*합격\\s*예측|합격\\s*안정성|상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|성적\\s*산출|입시\\s*전략|입시\\s*지식|경쟁률|모집\\s*요강|다음|더보기|결과|탭)",
            RegexOption.IGNORE_CASE
        ).containsMatchIn(label)
    }
}
