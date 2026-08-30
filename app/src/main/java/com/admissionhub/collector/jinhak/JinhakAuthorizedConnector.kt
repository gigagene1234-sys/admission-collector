package com.admissionhub.collector.jinhak

import org.json.JSONArray
import org.json.JSONObject

data class JinhakConnectorCapability(
    val kind: String,
    val label: String,
    val evidenceClass: String
)

data class JinhakCapabilitySnapshot(
    val capabilities: List<JinhakConnectorCapability>,
    val hasStructuredExportSignal: Boolean,
    val hasReportOutputSignal: Boolean
)

interface JinhakAuthorizedConnector {
    fun discoverCapabilities(): JinhakCapabilitySnapshot
    fun authenticateOrResume(): Boolean
    fun syncStudentProfile(): Int
    fun syncSavedApplications(): Int
    fun syncRecommendations(): Int
    fun syncPredictionReports(): Int
    fun syncMockSupportReports(): Int
    fun syncActualAdmitReports(): Int
    fun syncScoreCalculations(): Int
    fun syncSatMinimum(): Int
}

object JinhakCapabilityProbe {
    /**
     * Local WebView-only probe. It inspects visible official UI controls and returns
     * labels/types only. It does not return URLs, form values, cookies, tokens,
     * hidden API endpoints or raw DOM.
     */
    fun javascript(): String = """
        (function(){
          function visible(el){
            if(!el) return false;
            var s=getComputedStyle(el);
            if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
            var r=el.getBoundingClientRect();
            return r.width>0 && r.height>0;
          }
          var out=[];
          var seen={};
          var nodes=document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit]');
          for(var i=0;i<nodes.length && out.length<80;i++){
            var el=nodes[i];
            if(!visible(el)) continue;
            var label=(el.innerText||el.textContent||el.value||el.getAttribute('aria-label')||el.title||'')
              .replace(/\s+/g,' ').trim().slice(0,120);
            if(!label) continue;
            var kind='';
            if(/excel|xlsx|xls|csv|엑셀|내보내기|export/i.test(label)) kind='structured-export';
            else if(/pdf|인쇄|프린트|print|리포트\s*저장|보고서\s*저장/i.test(label)) kind='report-output';
            else if(/다운로드|download/i.test(label)) kind='download';
            else if(/이메일|메일\s*발송|email/i.test(label)) kind='email-report';
            else continue;
            var key=kind+'|'+label;
            if(seen[key]) continue;
            seen[key]=true;
            out.push({kind:kind,label:label,evidenceClass:'visible-official-ui-control'});
          }
          return JSON.stringify({controls:out});
        })();
    """.trimIndent()

    fun parse(raw: String): JinhakCapabilitySnapshot {
        val root = runCatching { JSONObject(raw) }.getOrElse { JSONObject() }
        val controls = root.optJSONArray("controls") ?: JSONArray()
        val parsed = mutableListOf<JinhakConnectorCapability>()
        for (i in 0 until controls.length()) {
            val item = controls.optJSONObject(i) ?: continue
            val kind = item.optString("kind").take(40)
            val label = item.optString("label").replace(Regex("\\s+"), " ").trim().take(120)
            if (kind.isBlank() || label.isBlank()) continue
            parsed += JinhakConnectorCapability(
                kind = kind,
                label = label,
                evidenceClass = item.optString("evidenceClass", "visible-official-ui-control").take(80)
            )
        }
        return JinhakCapabilitySnapshot(
            capabilities = parsed.distinctBy { "${it.kind}|${it.label}" },
            hasStructuredExportSignal = parsed.any { it.kind == "structured-export" },
            hasReportOutputSignal = parsed.any { it.kind == "report-output" || it.kind == "download" }
        )
    }
}
