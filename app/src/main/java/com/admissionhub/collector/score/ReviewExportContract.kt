package com.admissionhub.collector.score
import org.json.JSONObject
import java.io.Writer

/** Appends to the existing streaming object; old source collector provenance is never overwritten. */
object ReviewExportContract {
    fun append(writer: Writer, version: String, build: Int, sourceVersion: String, at: String, profile: JSONObject, score: JSONObject, hub: JSONObject) {
        val exporter = JSONObject().put("versionName", version).put("versionCode", build).put("exportedAt", at).put("sourceCollectorVersion", sourceVersion)
        writer.write(",\"exporter\":$exporter")
        writer.write(",\"studentScoreProfile\":$profile")
        writer.write(",\"scoreDecisionSummary\":$score")
        writer.write(",\"hubDashboard\":$hub")
    }
}
