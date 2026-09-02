from pathlib import Path

MAIN = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
SNAP = Path('app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt')
NAV = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakAgentNavigator.kt')
GRADLE = Path('app/build.gradle.kts')
MANIFEST = Path('app/src/main/AndroidManifest.xml')


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label} anchor not found')
    return text.replace(old, new, 1)


main = MAIN.read_text()
snap = SNAP.read_text()
nav = NAV.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

# ---------------------------------------------------------------------------
# v0.9.1: mission-first recovery from real-device v0.9.0 evidence.
# - promote same-card dynamic report controls, not only href anchors;
# - seed mission identity from already-normalized saved-application records;
# - bind only when exactly one trusted identity matches the same-card text;
# - preserve ledger/coverage across a re-entrant Jinhak batch start inside the
#   same unified session;
# - export non-secret login-preflight telemetry so E2E can be verified.
# ---------------------------------------------------------------------------

# Versioning.
main = replace_once(
    main,
    '        private const val VERSION = "0.9.0"\n        private const val BUILD_CODE = 10900\n',
    '        private const val VERSION = "0.9.1"\n        private const val BUILD_CODE = 10910\n',
    'main version'
)
gradle = replace_once(gradle, '        versionCode = 10900\n        versionName = "0.9.0"\n', '        versionCode = 10910\n        versionName = "0.9.1"\n', 'gradle version')
manifest = replace_once(manifest, 'android:label="Admission Collector v0.9.0 Auto Login Orchestrator"', 'android:label="Admission Collector v0.9.1 Mission Bootstrap Recovery"', 'manifest label')

# Runtime/session telemetry fields. No credential value is stored or exported.
main = replace_once(
    main,
    '    private var startupLoginTrigger = ""\n',
    '    private var startupLoginTrigger = ""\n'
    '    private var startupLoginAdigaRestoredLease = false\n'
    '    private var startupLoginJinhakRestoredLease = false\n'
    '    private var startupLoginAdigaAuthenticated = false\n'
    '    private var startupLoginJinhakAuthenticated = false\n'
    '    private var startupLoginUiOpenCount = 0\n'
    '    private var startupLoginVerifiedAtMs = 0L\n'
    '    private var jinhakBatchStartCount = 0\n'
    '    private val jinhakNormalizedMissionSeedContexts = linkedMapOf<String, JinhakApplicationMission.Context>()\n'
    '    private val jinhakNormalizedIdentitySeedKeys = linkedSetOf<String>()\n'
    '    private val jinhakNormalizedCandidateBindingKeys = linkedSetOf<String>()\n'
    '    private var jinhakNormalizedAmbiguousBindings = 0\n',
    'v091 telemetry fields'
)

# Reset login telemetry when a new preflight starts.
main = replace_once(
    main,
    '        startupLoginTrigger = trigger.take(40)\n        startupLoginPollGeneration += 1\n',
    '        startupLoginTrigger = trigger.take(40)\n'
    '        startupLoginAdigaRestoredLease = false\n'
    '        startupLoginJinhakRestoredLease = false\n'
    '        startupLoginAdigaAuthenticated = false\n'
    '        startupLoginJinhakAuthenticated = false\n'
    '        startupLoginUiOpenCount = 0\n'
    '        startupLoginVerifiedAtMs = 0L\n'
    '        startupLoginPollGeneration += 1\n',
    'login telemetry reset'
)

# Record whether the existing Android-keystore session lease was actually restored.
main = replace_once(
    main,
    '        val lease = runCatching { sessionVault.restore(which.wireName) }.getOrNull()\n        sessionState.text = if (lease?.restored == true) {\n',
    '        val lease = runCatching { sessionVault.restore(which.wireName) }.getOrNull()\n'
    '        if (which == ProviderId.ADIGA) {\n'
    '            startupLoginAdigaRestoredLease = lease?.restored == true\n'
    '        } else {\n'
    '            startupLoginJinhakRestoredLease = lease?.restored == true\n'
    '        }\n'
    '        sessionState.text = if (lease?.restored == true) {\n',
    'login restored lease telemetry'
)

# Count only a visible login UI open action; no form values are inspected.
main = replace_once(
    main,
    '            val action = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull()\n            when (action?.optString("action")) {\n',
    '            val action = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull()\n'
    '            if (action?.optString("action") == "url" || action?.optString("action") == "clicked") {\n'
    '                startupLoginUiOpenCount += 1\n'
    '            }\n'
    '            when (action?.optString("action")) {\n',
    'login ui telemetry'
)

