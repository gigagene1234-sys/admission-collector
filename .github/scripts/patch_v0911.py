from pathlib import Path
import re

main_path = Path('app/src/main/java/com/admissionhub/collector/MainActivity.kt')
ledger_path = Path('app/src/main/java/com/admissionhub/collector/jinhak/JinhakMissionTargetLedger.kt')
store_path = Path('app/src/main/java/com/admissionhub/collector/local/LocalCollectorStore.kt')
gradle_path = Path('app/build.gradle.kts')
manifest_path = Path('app/src/main/AndroidManifest.xml')

m = main_path.read_text()
l = ledger_path.read_text()
s = store_path.read_text()
g = gradle_path.read_text()
manifest = manifest_path.read_text()

# -----------------------------------------------------------------------------
# JinhakMissionTargetLedger: persistence payload + monotonic state transitions.
# -----------------------------------------------------------------------------
anchor = '    private val targets = linkedMapOf<String, Target>()\n\n    fun clear() = targets.clear()\n'
insert = '''    private val targets = linkedMapOf<String, Target>()
    private var mutationListener: ((JSONObject) -> Unit)? = null

    fun setMutationListener(listener: ((JSONObject) -> Unit)?) {
        mutationListener = listener
    }

    fun clear() = targets.clear()

    /** Restore persisted targets without emitting new persistence callbacks. */
    fun restorePersisted(payloads: List<JSONObject>): Int {
        var restored = 0
        for (payload in payloads) {
            val incoming = targetFromPersistenceJson(payload) ?: continue
            val existing = targets[incoming.targetId]
            if (existing == null) {
                targets[incoming.targetId] = incoming
                restored += 1
                continue
            }
            if (stateRank(incoming.state) > stateRank(existing.state)) {
                existing.state = incoming.state
                existing.failureReason = incoming.failureReason
            }
            existing.attempts = maxOf(existing.attempts, incoming.attempts)
            if (incoming.updatedAtMs > existing.updatedAtMs) {
                existing.scanIndex = incoming.scanIndex
                existing.tag = incoming.tag
                existing.missionPriority = maxOf(existing.missionPriority, incoming.missionPriority)
                existing.contextText = incoming.contextText
                existing.applicationContext = incoming.applicationContext
                existing.updatedAtMs = incoming.updatedAtMs
            }
            restored += 1
        }
        return restored
    }

    fun confirmedCoverage(): Map<String, Set<String>> {
        val result = linkedMapOf<String, MutableSet<String>>()
        targets.values.filter { it.state == State.CONFIRMED }.forEach { target ->
            result.getOrPut(target.identityKey) { linkedSetOf() }.add(target.lane)
        }
        return result
    }

    private fun persistenceJson(target: Target): JSONObject = JSONObject()
        .put("schemaVersion", 1)
        .put("targetId", target.targetId)
        .put("identityKey", target.identityKey)
        .put("lane", target.lane)
        .put("label", target.label)
        .put("kind", target.kind)
        .put("originRoute", target.originRoute)
        .put("scanIndex", target.scanIndex)
        .put("tag", target.tag)
        .put("missionPriority", target.missionPriority)
        .put("contextText", target.contextText)
        .put("applicationContext", target.applicationContext.toJson())
        .put("state", target.state.name.lowercase())
        .put("attempts", target.attempts)
        .put("failureReason", target.failureReason ?: JSONObject.NULL)
        .put("updatedAtMs", target.updatedAtMs)

    private fun targetFromPersistenceJson(obj: JSONObject): Target? {
        val targetId = obj.optString("targetId").takeIf { it.isNotBlank() && it != "null" } ?: return null
        val identityKey = obj.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: return null
        val lane = obj.optString("lane").takeIf { it.isNotBlank() && it != "reference" && it != "null" } ?: return null
        val context = JinhakApplicationMission.fromJson(obj.optJSONObject("applicationContext")) ?: return null
        if (context.identityKey != identityKey) return null
        val state = runCatching { State.valueOf(obj.optString("state", "pending").uppercase()) }.getOrDefault(State.PENDING)
        return Target(
            targetId = targetId,
            identityKey = identityKey,
            lane = lane,
            label = obj.optString("label").take(160),
            kind = obj.optString("kind").take(80),
            originRoute = obj.optString("originRoute").take(1200),
            scanIndex = obj.optInt("scanIndex", -1),
            tag = obj.optString("tag").take(80),
            missionPriority = obj.optInt("missionPriority", 180),
            contextText = obj.optString("contextText").take(6000),
            applicationContext = context,
            state = state,
            attempts = obj.optInt("attempts", 0).coerceAtLeast(0),
            failureReason = obj.optString("failureReason").takeIf { it.isNotBlank() && it != "null" }?.take(100),
            updatedAtMs = obj.optLong("updatedAtMs", System.currentTimeMillis())
        )
    }

    private fun stateRank(state: State): Int = when (state) {
        State.PENDING -> 0
        State.CLICKED -> 10
        State.DEFERRED -> 20
        State.FAILED -> 30
        State.SKIPPED -> 40
        State.CONFIRMED -> 50
    }

    private fun canTransition(from: State, to: State): Boolean = stateRank(to) >= stateRank(from)

    private fun notifyMutation(target: Target) {
        mutationListener?.invoke(persistenceJson(target))
    }
'''
if anchor not in l:
    raise SystemExit('ledger targets anchor not found')
