from pathlib import Path

# Integrate official-only published fallback after strict Adiga table rescan.
p=Path('app/src/main/java/com/admissionhub/collector/score/AdigaAutoScoreMaterializer.kt')
s=p.read_text()
old='''        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
'''
new='''        val publishedFallback = OfficialPublishedOutcomeFallback.materializeMissing(store, sessionId, selectedCandidates)

        return JSONObject()
            .put("schemaVersion", SCHEMA_VERSION)
'''
if old not in s: raise SystemExit('materializer return anchor missing')
s=s.replace(old,new,1)
old='''.put("historicalOutcomesStored", historicalOutcomesStored)
            .put("fullAdigaRecordsScanned", fullRescan.optInt("recordsScanned"))'''
new='''.put("historicalOutcomesStored", historicalOutcomesStored)
            .put("officialPublishedFallback", publishedFallback)
            .put("fullAdigaRecordsScanned", fullRescan.optInt("recordsScanned"))'''
if old not in s: raise SystemExit('materializer fallback result anchor missing')
s=s.replace(old,new,1)
p.write_text(s)

# Dashboard: surface official non-numeric availability instead of generic '미확인'.
p=Path('app/src/main/java/com/admissionhub/collector/hub/HubDashboardModel.kt')
s=p.read_text()
old='''        if (verified.isNotEmpty()) {
            val latestYear = verified.maxOf { it.optInt("academicYear", 0) }
            val sameYear = verified.filter { it.optInt("academicYear", 0) == latestYear }
            val parts = sameYear.sortedBy { metricOrder(it.optString("metricName")) }.take(4).map { outcomeDisplay(it) }
            out.put("officialOutcomeLabel", "공식 입결: $latestYear · ${parts.joinToString(" · ")}")
        }
        return out
'''
new='''        if (verified.isNotEmpty()) {
            val latestYear = verified.maxOf { it.optInt("academicYear", 0) }
            val sameYear = verified.filter { it.optInt("academicYear", 0) == latestYear }
            val parts = sameYear.sortedBy { metricOrder(it.optString("metricName")) }.take(4).map { outcomeDisplay(it) }
            out.put("officialOutcomeLabel", "공식 입결: $latestYear · ${parts.joinToString(" · ")}")
        } else {
            val availability = (0 until outcomes.length()).mapNotNull { outcomes.optJSONObject(it) }
                .firstOrNull { it.optBoolean("verified", false) && it.optJSONObject("detail")?.optString("availabilityStatus").orEmpty().isNotBlank() }
            if (availability != null) {
                val year = availability.optInt("academicYear", 0)
                val detail = availability.optJSONObject("detail") ?: JSONObject()
                out.put("officialOutcomeLabel", when (detail.optString("availabilityStatus")) {
                    "officially-suppressed" -> "공식 입결: $year · 대학 공식 비공개 · ${detail.optString("availabilityReason", "공개 제한")}" 
                    "new-program-no-prior-result" -> "공식 입결: $year · 전년도 수치 없음 · ${detail.optString("availabilityReason", "신설 모집단위")}" 
                    else -> "공식 입결: $year · ${detail.optString("availabilityReason", "수치 공개 없음")}" 
                })
            }
        }
        return out
'''
if old not in s: raise SystemExit('dashboard availability anchor missing')
s=s.replace(old,new,1)
p.write_text(s)
print('v0.16.1 official published fallback integrated')
