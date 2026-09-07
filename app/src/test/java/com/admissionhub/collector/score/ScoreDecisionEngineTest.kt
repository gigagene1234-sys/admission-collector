package com.admissionhub.collector.score

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScoreDecisionEngineTest {
    @Test fun invalidNumericScoreCannotBecomeEqualReference() {
        val own=verifiedConversion(930.0,"points-1000","higher-is-better").put("scoreValue","NaN")
        assertTrue(ScoreDecisionEngine.evaluate("accepted",own,JSONArray().put(verifiedOutcome(930.0,"points-1000",true)),null).getBoolean("hold"))
    }
    @Test fun invalidNumericReferenceIsNotComparable() {
        val outcome=verifiedOutcome(930.0,"points-1000",true).put("metricValue","NaN")
        assertTrue(ScoreDecisionEngine.evaluate("accepted",verifiedConversion(930.0,"points-1000","higher-is-better"),JSONArray().put(outcome),null).getBoolean("hold"))
    }
    @Test
    fun refusesToInventConversion() {
        val result = ScoreDecisionEngine.evaluate("accepted", null, JSONArray(), null)
        assertTrue(result.getBoolean("hold"))
        assertEquals("UNVERIFIED_CONVERSION", result.getString("decisionCode"))
    }

    @Test
    fun provisionalCanonicalBindingBlocksDecisionWithoutIndependentBindingProof() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(920.0, "points-1000", true))
        val result = ScoreDecisionEngine.evaluate("provisional", conversion, outcomes, null)
        assertEquals("UNVERIFIED_APPLICATION_BINDING", result.getString("decisionCode"))
    }

    @Test
    fun comparesOnlyVerifiedSameScaleWithExplicitDirection() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(920.0, "points-1000", true))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertFalse(result.getBoolean("hold"))
        assertEquals("ABOVE_REFERENCE", result.getString("decisionCode"))
        assertEquals(10.0, result.getDouble("advantageMargin"), 1e-9)
    }

    @Test
    fun lowerGradeAverageUsesLowerIsBetterDirection() {
        val conversion = verifiedConversion(2.8, "grade-average", "lower-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(3.1, "grade-average", true))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertEquals("ABOVE_REFERENCE", result.getString("decisionCode"))
        assertEquals(0.3, result.getDouble("advantageMargin"), 1e-9)
    }

    @Test
    fun mismatchedScaleIsNeverCompared() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray().put(verifiedOutcome(3.1, "grade-average", true))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertEquals("NO_COMPARABLE_OFFICIAL_OUTCOME", result.getString("decisionCode"))
    }

    @Test
    fun multipleReferencesRequireExplicitPrimary() {
        val conversion = verifiedConversion(930.0, "points-1000", "higher-is-better")
        val outcomes = JSONArray()
            .put(verifiedOutcome(910.0, "points-1000", false))
            .put(verifiedOutcome(920.0, "points-1000", false))
        val result = ScoreDecisionEngine.evaluate("accepted", conversion, outcomes, null)
        assertEquals("AMBIGUOUS_OFFICIAL_REFERENCE", result.getString("decisionCode"))
    }

    private fun verifiedConversion(value: Double, scale: String, direction: String) = JSONObject()
        .put("verified", true)
        .put("status", "verified")
        .put("scoreValue", value)
        .put("scoreScale", scale)
        .put("comparisonDirection", direction)

    private fun verifiedOutcome(value: Double, scale: String, primary: Boolean) = JSONObject()
        .put("verified", true)
        .put("metricName", "70% cut")
        .put("metricValue", value)
        .put("scoreScale", scale)
        .put("primaryReference", primary)
}