l = l.replace(anchor, insert, 1)

# Persist capture refreshes/additions. 30 targets are tiny; persisting all visible targets makes
# capture atomic from the runtime point of view and prevents a lifecycle gap between rows.
old = '        return added\n    }\n\n    fun hasMission(identityKey: String?): Boolean'
new = '        targets.values.forEach(::notifyMutation)\n        return added\n    }\n\n    fun hasMission(identityKey: String?): Boolean'
if old not in l:
    raise SystemExit('ledger capture return anchor not found')
l = l.replace(old, new, 1)

# Reconcile mutations must be persisted.
old = '''        }.forEach {
            it.state = State.SKIPPED
            it.failureReason = "lane-already-covered"
            it.updatedAtMs = System.currentTimeMillis()
        }
    }
'''
new = '''        }.forEach {
            it.state = State.SKIPPED
            it.failureReason = "lane-already-covered"
            it.updatedAtMs = System.currentTimeMillis()
            notifyMutation(it)
        }
    }
'''
if old not in l:
    raise SystemExit('ledger reconcile anchor not found')
l = l.replace(old, new, 1)

# Replace individual state mutators with monotonic + persisted versions.
old = '''    fun markAttempted(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.attempts += 1
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }

    fun markClicked(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.state = State.CLICKED
        target.failureReason = null
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }

    fun markDeferred(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.state = State.DEFERRED
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }
'''
new = '''    fun markAttempted(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.attempts += 1
        target.updatedAtMs = System.currentTimeMillis()
        notifyMutation(target)
        return true
    }

    fun markClicked(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        if (!canTransition(target.state, State.CLICKED)) return false
        target.state = State.CLICKED
        target.failureReason = null
        target.updatedAtMs = System.currentTimeMillis()
        notifyMutation(target)
        return true
    }

    fun markDeferred(targetId: String?): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        if (!canTransition(target.state, State.DEFERRED)) return false
        target.state = State.DEFERRED
        target.updatedAtMs = System.currentTimeMillis()
        notifyMutation(target)
        return true
    }
'''
if old not in l:
    raise SystemExit('ledger basic mutator anchor not found')
l = l.replace(old, new, 1)

