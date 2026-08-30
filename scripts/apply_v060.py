from pathlib import Path

ROOT = Path('.')
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
LOCAL = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# -----------------------------------------------------------------------------
# 1) Gate A conclusion: do not inherit a department from neighboring prediction
#    cards. v0.5.8 proved those candidates were mostly other prediction cards.
#    Keep only card-root or explicit ancestor attributes as department context.
# -----------------------------------------------------------------------------
s = SNAP.read_text()
start = s.find('    function departmentContextFor(el,rootText){')
probe = s.find('    function departmentProbeFor(el,rootText){', start)
if start < 0 or probe < 0:
    raise SystemExit('v0.5.8 department context/probe anchors missing')
explicit_department = r'''    function departmentContextFor(el,rootText){
      var direct=explicitDepartmentNames(rootText);
      if(direct.length===1) return {name:direct[0],source:'card-root',depth:0};
      var cur=el;
      for(var depth=0;cur&&depth<8;depth++,cur=cur.parentElement){
        var attrs=cleanText((cur.getAttribute&&cur.getAttribute('aria-label')||'')+' '+(cur.getAttribute&&cur.getAttribute('title')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-dept-name')||'')+' '+(cur.getAttribute&&cur.getAttribute('data-department-name')||''));
        var an=explicitDepartmentNames(attrs);
        if(an.length===1) return {name:an[0],source:'ancestor-attribute',depth:depth};
      }
      return {name:'',source:'missing',depth:-1};
    }

'''
s = s[:start] + explicit_department + s[probe:]

# Remove the v0.5.7-v0.5.8 diagnostic-only department probe function.
probe_start = s.find('    function departmentProbeFor(el,rootText){')
probe_end = s.find('    function universityContextFor(el,rootText){', probe_start)
if probe_start < 0 or probe_end < 0:
    raise SystemExit('department probe removal anchors missing')
s = s[:probe_start] + s[probe_end:]

old_stats = 'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0,departmentProbeCards:0,departmentProbeCandidates:0};'
new_stats = 'var jinhakCardStats={metricSeeds:0,candidateRoots:0,uniqueRoots:0,universityBoundRoots:0,universityContextRoots:0,universityMissingRoots:0,departmentBoundRoots:0,departmentContextRoots:0,departmentMissingRoots:0};'
if old_stats not in s:
    raise SystemExit('v0.5.8 jinhak stats anchor missing')
s = s.replace(old_stats, new_stats, 1)

old_ctx = '''      var universityCtx=universityContextFor(entry.el,entry.text);
      var departmentCtx=departmentContextFor(entry.el,entry.text);
      var departmentProbe=departmentProbeFor(entry.el,entry.text);
      jinhakCardStats.departmentProbeCards++;
      jinhakCardStats.departmentProbeCandidates+=departmentProbe.length;'''
new_ctx = '''      var universityCtx=universityContextFor(entry.el,entry.text);
      var departmentCtx=departmentContextFor(entry.el,entry.text);'''
if old_ctx not in s:
    raise SystemExit('v0.5.8 card probe invocation anchor missing')
s = s.replace(old_ctx, new_ctx, 1)

old_push = '''        department:departmentCtx.name,
        departmentSource:departmentCtx.source,
        departmentDepth:departmentCtx.depth,
        departmentProbe:departmentProbe
      });'''
new_push = '''        department:departmentCtx.name,
        departmentSource:departmentCtx.source,
        departmentDepth:departmentCtx.depth
      });'''
if old_push not in s:
    raise SystemExit('v0.5.8 card probe payload anchor missing')
s = s.replace(old_push, new_push, 1)
SNAP.write_text(s)

