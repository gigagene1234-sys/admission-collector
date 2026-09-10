package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject

/**
 * v0.18.5 application-report navigator.
 *
 * It never performs a generic Jinhak crawl. On the storage page, only a read-only report action
 * structurally bound to one application card is eligible. Inside a report family, only report
 * lane controls are eligible. This preserves same-application provenance across every click.
 */
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
        if (!JinhakManualStorageReportPolicy.isAllowedMissionUrl(route)) return emptyList()

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
                val contextText = obj.optString("contextText").replace(Regex("\\s+"), " ").trim().take(2400)
                if (scanIndex < 0 || label.isBlank()) continue

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
                val bound = !app?.identityKey.isNullOrBlank()
                if (!JinhakManualStorageReportPolicy.shouldPromoteAction(route, label, bound)) continue

                // Storage must always retain a same-card identity. Report pages inherit identity
                // through JinhakReportContextBridge and therefore may expose unbound tab controls.
                if (JinhakManualStorageReportPolicy.isStorageEntry(route) && !bound) continue

                val dedupeKey = listOf(scanIndex.toString(), label, kind, app?.identityKey ?: "report-tab").joinToString("|")
                if (!seen.add(dedupeKey)) continue

                val lane = JinhakReportContextBridge.laneHint(label)
                var priority = when (lane) {
                    "actual-admit" -> 130
                    "current-prediction" -> 125
                    "mock-support" -> 120
                    "score-analysis" -> 115
                    else -> 90
                }
                if (bound) priority += 35
                if (kind == "mission-link-navigation" || kind == "mission-bound-control") priority += 25
                if (promoted) priority += 20

                out += Candidate(
                    scanIndex = scanIndex,
                    label = label,
                    tag = tag,
                    kind = kind,
                    missionPriority = priority.coerceIn(0, 220),
                    contextText = contextText,
                    applicationContext = app,
                    promotedMissionAction = promoted,
                    applicationBindingSource = applicationBindingSource
                )
            }
        }

        // Same-card mission anchors are first-class. Generic site links never enter the candidate set.
        append("missionAgentActions", promoted = true, limit = 160)
        if (JinhakManualStorageReportPolicy.isReportUrl(route)) {
            append("agentActions", promoted = false, limit = 160)
        }

        return out.sortedWith(
            compareByDescending<Candidate> { !it.applicationContext?.identityKey.isNullOrBlank() }
                .thenByDescending { it.promotedMissionAction }
                .thenByDescending { it.missionPriority }
                .thenBy { it.scanIndex }
        )
    }

    fun key(safeRoute: String, candidate: Candidate): String = RecordUtils.sha256(
        listOf(
            safeRoute,
            candidate.scanIndex.toString(),
            candidate.label,
            candidate.kind,
            candidate.applicationContext?.identityKey ?: "report-tab"
        ).joinToString("|")
    )

    fun laneForCandidate(candidate: Candidate): String = JinhakReportContextBridge.laneHint(candidate.label)

    fun executionScript(candidate: Candidate): String {
        val expected = JSONObject.quote(candidate.label)
        val university = JSONObject.quote(candidate.applicationContext?.university.orEmpty().take(80))
        val department = JSONObject.quote(candidate.applicationContext?.departmentRaw.orEmpty().take(120))
        val admission = JSONObject.quote(candidate.applicationContext?.admission.orEmpty().take(100))
        val capacity = candidate.applicationContext?.capacity ?: -1
        val requiresSameCard = !candidate.applicationContext?.identityKey.isNullOrBlank()
        val reportPage = candidate.applicationContext == null
        return """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el), r=el.getBoundingClientRect();
                return s.display!=='none' && s.visibility!=='hidden' && s.opacity!=='0' && r.width>0 && r.height>0;
              }
              function clean(v){return String(v||'').replace(/\s+/g,' ').trim();}
              function norm(v){return clean(v).toLowerCase().replace(/[\s\[\](){}·._\-\/:|]/g,'');}
              function containsToken(text,token){var nt=norm(token);return !nt || norm(text).indexOf(nt)>=0;}
              var expected=$expected, uni=$university, dept=$department, adm=$admission, capacity=$capacity;
              var requireSameCard=${if (requiresSameCard) "true" else "false"};
              var requireReportPage=${if (reportPage) "true" else "false"};
              var storage=/\/jh\/high3\/early\/four-year-university\/library\/?$/i.test(location.pathname);
              var report=/\/jh\/high3\/early\/four-year-university\/report\//i.test(location.pathname);
              if(requireSameCard && !storage) return JSON.stringify({ok:false,reason:'storage-context-required'});
              if(requireReportPage && !report) return JSON.stringify({ok:false,reason:'report-context-required'});

              var blocked=/(원서\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의)/i;
              var allowed=/(합격\s*예측|합격\s*안정성|모의\s*지원|지원자\s*분포|실제\s*합격자|과거\s*입시결과|입시\s*결과|성적\s*분석|성적\s*산출|환산\s*점수|리포트)/i;
              var selector='a,button,[role=button],[role=tab],[onclick],[data-href],[data-url],[data-link],[data-path]';
              var nodes=document.querySelectorAll(selector);
              function labelOf(el){return clean(el&&(el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')||'')).slice(0,120);}
              function sameLabelCount(scope){
                if(!scope||!scope.querySelectorAll) return 0;
                var all=scope.querySelectorAll(selector), count=0;
                for(var i=0;i<all.length;i++) if(visible(all[i])&&labelOf(all[i])===expected) count++;
                return count;
              }
              function cardProof(el){
                if(!requireSameCard) return {ok:true,depth:0,reason:'report-tab'};
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
                  if(sameLabelCount(cur)!==1) continue;
                  return {ok:true,depth:d,reason:capacity>=0?'unique-card-capacity':'unique-card-admission'};
                }
                return {ok:false,depth:-1,reason:'bounded-card-proof-missing'};
              }
              function tryClick(el,resolution){
                if(!el||!visible(el)) return {ok:false,reason:'hidden-or-missing',resolution:resolution};
                var lab=labelOf(el);
                if(lab!==expected) return {ok:false,reason:'label-changed',resolution:resolution};
                if(blocked.test(lab)||!allowed.test(lab)) return {ok:false,reason:'policy-block',resolution:resolution};
                var proof=cardProof(el);
                if(!proof.ok) return {ok:false,reason:'same-card-context-mismatch',resolution:resolution,proofReason:proof.reason};
                try{
                  var before=location.href;
                  el.click();
                  return {ok:true,label:lab,before:before===location.href?'same-document':'navigation-started',resolution:resolution,proofReason:proof.reason};
                }catch(e){return {ok:false,reason:'click-failed',resolution:resolution};}
              }
              var primary=tryClick(nodes[${candidate.scanIndex}], 'scan-index');
              if(primary&&primary.ok) return JSON.stringify(primary);
              for(var i=0;i<nodes.length;i++){
                if(labelOf(nodes[i])!==expected) continue;
                var r=tryClick(nodes[i], 'bounded-fallback');
                if(r&&r.ok) return JSON.stringify(r);
              }
              return JSON.stringify({ok:false,reason:'report-action-not-found'});
            })();
        """.trimIndent()
    }
}
