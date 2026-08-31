from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
STORE = ROOT / 'app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected 1 anchor, found {count}')
    return text.replace(old, new, 1)

# ---------------------------------------------------------------------------
# 1) Jinhak: route-first classification and evidence-first table normalization.
# ---------------------------------------------------------------------------
j = JINHAK.read_text()

j = replace_once(
    j,
    '    private const val TARGET_YEAR = 2027\n',
    '''    private const val TARGET_YEAR = 2027
    private val TABLE_EVIDENCE_PAGE_TYPES = setOf(
        "jinhak-home",
        "jinhak-other",
        "jinhak-editorial-content",
        "jinhak-admission-strategy",
        "jinhak-admission-feature",
        "jinhak-media-content",
        "jinhak-curation",
        "jinhak-university-search"
    )
''',
    'table evidence type set'
)

j = replace_once(
    j,
    '        val editorialContent = Regex("(학과\\\\s*심층분석|대학\\\\s*심층분석|대학학과\\\\s*심층분석|지도로\\\\s*보는\\\\s*대학|대학교\\\\s*지도|캠퍼스맵)").containsMatchIn(pageTitle)\n',
    '''        val strategyRoute = path.contains("/univ-entrance-info/ipsi-analysis/ipsi-strategy")
        val featureRoute = path.contains("/univ-entrance-info/susi-special")
        val mediaRoute = path.contains("/jinhak-tv")
        val deepAnalysisRoute = path.contains("/univ-major/major-info/major-deep-analysis") ||
            path.contains("/univ-entrance-info/ipsi-analysis/ipsi-deep-analysis")
        val editorialContent = Regex("(학과\\s*심층분석|대학\\s*심층분석|대학학과\\s*심층분석|지도로\\s*보는\\s*대학|대학교\\s*지도|캠퍼스맵)").containsMatchIn(pageTitle)
''',
    'route class flags'
)

j = replace_once(
    j,
    '        val dedicatedMinimum = url.contains("esatminuniv") || Regex("(수능최저|최저학력기준)").containsMatchIn(headingText)\n',
    '''        // v0.7.1 showed that broad heading-text matching mislabeled strategy/articles
        // as a dedicated SAT-minimum tool. Only known dedicated routes may receive this type.
        val dedicatedMinimum = url.contains("esatminuniv") ||
            path.contains("/sat-minimum") || path.contains("/minimum-requirement")
''',
    'dedicated minimum route gate'
)

j = replace_once(
    j,
    '''            navigationError -> "jinhak-navigation-error"
            universityAdmissionInfo -> "jinhak-university-admission-info"
            editorialContent -> "jinhak-editorial-content"
            rootPage -> "jinhak-home"
''',
    '''            navigationError -> "jinhak-navigation-error"
            universityAdmissionInfo -> "jinhak-university-admission-info"
            strategyRoute -> "jinhak-admission-strategy"
            featureRoute -> "jinhak-admission-feature"
            mediaRoute -> "jinhak-media-content"
            deepAnalysisRoute || editorialContent -> "jinhak-editorial-content"
            rootPage -> "jinhak-home"
''',
    'route-first classify order'
)

j = replace_once(
    j,
    '''        if (pageType == "jinhak-university-admission-info") {
            return normalizeUniversityAdmissionInfo(snapshot, observedAt)
        }

        if (pageType == "jinhak-early-storage" || pageType == "jinhak-recommended-university") {
''',
    '''        if (pageType == "jinhak-university-admission-info") {
            return normalizeUniversityAdmissionInfo(snapshot, observedAt)
        }

        // Observation-first does not mean parser-last. v0.7.1 preserved 200+ tables but
        // most article/home/reference tables never became spreadsheet-ready rows. Convert
        // only explicit table cells; never invent missing university/department/admission.
        if (pageType in TABLE_EVIDENCE_PAGE_TYPES) {
            return normalizeTableEvidence(snapshot, pageType, observedAt)
        }

        if (pageType == "jinhak-early-storage" || pageType == "jinhak-recommended-university") {
''',
    'table evidence normalization entry'
)