# -----------------------------------------------------------------------------
# 2) Current-screen full semantic analysis bundle.
#    This is still user-triggered/on-demand. It sends no DOM/HTML, URL, cookie,
#    session token, form value or raw credential. Only admission-related visible
#    text already captured by SnapshotScript is sanitized and size-bounded.
# -----------------------------------------------------------------------------
for p in MAIN_FILES:
    m = p.read_text()

    # Stamp every Jinhak record with parser-version/quality metadata before local storage.
    old_stamp = '''            val records = normalizeSnapshot(snapshot)
            val collectedAt = Instant.now().toString()
            var localStats = JSONObject()'''
    new_stamp = '''            val records = normalizeSnapshot(snapshot)
            val collectedAt = Instant.now().toString()
            if (provider == ProviderId.JINHAK) {
                for (ri in 0 until records.length()) {
                    val r = records.optJSONObject(ri) ?: continue
                    val confidence = r.optString("confidence")
                    r.put("captureVersion", VERSION)
                        .put("analysisScope", "current-rendered-page-user-triggered")
                        .put("qualityState", if (confidence == "high") "accepted" else "provisional")
                    val year = if (r.isNull("year")) "" else r.optInt("year").toString()
                    val university = if (r.isNull("university")) "" else r.optString("university")
                    val department = if (r.isNull("department")) "" else r.optString("department")
                    val admission = if (r.isNull("admission")) "" else r.optString("admission")
                    if (university.isNotBlank() && department.isNotBlank() && admission.isNotBlank()) {
                        r.put("applicationIdentityKey", RecordUtils.sha256(listOf(year, university, department, admission).joinToString("|")))
                    } else {
                        r.put("applicationIdentityKey", JSONObject.NULL)
                    }
                }
            }
            var localStats = JSONObject()'''
    if old_stamp not in m:
        raise SystemExit(f'collectCurrentPage stamp anchor missing: {p}')
    m = m.replace(old_stamp, new_stamp, 1)

    start = m.find('    private fun buildJinhakDigest(snapshot: JSONObject, records: JSONArray, runId: String, collectedAt: String): JSONObject {')
    end = m.find('    private fun sendLatestJinhakAnalysisDigest() {', start)
    if start < 0 or end < 0:
        raise SystemExit(f'buildJinhakDigest anchors missing: {p}')

    full_digest = r'''    private fun sanitizeJinhakAnalysisText(value: String, maxLen: Int): String {
        if (maxLen <= 0) return ""
        var text = value.replace(Regex("""\s+"""), " ").trim()
        if (text.isBlank()) return ""
        text = text.replace(Regex("""(?i)[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"""), "[redacted-email]")
        text = text.replace(Regex("""(?<!\d)01[016789][-\s]?\d{3,4}[-\s]?\d{4}(?!\d)"""), "[redacted-phone]")
        text = text.replace(Regex("""(?<!\d)\d{6}[-\s]?[1-4]\d{6}(?!\d)"""), "[redacted-id]")
        text = text.replace(Regex("""(?i)(?:password|passwd|비밀번호)\s*[:：=]?\s*\S+"""), "[redacted-credential]")
        text = text.replace(Regex("""(?i)(?:user(?:name|id)?|아이디|회원번호)\s*[:：=]\s*[A-Za-z0-9._@-]{3,}"""), "[redacted-account]")
        return text.take(maxLen)
    }

    private fun buildJinhakDigest(snapshot: JSONObject, records: JSONArray, runId: String, collectedAt: String): JSONObject {
        val sanitizedRecords = JSONArray()
        var universityBound = 0
        var departmentBound = 0
        var admissionBound = 0
        var fullyBound = 0

        for (i in 0 until records.length()) {
            val r = records.optJSONObject(i) ?: continue
            val hasUniversity = !r.isNull("university") && r.optString("university").isNotBlank()
            val hasDepartment = !r.isNull("department") && r.optString("department").isNotBlank()
            val hasAdmission = !r.isNull("admission") && r.optString("admission").isNotBlank()
            if (hasUniversity) universityBound += 1
            if (hasDepartment) departmentBound += 1
            if (hasAdmission) admissionBound += 1
            if (hasUniversity && hasDepartment && hasAdmission) fullyBound += 1
        }

        val recordLimit = minOf(records.length(), 160)
        for (i in 0 until recordLimit) {
            val r = records.optJSONObject(i) ?: continue
            sanitizedRecords.put(JSONObject()
                .put("recordType", r.optString("recordType"))
                .put("providerPageType", r.optString("providerPageType"))
                .put("dataScope", r.optString("dataScope"))
                .put("year", if (r.isNull("year")) JSONObject.NULL else r.optInt("year"))
                .put("university", if (r.isNull("university")) JSONObject.NULL else r.optString("university"))
                .put("department", if (r.isNull("department")) JSONObject.NULL else r.optString("department"))
                .put("admission", if (r.isNull("admission")) JSONObject.NULL else r.optString("admission"))
                .put("metrics", r.optJSONObject("metrics") ?: JSONObject())
                .put("confidence", r.optString("confidence"))
                .put("qualityState", r.optString("qualityState", "provisional"))
                .put("captureVersion", r.optString("captureVersion", VERSION))
                .put("analysisScope", r.optString("analysisScope", "current-rendered-page-user-triggered"))
                .put("applicationIdentityKey", if (r.isNull("applicationIdentityKey")) JSONObject.NULL else r.optString("applicationIdentityKey"))
                .put("observedAt", r.optString("observedAt", collectedAt))
                .put("cardIndex", if (r.has("cardIndex")) r.optInt("cardIndex") else JSONObject.NULL)
                .put("contextSource", r.optString("contextSource"))
                .put("universityContextSource", if (r.isNull("universityContextSource")) JSONObject.NULL else r.optString("universityContextSource"))
                .put("universityContextDepth", r.optInt("universityContextDepth", -1))
                .put("departmentContextSource", if (r.isNull("departmentContextSource")) JSONObject.NULL else r.optString("departmentContextSource"))
                .put("departmentContextDepth", r.optInt("departmentContextDepth", -1)))
        }

        val textBudgetLimit = 180_000
        var remainingBudget = textBudgetLimit
        var capturedTextCharacters = 0
        fun budgeted(raw: String, maxLen: Int): String {
            if (remainingBudget <= 0) return ""
            val clean = sanitizeJinhakAnalysisText(raw, minOf(maxLen, remainingBudget))
            if (clean.isBlank()) return ""
            remainingBudget -= clean.length
            capturedTextCharacters += clean.length
            return clean
        }

        val safeContext = JSONArray()
        val rawContext = snapshot.optJSONArray("context") ?: JSONArray()
        for (i in 0 until minOf(rawContext.length(), 80)) {
            val value = budgeted(rawContext.optString(i), 700)
            if (value.isNotBlank()) safeContext.put(value)
            if (remainingBudget <= 0) break
        }

        val safeSelection = JSONArray()
        val rawSelection = snapshot.optJSONArray("selectionContext") ?: JSONArray()
        for (i in 0 until minOf(rawSelection.length(), 80)) {
            val value = budgeted(rawSelection.optString(i), 700)
            if (value.isNotBlank()) safeSelection.put(value)
            if (remainingBudget <= 0) break
        }

        val safeCards = JSONArray()
        val cards = snapshot.optJSONArray("jinhakCards") ?: JSONArray()
        for (i in 0 until minOf(cards.length(), 100)) {
            if (remainingBudget <= 0) break
            val card = cards.optJSONObject(i) ?: continue
            val visibleText = budgeted(card.optString("text"), 2400)
            if (visibleText.isBlank()) continue
            safeCards.put(JSONObject()
                .put("cardIndex", i)
                .put("rootTag", card.optString("rootTag").take(20))
                .put("rootScore", card.optInt("score", 0))
                .put("primaryPrediction", card.optBoolean("primaryPrediction", false))
                .put("university", card.optString("university").take(80).ifBlank { JSONObject.NULL })
                .put("universitySource", card.optString("universitySource").take(40).ifBlank { JSONObject.NULL })
                .put("universityDepth", card.optInt("universityDepth", -1))
                .put("department", card.optString("department").take(80).ifBlank { JSONObject.NULL })
                .put("departmentSource", card.optString("departmentSource").take(40).ifBlank { JSONObject.NULL })
                .put("departmentDepth", card.optInt("departmentDepth", -1))
                .put("visibleText", visibleText))
        }

        val safeTables = JSONArray()
        val tables = snapshot.optJSONArray("tables") ?: JSONArray()
        for (ti in 0 until minOf(tables.length(), 24)) {
            if (remainingBudget <= 0) break
            val table = tables.optJSONObject(ti) ?: continue
            val outRows = JSONArray()
            val rows = table.optJSONArray("rows") ?: JSONArray()
            for (ri in 0 until minOf(rows.length(), 100)) {
                if (remainingBudget <= 0) break
                val row = rows.optJSONArray(ri) ?: continue
                val outCells = JSONArray()
                for (ci in 0 until minOf(row.length(), 32)) {
                    val cell = budgeted(row.optString(ci), 700)
                    if (cell.isNotBlank()) outCells.put(cell)
                    if (remainingBudget <= 0) break
                }
                if (outCells.length() > 0) outRows.put(outCells)
            }
            val caption = budgeted(table.optString("caption"), 700)
            if (outRows.length() > 0 || caption.isNotBlank()) {
                safeTables.put(JSONObject()
                    .put("caption", if (caption.isBlank()) JSONObject.NULL else caption)
                    .put("rows", outRows))
            }
        }

        val safeBlocks = JSONArray()
        val blocks = snapshot.optJSONArray("blocks") ?: JSONArray()
        for (i in 0 until minOf(blocks.length(), 160)) {
            if (remainingBudget <= 0) break
            val value = budgeted(blocks.optString(i), 1400)
            if (value.isNotBlank()) safeBlocks.put(value)
        }

        val resourceLabels = JSONArray()
        val resources = snapshot.optJSONArray("resourceLinks") ?: JSONArray()
        for (i in 0 until minOf(resources.length(), 80)) {
            if (remainingBudget <= 0) break
            val label = budgeted(resources.optJSONObject(i)?.optString("label") ?: "", 500)
            if (label.isNotBlank()) resourceLabels.put(label)
        }

        val analysisBundle = JSONObject()
            .put("scope", "current-rendered-page-user-triggered")
            .put("pageType", snapshot.optString("providerPageType"))
            .put("pageTitle", budgeted(snapshot.optString("title"), 500))
            .put("context", safeContext)
            .put("selectionContext", safeSelection)
            .put("cards", safeCards)
            .put("tables", safeTables)
            .put("blocks", safeBlocks)
            .put("resourceLabels", resourceLabels)
            .put("coverage", JSONObject()
                .put("sourceCards", cards.length())
                .put("capturedCards", safeCards.length())
                .put("sourceTables", tables.length())
                .put("capturedTables", safeTables.length())
                .put("sourceBlocks", blocks.length())
                .put("capturedBlocks", safeBlocks.length())
                .put("capturedTextCharacters", capturedTextCharacters)
                .put("textBudgetLimit", textBudgetLimit)
                .put("budgetExhausted", remainingBudget <= 0))

        return JSONObject()
            .put("schemaVersion", 2)
            .put("type", "jinhak-full-screen-analysis")
            .put("pageType", snapshot.optString("providerPageType"))
            .put("collectedAt", collectedAt)
            .put("recordCount", records.length())
            .put("detectedStorageCards", cards.length())
            .put("cardCaptureStats", snapshot.optJSONObject("jinhakCardStats") ?: JSONObject())
            .put("bindingStats", JSONObject()
                .put("universityBound", universityBound)
                .put("departmentBound", departmentBound)
                .put("admissionBound", admissionBound)
                .put("fullyBound", fullyBound)
                .put("totalRecords", records.length()))
            .put("includedRecords", sanitizedRecords.length())
            .put("recordsTruncated", records.length() > sanitizedRecords.length())
            .put("localStats", localStore.stats(runId))
            .put("records", sanitizedRecords)
            .put("analysisBundle", analysisBundle)
            .put("privacy", "sanitized-visible-admission-text-no-dom-no-html-no-url-no-cookie-no-session-token-no-form-values-no-credential")
    }

'''
    m = m[:start] + full_digest + m[end:]

    # UI wording now reflects substantive current-screen analysis, not a probe.
    m = m.replace('현재 진학사 화면 분석·누적', '현재 진학사 화면 전체 분석·누적')
    m = m.replace('진학사 분석 전송', '진학사 전체 분석 전송')
    m = m.replace('진학사 화면의 과거입결·예측·성적지표를 분석 중…', '진학사 현재 화면의 카드·표·세부 설명·예측지표를 전체 분석 중…')
    m = m.replace('진학사 분석·누적 완료:', '진학사 전체 분석 준비 완료:')
    m = m.replace('진학사 구조화 분석 결과 전송 중… DOM·쿠키·로그인 정보는 보내지 않습니다.', '진학사 전체 분석 번들 전송 중… DOM·URL·쿠키·로그인 자격정보·폼 값은 보내지 않습니다.')
    m = m.replace('진학사 분석 전송 완료:', '진학사 전체 분석 전송 완료:')
    m = m.replace('진학사 분석 전송 완료', '진학사 전체 분석 전송 완료')
    m = m.replace('진학사 분석 전송 실패:', '진학사 전체 분석 전송 실패:')
    m = m.replace('진학사 분석 전송 실패', '진학사 전체 분석 전송 실패')

    if 'private const val VERSION = "0.5.8"' not in m or 'private const val BUILD_CODE = 10580' not in m:
        raise SystemExit(f'v0.5.8 version anchors missing: {p}')
    m = m.replace('private const val VERSION = "0.5.8"', 'private const val VERSION = "0.6.0"', 1)
    m = m.replace('private const val BUILD_CODE = 10580', 'private const val BUILD_CODE = 10600', 1)
    p.write_text(m)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirrors diverged')

