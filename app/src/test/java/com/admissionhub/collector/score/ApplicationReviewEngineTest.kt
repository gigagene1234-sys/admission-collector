package com.admissionhub.collector.score
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.time.Instant

class ApplicationReviewEngineTest {
    private val now=Instant.parse("2026-09-07T00:00:00Z")
    private fun candidate()=JSONObject().put("applicationIdentityKey","synthetic-a").put("academicYear",2027).put("admissionCategory","교과").put("admission","일반")
    private fun profile()=JSONObject().put("status","IMPORTED").put("academicYear",2027).put("fingerprint","fixture-profile").put("completeTranscriptConfirmedByUser",true)
    private fun input()=JSONObject().put("applicationIdentityKey","synthetic-a").put("academicYear",2027)
        .put("profileFingerprint","fixture-profile").put("sourceReviewConfirmed",true)
        .put("formulaSource","https://www.adiga.kr/guide").put("formulaExcerpt","Synthetic verified formula excerpt")
        .put("outcomeSource","https://www.adiga.kr/outcome").put("outcomeExcerpt","Synthetic A, 2026, fictional unit, 70% cutoff")
        .put("scoreScale","synthetic weighted grade").put("direction","lower-is-better").put("ownScore",3.0).put("referenceScore",3.5).put("maxScore",9)
        .put("metricName","70%컷").put("outcomeYear",2026).put("methodDescription","Same subjects and weighted grade definition confirmed in both years")
        .put("rulesSource","https://www.adiga.kr/guide").put("rulesExcerpt","Synthetic eligibility, deadline and documents")
        .put("rulesReviewConfirmed",true).put("eligibility",1).put("csat",3).put("documents",1).put("multipleApplications",1)
        .put("deadline","2026-09-11T09:00:00Z")
    private fun evaluate(i:JSONObject=input(),p:JSONObject=profile())=ApplicationReviewEngine.evaluate(candidate(),i,p,null,now)
    @Test fun completeEvidenceProducesConditionalReviewAndExactMargin() {
        val r=evaluate();assertEquals("REVIEWABLE",r.getString("code"));assertEquals(0.5,r.getDouble("advantageMargin"),1e-9)
        assertEquals("USER_REVIEWED_OFFICIAL_SOURCE",r.getString("basis"));assertFalse(r.getBoolean("probabilityInferred"));assertFalse(r.getBoolean("unsupportedThresholdsUsed"))
    }
    @Test fun emptyInputHoldsWithoutInventingScores() { val r=evaluate(JSONObject());assertEquals("HOLD",r.getString("code"));assertTrue(r.isNull("advantageMargin"));assertTrue(r.getJSONArray("missing").length()>0) }
    @Test fun changedProfileInvalidatesComparison() { val r=evaluate(p=profile().put("fingerprint","new"));assertFalse(r.getBoolean("comparisonReady")) }
    @Test fun otherApplicationsEvidenceCannotBind() { assertFalse(evaluate(input().put("applicationIdentityKey","synthetic-b")).getBoolean("comparisonReady")) }
    @Test fun futureAndCurrentOutcomeYearsCannotBeHistorical() {
        for(year in listOf(2027,2028)) assertFalse(evaluate(input().put("outcomeYear",year)).getBoolean("comparisonReady"))
    }
    @Test fun lowerScoreDirectionAndNegativeMarginAreExplained() { val r=evaluate(input().put("ownScore",4.0));assertEquals("SCORE_RISK",r.getString("code"));assertEquals(-0.5,r.getDouble("advantageMargin"),1e-9) }
    @Test fun unmetConditionOverridesFavorableGrade() { assertEquals("CONDITIONS_RECHECK",evaluate(input().put("eligibility",2)).getString("code")) }
    @Test fun passedDeadlineRequiresReview() { assertEquals("CONDITIONS_RECHECK",evaluate(input().put("deadline","2026-09-06T09:00:00Z")).getString("code")) }
    @Test fun unreviewedRulesNeverMarkReady() { assertEquals("HOLD",evaluate(input().put("rulesReviewConfirmed",false)).getString("code")) }
    @Test fun incompleteTranscriptHolds() { assertFalse(evaluate(p=profile().put("completeTranscriptConfirmedByUser",false)).getBoolean("comparisonReady")) }
    @Test fun outOfRangeScoreHolds() { assertFalse(evaluate(input().put("ownScore",12)).getBoolean("comparisonReady")) }
    @Test fun unsupportedSourcesAndSecretQueriesAreRejected() {
        assertFalse(ApplicationReviewEngine.officialUrl("https://college.ac.kr.evil.example/x"))
        assertFalse(ApplicationReviewEngine.officialUrl("https://jinhak.com/x"))
        assertFalse(ApplicationReviewEngine.officialUrl("https://www.adiga.kr/?token=dummy"))
    }
    @Test fun unknownInputFieldsNeverEnterExport() { assertFalse(evaluate(input().put("password","dummy")).getJSONObject("input").has("password")) }
    @Test fun interviewOverlapIsFlaggedWithoutChangingSlots() {
        val cards=JSONArray().put(JSONObject().put("slot",1).put("occupied",true).put("university","Synthetic U").put("applicationReview",JSONObject().put("input",JSONObject().put("interviewDate","2026-10-01"))))
            .put(JSONObject().put("slot",2).put("occupied",true).put("university","Synthetic U").put("applicationReview",JSONObject().put("input",JSONObject().put("interviewDate","2026-10-01"))))
        val before=cards.toString();val r=ApplicationReviewEngine.portfolio(cards)
        assertTrue(r.getJSONArray("warnings").toString().contains("면접일"));assertEquals(before,cards.toString());assertFalse(r.getBoolean("automaticSelection"))
    }
}