j = replace_once(
    j,
    '''        if (pageType == "jinhak-home" || pageType == "jinhak-university-search" || pageType == "jinhak-curation" ||
            pageType == "jinhak-other" || pageType == "jinhak-editorial-content" || pageType == "jinhak-navigation-error") {
            return result
        }
''',
    '''        if (pageType == "jinhak-home" || pageType == "jinhak-university-search" || pageType == "jinhak-curation" ||
            pageType == "jinhak-other" || pageType == "jinhak-editorial-content" ||
            pageType == "jinhak-admission-strategy" || pageType == "jinhak-admission-feature" ||
            pageType == "jinhak-media-content" || pageType == "jinhak-navigation-error") {
            return result
        }
''',
    'reference early return types'
)

j = replace_once(
    j,
    '''        val generic = GenericAdmissionParser.normalize(snapshot)
        for (i in 0 until generic.length()) {
''',
    '''        // Generic page-wide inference is intentionally gated. v0.7.1 produced false
        // bindings from article table headers (for example a literal 70% header becoming grade=70).
        val generic = if (pageType in setOf("jinhak-actual-admit-report", "jinhak-score-calc-report")) {
            GenericAdmissionParser.normalize(snapshot)
        } else JSONArray()
        for (i in 0 until generic.length()) {
''',
    'generic parser gate'
)

j = replace_once(
    j,
    '''        "jinhak-sat-minimum" -> "current-admission"
        "jinhak-score-calc-report", "jinhak-student-basic" -> "student-profile"
        "jinhak-home", "jinhak-university-search", "jinhak-curation" -> "reference-navigation"
        else -> "reference"
''',
    '''        "jinhak-sat-minimum" -> "current-admission"
        "jinhak-score-calc-report", "jinhak-student-basic" -> "student-profile"
        "jinhak-home", "jinhak-university-search", "jinhak-curation" -> "reference-navigation"
        "jinhak-admission-strategy", "jinhak-admission-feature", "jinhak-editorial-content", "jinhak-media-content" -> "admission-reference"
        else -> "reference"
''',
    'data scope reference types'
)