old = '''    fun markConfirmed(targetId: String?, identityKey: String?, lane: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        if (identityKey.isNullOrBlank() || target.identityKey != identityKey || lane == "reference" || target.lane != lane) return false
        target.state = State.CONFIRMED
        target.failureReason = null
        target.updatedAtMs = System.currentTimeMillis()
        // One confirmed lane is sufficient. Keep alternate same-lane entry points as evidence but
        // do not click them after the report has already been proven for this application.
        targets.values.filter {
            it.targetId != target.targetId && it.identityKey == target.identityKey && it.lane == target.lane && it.state == State.PENDING
        }.forEach {
            it.state = State.SKIPPED
            it.failureReason = "lane-confirmed-by-alternate-target"
            it.updatedAtMs = System.currentTimeMillis()
        }
        return true
    }

    fun markFailed(targetId: String?, reason: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        target.state = State.FAILED
        target.failureReason = reason.take(100)
        target.updatedAtMs = System.currentTimeMillis()
        return true
    }
'''
new = '''    fun markConfirmed(targetId: String?, identityKey: String?, lane: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        if (identityKey.isNullOrBlank() || target.identityKey != identityKey || lane == "reference" || target.lane != lane) return false
        if (!canTransition(target.state, State.CONFIRMED)) return false
        target.state = State.CONFIRMED
        target.failureReason = null
        target.updatedAtMs = System.currentTimeMillis()
        notifyMutation(target)
        // One confirmed lane is sufficient. Keep alternate same-lane entry points as evidence but
        // do not click them after the report has already been proven for this application.
        targets.values.filter {
            it.targetId != target.targetId && it.identityKey == target.identityKey && it.lane == target.lane && it.state == State.PENDING
        }.forEach {
            it.state = State.SKIPPED
            it.failureReason = "lane-confirmed-by-alternate-target"
            it.updatedAtMs = System.currentTimeMillis()
            notifyMutation(it)
        }
        return true
    }

    fun markFailed(targetId: String?, reason: String): Boolean {
        val target = targetId?.let { targets[it] } ?: return false
        if (!canTransition(target.state, State.FAILED)) return false
        target.state = State.FAILED
        target.failureReason = reason.take(100)
        target.updatedAtMs = System.currentTimeMillis()
        notifyMutation(target)
        return true
    }
'''
if old not in l:
    raise SystemExit('ledger confirmed/failed anchor not found')
l = l.replace(old, new, 1)

old = '''    fun failAllPending(reason: String) {
        targets.values.filter { it.state == State.PENDING }.forEach {
            it.state = State.FAILED
            it.failureReason = reason.take(100)
            it.updatedAtMs = System.currentTimeMillis()
        }
    }
'''
new = '''    fun failAllPending(reason: String) {
        targets.values.filter { it.state == State.PENDING }.forEach {
            it.state = State.FAILED
            it.failureReason = reason.take(100)
            it.updatedAtMs = System.currentTimeMillis()
            notifyMutation(it)
        }
    }
'''
if old not in l:
    raise SystemExit('ledger failAllPending anchor not found')
l = l.replace(old, new, 1)

old = '''        stranded.forEach {
            it.state = State.FAILED
            it.failureReason = reason.take(100)
            it.updatedAtMs = System.currentTimeMillis()
        }
        return stranded.size
'''
new = '''        stranded.forEach {
            it.state = State.FAILED
            it.failureReason = reason.take(100)
            it.updatedAtMs = System.currentTimeMillis()
            notifyMutation(it)
        }
        return stranded.size
'''
if old not in l:
    raise SystemExit('ledger failAllOutstanding anchor not found')
l = l.replace(old, new, 1)

# -----------------------------------------------------------------------------
# LocalCollectorStore: target + minimal runtime SQLite persistence.
# -----------------------------------------------------------------------------
if '"admission_collector_local_v1.db",\n    null,\n    4\n)' not in s:
    raise SystemExit('db version 4 anchor not found')
s = s.replace('"admission_collector_local_v1.db",\n    null,\n    4\n)', '"admission_collector_local_v1.db",\n    null,\n    5\n)', 1)

