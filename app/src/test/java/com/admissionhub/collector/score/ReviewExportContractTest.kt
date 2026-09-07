package com.admissionhub.collector.score
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.StringWriter

class ReviewExportContractTest {
    @Test fun streamingExportRoundTripPreservesSourceAndAddsReviewEvidence() {
        val writer=StringWriter();writer.write("{\"session\":{\"collectorVersion\":\"0.10.4\"}")
        val p=StudentScoreImport.parse(StudentScoreImport.TEMPLATE+"1,1,국어,국어,3,4,",2027,true)
        ReviewExportContract.append(writer,"0.13.0",113000,"0.10.4","2026-09-07T00:00:00Z",p,JSONObject().put("byIdentity",JSONObject()),JSONObject().put("applicationPortfolio",JSONObject().put("selected",6)))
        writer.write("}");val out=JSONObject(writer.toString())
        assertEquals("0.10.4",out.getJSONObject("session").getString("collectorVersion"))
        assertEquals("0.13.0",out.getJSONObject("exporter").getString("versionName"))
        assertEquals(p.getString("fingerprint"),out.getJSONObject("studentScoreProfile").getString("fingerprint"))
        assertTrue(out.getJSONObject("scoreDecisionSummary").has("byIdentity"));assertEquals(6,out.getJSONObject("hubDashboard").getJSONObject("applicationPortfolio").getInt("selected"))
    }
}