# -----------------------------------------------------------------------------
# 3) Gate B minimum integrity redesign: SQLite v2 + record provenance fields +
#    Jinhak parser-version isolation. Adiga resume behavior remains unchanged.
# -----------------------------------------------------------------------------
l = LOCAL.read_text()
l = l.replace('    1\n) {', '    2\n) {', 1)

old_records = '''            CREATE TABLE records(
              run_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL,
              provider TEXT NOT NULL,
              record_type TEXT,
              year INTEGER,
              university TEXT,
              department TEXT,
              admission TEXT,
              json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(run_id, fingerprint)
            )'''
new_records = '''            CREATE TABLE records(
              run_id TEXT NOT NULL,
              fingerprint TEXT NOT NULL,
              provider TEXT NOT NULL,
              record_type TEXT,
              year INTEGER,
              university TEXT,
              department TEXT,
              admission TEXT,
              capture_version TEXT,
              data_scope TEXT,
              observed_at TEXT,
              quality_state TEXT,
              provider_entity_id TEXT,
              canonical_university_id TEXT,
              canonical_department_id TEXT,
              canonical_admission_id TEXT,
              application_identity_key TEXT,
              json TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(run_id, fingerprint)
            )'''
if old_records not in l:
    raise SystemExit('LocalCollectorStore records schema anchor missing')