schema_anchor = '        db.execSQL("CREATE INDEX IF NOT EXISTS idx_adiga_plan_state ON adiga_plan_tasks(state,updated_at)")\n'
schema_insert = schema_anchor + '''

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS jinhak_mission_targets(
              session_id TEXT NOT NULL,
              target_id TEXT NOT NULL,
              identity_key TEXT NOT NULL,
              lane TEXT NOT NULL,
              state TEXT NOT NULL,
              state_rank INTEGER NOT NULL,
              payload_json TEXT NOT NULL,
              first_persisted_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              PRIMARY KEY(session_id,target_id)
            )
        """.trimIndent())
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_jinhak_mission_session_state ON jinhak_mission_targets(session_id,state,state_rank)")
        db.execSQL("CREATE INDEX IF NOT EXISTS idx_jinhak_mission_session_identity ON jinhak_mission_targets(session_id,identity_key,lane)")

        db.execSQL("""
            CREATE TABLE IF NOT EXISTS jinhak_mission_runtime(
              session_id TEXT PRIMARY KEY,
              active_target_id TEXT,
              current_batch_target TEXT,
              mission_origin_route TEXT,
              mission_needs_return INTEGER NOT NULL DEFAULT 0,
              report_bridge_json TEXT,
              updated_at TEXT NOT NULL
            )
        """.trimIndent())
'''
if schema_anchor not in s:
    raise SystemExit('store foundation schema anchor not found')
s = s.replace(schema_anchor, schema_insert, 1)

upgrade_anchor = '''        if (oldVersion < 4) {
            ensureFoundationSchema(db)
        }
    }
'''
upgrade_new = '''        if (oldVersion < 4) {
            ensureFoundationSchema(db)
        }
        if (oldVersion < 5) {
            ensureFoundationSchema(db)
        }
    }
'''
if upgrade_anchor not in s:
    raise SystemExit('store onUpgrade anchor not found')
s = s.replace(upgrade_anchor, upgrade_new, 1)

