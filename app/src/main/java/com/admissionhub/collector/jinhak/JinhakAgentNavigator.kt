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
        val applicationContext: JinhakApplicationMission.Context?,
        val promotedMissionAction: Boolean = false,
        val applicationBindingSource: String = ""
    )

    fun candidates(snapshot: JSONObject): List<Candidate> {
        val route = snapshot.optString("url")
        val out = mutableListOf<Candidate>()
        val seen = linkedSetOf<String>()

        fun append(arrayName: String, promoted: Boolean, limit: Int) {
            val array = snapshot.optJSONArray(arrayName) ?: JSONArray()
            for (i in 0 until minOf(array.length(), limit)) {
                val obj = array.optJSONObject(i) ?: continue
                val scanIndex = obj.optInt("scanIndex", -1)
                val label = obj.optString("label").replace(Regex("\\s+"), " ").trim().take(120)
                val tag = obj.optString("tag").take(24)
                val kind = obj.optString("kind", "read-navigation").take(40)
                val contextText = obj.optString("contextText")
                    .replace(Regex("\\s+"), " ").trim().take(2400)
                if (scanIndex < 0 || label.isBlank()) continue
                if (!isSafeReadNavigationLabel(label)) continue
                val explicitUniversity = obj.optString("applicationUniversity")
                    .replace(Regex("\\s+"), " ").trim().take(80).takeIf { it.isNotBlank() }
                val explicitDepartment = obj.optString("applicationDepartment")
                    .replace(Regex("\\s+"), " ").trim().take(120).takeIf { it.isNotBlank() }
                val applicationBindingSource = obj.optString("applicationBindingSource")
                    .replace(Regex("\\s+"), " ").trim().take(40)
                val app = JinhakApplicationMission.parseCard(
                    contextText,
                    explicitUniversity = explicitUniversity,
                    explicitDepartment = explicitDepartment
                )
                val dedupeKey = listOf(scanIndex.toString(), label, kind, app?.identityKey ?: contextText.take(1000)).joinToString("|")
                if (!seen.add(dedupeKey)) continue
                var priority = JinhakSiteTopology.priority(route, label)
                if (app?.identityKey != null) priority += 14
                if (app != null && Regex("(리포트|실제\\s*합격자|모의\\s*지원|합격\\s*예측)").containsMatchIn(label)) priority += 8
                if (kind == "mission-link-navigation" && app?.identityKey != null) priority += 35
                if (kind == "mission-bound-control" && app?.identityKey != null) priority += 35
                if (promoted && app?.identityKey != null) priority += 45
                out += Candidate(scanIndex, label, tag, kind, priority.coerceIn(0, 220), contextText, app, promoted, applicationBindingSource)
            }
        }

        // Dedicated mission anchors cannot be displaced by the generic action cap.
        append("missionAgentActions", promoted = true, limit = 120)
        append("agentActions", promoted = false, limit = 160)

        return out.sortedWith(
            compareByDescending<Candidate> { it.promotedMissionAction && it.applicationContext?.identityKey != null }
                .thenByDescending { it.kind == "mission-link-navigation" && it.applicationContext?.identityKey != null }
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
            candidate.promotedMissionAction.toString(),
            candidate.applicationContext?.identityKey ?: RecordUtils.sha256(candidate.contextText.take(1200))
        ).joinToString("|")
    )

    fun laneForCandidate(candidate: Candidate): String = JinhakMissionLaneSequencer.laneForLabel(candidate.label, candidate.kind)

    fun executionScript(candidate: Candidate): String {
        val expected = JSONObject.quote(candidate.label)
        val university = JSONObject.quote(candidate.applicationContext?.university.orEmpty().take(80))
        val department = JSONObject.quote(candidate.applicationContext?.departmentRaw.orEmpty().take(120))
        val admission = JSONObject.quote(candidate.applicationContext?.admission.orEmpty().take(100))
        val capacity = candidate.applicationContext?.capacity ?: -1
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
              function norm(v){
                return clean(v).toLowerCase().replace(/[\s\[\](){}·._\-\/:|]/g,'');
              }
              function containsToken(text,token){
                var nt=norm(token);
                return !nt || norm(text).indexOf(nt)>=0;
              }
              var expected=$expected, uni=$university, dept=$department, adm=$admission, capacity=$capacity;
              var requireSameCard=${if (requiresSameCard) "true" else "false"};
              var blocked=/(원서\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)/i;
              var allowed=/(실제\s*합격자|과거\s*입시결과|입시\s*결과|합격\s*예측\s*리포트|모의\s*지원\s*리포트|지원자\s*분포|대학.?학과별\s*합격\s*예측|합격\s*안정성|상세|보기|조회|검색|리포트|대학\s*정보|전형\s*정보|학과\s*정보|합격\s*예측|모의\s*지원|수시\s*저장소|정시\s*저장소|추천\s*대학|성적\s*분석|성적\s*산출|입시\s*전략|입시\s*지식|경쟁률|모집\s*요강|다음|더보기|결과|탭)/i;
              var selector='a,button,[role=button],[role=tab],[onclick],[data-href],[data-url],[data-link],[data-path]';
              var nodes=document.querySelectorAll(selector);
              function labelOf(el){return clean(el&& (el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')||'')).slice(0,120);}
              function matchingActionCount(scope){
                if(!scope||!scope.querySelectorAll) return 0;
                var all=scope.querySelectorAll(selector), count=0;
                for(var i=0;i<all.length;i++){
                  if(visible(all[i])&&labelOf(all[i])===expected) count++;
                  if(count>1) break;
                }
                return count;
              }
              function cardProof(el){
                if(!requireSameCard) return {ok:true,depth:0,reason:'not-required'};
                var cur=el;
                for(var d=0;cur&&d<10;d++,cur=cur.parentElement){
                  var tag=String(cur.tagName||'').toUpperCase();
                  if(tag==='BODY'||tag==='HTML') break;
                  var t=clean(cur.innerText||cur.textContent||'').slice(0,9000);
                  if(!t||t.length>8500) continue;
                  if(!containsToken(t,uni)||!containsToken(t,dept)) continue;
                  var metricCount=(t.match(/[0-9,]+\s*명\s*(?:\||\s)*내\s*점수/ig)||[]).length;
                  if(metricCount>1) continue;
                  var capacityOk=false;
                  if(capacity>=0){
                    var capRx=new RegExp('(?:^|[^0-9])'+capacity+'\\s*명\\s*(?:\\||\\s)*내\\s*점수','i');
                    capacityOk=capRx.test(t)&&metricCount===1;
                  }
                  var admissionOk=!!adm&&containsToken(t,adm);
                  if(capacity>=0 ? !capacityOk : !admissionOk) continue;
                  if(matchingActionCount(cur)!==1) continue;
                  return {ok:true,depth:d,reason:capacity>=0?'unique-card-capacity':'unique-card-admission'};
                }
                return {ok:false,depth:-1,reason:'bounded-card-proof-missing'};
              }
              function tryClick(el,resolution){
                if(!el) return null;
                if(!visible(el)) return {ok:false,reason:'hidden',resolution:resolution};
                var lab=labelOf(el);
                if(lab!==expected) return {ok:false,reason:'label-changed',resolution:resolution,observedLabel:lab};
                if(blocked.test(lab)||!allowed.test(lab)) return {ok:false,reason:'policy-block',resolution:resolution};
                var proof=cardProof(el);
                if(!proof.ok) return {ok:false,reason:'same-card-context-mismatch',resolution:resolution,proofReason:proof.reason};
                try{
                  var before=location.href;
                  el.click();
                  return {ok:true,label:lab,before:before===location.href?'same-document':'navigation-started',resolution:resolution,matchedSameCard:requireSameCard,contextDepth:proof.depth,proofReason:proof.reason};
                }catch(e){return {ok:false,reason:'click-failed',resolution:resolution};}
              }
              var primary=tryClick(nodes[${candidate.scanIndex}], 'scan-index');
              if(primary&&primary.ok) return JSON.stringify(primary);

              // SPA order may change after the snapshot. Re-resolve only the exact same label and
              // accept it only when bounded card ownership is independently reproved.
              var fallbackReasons=[];
              var sameLabelSeen=0;
              for(var i=0;i<nodes.length;i++){
                var el=nodes[i];
                if(labelOf(el)!==expected) continue;
                sameLabelSeen++;
                var result=tryClick(el,'bounded-context-fallback');
                if(result&&result.ok) return JSON.stringify(result);
                if(result&&result.reason) fallbackReasons.push(result.reason+':'+String(result.proofReason||''));
              }
              return JSON.stringify({
                ok:false,
                reason:requireSameCard?'same-card-action-not-found':'action-not-found',
                primaryReason:primary&&primary.reason?primary.reason:'missing',
                sameLabelSeen:sameLabelSeen,
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