# Record provider-authenticated state and final verification time.
main = replace_once(
    main,
    '    private fun onStartupProviderAuthenticated(expectedProvider: ProviderId, generation: Int) {\n        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return\n        startupLoginPollGeneration += 1\n',
    '    private fun onStartupProviderAuthenticated(expectedProvider: ProviderId, generation: Int) {\n'
    '        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return\n'
    '        if (expectedProvider == ProviderId.ADIGA) startupLoginAdigaAuthenticated = true else startupLoginJinhakAuthenticated = true\n'
    '        startupLoginPollGeneration += 1\n',
    'login provider authenticated telemetry'
)
main = replace_once(
    main,
    '            startupLoginPreflightActive = false\n            startupLoginPreflightVerified = true\n            startupLoginStage = "verified"\n',
    '            startupLoginPreflightActive = false\n'
    '            startupLoginPreflightVerified = true\n'
    '            startupLoginVerifiedAtMs = System.currentTimeMillis()\n'
    '            startupLoginStage = "verified"\n',
    'login verified timestamp'
)

# Persist safe login-preflight telemetry into the exported PRECHECK diagnostics.
main = replace_once(
    main,
    '        localStore.recordSyncState(sessionId, UnifiedSyncState.PRECHECK.name, null, JSONObject().put("collectorVersion", VERSION), false)\n',
    '        localStore.recordSyncState(\n'
    '            sessionId, UnifiedSyncState.PRECHECK.name, null,\n'
    '            JSONObject()\n'
    '                .put("collectorVersion", VERSION)\n'
    '                .put("loginPreflight", JSONObject()\n'
    '                    .put("verified", startupLoginPreflightVerified)\n'
    '                    .put("adigaAuthenticated", startupLoginAdigaAuthenticated)\n'
    '                    .put("jinhakAuthenticated", startupLoginJinhakAuthenticated)\n'
    '                    .put("adigaRestoredLease", startupLoginAdigaRestoredLease)\n'
    '                    .put("jinhakRestoredLease", startupLoginJinhakRestoredLease)\n'
    '                    .put("loginUiOpenCount", startupLoginUiOpenCount)\n'
    '                    .put("verifiedAtMs", startupLoginVerifiedAtMs)\n'
    '                    .put("credentialStored", false)),\n'
    '            false\n'
    '        )\n',
    'precheck login telemetry'
)

# A new unified Jinhak phase owns a fresh persistent mission identity cache.
main = replace_once(
    main,
    '        unifiedAutoCaptureScheduled = false\n        unifiedJinhakCapturedPages.clear()\n\n        provider = ProviderId.JINHAK\n',
    '        unifiedAutoCaptureScheduled = false\n'
    '        unifiedJinhakCapturedPages.clear()\n'
    '        jinhakBatchStartCount = 0\n'
    '        jinhakNormalizedMissionSeedContexts.clear()\n'
    '        jinhakNormalizedIdentitySeedKeys.clear()\n'
    '        jinhakNormalizedCandidateBindingKeys.clear()\n'
    '        jinhakNormalizedAmbiguousBindings = 0\n\n'
    '        provider = ProviderId.JINHAK\n',
    'jinhak unified phase reset'
)