methods_anchor = '    private fun nullableInt(obj: JSONObject, key: String): Int? =\n'
store_methods = '''    private fun jinhakMissionStateRank(state: String): Int = when (state.lowercase()) {
        "pending" -> 0
        "clicked" -> 10
        "deferred" -> 20
        "failed" -> 30
        "skipped" -> 40
        "confirmed" -> 50
        else -> -1
    }

    /** Upsert a mission target without ever allowing a lower-ranked state to overwrite progress. */
    fun upsertJinhakMissionTarget(sessionId: String, payload: JSONObject): Boolean {
        if (sessionId.isBlank()) return false
        val targetId = payload.optString("targetId").takeIf { it.isNotBlank() && it != "null" } ?: return false
        val identityKey = payload.optString("identityKey").takeIf { it.isNotBlank() && it != "null" } ?: return false
        val lane = payload.optString("lane").takeIf { it.isNotBlank() && it != "reference" && it != "null" } ?: return false
        val state = payload.optString("state", "pending").lowercase()
        val rank = jinhakMissionStateRank(state)
        if (rank < 0) return false
        val now = Instant.now().toString()
        val db = writableDatabase
        db.beginTransaction()
        return try {
            val existing = db.rawQuery(
                "SELECT state_rank,first_persisted_at FROM jinhak_mission_targets WHERE session_id=? AND target_id=? LIMIT 1",
                arrayOf(sessionId, targetId)
            ).use { c -> if (c.moveToFirst()) Pair(c.getInt(0), c.getString(1)) else null }
            if (existing != null && existing.first > rank) {
                db.setTransactionSuccessful()
                false
            } else {
                val cv = ContentValues().apply {
                    put("session_id", sessionId)
                    put("target_id", targetId)
                    put("identity_key", identityKey)
                    put("lane", lane)
                    put("state", state)
                    put("state_rank", rank)
                    put("payload_json", payload.toString())
                    put("first_persisted_at", existing?.second ?: now)
                    put("updated_at", now)
                }
                db.insertWithOnConflict("jinhak_mission_targets", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
                db.setTransactionSuccessful()
                true
            }
        } finally {
            db.endTransaction()
        }
    }

    fun loadJinhakMissionTargets(sessionId: String): List<JSONObject> {
        if (sessionId.isBlank()) return emptyList()
        val out = mutableListOf<JSONObject>()
        readableDatabase.rawQuery(
            "SELECT payload_json FROM jinhak_mission_targets WHERE session_id=? ORDER BY first_persisted_at,target_id",
            arrayOf(sessionId)
        ).use { c ->
            while (c.moveToNext()) {
                runCatching { JSONObject(c.getString(0)) }.getOrNull()?.let(out::add)
            }
        }
        return out
    }

    fun storeJinhakMissionRuntime(sessionId: String, payload: JSONObject) {
        if (sessionId.isBlank()) return
        val cv = ContentValues().apply {
            put("session_id", sessionId)
            putNullable("active_target_id", payload.optString("activeTargetId").takeIf { it.isNotBlank() && it != "null" })
            putNullable("current_batch_target", payload.optString("currentBatchTarget").takeIf { it.isNotBlank() && it != "null" })
            putNullable("mission_origin_route", payload.optString("missionOriginRoute").takeIf { it.isNotBlank() && it != "null" })
            put("mission_needs_return", if (payload.optBoolean("missionNeedsReturn", false)) 1 else 0)
            val bridge = payload.optJSONObject("reportBridgeContext")
            putNullable("report_bridge_json", bridge?.toString())
            put("updated_at", Instant.now().toString())
        }
        writableDatabase.insertWithOnConflict("jinhak_mission_runtime", null, cv, SQLiteDatabase.CONFLICT_REPLACE)
    }

    fun loadJinhakMissionRuntime(sessionId: String): JSONObject? {
        if (sessionId.isBlank()) return null
        return readableDatabase.rawQuery(
            "SELECT active_target_id,current_batch_target,mission_origin_route,mission_needs_return,report_bridge_json,updated_at FROM jinhak_mission_runtime WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c ->
            if (!c.moveToFirst()) return@use null
            JSONObject()
                .put("activeTargetId", if (c.isNull(0)) JSONObject.NULL else c.getString(0))
                .put("currentBatchTarget", if (c.isNull(1)) JSONObject.NULL else c.getString(1))
                .put("missionOriginRoute", if (c.isNull(2)) JSONObject.NULL else c.getString(2))
                .put("missionNeedsReturn", c.getInt(3) != 0)
                .put("reportBridgeContext", if (c.isNull(4)) JSONObject.NULL else runCatching { JSONObject(c.getString(4)) }.getOrNull() ?: JSONObject.NULL)
                .put("updatedAt", c.getString(5))
        }
    }

    fun jinhakMissionPersistenceSummary(sessionId: String): JSONObject {
        if (sessionId.isBlank()) return JSONObject().put("persistedTargets", 0).put("persistedIdentities", 0)
        val db = readableDatabase
        val counts = db.rawQuery(
            "SELECT COUNT(*),COUNT(DISTINCT identity_key)," +
                "SUM(CASE WHEN state='pending' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='clicked' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='deferred' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='confirmed' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='failed' THEN 1 ELSE 0 END)," +
                "SUM(CASE WHEN state='skipped' THEN 1 ELSE 0 END) " +
                "FROM jinhak_mission_targets WHERE session_id=?",
            arrayOf(sessionId)
        ).use { c ->
            if (!c.moveToFirst()) intArrayOf(0,0,0,0,0,0,0,0)
            else IntArray(8) { i -> if (c.isNull(i)) 0 else c.getInt(i) }
        }
        val runtimePresent = db.rawQuery(
            "SELECT active_target_id IS NOT NULL FROM jinhak_mission_runtime WHERE session_id=? LIMIT 1",
            arrayOf(sessionId)
        ).use { c -> c.moveToFirst() && c.getInt(0) != 0 }
        return JSONObject()
            .put("schemaVersion", 1)
            .put("persistedTargets", counts[0])
            .put("persistedIdentities", counts[1])
            .put("pending", counts[2])
            .put("clicked", counts[3])
            .put("deferred", counts[4])
            .put("confirmed", counts[5])
            .put("failed", counts[6])
            .put("skipped", counts[7])
            .put("activeTargetPersisted", runtimePresent)
            .put("monotonicStateGuard", true)
            .put("credentialStored", false)
            .put("sessionSecretStored", false)
    }

'''
if methods_anchor not in s:
    raise SystemExit('store methods insertion anchor not found')