helper_anchor = '    private fun predictionMetrics(text: String): JSONObject {\n'
helper_code = r'''    private fun normalizeTableEvidence(snapshot: JSONObject, pageType: String, observedAt: String): JSONArray {
        val out = JSONArray()
        val tables = snapshot.optJSONArray("tables") ?: return out
        val title = snapshot.optString("title").replace(Regex("\\s+"), " ").trim()
        val explicitUniversity = Regex("([가-힣A-Za-z0-9·.&()\\-]{2,45}(?:대학교|교육대학교|과학기술원)(?:\\([^)]+\\))?)")
            .find(title)?.groupValues?.getOrNull(1)?.trim()?.takeIf { it.isNotBlank() }
        val titleYear = Regex("(20[0-9]{2})\\s*학년도").find(title)?.groupValues?.getOrNull(1)?.toIntOrNull()
            ?: Regex("(?<![0-9])(20[0-9]{2})(?![0-9])").find(title)?.groupValues?.getOrNull(1)?.toIntOrNull()

        fun cleanCell(value: String): String = value.replace(Regex("\\s+"), " ").trim().take(1200)
        fun relevantHeader(cells: List<String>): Boolean {
            val h = cells.joinToString(" | ")
            val metric = Regex("(경쟁률|모의지원|합격예측|적정지원컷|평균점|모집인원|지원자|충원|충원율|50%|70%|등급|환산점수|합격선|순위)")
            val identity = Regex("(전형|학과명|모집단위|대학명|학부|전공)")
            return metric.containsMatchIn(h) && identity.containsMatchIn(h)
        }
        fun uniqueHeader(raw: String, index: Int, used: MutableSet<String>): String {
            val base = cleanCell(raw).ifBlank { "column${index + 1}" }
            var key = base
            var suffix = 2
            while (!used.add(key)) { key = "$base#$suffix"; suffix += 1 }
            return key
        }
        fun numeric(raw: String): Double? = Regex("-?[0-9]+(?:\\.[0-9]+)?").find(raw.replace(",", ""))?.value?.toDoubleOrNull()

        for (ti in 0 until minOf(tables.length(), 32)) {
            val rows = tables.optJSONObject(ti)?.optJSONArray("rows") ?: continue
            if (rows.length() < 2) continue
            val headerRow = rows.optJSONArray(0) ?: continue
            val headers = mutableListOf<String>()
            val used = linkedSetOf<String>()
            for (ci in 0 until minOf(headerRow.length(), 36)) headers += uniqueHeader(headerRow.optString(ci), ci, used)
            if (!relevantHeader(headers)) continue
            val headerText = headers.joinToString(" | ")
            val tableYear = Regex("(20[0-9]{2})\\s*학년도").find(headerText)?.groupValues?.getOrNull(1)?.toIntOrNull() ?: titleYear
            val predictionLike = Regex("(모의지원|합격예측|적정지원컷|내\\s*점수|칸)").containsMatchIn(headerText)
            val historicalLike = !predictionLike && (tableYear != null || Regex("(입시결과|충원|50%|70%|등급)").containsMatchIn(title + " " + headerText))
            val scope = when {
                predictionLike -> "current-prediction-reference"
                historicalLike -> "historical-reference"
                else -> "admission-reference"
            }

            for (ri in 1 until minOf(rows.length(), 220)) {
                val row = rows.optJSONArray(ri) ?: continue
                val cells = mutableListOf<String>()
                for (ci in 0 until minOf(row.length(), headers.size)) cells += cleanCell(row.optString(ci))
                if (cells.all { it.isBlank() }) continue
                if (cells.joinToString("|") == headers.joinToString("|")) continue

                val columns = JSONObject()
                for (ci in cells.indices) if (cells[ci].isNotBlank()) columns.put(headers[ci], cells[ci])
                if (columns.length() < 2) continue

                var department: String? = null
                var admission: String? = null
                var combined: String? = null
                for (ci in headers.indices) {
                    val h = headers[ci]
                    val v = cells.getOrNull(ci)?.takeIf { it.isNotBlank() } ?: continue
                    when {
                        h.contains("전형/학과") || h.contains("전형/모집단위") -> combined = v
                        (h == "모집단위" || h.contains("학과명") || h == "학과" || h == "전공") -> department = v
                        (h == "전형" || h.contains("전형명")) -> admission = v
                    }
                }

                val metrics = JSONObject().put("columns", columns)
                combined?.let { metrics.put("combinedAdmissionDepartmentLabel", it) }
                for (ci in headers.indices) {
                    val h = headers[ci]
                    val v = cells.getOrNull(ci).orEmpty()
                    val n = numeric(v) ?: continue
                    when {
                        h.contains("전년도") && h.contains("경쟁률") -> metrics.put("previousCompetition", n)
                        h.contains("모의지원") && h.contains("경쟁률") -> metrics.put("mockCompetition", n)
                        h.contains("경쟁률") -> metrics.put("competition", n)
                        h.contains("모의지원자") && h.contains("평균점") -> metrics.put("mockApplicantAverageScore", n)
                        h.contains("적정지원컷") || h.contains("합격예측") && h.contains("컷") -> metrics.put("predictedSupportCut", n)
                        h.contains("모집인원") -> metrics.put("capacity", n)
                        h.contains("지원자") -> metrics.put("applicants", n)
                        h.contains("충원율") -> metrics.put("fillRate", n)
                        h.contains("충원") -> metrics.put("additionalAdmits", n)
                        h.contains("50%") -> metrics.put("cut50", n)
                        h.contains("70%") -> metrics.put("cut70", n)
                        h.contains("평균") && h.contains("등급") -> metrics.put("averageGrade", n)
                    }
                }

                val record = JSONObject()
                    .put("recordType", "jinhak-table-evidence")
                    .put("providerPageType", pageType)
                    .put("dataScope", scope)
                    .put("year", tableYear ?: JSONObject.NULL)
                    .put("university", explicitUniversity ?: JSONObject.NULL)
                    .put("department", department ?: JSONObject.NULL)
                    .put("admission", admission ?: JSONObject.NULL)
                    .put("metrics", metrics)
                    .put("observedAt", observedAt)
                    .put("tableIndex", ti)
                    .put("rowOrdinal", ri)
                    .put("confidence", if (explicitUniversity != null || department != null || admission != null) "medium" else "raw")
                    .put("sourcePage", safePath(snapshot.optString("url")))
                    .put("rawEvidence", cells.joinToString(" | ").take(5000))
                record.put("sourceRowFingerprint", fingerprint(record, observedAt, preserveSnapshot = predictionLike))
                out.put(record)
            }
        }
        return RecordUtils.dedupe(out)
    }

'''
j = replace_once(j, helper_anchor, helper_code + helper_anchor, 'insert table evidence parser')
JINHAK.write_text(j)

