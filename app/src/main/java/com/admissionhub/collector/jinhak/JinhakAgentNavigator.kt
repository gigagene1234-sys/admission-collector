package com.admissionhub.collector.jinhak

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject

object JinhakAgentNavigator {
    data class Candidate(val scanIndex: Int, val label: String, val tag: String, val kind: String)

    fun candidates(snapshot: JSONObject): List<Candidate> {
        val array = snapshot.optJSONArray("agentActions") ?: JSONArray()
        val out = mutableListOf<Candidate>()
        for (i in 0 until minOf(array.length(), 80)) {
            val obj = array.optJSONObject(i) ?: continue
            val scanIndex = obj.optInt("scanIndex", -1)
            val label = obj.optString("label").replace(Regex("\\s+"), " ").trim().take(120)
            val tag = obj.optString("tag").take(24)
            val kind = obj.optString("kind", "read-navigation").take(40)
            if (scanIndex < 0 || label.isBlank()) continue
            if (!isSafeReadNavigationLabel(label)) continue
            out += Candidate(scanIndex, label, tag, kind)
        }
        return out
    }

    fun key(safeRoute: String, candidate: Candidate): String = RecordUtils.sha256(
        listOf(safeRoute, candidate.scanIndex.toString(), candidate.label, candidate.tag, candidate.kind).joinToString("|")
    )

    fun executionScript(candidate: Candidate): String {
        val expected = JSONObject.quote(candidate.label)
        return """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0&&r.height>0;
              }
              function clean(v){return String(v||'').replace(/\\s+/g,' ').trim();}
              var nodes=document.querySelectorAll('a,button,[role=button],[role=tab],[onclick],[data-href],[data-url],[data-link],[data-path]');
              var el=nodes[${candidate.scanIndex}];
              if(!el||!visible(el)) return JSON.stringify({ok:false,reason:'missing-or-hidden'});
              var label=clean(el.innerText||el.textContent||el.getAttribute('aria-label')||el.getAttribute('title')||'').slice(0,120);
              var expected=$expected;
              if(label!==expected) return JSON.stringify({ok:false,reason:'label-changed'});
              var blocked=/(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)/i;
              var allowed=/(상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|다음|더보기|결과|탭)/i;
              if(blocked.test(label)||!allowed.test(label)) return JSON.stringify({ok:false,reason:'policy-block'});
              var before=location.href;
              try{el.click();}catch(e){return JSON.stringify({ok:false,reason:'click-failed'});}
              return JSON.stringify({ok:true,label:label,before:before===location.href?'same-document':'navigation-started'});
            })();
        """.trimIndent()
    }

    private fun isSafeReadNavigationLabel(label: String): Boolean {
        if (Regex("(원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰)", RegexOption.IGNORE_CASE).containsMatchIn(label)) return false
        return Regex("(상세|보기|조회|검색|리포트|대학\\s*정보|전형\\s*정보|학과\\s*정보|합격\\s*예측|모의\\s*지원|수시\\s*저장소|정시\\s*저장소|추천\\s*대학|성적\\s*분석|다음|더보기|결과|탭)", RegexOption.IGNORE_CASE).containsMatchIn(label)
    }
}