s = s.replace(methods_anchor, store_methods + methods_anchor, 1)

# -----------------------------------------------------------------------------
# MainActivity: persist every target mutation + runtime checkpoint, restore before reset.
# -----------------------------------------------------------------------------
init_anchor = '''        localStore = LocalCollectorStore(this)
        sessionVault = SecureSessionVault(this)
'''
init_new = '''        localStore = LocalCollectorStore(this)
        jinhakMissionTargetLedger.setMutationListener { payload -> persistJinhakMissionMutation(payload) }
        sessionVault = SecureSessionVault(this)
'''
if init_anchor not in m:
    raise SystemExit('MainActivity localStore init anchor not found')
m = m.replace(init_anchor, init_new, 1)

checkpoint_anchor = '''    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {
        runCatching {
            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit()
                .putBoolean("resumeUnified", forceResume)
                .putString("provider", provider.wireName)
                .putString("phase", unifiedPhase)
                .putString("safePath", runtimeLastSafePath)
                .putInt("batchPageCount", batchPageCount)
                .putInt("queueSize", batchQueue.size)
                .putInt("errorCount", batchErrors.length())
                .apply()
        }
    }
'''
checkpoint_new = checkpoint_anchor[:-6] + '''        if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {
            persistJinhakMissionRuntimeState("runtime-checkpoint")
        }
    }
'''
# The slice above intentionally drops the original final "    }\n" only.
if checkpoint_anchor not in m:
    raise SystemExit('runtime checkpoint anchor not found')
m = m.replace(checkpoint_anchor, checkpoint_new, 1)

helper_anchor = '    private fun recordRuntimeEvent(type: String, detail: JSONObject = JSONObject(), synchronous: Boolean = false) {\n'
helpers = '''    private fun persistJinhakMissionMutation(payload: JSONObject) {
        val sessionId = unifiedSessionId?.takeIf { unifiedRunning && unifiedPhase == "jinhak" } ?: return
        localStore.upsertJinhakMissionTarget(sessionId, payload)
        persistJinhakMissionRuntimeState("target-mutation", payload)
    }

    private fun persistJinhakMissionRuntimeState(trigger: String, mutatedTarget: JSONObject? = null) {
        val sessionId = unifiedSessionId?.takeIf { unifiedRunning && unifiedPhase == "jinhak" } ?: return
        val mutatedId = mutatedTarget?.optString("targetId").orEmpty()
        val mutatedState = mutatedTarget?.optString("state").orEmpty()
        val terminalMutation = mutatedId.isNotBlank() && mutatedId == jinhakActiveMissionTargetId &&
            mutatedState in setOf("confirmed", "failed", "skipped")
        val activeTarget = if (terminalMutation) null else jinhakActiveMissionTargetId
        localStore.storeJinhakMissionRuntime(
            sessionId,
            JSONObject()
                .put("activeTargetId", activeTarget ?: JSONObject.NULL)
                .put("currentBatchTarget", currentBatchTarget ?: JSONObject.NULL)
                .put("missionOriginRoute", jinhakMissionOriginRoute.ifBlank { JSONObject.NULL })
                .put("missionNeedsReturn", jinhakMissionNeedsReturn)
                .put("reportBridgeContext", jinhakReportBridgeContext?.let { JSONObject(it.toString()) } ?: JSONObject.NULL)
                .put("trigger", trigger.take(60))
                .put("updatedAtMs", System.currentTimeMillis())
        )
    }

    private fun restoreJinhakMissionPersistence(sessionId: String, trigger: String): Int {
        if (sessionId.isBlank()) return 0
        val persistedTargets = localStore.loadJinhakMissionTargets(sessionId)
        val restored = jinhakMissionTargetLedger.restorePersisted(persistedTargets)
        if (restored > 0) {
            jinhakMissionCoverage.clear()
            jinhakMissionTargetLedger.confirmedCoverage().forEach { (identity, lanes) ->
                jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() }.addAll(lanes)
            }
        }
        localStore.loadJinhakMissionRuntime(sessionId)?.let { runtime ->
            jinhakActiveMissionTargetId = runtime.optString("activeTargetId").takeIf { it.isNotBlank() && it != "null" }
            currentBatchTarget = runtime.optString("currentBatchTarget").takeIf { it.isNotBlank() && it != "null" } ?: currentBatchTarget
            jinhakMissionOriginRoute = runtime.optString("missionOriginRoute").takeIf { it.isNotBlank() && it != "null" }.orEmpty()
            jinhakMissionNeedsReturn = runtime.optBoolean("missionNeedsReturn", false)
            jinhakReportBridgeContext = runtime.optJSONObject("reportBridgeContext")
            jinhakMissionContext = JinhakReportContextBridge.context(jinhakReportBridgeContext)
        }
        if (restored > 0) {
            recordRuntimeEvent(
                "jinhak-mission-persistence-restored",
                JSONObject()
                    .put("trigger", trigger.take(60))
                    .put("restoredTargets", restored)
                    .put("summary", localStore.jinhakMissionPersistenceSummary(sessionId))
                    .put("stateRegressionAllowed", false)
            )
        }
        return restored
    }

'''
if helper_anchor not in m:
    raise SystemExit('MainActivity helper insertion anchor not found')