# ---------------------------------------------------------------------------
# 2) MainActivity: separate observation retention from navigation expansion.
#    Repeated exact rendered states remain observed, but their outgoing links are
#    expanded only once. Same URL with changed context/content remains expandable.
# ---------------------------------------------------------------------------
m = MAIN.read_text()
m = replace_once(
    m,
    '    private val jinhakAgentActionSeen = linkedSetOf<String>()\n',
    '''    private val jinhakAgentActionSeen = linkedSetOf<String>()
    private val jinhakExpandedNavigationStates = linkedSetOf<String>()
    private var jinhakRepeatedNavigationStateSkips = 0
    private var jinhakUniqueNavigationStates = 0
''',
    'navigation state fields'
)

m = replace_once(
    m,
    '''        jinhakAgentActionSeen.clear()
        jinhakAgentActionInFlight = false
        jinhakAgentActionsExecuted = 0
''',
    '''        jinhakAgentActionSeen.clear()
        jinhakExpandedNavigationStates.clear()
        jinhakRepeatedNavigationStateSkips = 0
        jinhakUniqueNavigationStates = 0
        jinhakAgentActionInFlight = false
        jinhakAgentActionsExecuted = 0
''',
    'navigation state reset'
)

m = replace_once(
    m,
    '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) jinhakConsecutiveStalls = 0
            if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {
''',
    '''            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) jinhakConsecutiveStalls = 0
            var jinhakExpansionStateKey: String? = null
            var jinhakExpandOutgoingLinks = true
            if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {
''',
    'expansion state locals'
)

m = replace_once(
    m,
    '''                    val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                    val pageKey = RecordUtils.sha256(navKey)
                    localStore.storeUnifiedAnalysisCapture(
''',
    '''                    val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                    val pageKey = RecordUtils.sha256(navKey)
                    val safeRoute = runtimeSafePath(snapshot.optString("url"))
                    val explicitContext = ObservationEvidence.explicitContextFromDigest(digest)
                    val expansionIdentity = ObservationEvidence.identity(
                        ProviderId.JINHAK.wireName, safeRoute, explicitContext, digest
                    )
                    jinhakExpansionStateKey = expansionIdentity.observationId
                    jinhakExpandOutgoingLinks = jinhakExpandedNavigationStates.add(expansionIdentity.observationId)
                    if (jinhakExpandOutgoingLinks) {
                        jinhakUniqueNavigationStates += 1
                    } else {
                        jinhakRepeatedNavigationStateSkips += 1
                        recordRuntimeEvent("jinhak-repeat-state-expansion-skip", JSONObject()
                            .put("safePath", safeRoute)
                            .put("pageType", snapshot.optString("providerPageType")))
                    }
                    localStore.storeUnifiedAnalysisCapture(
''',
    'expansion identity computation'
)

m = replace_once(
    m,
    '''            if (activeAction == null || pageType == "adiga-university-list") {
                enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
            }
''',
    '''            if (activeAction == null || pageType == "adiga-university-list") {
                if (provider != ProviderId.JINHAK || jinhakExpandOutgoingLinks) {
                    enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
                }
            }
''',
    'gate discovered link expansion'
)

m = replace_once(
    m,
    '''            if (provider == ProviderId.JINHAK && activeAction == null && maybeExecuteJinhakAgentAction(snapshot)) {
                return@collectSnapshot
            }
''',
    '''            if (provider == ProviderId.JINHAK && activeAction == null && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {
                return@collectSnapshot
            }
''',
    'agent state key call'
)

m = replace_once(
    m,
    '''    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject): Boolean {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return false
        if (jinhakAgentActionInFlight || jinhakAgentActionsExecuted >= MAX_JINHAK_AGENT_ACTIONS) return false
        val route = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        val candidate = JinhakAgentNavigator.candidates(snapshot).firstOrNull { action ->
            !jinhakAgentActionSeen.contains(JinhakAgentNavigator.key(route, action))
        } ?: return false
        val actionKey = JinhakAgentNavigator.key(route, candidate)
''',
    '''    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject, expansionStateKey: String?): Boolean {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return false
        if (jinhakAgentActionInFlight || jinhakAgentActionsExecuted >= MAX_JINHAK_AGENT_ACTIONS) return false
        val route = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        fun actionKeyFor(action: JinhakAgentNavigator.Candidate): String = RecordUtils.sha256(
            "${expansionStateKey ?: runtimeSafePath(route)}|${JinhakAgentNavigator.key(route, action)}"
        )
        val candidate = JinhakAgentNavigator.candidates(snapshot).firstOrNull { action ->
            !jinhakAgentActionSeen.contains(actionKeyFor(action))
        } ?: return false
        val actionKey = actionKeyFor(candidate)
''',
    'agent state-aware identity'
)

m = replace_once(
    m,
    '''                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)
                .put("cloudFrontierPublished", cloudFrontierPublished)
''',
    '''                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)
                .put("jinhakUniqueNavigationStates", jinhakUniqueNavigationStates)
                .put("jinhakRepeatedNavigationStateSkips", jinhakRepeatedNavigationStateSkips)
                .put("cloudFrontierPublished", cloudFrontierPublished)
''',
    'batch summary navigation diagnostics'
)

m = replace_once(
    m,
    '''            if (sessionId != null) {
                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }
                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "jinhak:$effectiveReason")
            }
            handler.postDelayed({ finishUnifiedCollection("jinhak:$effectiveReason") }, 350L)
''',
    '''            if (sessionId != null) {
                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }
                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "jinhak:$effectiveReason")
                localStore.recordSyncState(
                    sessionId,
                    "JINHAK_CRAWL_DIAGNOSTICS",
                    ProviderId.JINHAK.wireName,
                    JSONObject()
                        .put("attemptedSnapshots", batchPageCount)
                        .put("successfulSnapshots", batchSnapshots.length())
                        .put("errorEvents", batchErrors.length())
                        .put("uniqueNavigationExpansionStates", jinhakUniqueNavigationStates)
                        .put("repeatedNavigationStateSkips", jinhakRepeatedNavigationStateSkips)
                        .put("agentActionsExecuted", jinhakAgentActionsExecuted)
                        .put("cloudFrontierPublished", cloudFrontierPublished)
                        .put("cloudFrontierClaimed", cloudFrontierClaimed),
                    false
                )
            }
            handler.postDelayed({ finishUnifiedCollection("jinhak:$effectiveReason") }, 350L)
