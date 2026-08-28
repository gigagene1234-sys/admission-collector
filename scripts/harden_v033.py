from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def patch_worker(text: str) -> str:
    text = text.replace('version: "0.3.2"', 'version: "0.3.3"')
    if 'url.pathname === "/v1/runs/latest"' not in text:
        anchor = '''      if (request.method === "POST" && url.pathname === "/v1/runs") {\n        const body = await readJson(request, 128_000);\n        return createRun(env, body);\n      }\n'''
        insert = '''      if (request.method === "GET" && url.pathname === "/v1/runs/latest") {\n        const provider = String(url.searchParams.get("provider") || "").slice(0, 40);\n        if (!provider) return json({ error: "provider is required" }, 400);\n        return getLatestActiveRun(env, provider);\n      }\n\n''' + anchor
        text = replace_once(text, anchor, insert, "latest active run route")
    if 'async function getLatestActiveRun' not in text:
        anchor = 'async function createRun(env, body) {\n'
        helper = '''async function getLatestActiveRun(env, provider) {\n  const row = await env.DB.prepare(`\n    SELECT run_id, provider, collector_version, status, created_at, updated_at\n    FROM runs\n    WHERE provider = ? AND status = 'collecting'\n    ORDER BY updated_at DESC\n    LIMIT 1\n  `).bind(provider).first();\n\n  return json({\n    runId: row?.run_id || null,\n    provider: row?.provider || provider,\n    collectorVersion: row?.collector_version || null,\n    status: row?.status || null,\n    updatedAt: row?.updated_at || null,\n  });\n}\n\n'''
        text = replace_once(text, anchor, helper + anchor, "latest active run helper")
    return text


def patch_client(text: str) -> str:
    text = text.replace(' * v0.3.2 Cloudflare offload client.', ' * v0.3.3 Cloudflare offload client.')
    if 'fun getLatestActiveRun' not in text:
        anchor = '''    fun getStatus(\n        runId: String,\n        callback: (Result<JSONObject>) -> Unit\n    ) = io.execute {\n        callback(runCatching { get("/v1/runs/${encode(runId)}/status") })\n    }\n\n'''
        method = anchor + '''    fun getLatestActiveRun(\n        provider: String,\n        callback: (Result<String?>) -> Unit\n    ) = io.execute {\n        callback(runCatching {\n            get("/v1/runs/latest?provider=${encode(provider)}")\n                .optString("runId")\n                .takeIf { it.isNotBlank() && it != "null" }\n        })\n    }\n\n'''
        text = replace_once(text, anchor, method, "latest active run client")
    return text


