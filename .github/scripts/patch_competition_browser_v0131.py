from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
CLIENT = ROOT / "app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadClient.kt"
COORD = ROOT / "app/src/main/java/com/admissionhub/collector/cloud/CloudOffloadCoordinator.kt"
GRADLE = ROOT / "app/build.gradle.kts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one anchor, found {count}")
    return text.replace(old, new, 1)


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "import com.admissionhub.collector.cloud.CloudOffloadCoordinator\n",
        "import com.admissionhub.collector.cloud.CloudOffloadCoordinator\n"
        "import com.admissionhub.collector.competition.CompetitionBrowserCollector\n",
        "main import",
    )
    text = replace_once(
        text,
        "    private lateinit var slowLanePool: JinhakSlowLanePool\n",
        "    private lateinit var slowLanePool: JinhakSlowLanePool\n"
        "    private lateinit var competitionCollector: CompetitionBrowserCollector\n",
        "main field",
    )
    text = replace_once(
        text,
        "        configureWebView()\n        initializeProcessResumeJournal()",
        "        configureWebView()\n"
        "        competitionCollector = CompetitionBrowserCollector(\n"
        "            activity = this,\n"
        "            host = slowLaneHost,\n"
        "            cloud = cloudOffload,\n"
        "            isBusy = { unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive },\n"
        "            onStatus = { message -> if (!unifiedRunning && !batchRunning) status.text = message },\n"
        "        )\n"
        "        competitionCollector.start()\n"
        "        initializeProcessResumeJournal()",
        "main init",
    )
    text = replace_once(
        text,
        "        if (::slowLanePool.isInitialized) slowLanePool.destroy()\n        handler.removeCallbacksAndMessages(null)",
        "        if (::slowLanePool.isInitialized) slowLanePool.destroy()\n"
        "        if (::competitionCollector.isInitialized) competitionCollector.destroy()\n"
        "        handler.removeCallbacksAndMessages(null)",
        "main destroy",
    )
    text = text.replace('private const val VERSION = "0.13.0"', 'private const val VERSION = "0.13.1"')
    text = text.replace("private const val BUILD_CODE = 113000", "private const val BUILD_CODE = 113100")
    MAIN.write_text(text, encoding="utf-8")


def patch_client() -> None:
    text = CLIENT.read_text(encoding="utf-8")
    old = """    fun shutdown() {\n        io.shutdownNow()\n    }\n"""
    new = """    fun observeCompetition(\n        observation: JSONObject,\n        callback: (Result<JSONObject>) -> Unit = {}\n    ) = io.execute {\n        callback(runCatching { post(\"/v1/competition/observe\", observation) })\n    }\n\n    fun shutdown() {\n        io.shutdownNow()\n    }\n"""
    text = replace_once(text, old, new, "client observe")
    CLIENT.write_text(text, encoding="utf-8")


def patch_coordinator() -> None:
    text = COORD.read_text(encoding="utf-8")
    old = """    fun pendingPages(callback: (Result<JSONObject>) -> Unit) {\n"""
    new = """    fun observeCompetition(\n        observation: JSONObject,\n        callback: (Result<JSONObject>) -> Unit = {}\n    ) {\n        if (!isConfigured()) {\n            callback(Result.failure(IllegalStateException(\"competition-cloud-not-configured\")))\n            return\n        }\n        val currentClient = synchronized(lock) { ensureClientLocked(); client }\n        if (currentClient == null) {\n            callback(Result.failure(IllegalStateException(\"competition-cloud-client-unavailable\")))\n            return\n        }\n        currentClient.observeCompetition(observation) { result ->\n            result.onFailure { lastError = it.message }\n            callback(result)\n        }\n    }\n\n    fun pendingPages(callback: (Result<JSONObject>) -> Unit) {\n"""
    text = replace_once(text, old, new, "coordinator observe")
    COORD.write_text(text, encoding="utf-8")


def patch_gradle() -> None:
    text = GRADLE.read_text(encoding="utf-8")
    text = text.replace("versionCode = 113000", "versionCode = 113100")
    text = text.replace('versionName = "0.13.0"', 'versionName = "0.13.1"')
    GRADLE.write_text(text, encoding="utf-8")


patch_main()
patch_client()
patch_coordinator()
patch_gradle()
print("competition browser v0.13.1 patch applied or already present")