m = m.replace(helper_anchor, helpers + helper_anchor, 1)

# Restore on Activity/process resume before the Jinhak browser is opened.
resume_anchor = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
'''
resume_new = '''            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            val restoredMissionTargets = restoreJinhakMissionPersistence(sessionId, "activity-resume")
            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
'''
if resume_anchor not in m:
    raise SystemExit('resume Jinhak anchor not found')
m = m.replace(resume_anchor, resume_new, 1)

status_old = '"이전 중단 감지: 암호화 로그인 세션을 복구하고 진학사 에이전트를 체크포인트에서 재개합니다."'
status_new = '"이전 중단 감지: 암호화 로그인 세션과 mission ${restoredMissionTargets}개를 복구하고 진학사 에이전트를 체크포인트에서 재개합니다."'
if status_old not in m:
    raise SystemExit('resume status anchor not found')
m = m.replace(status_old, status_new, 1)

# Restore persisted ledger before deciding whether the first Jinhak batch after lifecycle restart
# is allowed to clear mission state.
preserve_anchor = '''        val preserveJinhakMissionState = provider == ProviderId.JINHAK && unifiedRunning && jinhakBatchStartCount > 0
        if (provider == ProviderId.JINHAK) {
'''
preserve_new = '''        val restoredPersistedMissionTargets = if (provider == ProviderId.JINHAK && unifiedRunning) {
            unifiedSessionId?.let { restoreJinhakMissionPersistence(it, "batch-start") } ?: 0
        } else 0
        val preserveJinhakMissionState = provider == ProviderId.JINHAK && unifiedRunning &&
            (jinhakBatchStartCount > 0 || restoredPersistedMissionTargets > 0)
        if (provider == ProviderId.JINHAK) {
'''
if preserve_anchor not in m:
    raise SystemExit('startBatch preserve anchor not found')
m = m.replace(preserve_anchor, preserve_new, 1)

# After volatile batch fields reset, re-apply persisted minimal runtime before choosing resume URL.
post_reset_anchor = '''        jinhakAbsoluteTargetKey = ""
        ++jinhakAbsoluteTargetGeneration
        disarmBatchNavigationWatchdog()
        currentBatchTarget = if (provider == ProviderId.JINHAK) {
            canonicalizeBatchUrl(currentAdapter().seedUrls().firstOrNull() ?: url)
        } else canonicalizeBatchUrl(url)
'''
post_reset_new = '''        jinhakAbsoluteTargetKey = ""
        ++jinhakAbsoluteTargetGeneration
        disarmBatchNavigationWatchdog()
        if (preserveJinhakMissionState && provider == ProviderId.JINHAK) {
            unifiedSessionId?.let { restoreJinhakMissionPersistence(it, "post-batch-reset") }
        }
        currentBatchTarget = if (provider == ProviderId.JINHAK && preserveJinhakMissionState && !currentBatchTarget.isNullOrBlank()) {
            currentBatchTarget
        } else if (provider == ProviderId.JINHAK) {
            canonicalizeBatchUrl(currentAdapter().seedUrls().firstOrNull() ?: url)
        } else canonicalizeBatchUrl(url)
'''
if post_reset_anchor not in m:
    raise SystemExit('post-reset current target anchor not found')
m = m.replace(post_reset_anchor, post_reset_new, 1)

# Add persistence counters to the existing live Jinhak diagnostic used by unified export.
diag_anchor = '''                .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("referenceRoutesTracked", jinhakReferenceRouteCaptureCounts.size)
'''
diag_new = '''                .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("missionPersistence", localStore.jinhakMissionPersistenceSummary(sessionId))
                .put("referenceRoutesTracked", jinhakReferenceRouteCaptureCounts.size)
'''
if diag_anchor not in m:
    raise SystemExit('live diagnostic persistence anchor not found')
m = m.replace(diag_anchor, diag_new, 1)

# Version metadata.
for old, new in [
    ('private const val VERSION = "0.9.10"', 'private const val VERSION = "0.9.11"'),
    ('private const val BUILD_CODE = 109100', 'private const val BUILD_CODE = 109110'),
]:
    if old not in m:
        raise SystemExit(f'MainActivity version anchor not found: {old}')
    m = m.replace(old, new, 1)
for old, new in [
    ('versionCode = 109100', 'versionCode = 109110'),
    ('versionName = "0.9.10"', 'versionName = "0.9.11"'),
]:
    if old not in g:
        raise SystemExit(f'Gradle version anchor not found: {old}')
    g = g.replace(old, new, 1)
old_label = 'android:label="Admission Collector v0.9.10 Renderer Recovery"'
new_label = 'android:label="Admission Collector v0.9.11 Mission State Persistence"'
if old_label not in manifest:
    raise SystemExit('Manifest v0.9.10 label anchor not found')
manifest = manifest.replace(old_label, new_label, 1)

# Safety/completeness invariants.
required_main = [
    'restoreJinhakMissionPersistence(sessionId, "activity-resume")',
    'restoreJinhakMissionPersistence(it, "batch-start")',
    'restoreJinhakMissionPersistence(it, "post-batch-reset")',
    'persistJinhakMissionRuntimeState("runtime-checkpoint")',
    'jinhakMissionTargetLedger.setMutationListener',
    '.put("missionPersistence", localStore.jinhakMissionPersistenceSummary(sessionId))',
    'webview-renderer-recovered-in-place',
]
required_ledger = [
    'fun restorePersisted(payloads: List<JSONObject>)',
    'fun confirmedCoverage()',
    'private fun stateRank(state: State)',
    'private fun canTransition(from: State, to: State)',
    'notifyMutation(target)',
]
required_store = [
    'CREATE TABLE IF NOT EXISTS jinhak_mission_targets',
    'CREATE TABLE IF NOT EXISTS jinhak_mission_runtime',
    'fun upsertJinhakMissionTarget',
    'fun loadJinhakMissionTargets',
    'fun storeJinhakMissionRuntime',
    'fun loadJinhakMissionRuntime',
    'fun jinhakMissionPersistenceSummary',
]
for name, text, required in [('main', m, required_main), ('ledger', l, required_ledger), ('store', s, required_store)]:
    missing = [x for x in required if x not in text]
    if missing:
        raise SystemExit(f'{name} missing invariant(s): ' + ', '.join(missing))
if 'handler.postDelayed({ recreate() }, 250L)' in m:
    raise SystemExit('v0.9.10 renderer recovery regressed')
if '.put("username", credentials.username)' in m or '.put("password", credentials.password)' in m:
    raise SystemExit('credential export invariant failed')

main_path.write_text(m)
ledger_path.write_text(l)
store_path.write_text(s)
gradle_path.write_text(g)
manifest_path.write_text(manifest)
print('Applied v0.9.11 Mission State Persistence patch')