l = l.replace(old_records, new_records, 1)

old_upgrade = '    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) = Unit\n'
new_upgrade = '''    override fun onUpgrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        if (oldVersion < 2) {
            val additions = listOf(
                "capture_version TEXT",
                "data_scope TEXT",
                "observed_at TEXT",
                "quality_state TEXT",
                "provider_entity_id TEXT",
                "canonical_university_id TEXT",
                "canonical_department_id TEXT",
                "canonical_admission_id TEXT",
                "application_identity_key TEXT"
            )
            for (column in additions) db.execSQL("ALTER TABLE records ADD COLUMN $column")
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_records_run_quality ON records(run_id,quality_state)")
            db.execSQL("CREATE INDEX IF NOT EXISTS idx_records_application_identity ON records(run_id,application_identity_key)")
        }
    }
'''
if old_upgrade not in l:
    raise SystemExit('LocalCollectorStore onUpgrade anchor missing')
l = l.replace(old_upgrade, new_upgrade, 1)

old_begin_start = l.find('    fun beginOrResume(provider: String, collectorVersion: String): String {')
old_begin_end = l.find('    fun latestResumableRun(provider: String): String?', old_begin_start)
if old_begin_start < 0 or old_begin_end < 0:
    raise SystemExit('LocalCollectorStore beginOrResume anchors missing')