''',
    'persist crawl diagnostics'
)
MAIN.write_text(m)

# ---------------------------------------------------------------------------
# 3) Export: make the promised Errors/Coverage workbook sheets reproducible.
# ---------------------------------------------------------------------------
s = STORE.read_text()

write_obs_end = '''        fun writeObservations() {
            writer.write("[")
            var first = true
            readableDatabase.rawQuery(
                "SELECT observation_id,provider,safe_route_key,page_type_guess,page_type_confidence,auth_state_class,explicit_context_json,content_fingerprint,context_fingerprint,capture_version,evidence_json,reprocess_state,first_observed_at,last_observed_at,seen_count FROM observations WHERE session_id=? ORDER BY last_observed_at,observation_id",
                arrayOf(sessionId)
            ).use { c ->
                while (c.moveToNext()) {
                    if (!first) writer.write(",")
                    first = false
                    writer.write("{\\\"observationId\\\":")
                    writeNullableString(c.getString(0))
                    writer.write(",\\\"provider\\\":")
                    writeNullableString(c.getString(1))
                    writer.write(",\\\"safeRouteKey\\\":")
                    writeNullableString(c.getString(2))
                    writer.write(",\\\"pageTypeGuess\\\":")
                    writeNullableString(if (c.isNull(3)) null else c.getString(3))
                    writer.write(",\\\"pageTypeConfidence\\\":${c.getDouble(4)}")
                    writer.write(",\\\"authStateClass\\\":")
                    writeNullableString(if (c.isNull(5)) null else c.getString(5))
                    writer.write(",\\\"explicitContext\\\":${c.getString(6)}")
                    writer.write(",\\\"contentFingerprint\\\":")
                    writeNullableString(c.getString(7))
                    writer.write(",\\\"contextFingerprint\\\":")
                    writeNullableString(c.getString(8))
                    writer.write(",\\\"captureVersion\\\":")
                    writeNullableString(c.getString(9))
                    writer.write(",\\\"evidence\\\":${c.getString(10)}")
                    writer.write(",\\\"reprocessState\\\":")
                    writeNullableString(c.getString(11))
                    writer.write(",\\\"firstObservedAt\\\":")
                    writeNullableString(c.getString(12))
                    writer.write(",\\\"lastObservedAt\\\":")
                    writeNullableString(c.getString(13))
                    writer.write(",\\\"seenCount\\\":${c.getInt(14)}}")
                }
            }
            writer.write("]")
        }