# Detect re-entrant batch initialization. Preserve mission ledger/coverage inside
# the same unified session rather than silently discarding already-proven work.
main = replace_once(
    main,
    '        if (startupLoginPreflightActive) {\n            Toast.makeText(this, "로그인 준비가 끝난 뒤 수집이 자동 시작됩니다.", Toast.LENGTH_SHORT).show()\n            return\n        }\n        val url = webView.url\n',
    '        if (startupLoginPreflightActive) {\n'
    '            Toast.makeText(this, "로그인 준비가 끝난 뒤 수집이 자동 시작됩니다.", Toast.LENGTH_SHORT).show()\n'
    '            return\n'
    '        }\n'
    '        val preserveJinhakMissionState = provider == ProviderId.JINHAK && unifiedRunning && jinhakBatchStartCount > 0\n'
    '        if (provider == ProviderId.JINHAK) {\n'
    '            jinhakBatchStartCount += 1\n'
    '            recordRuntimeEvent("jinhak-batch-start", JSONObject()\n'
    '                .put("count", jinhakBatchStartCount)\n'
    '                .put("preserveMissionState", preserveJinhakMissionState))\n'
    '        }\n'
    '        val url = webView.url\n',
    'batch reentry telemetry'
)
main = replace_once(
    main,
    '        jinhakMissionCoverage.clear()\n        jinhakMissionTargetLedger.clear()\n',
    '        if (!preserveJinhakMissionState) {\n'
    '            jinhakMissionCoverage.clear()\n'
    '            jinhakMissionTargetLedger.clear()\n'
    '        }\n',
    'preserve mission state on reentry'
)
main = replace_once(
    main,
    '        jinhakReportConfirmedKeys.clear()\n',
    '        if (!preserveJinhakMissionState) jinhakReportConfirmedKeys.clear()\n',
    'preserve report confirmations on reentry'
)

# Seed application identity from already-normalized saved-application records,
# then use that trusted identity only as a unique same-card fallback.
main = replace_once(
    main,
    '                val parsedMissionCandidates = JinhakAgentNavigator.candidates(snapshot)\n',
    '                val rawMissionCandidates = JinhakAgentNavigator.candidates(snapshot)\n'
    '                val normalizedMissionSeeds = jinhakMissionContextsFromNormalizedRecords(pageRecords)\n'
    '                normalizedMissionSeeds.forEach { context ->\n'
    '                    val identity = context.identityKey ?: return@forEach\n'
    '                    jinhakNormalizedMissionSeedContexts[identity] = context\n'
    '                    jinhakNormalizedIdentitySeedKeys.add(identity)\n'
    '                    if (pageTypeNow == "jinhak-early-storage") {\n'
    '                        jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() }.add("saved-application")\n'
    '                    }\n'
    '                }\n'
    '                val parsedMissionCandidates = bindJinhakCandidatesFromNormalizedRecords(\n'
    '                    rawMissionCandidates,\n'
    '                    jinhakNormalizedMissionSeedContexts.values.toList()\n'
    '                )\n',
    'normalized mission seed binding'
)

# Export explicit v0.9.1 mission bootstrap diagnostics in both live and final summaries.
needle = '                .put("applicationAnchorStructuredBindings", jinhakMissionAnchorStructuredKeys.size)\n'
replacement = needle + \
    '                .put("normalizedApplicationIdentitySeeds", jinhakNormalizedIdentitySeedKeys.size)\n' \
    '                .put("normalizedApplicationCandidateBindings", jinhakNormalizedCandidateBindingKeys.size)\n' \
    '                .put("normalizedApplicationAmbiguousBindings", jinhakNormalizedAmbiguousBindings)\n' \
    '                .put("jinhakBatchStartCount", jinhakBatchStartCount)\n'
if main.count(needle) < 1:
    raise SystemExit('live structured diagnostic anchor not found')
main = main.replace(needle, replacement)

needle2 = '                        .put("applicationAnchorStructuredBindings", jinhakMissionAnchorStructuredKeys.size)\n'
replacement2 = needle2 + \
    '                        .put("normalizedApplicationIdentitySeeds", jinhakNormalizedIdentitySeedKeys.size)\n' \
    '                        .put("normalizedApplicationCandidateBindings", jinhakNormalizedCandidateBindingKeys.size)\n' \
    '                        .put("normalizedApplicationAmbiguousBindings", jinhakNormalizedAmbiguousBindings)\n' \
    '                        .put("jinhakBatchStartCount", jinhakBatchStartCount)\n'
if needle2 in main:
    main = main.replace(needle2, replacement2)

# Helpers are deliberately bounded to normalized records produced from the same
# rendered snapshot. They never inspect cookies, DOM storage, form values, or
# neighbouring-card data.
marker = '    private fun normalizeSnapshot(snapshot: JSONObject): JSONArray =\n'
if marker not in main:
    raise SystemExit('normalizeSnapshot helper insertion marker not found')