new_begin = '''    fun beginOrResume(provider: String, collectorVersion: String): String {
        val db = writableDatabase
        var existingId: String? = null
        var existingVersion: String? = null
        db.rawQuery(
            "SELECT run_id,collector_version FROM runs WHERE provider=? AND status IN ('collecting','stopped','incomplete') ORDER BY updated_at DESC LIMIT 1",
            arrayOf(provider)
        ).use { c ->
            if (c.moveToFirst()) {
                existingId = c.getString(0)
                existingVersion = c.getString(1)
            }
        }
        val now = Instant.now().toString()

        // Jinhak parser generations must never silently mix in one beta run.
        if (provider == "jinhak" && !existingId.isNullOrBlank() && existingVersion != collectorVersion) {
            val close = ContentValues().apply {
                put("status", "stopped")
                put("completion_reason", "parser-version-boundary:${existingVersion ?: "unknown"}->$collectorVersion")
                put("updated_at", now)
            }
            db.update("runs", close, "run_id=?", arrayOf(existingId))
            existingId = null
            existingVersion = null
        }

        if (!existingId.isNullOrBlank()) {
            val cv = ContentValues().apply {
                put("collector_version", collectorVersion)
                put("status", "collecting")
                putNull("completion_reason")
                put("updated_at", now)
            }
            db.update("runs", cv, "run_id=?", arrayOf(existingId))
            return existingId!!
        }

        val id = UUID.randomUUID().toString()
        val cv = ContentValues().apply {
            put("run_id", id)
            put("provider", provider)
            put("collector_version", collectorVersion)
            put("status", "collecting")
            putNull("completion_reason")
            put("started_at", now)
            put("updated_at", now)
        }
        db.insertOrThrow("runs", null, cv)
        return id
    }

'''
l = l[:old_begin_start] + new_begin + l[old_begin_end:]