def patch_coordinator(text: str) -> str:
    text = text.replace('Cloudflare checkpoint coordinator for Admission Collector v0.3.2.', 'Cloudflare checkpoint coordinator for Admission Collector v0.3.3.')
    if 'private fun recoverOrCreateRun' in text:
        return text
    old = '''        client?.createRun(\n            provider = provider,\n            collectorVersion = collectorVersion,\n            metadata = JSONObject()\n                .put("client", "android")\n                .put("checkpointMode", "incremental")\n        ) { result ->\n            val runId = result.getOrNull()\n            val error = result.exceptionOrNull()\n            synchronized(lock) {\n                creatingRun = false\n                if (runId != null) {\n                    activeRunId = runId\n                    prefs.edit()\n                        .putString(KEY_ACTIVE_RUN, runId)\n                        .putString(KEY_ACTIVE_PROVIDER, provider)\n                        .apply()\n                } else {\n                    lastError = error?.message ?: "run creation failed"\n                }\n            }\n            if (runId != null) flushPending()\n            onReady?.invoke(runId)\n        }\n    }\n\n'''
    new = '''        recoverOrCreateRun(provider, collectorVersion, onReady)\n    }\n\n    /**\n     * Recovers the newest unfinished server-side run when local SharedPreferences were\n     * lost (for example after the one-time migration from an ephemeral debug signature).\n     * This preserves D1 checkpoints without exporting browser credentials or cookies.\n     */\n    private fun recoverOrCreateRun(\n        provider: String,\n        collectorVersion: String,\n        onReady: ((String?) -> Unit)?\n    ) {\n        val currentClient = synchronized(lock) { ensureClientLocked(); client }\n        if (currentClient == null) {\n            synchronized(lock) { creatingRun = false }\n            onReady?.invoke(null)\n            return\n        }\n\n        currentClient.getLatestActiveRun(provider) { lookup ->\n            val recovered = lookup.getOrNull()\n            if (!recovered.isNullOrBlank()) {\n                synchronized(lock) {\n                    creatingRun = false\n                    activeRunId = recovered\n                    activeProvider = provider\n                    reusedRun = true\n                    prefs.edit()\n                        .putString(KEY_ACTIVE_RUN, recovered)\n                        .putString(KEY_ACTIVE_PROVIDER, provider)\n                        .apply()\n                }\n                flushPending()\n                onReady?.invoke(recovered)\n                return@getLatestActiveRun\n            }\n\n            currentClient.createRun(\n                provider = provider,\n                collectorVersion = collectorVersion,\n                metadata = JSONObject()\n                    .put("client", "android")\n                    .put("checkpointMode", "incremental")\n                    .put("recoveryLookup", if (lookup.isSuccess) "none-found" else "failed")\n            ) { result ->\n                val runId = result.getOrNull()\n                val error = result.exceptionOrNull()\n                synchronized(lock) {\n                    creatingRun = false\n                    if (runId != null) {\n                        activeRunId = runId\n                        activeProvider = provider\n                        reusedRun = false\n                        prefs.edit()\n                            .putString(KEY_ACTIVE_RUN, runId)\n                            .putString(KEY_ACTIVE_PROVIDER, provider)\n                            .apply()\n                    } else {\n                        lastError = error?.message ?: lookup.exceptionOrNull()?.message ?: "run creation failed"\n                    }\n                }\n                if (runId != null) flushPending()\n                onReady?.invoke(runId)\n            }\n        }\n    }\n\n'''
    return replace_once(text, old, new, "coordinator server recovery")


def patch_gradle(text: str) -> str:
    if 'ADMISSION_SIGNING_STORE_FILE' in text:
        return text
    prefix = '''val admissionSigningStore = System.getenv("ADMISSION_SIGNING_STORE_FILE")\nval admissionSigningPassword = System.getenv("ADMISSION_SIGNING_PASSWORD")\n\n'''
    text = prefix + text
    old = '''    buildTypes {\n        release {\n            isMinifyEnabled = false\n        }\n    }\n'''
    new = '''    signingConfigs {\n        if (!admissionSigningStore.isNullOrBlank() && !admissionSigningPassword.isNullOrBlank()) {\n            create("admissionStable") {\n                storeFile = file(admissionSigningStore)\n                storePassword = admissionSigningPassword\n                keyAlias = "admission"\n                keyPassword = admissionSigningPassword\n            }\n        }\n    }\n\n    buildTypes {\n        debug {\n            signingConfigs.findByName("admissionStable")?.let { signingConfig = it }\n        }\n        release {\n            isMinifyEnabled = false\n            signingConfigs.findByName("admissionStable")?.let { signingConfig = it }\n        }\n    }\n'''
    return replace_once(text, old, new, "stable Android signing config")


worker = ROOT / "cloudflare/src/index.js"
worker.write_text(patch_worker(worker.read_text()), encoding="utf-8")

client = ROOT / "app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadClient.kt"
client.write_text(patch_client(client.read_text()), encoding="utf-8")

coordinator = ROOT / "app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt"
coordinator.write_text(patch_coordinator(coordinator.read_text()), encoding="utf-8")

gradle = ROOT / "app/build.gradle.kts"
gradle.write_text(patch_gradle(gradle.read_text()), encoding="utf-8")

print("v0.3.3 recovery/signing hardening applied")
