from pathlib import Path

# Add a global verified-numeric-outcome existence helper. Official outcome storage is keyed by
# application identity across sessions, so fallback must not depend on whether the latest failed
# Jinhak session rebuilt canonical_applications.
p=Path('app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt')
s=p.read_text()
anchor='''    fun storeOfficialAdmissionOutcome(
'''
helper='''    fun hasVerifiedNumericOfficialOutcome(applicationIdentityKey: String): Boolean {
        if (applicationIdentityKey.isBlank()) return false
        return readableDatabase.rawQuery(
            "SELECT 1 FROM score_official_outcomes WHERE application_identity_key=? AND verified=1 AND metric_value IS NOT NULL LIMIT 1",
            arrayOf(applicationIdentityKey)
        ).use { it.moveToFirst() }
    }

'''
if helper not in s:
    if anchor not in s: raise SystemExit('LocalCollectorStore outcome anchor missing')
    s=s.replace(anchor,helper+anchor,1)
p.write_text(s)

# Use the global check and accept the canonical short names actually displayed by the app.
p=Path('app/src/main/java/com/admissionhub/collector/score/OfficialPublishedOutcomeFallback.kt')
s=p.read_text()
old='''        val summary = store.scoreDecisionSummary(sessionId).optJSONObject("byIdentity") ?: JSONObject()
        var matched = 0
'''
new='''        var matched = 0
'''
if old not in s: raise SystemExit('fallback summary anchor missing')
s=s.replace(old,new,1)
old='''            val existing = summary.optJSONObject(identity)?.optJSONArray("officialOutcomes") ?: JSONArray()
            val hasVerifiedNumeric = (0 until existing.length()).any { i ->
                val row = existing.optJSONObject(i)
                row != null && row.optBoolean("verified", false) && row.has("metricValue") && !row.isNull("metricValue")
            }
            if (hasVerifiedNumeric) continue
'''
new='''            if (store.hasVerifiedNumericOfficialOutcome(identity)) continue
'''
if old not in s: raise SystemExit('fallback numeric dedupe anchor missing')
s=s.replace(old,new,1)
s=s.replace('department == "철도차량시스템공학" && admission.contains("학생부종합2")',
            'department in setOf("철도차량시스템공", "철도차량시스템공학") && admission.contains("학생부종합2")',1)
s=s.replace('department == "반도체시스템공학" && admission.contains("지역인재교과")',
            'department in setOf("반도체시스템공", "반도체시스템공학") && admission.contains("지역인재교과")',1)
p.write_text(s)
print('v0.16.1 fallback identity and dedupe patch applied')