old_values = '''                    putNullable("university", nullableString(obj, "university"))
                    putNullable("department", nullableString(obj, "department"))
                    putNullable("admission", nullableString(obj, "admission"))
                    put("json", obj.toString())'''
new_values = '''                    putNullable("university", nullableString(obj, "university"))
                    putNullable("department", nullableString(obj, "department"))
                    putNullable("admission", nullableString(obj, "admission"))
                    putNullable("capture_version", nullableString(obj, "captureVersion"))
                    putNullable("data_scope", nullableString(obj, "dataScope"))
                    putNullable("observed_at", nullableString(obj, "observedAt"))
                    putNullable("quality_state", nullableString(obj, "qualityState"))
                    putNullable("provider_entity_id", nullableString(obj, "providerEntityId"))
                    putNullable("canonical_university_id", nullableString(obj, "canonicalUniversityId"))
                    putNullable("canonical_department_id", nullableString(obj, "canonicalDepartmentId"))
                    putNullable("canonical_admission_id", nullableString(obj, "canonicalAdmissionId"))
                    putNullable("application_identity_key", nullableString(obj, "applicationIdentityKey"))
                    put("json", obj.toString())'''
if old_values not in l:
    raise SystemExit('LocalCollectorStore storeRecords anchor missing')
l = l.replace(old_values, new_values, 1)

old_stats_return = '''        return JSONObject()
            .put("runId", runId)
            .put("records", scalar("SELECT COUNT(*) FROM records WHERE run_id=?"))
            .put("completedPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='completed'"))'''
new_stats_return = '''        return JSONObject()
            .put("runId", runId)
            .put("records", scalar("SELECT COUNT(*) FROM records WHERE run_id=?"))
            .put("acceptedRecords", scalar("SELECT COUNT(*) FROM records WHERE run_id=? AND quality_state='accepted'"))
            .put("provisionalRecords", scalar("SELECT COUNT(*) FROM records WHERE run_id=? AND quality_state='provisional'"))
            .put("completedPages", scalar("SELECT COUNT(*) FROM pages WHERE run_id=? AND state='completed'"))'''
if old_stats_return not in l:
    raise SystemExit('LocalCollectorStore stats anchor missing')
l = l.replace(old_stats_return, new_stats_return, 1)
LOCAL.write_text(l)

# Android version/label.
g = GRADLE.read_text()
if 'versionCode = 10580' not in g or 'versionName = "0.5.8"' not in g:
    raise SystemExit('v0.5.8 Gradle anchors missing')
g = g.replace('versionCode = 10580', 'versionCode = 10600', 1)
g = g.replace('versionName = "0.5.8"', 'versionName = "0.6.0"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
if 'Admission Collector v0.5.8 Jinhak Department Boundary Probe' not in mf:
    raise SystemExit('v0.5.8 manifest anchor missing')
mf = mf.replace(
    'Admission Collector v0.5.8 Jinhak Department Boundary Probe',
    'Admission Collector v0.6.0 Jinhak Full Screen Analyzer',
    1,
)
MANIFEST.write_text(mf)

print('v0.6.0 Jinhak full screen analyzer patch applied')
