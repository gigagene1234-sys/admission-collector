package com.admissionhub.collector.observation

import com.admissionhub.collector.parser.RecordUtils
import org.json.JSONArray
import org.json.JSONObject

data class ObservationIdentity(
    val observationId: String,
    val contentFingerprint: String,
    val contextFingerprint: String
)

object ObservationEvidence {
    fun identity(
        provider: String,
        safeRouteKey: String,
        explicitContext: JSONObject,
        evidence: JSONObject
    ): ObservationIdentity {
        val contextStable = stableContext(explicitContext)
        val evidenceStable = stableEvidence(evidence)
        val contextFingerprint = RecordUtils.sha256(contextStable)
        val contentFingerprint = RecordUtils.sha256(evidenceStable)
        val observationId = RecordUtils.sha256(
            listOf(provider, safeRouteKey, contextFingerprint, contentFingerprint).joinToString("|")
        )
        return ObservationIdentity(observationId, contentFingerprint, contextFingerprint)
    }

    fun explicitContextFromDigest(digest: JSONObject): JSONObject {
        val bundle = digest.optJSONObject("analysisBundle") ?: JSONObject()
        return JSONObject()
            .put("pageType", digest.optString("pageType"))
            .put("context", bundle.optJSONArray("context") ?: JSONArray())
            .put("selectionContext", bundle.optJSONArray("selectionContext") ?: JSONArray())
    }

    private fun stableContext(context: JSONObject): String = JSONObject()
        .put("pageType", context.optString("pageType"))
        .put("context", context.optJSONArray("context") ?: JSONArray())
        .put("selectionContext", context.optJSONArray("selectionContext") ?: JSONArray())
        .toString()

    private fun stableEvidence(evidence: JSONObject): String {
        val bundle = evidence.optJSONObject("analysisBundle") ?: evidence
        return JSONObject()
            .put("pageType", evidence.optString("pageType", bundle.optString("pageType")))
            .put("pageTitle", bundle.optString("pageTitle"))
            .put("context", bundle.optJSONArray("context") ?: JSONArray())
            .put("selectionContext", bundle.optJSONArray("selectionContext") ?: JSONArray())
            .put("cards", bundle.optJSONArray("cards") ?: JSONArray())
            .put("tables", bundle.optJSONArray("tables") ?: JSONArray())
            .put("blocks", bundle.optJSONArray("blocks") ?: JSONArray())
            .put("resourceLabels", bundle.optJSONArray("resourceLabels") ?: JSONArray())
            .toString()
    }
}
