from pathlib import Path

MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
STORE = Path('app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt')

m = MAIN.read_text()
# Remove now-unused URL-only pageKey variable in the scheduling stage.
m = m.replace('''        val pageKey = RecordUtils.sha256(canonical)\n        unifiedAutoCaptureScheduled = true\n''',
              '''        unifiedAutoCaptureScheduled = true\n''', 1)
# Use capability profile in visible status to avoid a dead architecture import.
m = m.replace('''        val capabilities = ProviderCapabilities.profile(which)\n        status.text = if (which == ProviderId.JINHAK) {\n            "진학사 observation-first 모드 · 공식 export/report capability 자동 탐지 · 현재 화면은 분류 여부와 무관하게 증거 보존"\n        } else {\n            "어디가 공식정보 모드 · deterministic ID/year planner 기반 전환 준비 · 기존 체크포인트 보존"\n        }\n''',
'''        val capabilities = ProviderCapabilities.profile(which)\n        status.text = if (which == ProviderId.JINHAK) {\n            "진학사 observation-first 모드 · active ${capabilities.active.size} / discoverable ${capabilities.discoverable.size} · 분류 여부와 무관하게 증거 보존"\n        } else {\n            "어디가 공식정보 모드 · active ${capabilities.active.size} · deterministic ID/year planner 기반 전환 준비"\n        }\n''', 1)
MAIN.write_text(m)

s = STORE.read_text()
old = r'''    fun observationStats(sessionId: String?): JSONObject {
        val where = if (sessionId == null) "" else " WHERE session_id=?"
        val args = if (sessionId == null) emptyArray() else arrayOf(sessionId)
        fun scalar(sql: String): Int = readableDatabase.rawQuery(sql + where, args).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        return JSONObject()
            .put("observations", scalar("SELECT COUNT(*) FROM observations"))
            .put("unknownOrPotential", scalar("SELECT COUNT(*) FROM observations" + if (where.isBlank()) " WHERE page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other')" else " WHERE session_id=? AND (page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other'))"))
    }
'''
new = r'''    fun observationStats(sessionId: String?): JSONObject {
        val args: Array<String> = if (sessionId == null) emptyArray() else arrayOf(sessionId)
        val totalSql = if (sessionId == null) {
            "SELECT COUNT(*) FROM observations"
        } else {
            "SELECT COUNT(*) FROM observations WHERE session_id=?"
        }
        val unknownSql = if (sessionId == null) {
            "SELECT COUNT(*) FROM observations WHERE page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other')"
        } else {
            "SELECT COUNT(*) FROM observations WHERE session_id=? AND (page_type_guess IS NULL OR page_type_guess IN ('','jinhak-other'))"
        }
        fun scalar(sql: String): Int = readableDatabase.rawQuery(sql, args).use { c -> if (c.moveToFirst()) c.getInt(0) else 0 }
        return JSONObject()
            .put("observations", scalar(totalSql))
            .put("unknownOrPotential", scalar(unknownSql))
    }
'''
if old not in s:
    raise SystemExit('observationStats generated anchor missing')
s = s.replace(old, new, 1)
STORE.write_text(s)