'''

extra_writers = r'''
        fun safeNavigationEvidence(raw: String?): String? {
            if (raw.isNullOrBlank()) return null
            return try {
                val uri = java.net.URI(raw)
                val host = uri.host.orEmpty().lowercase()
                val path = uri.path.orEmpty().ifBlank { "/" }
                if (host.isBlank()) path.substringBefore('?').take(500) else "$host$path".take(500)
            } catch (_: Exception) { raw.substringBefore('?').substringBefore('#').take(500) }
        }
        fun writeErrors(runId: String?) {
            writer.write("{\"documents\":[")
            var firstDocument = true
            if (runId != null) {
                readableDatabase.rawQuery(
                    "SELECT navigation_key,state,error_type,retry_count,updated_at FROM documents WHERE run_id=? AND (state!='completed' OR error_type IS NOT NULL) ORDER BY updated_at,navigation_key",
                    arrayOf(runId)
                ).use { c ->
                    while (c.moveToNext()) {
                        if (!firstDocument) writer.write(",")
                        firstDocument = false
                        writer.write("{\"safePath\":")
                        writeNullableString(safeNavigationEvidence(c.getString(0)))
                        writer.write(",\"state\":")
                        writeNullableString(c.getString(1))
                        writer.write(",\"errorType\":")
                        writeNullableString(if (c.isNull(2)) null else c.getString(2))
                        writer.write(",\"retryCount\":${c.getInt(3)},\"updatedAt\":")
                        writeNullableString(c.getString(4))
                        writer.write("}")
                    }
                }
            }
            writer.write("],\"pages\":[")
            var firstPage = true
            if (runId != null) {
                readableDatabase.rawQuery(
                    "SELECT family_key,requested_year,page,total_pages,state,error_type,retry_count,updated_at FROM pages WHERE run_id=? AND (state!='completed' OR error_type IS NOT NULL) ORDER BY updated_at,family_key,page",
                    arrayOf(runId)
                ).use { c ->
                    while (c.moveToNext()) {
                        if (!firstPage) writer.write(",")
                        firstPage = false
                        writer.write("{\"familyKey\":")
                        writeNullableString(safeNavigationEvidence(c.getString(0)))
                        writer.write(",\"requestedYear\":${c.getInt(1)},\"page\":${c.getInt(2)},\"totalPages\":${c.getInt(3)},\"state\":")
                        writeNullableString(c.getString(4))
                        writer.write(",\"errorType\":")
                        writeNullableString(if (c.isNull(5)) null else c.getString(5))
                        writer.write(",\"retryCount\":${c.getInt(6)},\"updatedAt\":")
                        writeNullableString(c.getString(7))
                        writer.write("}")
                    }
                }
            }
            writer.write("]}")
        }
        fun writeSyncDiagnostics() {
            writer.write("[")
            var first = true
            readableDatabase.rawQuery(
                "SELECT state,provider,requires_user_action,detail_json,created_at FROM sync_state_events WHERE session_id=? ORDER BY created_at,event_id",
                arrayOf(sessionId)
            ).use { c ->
                while (c.moveToNext()) {
                    if (!first) writer.write(",")
                    first = false
                    writer.write("{\"state\":")
                    writeNullableString(c.getString(0))
                    writer.write(",\"provider\":")
                    writeNullableString(if (c.isNull(1)) null else c.getString(1))
                    writer.write(",\"requiresUserAction\":${c.getInt(2) != 0},\"detail\":${c.getString(3)},\"createdAt\":")
                    writeNullableString(c.getString(4))
                    writer.write("}")
                }
            }
            writer.write("]")
        }