helper = r'''    private fun jinhakMissionContextsFromNormalizedRecords(records: JSONArray): List<JinhakApplicationMission.Context> {
        val out = linkedMapOf<String, JinhakApplicationMission.Context>()
        for (i in 0 until records.length()) {
            val record = records.optJSONObject(i) ?: continue
            if (record.optString("recordType") != "jinhak-saved-application-prediction") continue
            val identity = record.optString("applicationIdentityKey").takeIf { it.isNotBlank() && it != "null" } ?: continue
            val university = record.optString("university").takeIf { it.isNotBlank() && it != "null" } ?: continue
            val department = record.optString("department").takeIf { it.isNotBlank() && it != "null" } ?: continue
            val admission = record.optString("admission").takeIf { it.isNotBlank() && it != "null" }
            val metrics = record.optJSONObject("metrics") ?: JSONObject()
            val category = metrics.optString("admissionCategory").takeIf { it.isNotBlank() && it != "null" }
            val campus = metrics.optString("campus").takeIf { it.isNotBlank() && it != "null" }
            val capacity = if (metrics.has("capacity") && !metrics.isNull("capacity")) metrics.optInt("capacity").takeIf { it >= 0 } else null
            out.putIfAbsent(
                identity,
                JinhakApplicationMission.Context(
                    year = record.optInt("year", 2027),
                    university = university,
                    admissionCategory = category,
                    admission = admission,
                    campus = campus,
                    departmentRaw = department,
                    capacity = capacity,
                    identityKey = identity,
                    parseSource = "normalized-saved-application-record",
                    confidence = record.optString("confidence", "medium").ifBlank { "medium" },
                    rawCombinedLabel = null
                )
            )
        }
        return out.values.toList()
    }

    private fun jinhakMissionMatchToken(value: String?): String =
        value.orEmpty().lowercase()
            .replace(" ", "")
            .replace("\t", "")
            .replace("\n", "")
            .replace("·", "")
            .replace("・", "")
            .replace("ㆍ", "")
            .replace("[", "")
            .replace("]", "")
            .replace("(", "")
            .replace(")", "")
            .replace("-", "")
            .replace("_", "")
            .replace(".", "")
            .replace("|", "")
            .replace(":", "")

    private fun bindJinhakCandidatesFromNormalizedRecords(
        candidates: List<JinhakAgentNavigator.Candidate>,
        seeds: List<JinhakApplicationMission.Context>
    ): List<JinhakAgentNavigator.Candidate> {
        if (seeds.isEmpty()) return candidates
        return candidates.map { candidate ->
            if (candidate.applicationContext?.identityKey != null || !candidate.promotedMissionAction) return@map candidate
            if (candidate.applicationBindingSource != "same-card-root" && candidate.applicationBindingSource != "unique-card-container") return@map candidate
            val haystack = jinhakMissionMatchToken(candidate.contextText)
            if (haystack.isBlank()) return@map candidate
            val matches = seeds.filter { context ->
                val university = jinhakMissionMatchToken(context.university)
                val department = jinhakMissionMatchToken(context.departmentRaw)
                val admission = jinhakMissionMatchToken(context.admission)
                university.isNotBlank() && department.isNotBlank() &&
                    haystack.contains(university) && haystack.contains(department) &&
                    (admission.isBlank() || haystack.contains(admission))
            }.distinctBy { it.identityKey }
            if (matches.size != 1) {
                if (matches.size > 1) jinhakNormalizedAmbiguousBindings += 1
                return@map candidate
            }
            val context = matches.single()
            val identity = context.identityKey ?: return@map candidate
            jinhakNormalizedCandidateBindingKeys.add(
                RecordUtils.sha256(listOf(identity, candidate.label, candidate.scanIndex.toString()).joinToString("|"))
            )
            candidate.copy(
                applicationContext = context,
                missionPriority = maxOf(candidate.missionPriority, 210),
                promotedMissionAction = true
            )
        }
    }

'''
main = main.replace(marker, helper + marker, 1)

# ---------------------------------------------------------------------------
# Snapshot: same-card dynamic controls (e.g. a JS/SPA "리포트" button) are mission
# controls even when they do not expose an href. Read-only allow/block policy is
# unchanged; cross-card/sibling inference remains prohibited.
# ---------------------------------------------------------------------------
snap = replace_once(
    snap,
    "      var missionLink=!!route && String(a.tagName||'').toUpperCase()==='A' && applicationContext.length>0;\n",
    "      var missionLink=!!route && String(a.tagName||'').toUpperCase()==='A' && applicationContext.length>0;\n"
    "      var missionBoundControl=applicationContext.length>0 && !!label && !agentBlocked.test(label+' '+meta2) && agentAllowed.test(label);\n",
    'mission bound control declaration'
)
snap = replace_once(
    snap,
    '      if(missionLink && missionAnchorDiscovery.length<160){\n',
    '      if(missionBoundControl && missionAnchorDiscovery.length<160){\n',
    'mission discovery promotion'
)
snap = replace_once(
    snap,
    "          missionAnchorDiscovery.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:'mission-link-navigation',contextText:applicationContext,applicationUniversity:applicationBinding.university,applicationDepartment:applicationBinding.department,applicationBindingSource:applicationBinding.source});\n",
    "          missionAnchorDiscovery.push({scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:missionLink?'mission-link-navigation':'mission-bound-control',contextText:applicationContext,applicationUniversity:applicationBinding.university,applicationDepartment:applicationBinding.department,applicationBindingSource:applicationBinding.source});\n",
    'mission discovery kind'
)
snap = replace_once(
    snap,
    "        var entry={scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:missionLink?'mission-link-navigation':(role==='tab'?'tab-navigation':'read-navigation'),contextText:applicationContext,applicationUniversity:applicationBinding.university,applicationDepartment:applicationBinding.department,applicationBindingSource:applicationBinding.source};\n",
    "        var entry={scanIndex:li,label:label,tag:String(a.tagName||'').slice(0,20),kind:missionLink?'mission-link-navigation':(missionBoundControl?'mission-bound-control':(role==='tab'?'tab-navigation':'read-navigation')),contextText:applicationContext,applicationUniversity:applicationBinding.university,applicationDepartment:applicationBinding.department,applicationBindingSource:applicationBinding.source};\n",
    'mission entry kind'
)
snap = replace_once(
    snap,
    '        if(missionLink && missionAgentActions.length<120 && !seenMissionAgentAction[ak]){\n',
    '        if(missionBoundControl && missionAgentActions.length<120 && !seenMissionAgentAction[ak]){\n',
    'mission agent promotion'
)

# ---------------------------------------------------------------------------
# Navigator: retain binding provenance so normalized-record fallback is allowed
# only for exact same-card / uniquely-bounded card contexts.
# ---------------------------------------------------------------------------
nav = replace_once(
    nav,
    '        val applicationContext: JinhakApplicationMission.Context?,\n        val promotedMissionAction: Boolean = false\n',
    '        val applicationContext: JinhakApplicationMission.Context?,\n'
    '        val promotedMissionAction: Boolean = false,\n'
    '        val applicationBindingSource: String = ""\n',
    'candidate binding source field'
)
nav = replace_once(
    nav,
    '                val explicitDepartment = obj.optString("applicationDepartment")\n                    .replace(Regex("\\\\s+"), " ").trim().take(120).takeIf { it.isNotBlank() }\n                val app = JinhakApplicationMission.parseCard(\n',
    '                val explicitDepartment = obj.optString("applicationDepartment")\n'
    '                    .replace(Regex("\\\\s+"), " ").trim().take(120).takeIf { it.isNotBlank() }\n'
    '                val applicationBindingSource = obj.optString("applicationBindingSource")\n'
    '                    .replace(Regex("\\\\s+"), " ").trim().take(40)\n'
    '                val app = JinhakApplicationMission.parseCard(\n',
    'navigator binding source parse'
)
nav = replace_once(
    nav,
    '                if (kind == "mission-link-navigation" && app?.identityKey != null) priority += 35\n                if (promoted && app?.identityKey != null) priority += 45\n                out += Candidate(scanIndex, label, tag, kind, priority.coerceIn(0, 220), contextText, app, promoted)\n',
    '                if (kind == "mission-link-navigation" && app?.identityKey != null) priority += 35\n'
    '                if (kind == "mission-bound-control" && app?.identityKey != null) priority += 35\n'
    '                if (promoted && app?.identityKey != null) priority += 45\n'
    '                out += Candidate(scanIndex, label, tag, kind, priority.coerceIn(0, 220), contextText, app, promoted, applicationBindingSource)\n',
    'navigator candidate construction'
)

MAIN.write_text(main)
SNAP.write_text(snap)
NAV.write_text(nav)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)
print('v0.9.1 mission bootstrap recovery patch applied')