'''

s = replace_once(s, write_obs_end, write_obs_end + extra_writers, 'export helper insertion')

s = replace_once(
    s,
    'writer.write(",\\\"analysisReady\\\":{\\\"contractVersion\\\":1,\\\"purpose\\\":\\\"assistant-xlsx-dashboard-generation\\\",\\\"authoritativeLayers\\\":[\\\"sources.adiga.records\\\",\\\"sources.jinhak.records\\\",\\\"sources.jinhak.pageAnalyses\\\",\\\"observationEvidence\\\"],',
    'writer.write(",\\\"analysisReady\\\":{\\\"contractVersion\\\":2,\\\"purpose\\\":\\\"assistant-xlsx-dashboard-generation\\\",\\\"authoritativeLayers\\\":[\\\"sources.adiga.records\\\",\\\"sources.jinhak.records\\\",\\\"sources.jinhak.pageAnalyses\\\",\\\"observationEvidence\\\",\\\"errorEvidence\\\",\\\"syncDiagnostics\\\"],',
    'analysis ready v2'
)

s = replace_once(
    s,
    '''        writer.write("}},\\\"observationEvidence\\\":")
        writeObservations()
        writer.write("}")
''',
    '''        writer.write("}},\\\"observationEvidence\\\":")
        writeObservations()
        writer.write(",\\\"errorEvidence\\\":{\\\"adiga\\\":")
        writeErrors(adigaRun)
        writer.write(",\\\"jinhak\\\":")
        writeErrors(jinhakRun)
        writer.write("},\\\"syncDiagnostics\\\":")
        writeSyncDiagnostics()
        writer.write("}")
''',
    'stream error diagnostics export'
)
STORE.write_text(s)

print('Applied v0.8.0 post-v0.7.1 quality patch: route-first classification, table evidence, state expansion gate, error/diagnostic export')
