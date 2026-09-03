package com.admissionhub.collector

import android.app.Activity
import android.app.AlertDialog
import android.content.Intent
import android.graphics.Bitmap
import android.net.Uri
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.webkit.CookieManager
import android.webkit.WebChromeClient
import android.webkit.JsResult
import android.webkit.RenderProcessGoneDetail
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Button
import android.widget.EditText
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.TextView
import android.widget.Toast
import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import com.admissionhub.collector.capture.SnapshotScript
import com.admissionhub.collector.cloud.CloudOffloadCoordinator
import com.admissionhub.collector.local.LocalCollectorStore
import com.admissionhub.collector.observation.ObservationEvidence
import com.admissionhub.collector.jinhak.JinhakCapabilityProbe
import com.admissionhub.collector.jinhak.JinhakAgentNavigator
import com.admissionhub.collector.jinhak.JinhakSiteTopology
import com.admissionhub.collector.jinhak.JinhakApplicationMission
import com.admissionhub.collector.jinhak.JinhakSlowLanePool
import com.admissionhub.collector.jinhak.JinhakReportContextBridge
import com.admissionhub.collector.jinhak.JinhakMissionLaneSequencer
import com.admissionhub.collector.jinhak.JinhakMissionTargetLedger
import com.admissionhub.collector.session.SecureSessionVault
import com.admissionhub.collector.session.CredentialVault
import com.admissionhub.collector.provider.ProviderCapabilities
import com.admissionhub.collector.provider.ProviderCapability
import com.admissionhub.collector.sync.UnifiedSyncState
import com.admissionhub.collector.parser.RecordUtils
import com.admissionhub.collector.provider.PaginationPlan
import com.admissionhub.collector.provider.ProviderAdapter
import com.admissionhub.collector.provider.ProviderId
import com.admissionhub.collector.provider.ProviderRegistry
import java.time.Instant
import java.util.ArrayDeque

class MainActivity : Activity() {
    private lateinit var webView: WebView
    private lateinit var status: TextView
    private lateinit var sessionState: TextView
    private lateinit var preview: TextView
    private lateinit var batchButton: Button
    private lateinit var batchCover: TextView
    private lateinit var diagnosticButton: Button
    private lateinit var unifiedButton: Button
    private lateinit var cloudOffload: CloudOffloadCoordinator
    private lateinit var localStore: LocalCollectorStore
    private lateinit var sessionVault: SecureSessionVault
    private lateinit var credentialVault: CredentialVault
    private lateinit var slowLaneHost: FrameLayout
    private lateinit var slowLanePool: JinhakSlowLanePool

    private val handler = Handler(Looper.getMainLooper())
    private val sessionKeepAlive = object : Runnable {
        override fun run() {
            val active = unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive
            if (active) {
                if (provider == ProviderId.JINHAK) {
                    jinhakSessionKeepAliveTicks += 1
                    if (!hasWindowFocus()) jinhakSessionKeepAliveBackgroundTicks += 1
                }
                attemptSessionExtension()
                if (provider == ProviderId.JINHAK) {
                    val current = webView.url.orEmpty()
                    if (batchPausedForLogin || jinhakTransitionAuthGateActive || isProviderLoginUrl(ProviderId.JINHAK, current)) {
                        scheduleJinhakLoginRecovery("session-keepalive")
                    } else if (batchRunning) {
                        checkSessionState { needsLogin, _ ->
                            if (batchRunning && provider == ProviderId.JINHAK && needsLogin) {
                                batchPausedForLogin = true
                                jinhakAuthVerifiedForBatch = false
                                jinhakCoreBootstrapState = "keepalive-login-recovery"
                                jinhakReauthCycles += 1
                                persistJinhakAuthDiagnostics("keepalive-needs-login")
                                scheduleJinhakLoginRecovery("keepalive-needs-login")
                            }
                        }
                    }
                    persistJinhakAuthDiagnostics("session-keepalive")
                }
            }
            handler.postDelayed(this, 45_000L)
        }
    }
    private data class BatchPageAction(
        val baseUrl: String,
        val page: Int,
        val familyKey: String,
        val requestedYear: Int?,
        val totalPages: Int,
        val pageSize: Int,
        val totalItems: Int,
        val retry: Int = 0
    )

    private data class ListFingerprint(
        val requestedYear: Int?,
        val totalItems: Int,
        val pageSize: Int,
        val fingerprint: String
    )

    private val batchQueue = ArrayDeque<String>()
    private val batchVisited = linkedSetOf<String>()
    private val batchQueued = linkedSetOf<String>()
    private val batchPageActions = ArrayDeque<BatchPageAction>()
    private val batchPageActionQueued = linkedSetOf<String>()
    private val batchPageActionVisited = linkedSetOf<String>()
    private val batchPageActionFailed = linkedSetOf<String>()
    private val batchPaginationPlanned = linkedSetOf<String>()
    private val batchListFingerprints = linkedMapOf<String, ListFingerprint>()
    private val batchLastTableSignatures = linkedMapOf<String, String>()
    private val batchBootstrapSearchAttempted = linkedSetOf<String>()
    private var batchReadinessPolling = false
    private var batchSnapshots = JSONArray()
    private var batchRecords = JSONArray()
    private var batchResources = JSONArray()
    private var batchErrors = JSONArray()
    private var batchRetryEvents = JSONArray()
    private var batchDuplicateYearViews = JSONArray()
    private var batchRunning = false
    private var batchPausedForLogin = false
    private var batchCollecting = false
    private var currentBatchTarget: String? = null
    private var pendingBatchPageAction: BatchPageAction? = null
    private var activeBatchPageAction: BatchPageAction? = null
    private var batchPageCount = 0
    private var batchPaginationRetries = 0
    private var batchCloudPlansPending = 0
    private var batchCloudResumePlans = 0
    private var batchCloudPagesScheduled = 0
    private var batchCloudPagesSkipped = 0
    private var batchCloudPagesDeferred = 0
    private var batchContextRecoveries = 0
    private var batchSessionSyncRetries = 0
    private var batchNavigationWatchdogGeneration = 0
    private var batchNavigationWatchdogRecovery = false
    private var batchCloudFinalCheckInProgress = false
    private var batchLocalResumePlans = 0
    private var batchLocalPagesScheduled = 0
    private var batchLocalPagesSkipped = 0
    private var batchLocalRecordsPersisted = 0
    private var localRunId: String? = null
    private val batchPersistedPageSignatureOwners = linkedMapOf<String, MutableMap<String, Int>>()
    private var batchAuditPagesScheduled = 0
    private var batchUniversityDiscoveryPagesScheduled = 0

    private var lastJson: String = ""
    private var provider: ProviderId = ProviderId.ADIGA
    private var lastJinhakDigest = JSONObject()
    private var unifiedSessionId: String? = null
    private var unifiedRunning = false
    private var unifiedPhase = "idle"
    private var unifiedPendingAdigaStart = false
    private var unifiedPendingJinhakStart = false
    private var unifiedJinhakAutoCapture = false
    private val unifiedJinhakCapturedPages = linkedSetOf<String>()
    private var unifiedAutoCaptureScheduled = false
    private val jinhakAgentActionSeen = linkedSetOf<String>()
    private val jinhakExpandedNavigationStates = linkedSetOf<String>()
    private var jinhakRepeatedNavigationStateSkips = 0
    private var jinhakUniqueNavigationStates = 0
    private var jinhakAgentActionInFlight = false
    private var jinhakAgentActionsExecuted = 0
    private var jinhakMissionActionsExecuted = 0
    private var jinhakGenericActionsExecuted = 0
    private val jinhakReferenceRouteCaptureCounts = linkedMapOf<String, Int>()
    private var jinhakReferenceRepeatSkips = 0
    private var jinhakNoProgressFences = 0
    private var jinhakLastMeaningfulProgressAtMs = 0L
    private var jinhakProgressFenceGeneration = 0
    private var jinhakLastLiveDiagnosticsAtMs = 0L
    private var jinhakMissionContext: JinhakApplicationMission.Context? = null
    private var jinhakMissionOriginRoute = ""
    private var jinhakMissionNeedsReturn = false
    private var jinhakApplicationBoundActions = 0
    private var jinhakApplicationMissionReturns = 0
    private val jinhakMissionCoverage = linkedMapOf<String, MutableSet<String>>()
    private val jinhakMissionTargetLedger = JinhakMissionTargetLedger()
    private var jinhakActiveMissionTargetId: String? = null
    private val jinhakSlowLaneMissionTargetIds = linkedMapOf<String, String>()
    private val jinhakMissionAnchorDiscoveredKeys = linkedSetOf<String>()
    private val jinhakMissionAnchorPromotedKeys = linkedSetOf<String>()
    private val jinhakMissionAnchorParsedKeys = linkedSetOf<String>()
    private val jinhakMissionAnchorStructuredKeys = linkedSetOf<String>()
    private val jinhakMissionBindingSourceKeys = linkedSetOf<String>()
    private val jinhakMissionBindingSourceCounts = linkedMapOf<String, Int>()
    private val jinhakMissionAnchorSelectedKeys = linkedSetOf<String>()
    private val jinhakMissionAnchorClickedKeys = linkedSetOf<String>()
    private val jinhakReportConfirmedKeys = linkedSetOf<String>()
    private var jinhakMissionAnchorActionsExecuted = 0
    private var jinhakConsentGatePending = false
    private var jinhakConsentResumePending = false
    private var jinhakConsentGatesEncountered = 0
    private var jinhakConsentGatesResolved = 0
    private var jinhakMissionBootstrapStartedAtMs = 0L
    private var jinhakFirstPopulatedStorageAtMs = 0L
    private var jinhakUnboundSavedApplicationObservations = 0
    private var jinhakLastAgentActionLabel = ""
    private var jinhakLastAgentActionOriginRoute = ""
    private var jinhakLastAgentActionMissionContext: JinhakApplicationMission.Context? = null
    private var jinhakSlowLaneEscalated = 0
    private var jinhakSlowLaneCompleted = 0
    private var jinhakSlowLaneFailed = 0
    private var jinhakSlowLaneUserActionRequired = 0
    private var jinhakSlowLaneCompletedDurationMs = 0L
    private var jinhakSlowLaneMaxDurationMs = 0L
    private var jinhakReportBridgeContext: JSONObject? = null
    private var jinhakReportBridgeArmed = 0
    private var jinhakReportBridgeApplied = 0
    private var jinhakReportBridgeConfirmed = 0
    private var jinhakMissionAnchorActionsAttempted = 0
    private val jinhakAnchorRejectReasons = linkedMapOf<String, Int>()
    private val jinhakSlowLaneFailureReasons = linkedMapOf<String, Int>()
    private val cloudFrontierTaskIds = linkedMapOf<String, String>()
    private var cloudFrontierClaimInProgress = false
    private var cloudFrontierClaimAttempts = 0
    private var cloudFrontierPublished = 0
    private var cloudFrontierClaimed = 0
    private var cloudFrontierCompleted = 0
    private var cloudFrontierCompletionFailed = 0
    private var batchSkipSnapshotUntilMs = 0L
    private var runtimeLastSafePath = ""
    private var runtimeRendererRecovering = false
    private var jinhakStallWatchdogGeneration = 0
    private var jinhakConsecutiveStalls = 0
    private var jinhakRecoveredStalls = 0
    private var jinhakAbsoluteTargetKey = ""
    private var jinhakAbsoluteTargetGeneration = 0
    private var unifiedFinishInProgress = false
    private var pendingUnifiedExportSessionId: String? = null
    private var startupLoginPreflightActive = false
    private var startupLoginPreflightVerified = false
    private var startupLoginStage = "idle"
    private var startupLoginOpenAttempted = false
    private var startupLoginPollGeneration = 0
    private var startupLoginTrigger = ""
    private var startupLoginAdigaRestoredLease = false
    private var startupLoginJinhakRestoredLease = false
    private var startupLoginAdigaAuthenticated = false
    private var startupLoginJinhakAuthenticated = false
    private var startupLoginUiOpenCount = 0
    private var startupLoginVerifiedAtMs = 0L
    private var startupSessionPreflightBypassed = false
    private var credentialAutoLoginInFlight = false
    private var credentialAutoLoginLastAttemptAtMs = 0L
    private var credentialAutoLoginAttempts = 0
    private var startupCredentialPromptedProvider: ProviderId? = null
    private var credentialLoginSurfaceGeneration = 0
    private var credentialLoginSurfaceKey = ""
    private var credentialLoginSurfaceAttempts = 0
    private var credentialAwaitingLoginExitProvider: ProviderId? = null
    private var credentialLoginSurfaceSeenProvider: ProviderId? = null
    private var credentialLoginSurfaceSeenAtMs = 0L
    private var credentialLoginSurfaceDetections = 0
    private var credentialAutoLoginSubmissions = 0
    private var credentialAutoLoginSuccesses = 0
    private var credentialAutoLoginFailures = 0
    private var credentialAutoLoginLastResult = ""
    private var credentialAutoLoginLastProvider = ""
    private var credentialAutoLoginLastAtMs = 0L
    private var batchRenderedLoginSurfacePauses = 0
    private var crossVersionResumeBlocks = 0
    private var staleSessionLeaseBypassesPrevented = 0
    private var loginRouteFallbackPauses = 0
    private var loginRouteFallbackCredentialPrompts = 0
    private var jinhakCoreScopeBlockedUrls = 0
    private val jinhakCoreScopeBlockedLaneCounts = linkedMapOf<String, Int>()
    private var jinhakAuthVerifiedForBatch = false
    private var jinhakCoreBootstrapState = "idle"
    private var startupJinhakProtectedProbeAttempted = false
    private var startupAuthIndeterminatePolls = 0
    private var jinhakProtectedCoreStablePasses = 0
    private var jinhakTransitionAuthGateActive = false
    private var jinhakLoginRecoveryGeneration = 0
    private var jinhakLoginRecoveryPolls = 0
    private var jinhakReauthCycles = 0
    private var jinhakAuthVerificationFailures = 0
    private var jinhakTransitionAuthChecks = 0
    private var jinhakLastCoreVerifiedAtMs = 0L
    private var jinhakLastAuthEvidence = "none"
    private var jinhakSessionKeepAliveTicks = 0
    private var jinhakSessionKeepAliveBackgroundTicks = 0
    private var jinhakSessionExtensionClicks = 0
    private var jinhakOriginInferredMissionTargets = 0
    private var jinhakExternalNavigationsBlocked = 0
    private var jinhakBatchStartCount = 0
    private val jinhakNormalizedMissionSeedContexts = linkedMapOf<String, JinhakApplicationMission.Context>()
    private val jinhakNormalizedIdentitySeedKeys = linkedSetOf<String>()
    private val jinhakNormalizedCandidateBindingKeys = linkedSetOf<String>()
    private var jinhakNormalizedAmbiguousBindings = 0

    companion object {
        private const val SAVE_JSON_REQUEST = 7001
        private const val MAX_BATCH_PAGES = 3200
        private const val MAX_PAGE_RETRIES = 3
        private const val PREVIEW_LIMIT = 16000
        private const val MAX_SESSION_SYNC_RETRIES = 3
        private const val BATCH_NAVIGATION_TIMEOUT_MS = 15_000L
        private const val MAX_JINHAK_AUTONAV_PAGES = 420
        private const val JINHAK_SOFT_STALL_MS = 12_000L
        private const val JINHAK_HARD_STALL_MS = 24_000L
        private const val JINHAK_SLOW_ESCALATION_MS = 35_000L
        private const val MAX_JINHAK_CONSECUTIVE_STALLS = 4
        private const val MAX_JINHAK_GENERIC_ACTIONS = 180
        private const val MAX_JINHAK_MISSION_ACTIONS = 220
        private const val MAX_JINHAK_REFERENCE_ROUTE_CAPTURES = 2
        private const val JINHAK_NO_PROGRESS_FENCE_MS = 60_000L
        private const val JINHAK_PROGRESS_FENCE_POLL_MS = 15_000L
        private const val JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS = 10_000L
        private const val AUTO_LOGIN_AND_COLLECT_ON_LAUNCH = true
        private const val LOGIN_PREFLIGHT_DOM_SETTLE_MS = 300L
        private const val LOGIN_PREFLIGHT_POLL_MS = 1_500L
        private const val JINHAK_LOGIN_RECOVERY_POLL_MS = 1_500L
        private const val JINHAK_CORE_AUTH_STABLE_PASSES = 2
        private const val MAX_CLOUD_FRONTIER_CLAIM_ATTEMPTS = 3
        private const val RUNTIME_PREFS = "collector_runtime_v064"
        private const val VERSION = "0.9.9"
        private const val BUILD_CODE = 10990
        private const val LOCAL_FIRST_BETA = true
        private const val ADIGA_RETRY_SUSPENDED = true
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        installRuntimeCrashGuard()
        cloudOffload = CloudOffloadCoordinator(this)
        localStore = LocalCollectorStore(this)
        sessionVault = SecureSessionVault(this)
        credentialVault = CredentialVault(this)
        buildUi()
        slowLanePool = JinhakSlowLanePool(this, slowLaneHost, object : JinhakSlowLanePool.Listener {
            override fun onSlowLaneCompleted(task: JinhakSlowLanePool.Task, snapshot: JSONObject, stats: JinhakSlowLanePool.ResultStats) {
                handleJinhakSlowLaneCompleted(task, snapshot, stats)
            }
            override fun onSlowLaneFailed(task: JinhakSlowLanePool.Task, reason: String, stats: JinhakSlowLanePool.ResultStats) {
                handleJinhakSlowLaneFailed(task, reason, stats)
            }
            override fun onSlowLaneStatsChanged(stats: JinhakSlowLanePool.Stats) {
                if (batchRunning && provider == ProviderId.JINHAK && stats.running + stats.queued > 0) {
                    sessionState.text = "● 로그인 유지 / 병렬 slow ${stats.running} · 대기 ${stats.queued}"
                }
            }
        })
        configureWebView()
        val resumed = resumeInterruptedUnifiedSessionIfNeeded()
        if (!resumed) {
            if (AUTO_LOGIN_AND_COLLECT_ON_LAUNCH) {
                handler.postDelayed({ startAutomaticLoginAndCollectionSequence("app-launch") }, 350L)
            } else {
                openProvider(ProviderId.JINHAK)
            }
        }
        handler.postDelayed({ sendPendingRuntimeEvents() }, 1200L)
    }

    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        if (level >= TRIM_MEMORY_RUNNING_LOW) {
            recordRuntimeEvent("memory-trim", JSONObject().put("level", level))
            if (provider == ProviderId.JINHAK) {
                if (::slowLanePool.isInitialized) slowLanePool.setMaxActiveWorkers(1)
                // SQLite is authoritative. Do not retain large autonomous-crawl copies in RAM.
                batchSnapshots = JSONArray()
                batchRecords = JSONArray()
                batchResources = JSONArray()
                lastJinhakDigest = JSONObject()
                lastJson = ""
            }
        }
    }

    private fun buildUi() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(10, 10, 10, 10)
        }

        root.addView(TextView(this).apply {
            text = "Admission Collector v$VERSION · build $BUILD_CODE · LOCAL-FIRST"
            gravity = Gravity.CENTER
            textSize = 13f
            setPadding(8, 6, 8, 6)
        }, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ))

        val tabs = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        tabs.addView(Button(this).apply {
            text = "어디가"
            setOnClickListener { openProvider(ProviderId.ADIGA) }
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        tabs.addView(Button(this).apply {
            text = "진학사"
            setOnClickListener { openProvider(ProviderId.JINHAK) }
        }, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val sessionRow = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
        }
        sessionState = TextView(this).apply {
            text = "세션 상태 확인 중"
            setPadding(8, 8, 8, 8)
        }
        val sessionButton = Button(this).apply {
            text = "계정 자동로그인 설정"
            setOnClickListener { showCredentialDialog(provider, continueAfterSave = false) }
        }
        val liveWebButton = Button(this).apply {
            text = "Live 웹"
            setOnClickListener {
                val target = cloudOffload.liveDashboardUrl()
                if (target == null) {
                    Toast.makeText(this@MainActivity, "Cloudflare 수집 토큰을 먼저 한 번 설정해주세요.", Toast.LENGTH_LONG).show()
                    cloudOffload.showSettingsDialog(this@MainActivity)
                } else {
                    runCatching { startActivity(Intent(Intent.ACTION_VIEW, Uri.parse(target))) }
                        .onFailure { Toast.makeText(this@MainActivity, "웹 대시보드를 열 수 없습니다.", Toast.LENGTH_LONG).show() }
                }
            }
        }
        sessionRow.addView(sessionState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        sessionRow.addView(sessionButton)
        sessionRow.addView(liveWebButton)

        val actions1 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val back = Button(this).apply {
            text = "←"
            setOnClickListener { if (webView.canGoBack()) webView.goBack() }
        }
        val currentCollect = Button(this).apply {
            text = "현재 페이지 수집"
            setOnClickListener { collectCurrentPage() }
        }
        batchButton = Button(this).apply {
            text = "접근 가능 정보 일괄 수집"
            setOnClickListener {
                if (batchRunning) confirmStopBatch() else startBatch()
            }
        }
        actions1.addView(back)
        actions1.addView(currentCollect, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions1.addView(batchButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val actions2 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        val resume = Button(this).apply {
            text = "로그인/동의 후 계속"
            setOnClickListener { resumeAfterLogin() }
        }
        val save = Button(this).apply {
            text = "JSON 저장"
            setOnClickListener { saveJson() }
        }
        val localState = Button(this).apply {
            text = "로컬 진행상태"
            setOnClickListener {
                val runId = localRunId ?: localStore.latestResumableRun(provider.wireName)
                val message = if (runId == null) {
                    "현재 이어받을 로컬 수집이 없습니다."
                } else {
                    localStore.stats(runId).toString(2)
                }
                AlertDialog.Builder(this@MainActivity)
                    .setTitle("Local-First 저장 상태")
                    .setMessage(message)
                    .setPositiveButton("확인", null)
                    .show()
            }
        }
        actions2.addView(resume, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(save, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions2.addView(localState, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        val actions3 = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER
        }
        unifiedButton = Button(this).apply {
            text = "자동 로그인 + 통합 수집"
            setOnClickListener {
                when {
                    startupLoginPreflightActive -> cancelStartupLoginPreflight("user-cancel")
                    unifiedRunning -> finishUnifiedCollection("user-finish")
                    else -> startUnifiedCollection()
                }
            }
        }
        diagnosticButton = Button(this).apply {
            text = "진학사 전체 분석 전송"
            setOnClickListener {
                if (provider == ProviderId.JINHAK) sendLatestJinhakAnalysisDigest() else sendLatestLocalDiagnostic(manual = true)
            }
        }
        actions3.addView(unifiedButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        actions3.addView(diagnosticButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        status = TextView(this).apply {
            text = "Admission Collector v$VERSION 준비 중"
            setPadding(8, 8, 8, 8)
        }

        webView = WebView(this)
        batchCover = TextView(this).apply {
            text = "수집 대기 중"
            gravity = Gravity.CENTER
            textSize = 18f
            setTextColor(android.graphics.Color.DKGRAY)
            setBackgroundColor(android.graphics.Color.WHITE)
            setPadding(32, 32, 32, 32)
            visibility = View.GONE
            isClickable = true
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_YES
        }
        slowLaneHost = FrameLayout(this).apply {
            alpha = 0.01f
            isClickable = false
            isFocusable = false
            importantForAccessibility = View.IMPORTANT_FOR_ACCESSIBILITY_NO_HIDE_DESCENDANTS
            translationX = -10000f
            translationY = -10000f
        }
        val browserStack = FrameLayout(this).apply {
            addView(webView, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(slowLaneHost, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
            addView(batchCover, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }
        preview = TextView(this).apply {
            text = "수집 결과가 여기에 표시됩니다."
            setTextIsSelectable(true)
            setPadding(12, 12, 12, 12)
        }
        val scroll = ScrollView(this).apply { addView(preview) }

        root.addView(tabs)
        root.addView(sessionRow)
        root.addView(actions1)
        root.addView(actions2)
        root.addView(actions3)
        root.addView(status)
        root.addView(browserStack, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 3f))
        root.addView(scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 2f))
        setContentView(root)
    }

    @Suppress("SetJavaScriptEnabled")
    private fun configureWebView() {
        runtimeRendererRecovering = false
        WebView.setWebContentsDebuggingEnabled(false)
        CookieManager.getInstance().apply {
            setAcceptCookie(true)
            setAcceptThirdPartyCookies(webView, true)
        }

        webView.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            databaseEnabled = true
            cacheMode = WebSettings.LOAD_DEFAULT
            javaScriptCanOpenWindowsAutomatically = true
            setSupportMultipleWindows(true)
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            userAgentString = userAgentString + " AdmissionCollector/$VERSION"
        }

        webView.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val target = request.url?.toString().orEmpty()
                if (batchRunning && provider == ProviderId.JINHAK && target.isNotBlank() && !ProviderRegistry.adapter(ProviderId.JINHAK).accepts(target)) {
                    jinhakExternalNavigationsBlocked += 1
                    recordRuntimeEvent("jinhak-external-navigation-blocked", JSONObject()
                        .put("targetSafePath", runtimeSafePath(target))
                        .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget)))
                    return true
                }
                return false
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                runtimeLastSafePath = runtimeSafePath(url)
                persistRuntimeCheckpoint()
                if (batchRunning && !batchPausedForLogin) {
                    if (provider == ProviderId.JINHAK) armJinhakAbsoluteTargetWatchdog(url)
                    armBatchNavigationWatchdog(url)
                    status.text = "수집 엔진 로딩: ${safeDisplayUrl(url)}"
                    if (::batchCover.isInitialized) {
                        batchCover.text = "입시정보 수집 중\n\n페이지 렌더링은 이 화면 뒤에서 처리됩니다.\n${safeDisplayUrl(url)}"
                    }
                } else if (!batchRunning) {
                    status.text = "불러오는 중: ${safeDisplayUrl(url)}"
                }
            }

            override fun onPageFinished(view: WebView, url: String) {
                CookieManager.getInstance().flush()
                // v0.9.5: never navigate to login proactively. Probe the rendered DOM after
                // every navigation and auto-login only when an actual login surface is visible.
                scheduleLoginSurfaceDetection(provider, "page-finished")
                if (startupLoginPreflightActive) {
                    handleStartupLoginPreflightPageFinished(url)
                    return
                }
                if (unifiedRunning && unifiedPhase == "adiga" && unifiedPendingAdigaStart && provider == ProviderId.ADIGA && !batchRunning) {
                    unifiedPendingAdigaStart = false
                    handler.postDelayed({
                        if (unifiedRunning && unifiedPhase == "adiga" && !batchRunning) startBatch()
                    }, 350L)
                    return
                }
                if (unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK && jinhakTransitionAuthGateActive && !batchRunning) {
                    handleJinhakTransitionAuthGate(url)
                    return
                }
                if (unifiedRunning && unifiedPhase == "jinhak" && unifiedPendingJinhakStart && provider == ProviderId.JINHAK && !batchRunning) {
                    unifiedPendingJinhakStart = false
                    unifiedJinhakAutoCapture = false
                    status.text = "통합 수집 2/2 · 진학사 자동 크롤러 시작: 접근 가능한 진학사 화면을 자율 순회합니다."
                    handler.postDelayed({
                        if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
                    }, 450L)
                    return
                }
                if (!batchRunning && unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK && unifiedJinhakAutoCapture) {
                    scheduleUnifiedJinhakAutoCapture(url)
                }
                if (batchRunning && !batchPausedForLogin) {
                    // v0.9.6: authentication is a gate in front of snapshot processing. A
                    // protected target that redirects to a rendered login form must not be
                    // counted as a failed/visited document and skipped. Detect first, pause
                    // while keeping currentBatchTarget intact, then retry that exact target
                    // after the login surface disappears.
                    continueBatchAfterRenderedLoginGuard(url, 0)
                    return
                }
                if (batchPausedForLogin) {
                    if (provider == ProviderId.JINHAK) {
                        scheduleJinhakLoginRecovery("batch-paused-page-finished")
                    } else {
                        checkSessionState { needsLogin, authenticated ->
                            if (!needsLogin && authenticated) {
                                sessionState.text = "● 로그인 상태 복구 감지"
                                resumeAfterLogin()
                            }
                        }
                    }
                } else {
                    status.text = "현재 페이지: ${safeDisplayUrl(url)}"
                    checkSessionState()
                }
            }

            override fun onRenderProcessGone(view: WebView?, detail: RenderProcessGoneDetail?): Boolean {
                if (runtimeRendererRecovering) return true
                runtimeRendererRecovering = true
                val didCrash = detail?.didCrash() ?: false
                recordRuntimeEvent(
                    "webview-renderer-gone",
                    JSONObject()
                        .put("didCrash", didCrash)
                        .put("priorityAtExit", detail?.rendererPriorityAtExit() ?: -1)
                        .put("batchRunning", batchRunning)
                )
                localRunId?.let { runId ->
                    val key = currentBatchTarget?.let { canonicalizeBatchUrl(it) }.orEmpty()
                    if (key.isNotBlank()) localStore.markDocument(runId, key, "error", 0, "webview-renderer-gone")
                }
                persistRuntimeCheckpoint(forceResume = unifiedRunning)
                batchRunning = false
                batchCollecting = false
                disarmBatchNavigationWatchdog()
                runCatching {
                    (view?.parent as? ViewGroup)?.removeView(view)
                    view?.destroy()
                }
                handler.postDelayed({ recreate() }, 250L)
                return true
            }
        }

        webView.webChromeClient = object : WebChromeClient() {
            override fun onJsAlert(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                if (batchRunning && provider == ProviderId.ADIGA) {
                    result?.confirm()
                    if (isAdigaBlockingErrorMessage(message)) {
                        handleAdigaBlockingDialog(message)
                    } else {
                        status.text = "어디가 안내창 자동 확인 후 수집 계속"
                    }
                    return true
                }
                return super.onJsAlert(view, url, message, result)
            }

            override fun onJsConfirm(view: WebView?, url: String?, message: String?, result: JsResult?): Boolean {
                if (batchRunning && provider == ProviderId.ADIGA && isAdigaBlockingErrorMessage(message)) {
                    result?.confirm()
                    handleAdigaBlockingDialog(message)
                    return true
                }
                return super.onJsConfirm(view, url, message, result)
            }

            override fun onCreateWindow(
                view: WebView?,
                isDialog: Boolean,
                isUserGesture: Boolean,
                resultMsg: android.os.Message?
            ): Boolean {
                val transport = resultMsg?.obj as? WebView.WebViewTransport ?: return false
                val child = WebView(this@MainActivity)
                child.settings.javaScriptEnabled = true
                child.settings.domStorageEnabled = true
                child.settings.javaScriptCanOpenWindowsAutomatically = true
                child.settings.setSupportMultipleWindows(true)
                child.webViewClient = object : WebViewClient() {
                    override fun shouldOverrideUrlLoading(v: WebView, request: WebResourceRequest): Boolean {
                        webView.loadUrl(request.url.toString())
                        return true
                    }

                    override fun onPageFinished(v: WebView, url: String) {
                        if (url.isNotBlank() && url != "about:blank") webView.loadUrl(url)
                    }
                }
                transport.webView = child
                resultMsg.sendToTarget()
                return true
            }
        }
    }

    private fun attemptSessionExtension() {
        if (!::webView.isInitialized) return
        val js = """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0 && r.height>0;
              }
              var body=(document.body&&document.body.innerText?document.body.innerText:'').replace(/\s+/g,' ');
              if(!/(자동\s*로그아웃|로그인\s*시간.*연장|세션.*연장)/i.test(body)) return false;
              var nodes=document.querySelectorAll('button,a,[role=button]');
              for(var i=0;i<nodes.length;i++){
                var el=nodes[i];
                if(!visible(el)) continue;
                var label=(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
                if(/^(연장하기|로그인\s*연장|세션\s*연장|시간\s*연장)$/i.test(label)){
                  try{ el.click(); return true; }catch(e){}
                }
              }
              return false;
            })();
        """.trimIndent()
        listOf(webView).forEach { target ->
            target.evaluateJavascript(js) { result ->
                if (result == "true") {
                    CookieManager.getInstance().flush()
                    if (provider == ProviderId.JINHAK) {
                        jinhakSessionExtensionClicks += 1
                        persistJinhakAuthDiagnostics("session-extension-click")
                    }
                    sessionState.text = "● 로그인 세션 자동 연장"
                }
            }
        }
    }

    private fun currentAdapter(): ProviderAdapter = ProviderRegistry.adapter(provider)

    private fun openProvider(which: ProviderId) {
        if (startupLoginPreflightActive) {
            Toast.makeText(this, "자동 로그인 준비 중에는 사이트 전환을 로그인 오케스트레이터가 관리합니다.", Toast.LENGTH_SHORT).show()
            return
        }
        if (unifiedRunning) {
            Toast.makeText(this, "통합 수집 중에는 서비스 전환을 수집 엔진이 관리합니다.", Toast.LENGTH_SHORT).show()
            return
        }
        if (batchRunning) stopBatch("서비스 전환")
        provider = which
        localRunId = localStore.latestResumableRun(which.wireName)
        CookieManager.getInstance().flush()
        val restoredLease = runCatching { sessionVault.restore(which.wireName) }.getOrNull()
        sessionState.text = if (restoredLease?.restored == true) {
            "● 암호화 세션 lease 복구 · ${restoredLease.leaseId.take(8)}…"
        } else "세션 상태 확인 중"
        val capabilities = ProviderCapabilities.profile(which)
        status.text = if (which == ProviderId.JINHAK) {
            "진학사 observation-first 모드 · active ${capabilities.active.size} / discoverable ${capabilities.discoverable.size} · 분류 여부와 무관하게 증거 보존"
        } else {
            "어디가 공식정보 모드 · active ${capabilities.active.size} · deterministic ID/year planner 기반 전환 준비"
        }
        batchButton.text = when (which) {
            ProviderId.JINHAK -> "진학사 에이전트 자동 수집"
            ProviderId.ADIGA -> "어디가 복구 보류"
        }
        diagnosticButton.text = if (which == ProviderId.JINHAK) "진학사 전체 분석 전송" else "어디가 진단 로그 전송"
        webView.loadUrl(which.homeUrl)
    }

    private fun refreshSessionOrOpenLogin() {
        checkSessionState { needsLogin, authenticated ->
            if (authenticated) {
                sessionState.text = "● 로그인 유지됨"
                if (batchRunning && batchPausedForLogin) resumeAfterLogin()
                return@checkSessionState
            }
            // v0.9.5: refresh means re-probe only. It must never click a login link,
            // navigate to a login URL, or bounce the user back to provider.homeUrl.
            scheduleLoginSurfaceDetection(provider, "session-refresh")
            sessionState.text = if (needsLogin) "○ 로그인 필요 감지 · 로그인 화면 대기" else "△ 로그인 상태 재확인 중 · 현재 화면 유지"
            status.text = if (needsLogin) {
                "로그인이 필요한 상태가 감지되었습니다. 현재 화면을 유지하며 로그인 폼이 렌더링되면 저장 계정으로 자동 로그인합니다."
            } else {
                "로그인 상태가 확정되지 않았습니다. 화면 이동 없이 현재 페이지에서 다시 확인합니다."
            }
        }
    }

    private fun checkSessionState(callback: ((Boolean, Boolean) -> Unit)? = null) {
        val js = """
            (function(){
              function visible(el){
                if(!el) return false;
                var s=getComputedStyle(el);
                if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false;
                var r=el.getBoundingClientRect();
                return r.width>0 && r.height>0;
              }
              function roots(doc){
                var out=[doc];
                try{
                  var all=doc.querySelectorAll('*');
                  for(var i=0;i<all.length;i++) if(all[i].shadowRoot) out.push(all[i].shadowRoot);
                }catch(e){}
                return out;
              }
              var docs=[document];
              try{
                var frames=document.querySelectorAll('iframe,frame');
                for(var f=0;f<frames.length;f++) try{ if(frames[f].contentDocument) docs.push(frames[f].contentDocument); }catch(e){}
              }catch(e){}
              var loginSurface=false;
              var bodyText='';
              var logoutControl=false;
              for(var d=0;d<docs.length;d++){
                var doc=docs[d];
                try{ bodyText += ' ' + ((doc.body&&doc.body.innerText)||''); }catch(e){}
                var rs=roots(doc);
                var visiblePassword=false;
                var visibleUser=false;
                for(var r=0;r<rs.length;r++){
                  var root=rs[r];
                  try{
                    var pw=root.querySelectorAll('input[type=password]');
                    for(var p=0;p<pw.length;p++) if(visible(pw[p])) { visiblePassword=true; break; }
                    var us=root.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])');
                    for(var u=0;u<us.length;u++){
                      if(!visible(us[u])) continue;
                      var meta=((us[u].name||'')+' '+(us[u].id||'')+' '+(us[u].placeholder||'')+' '+(us[u].autocomplete||'')).toLowerCase();
                      if(/아이디|user|login|member|email|account|id/.test(meta) && !/search|검색/.test(meta)) { visibleUser=true; break; }
                    }
                    var controls=root.querySelectorAll('a,button,[role=button],input[type=submit],input[type=button]');
                    for(var c=0;c<controls.length;c++){
                      var node=controls[c]; if(!visible(node)) continue;
                      var label=(node.innerText||node.value||node.textContent||node.getAttribute('aria-label')||'').replace(/\s+/g,' ').trim();
                      if(/^(로그아웃|log\s*out|sign\s*out)$/i.test(label)){ logoutControl=true; break; }
                    }
                  }catch(e){}
                }
                if(visiblePassword && visibleUser) loginSurface=true;
              }
              var loginRequired=/(로그인이\s*필요|로그인\s*후\s*(?:이용|사용)|로그인해\s*주세요|로그인해주세요|회원만\s*이용|서비스\s*이용을\s*위해\s*로그인)/i.test(bodyText.slice(0,24000));
              return JSON.stringify({needsLogin:(loginSurface||loginRequired)&&!logoutControl,authenticated:logoutControl,loginSurface:loginSurface,loginRequired:loginRequired,urlLooksLogin:/(\/member\/login|\/mbs\/log\/|mbslogview)/i.test(location.href)});
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            try {
                val obj = JSONObject(decodeJsString(encoded))
                val needsLogin = obj.optBoolean("needsLogin", false)
                var authenticated = obj.optBoolean("authenticated", false)
                val loginSurface = obj.optBoolean("loginSurface", false)
                val now = System.currentTimeMillis()
                if (loginSurface) {
                    credentialLoginSurfaceSeenProvider = provider
                    credentialLoginSurfaceSeenAtMs = now
                }
                // A submitted credential login is considered successful only after the
                // actual login surface disappears and no explicit login-required state remains.
                if (!authenticated && !needsLogin && !loginSurface && credentialAwaitingLoginExitProvider == provider) {
                    credentialAutoLoginLastResult = "submitted-awaiting-provider-verification"
                    credentialAutoLoginLastProvider = provider.wireName
                    credentialAutoLoginLastAtMs = now
                    if (provider == ProviderId.JINHAK) {
                        jinhakAuthVerifiedForBatch = false
                        jinhakCoreBootstrapState = "credential-submitted-awaiting-core-verification"
                    }
                }
                sessionState.text = when {
                    authenticated -> "● 로그인 유지됨 · 보안 세션 lease 갱신"
                    loginSurface -> "○ 로그인 화면 감지 · 자동 로그인 준비"
                    needsLogin -> "○ 로그인 필요 상태 감지"
                    else -> "△ 로그인 상태 미확정 · 현재 화면 유지"
                }
                if (authenticated) {
                    val currentUrl = webView.url.orEmpty()
                    if (currentUrl.isNotBlank()) runCatching { sessionVault.captureAuthenticated(provider.wireName, currentUrl, VERSION) }
                }
                callback?.invoke(needsLogin, authenticated)
            } catch (_: Exception) {
                sessionState.text = "△ 로그인 상태 확인 불가 · 현재 화면 유지"
                callback?.invoke(false, false)
            }
        }
    }

    private fun runtimeSafePath(url: String?): String {
        if (url.isNullOrBlank()) return ""
        return try {
            val uri = Uri.parse(url)
            val host = uri.host.orEmpty().lowercase()
            val path = uri.path.orEmpty().ifBlank { "/" }
            if (host.isBlank()) path.take(300) else "$host$path".take(300)
        } catch (_: Exception) { "unparseable" }
    }

    private fun persistRuntimeCheckpoint(forceResume: Boolean = unifiedRunning) {
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

    private fun recordRuntimeEvent(type: String, detail: JSONObject = JSONObject(), synchronous: Boolean = false) {
        runCatching {
            val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
            val arr = runCatching { JSONArray(prefs.getString("events", "[]")) }.getOrElse { JSONArray() }
            val event = JSONObject()
                .put("at", Instant.now().toString())
                .put("type", type.take(80))
                .put("collectorVersion", VERSION)
                .put("provider", provider.wireName)
                .put("phase", unifiedPhase.take(40))
                .put("safePath", runtimeLastSafePath.take(300))
                .put("batchPageCount", batchPageCount)
                .put("queueSize", batchQueue.size)
                .put("errorCount", batchErrors.length())
                .put("detail", detail)
            arr.put(event)
            while (arr.length() > 40) arr.remove(0)
            val editor = prefs.edit().putString("events", arr.toString())
                .putBoolean("hasPendingEvents", true)
            if (synchronous) editor.commit() else editor.apply()
        }
    }

    private fun installRuntimeCrashGuard() {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            runCatching {
                val frames = JSONArray()
                throwable.stackTrace.take(18).forEach { frame ->
                    frames.put("${frame.className}.${frame.methodName}:${frame.lineNumber}".take(220))
                }
                recordRuntimeEvent(
                    "uncaught-exception",
                    JSONObject()
                        .put("exceptionClass", throwable.javaClass.name.take(160))
                        .put("thread", thread.name.take(80))
                        .put("frames", frames),
                    synchronous = true
                )
                persistRuntimeCheckpoint(forceResume = unifiedRunning)
            }
            previous?.uncaughtException(thread, throwable)
        }
    }

    private fun sendPendingRuntimeEvents() {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        if (!prefs.getBoolean("hasPendingEvents", false)) return
        val arr = runCatching { JSONArray(prefs.getString("events", "[]")) }.getOrElse { JSONArray() }
        if (arr.length() == 0) {
            prefs.edit().putBoolean("hasPendingEvents", false).apply()
            return
        }
        val payload = JSONObject()
            .put("schemaVersion", 1)
            .put("type", "collector-runtime-events")
            .put("collectorVersion", VERSION)
            .put("events", arr)
            .put("privacy", "class-method-stack-and-sanitized-host-path-only-no-query-no-cookie-no-session-token-no-form-values")
        cloudOffload.sendDiagnostic("runtime", VERSION, payload) { result ->
            if (result.isSuccess) {
                prefs.edit().remove("events").putBoolean("hasPendingEvents", false).apply()
            }
        }
    }

    private fun resumeInterruptedUnifiedSessionIfNeeded(): Boolean {
        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)
        val requested = prefs.getBoolean("resumeUnified", false)
        val sessionId = localStore.latestUnifiedSession() ?: return false
        val session = localStore.unifiedStatus(sessionId)
        if (!requested || session.optString("status") != "running") return false
        // v0.9.6: never continue a running unified session created by another collector
        // version. Cross-version resume mixes old navigation/auth state with new code and
        // makes login diagnostics impossible to interpret. Preserve the old local data by
        // stopping only the unified session envelope, then start a fresh current-version run.
        val sessionCollectorVersion = session.optString("collectorVersion")
        if (sessionCollectorVersion.isNotBlank() && sessionCollectorVersion != VERSION) {
            crossVersionResumeBlocks += 1
            localStore.updateUnifiedSession(
                sessionId,
                session.optString("phase", "interrupted"),
                "stopped",
                "cross-version-resume-blocked:$sessionCollectorVersion->$VERSION"
            )
            prefs.edit().putBoolean("resumeUnified", false).apply()
            recordRuntimeEvent(
                "cross-version-session-resume-blocked",
                JSONObject()
                    .put("fromVersion", sessionCollectorVersion.take(40))
                    .put("toVersion", VERSION)
                    .put("dataPreserved", true)
            )
            return false
        }

        unifiedSessionId = sessionId
        unifiedRunning = true
        unifiedPhase = session.optString("phase", "jinhak")
        unifiedButton.text = "통합 수집 종료"
        jinhakConsecutiveStalls = 0
        batchRunning = false
        batchCollecting = false

        return if (unifiedPhase == "adiga") {
            provider = ProviderId.ADIGA
            localRunId = session.optJSONObject("adiga")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
                ?: localStore.beginOrResume(ProviderId.ADIGA.wireName, VERSION)
            unifiedPendingAdigaStart = true
            unifiedPendingJinhakStart = false
            status.text = "이전 튕김/중단 감지: 어디가 체크포인트에서 통합 수집을 자동 복구합니다."
            val seed = ProviderRegistry.adapter(ProviderId.ADIGA).seedUrls().firstOrNull() ?: ProviderId.ADIGA.homeUrl
            webView.loadUrl(seed)
            true
        } else {
            provider = ProviderId.JINHAK
            unifiedPhase = "jinhak"
            localRunId = session.optJSONObject("jinhak")?.optString("runId")?.takeIf { it.isNotBlank() && it != "null" }
                ?: localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = true
            unifiedJinhakAutoCapture = false
            val lease = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
            status.text = if (lease?.restored == true) {
                "이전 중단 감지: 암호화 로그인 세션을 복구하고 진학사 에이전트를 체크포인트에서 재개합니다."
            } else {
                "이전 중단 감지: 저장된 브라우저 세션을 검증한 뒤 진학사 에이전트를 재개합니다."
            }
            webView.loadUrl(ProviderId.JINHAK.homeUrl)
            true
        }
    }

    private fun providerLoginUrl(which: ProviderId): String = when (which) {
        ProviderId.JINHAK -> "https://www.jinhak.com/jh/member/login"
        ProviderId.ADIGA -> "https://www.adiga.kr/mbs/log/mbsLogView.do?menuId=PCMBSLOG1000"
    }

    private fun isProviderLoginUrl(which: ProviderId, rawUrl: String): Boolean {
        val url = rawUrl.lowercase()
        if (url.isBlank()) return false
        return when (which) {
            ProviderId.JINHAK -> url.contains("jinhak.com/") && (url.contains("/member/login") || url.contains("signin") || url.contains("login"))
            ProviderId.ADIGA -> url.contains("adiga.kr/") && (url.contains("/mbs/log/") || url.contains("mbslogview") || url.contains("login"))
        }
    }

    private fun showCredentialDialog(which: ProviderId, continueAfterSave: Boolean) {
        val existing = runCatching { credentialVault.load(which.wireName) }.getOrNull()
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            val p = (18 * resources.displayMetrics.density).toInt()
            setPadding(p, p / 2, p, 0)
        }
        val username = EditText(this).apply {
            hint = "${which.displayName} 아이디"
            inputType = InputType.TYPE_CLASS_TEXT
            setText(existing?.username.orEmpty())
            setSelection(text.length)
        }
        val password = EditText(this).apply {
            hint = if (existing != null) "비밀번호 변경 시에만 다시 입력" else "비밀번호"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        layout.addView(username)
        layout.addView(password)

        val dialog = AlertDialog.Builder(this)
            .setTitle("${which.displayName} 자동로그인")
            .setMessage("이 기기 안에 Android Keystore로 암호화 저장합니다. 계정정보는 수집 JSON·로그·Cloud·웹 대시보드로 전송하지 않습니다.")
            .setView(layout)
            .setNeutralButton("저장정보 삭제") { _, _ ->
                credentialVault.clear(which.wireName)
                sessionState.text = "○ ${which.displayName} 자동로그인 정보 삭제됨"
            }
            .setNegativeButton("취소", null)
            .setPositiveButton("저장") { _, _ ->
                val u = username.text.toString().trim()
                val p = password.text.toString().ifBlank { existing?.password.orEmpty() }
                if (u.isBlank() || p.isBlank()) {
                    Toast.makeText(this, "아이디와 비밀번호를 모두 입력해야 합니다.", Toast.LENGTH_LONG).show()
                    return@setPositiveButton
                }
                runCatching { credentialVault.save(which.wireName, u, p) }
                    .onSuccess {
                        sessionState.text = "● ${which.displayName} 자동로그인 정보 저장됨"
                        recordRuntimeEvent("credential-vault-updated", JSONObject()
                            .put("provider", which.wireName)
                            .put("credentialStored", true)
                            .put("credentialExported", false))
                        if (continueAfterSave) {
                            credentialAutoLoginInFlight = false
                            credentialAutoLoginLastAttemptAtMs = 0L
                            credentialLoginSurfaceAttempts = 0
                            // Do not force a login URL. If the site has already rendered a login
                            // surface, the passive detector will fill and submit it immediately.
                            scheduleLoginSurfaceDetection(which, "credential-saved")
                        }
                    }
                    .onFailure { Toast.makeText(this, "암호화 저장 실패: ${it.javaClass.simpleName}", Toast.LENGTH_LONG).show() }
            }
            .create()
        dialog.show()
    }

    private fun probeLoginSurface(which: ProviderId, callback: (JSONObject) -> Unit) {
        if (provider != which) { callback(JSONObject().put("detected", false)); return }
        val js = """
            (function(){
              try{
                function visible(el){ if(!el) return false; var s=getComputedStyle(el); if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false; var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
                function roots(doc){ var out=[doc]; try{var all=doc.querySelectorAll('*'); for(var i=0;i<all.length;i++) if(all[i].shadowRoot) out.push(all[i].shadowRoot);}catch(e){} return out; }
                var docs=[document]; try{var fs=document.querySelectorAll('iframe,frame'); for(var f=0;f<fs.length;f++) try{if(fs[f].contentDocument) docs.push(fs[f].contentDocument);}catch(e){}}catch(e){}
                var best=null;
                for(var d=0;d<docs.length;d++){
                  var rs=roots(docs[d]);
                  for(var r=0;r<rs.length;r++){
                    var root=rs[r], passes=[]; try{passes=Array.from(root.querySelectorAll('input[type=password]')).filter(visible);}catch(e){}
                    for(var p=0;p<passes.length;p++){
                      var pass=passes[p], form=pass.form||pass.closest('form'), candidates=[];
                      var base=form||root;
                      try{candidates=Array.from(base.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                      if(!candidates.length) try{candidates=Array.from(root.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                      function score(el){ var meta=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase(); var n=0; if(/아이디|user|login|member|email|account/.test(meta)) n+=50; if(/\bid\b/.test(meta)) n+=25; if((el.autocomplete||'').toLowerCase()==='username') n+=80; if((el.type||'').toLowerCase()==='email') n+=10; if(/search|검색/.test(meta)) n-=120; if(form&&el.form===form) n+=100; return n; }
                      candidates.sort(function(a,b){return score(b)-score(a);});
                      var user=candidates[0]||null;
                      var controls=[]; try{controls=Array.from((form||root).querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                      if(!controls.length) try{controls=Array.from(root.querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                      function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\s+/g,' ').trim();}
                      var submit=controls.find(function(el){return /^(로그인|로그인하기|log\s*in|sign\s*in)$/i.test(label(el));})||null;
                      if(user){ best={user:true,pass:true,submit:!!submit,form:!!form}; break; }
                    }
                    if(best) break;
                  }
                  if(best) break;
                }
                var text=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,20000);
                var credentialError=/(아이디\s*(?:또는|나)\s*비밀번호.*(?:확인|일치|오류)|비밀번호.*일치하지|잘못된\s*비밀번호|로그인에\s*실패)/i.test(text);
                return JSON.stringify({detected:!!best,hasUser:!!(best&&best.user),hasPassword:!!(best&&best.pass),hasSubmit:!!(best&&best.submit),hasForm:!!(best&&best.form),credentialError:credentialError,urlLooksLogin:/(\/member\/login|\/mbs\/log\/|mbslogview)/i.test(location.href)});
              }catch(e){return JSON.stringify({detected:false,error:'probe-error'});}
            })();
        """.trimIndent()
        webView.evaluateJavascript(js) { encoded ->
            val obj = runCatching { JSONObject(decodeJsString(encoded)) }.getOrElse { JSONObject().put("detected", false).put("error", "decode-error") }
            if (obj.optBoolean("detected", false)) {
                credentialLoginSurfaceSeenProvider = which
                credentialLoginSurfaceSeenAtMs = System.currentTimeMillis()
            }
            callback(obj)
        }
    }

    private fun scheduleLoginSurfaceDetection(which: ProviderId, reason: String) {
        if (provider != which) return
        val generation = ++credentialLoginSurfaceGeneration
        var detectionCounted = false
        val delays = longArrayOf(100L, 420L, 1_050L, 2_300L)
        delays.forEach { delay ->
            handler.postDelayed({
                if (provider != which || generation != credentialLoginSurfaceGeneration) return@postDelayed
                probeLoginSurface(which) { probe ->
                    if (provider != which || generation != credentialLoginSurfaceGeneration) return@probeLoginSurface
                    if (!probe.optBoolean("detected", false)) return@probeLoginSurface
                    if (!detectionCounted) {
                        detectionCounted = true
                        credentialLoginSurfaceDetections += 1
                        credentialAutoLoginLastProvider = which.wireName
                        credentialAutoLoginLastAtMs = System.currentTimeMillis()
                    }
                    if (batchRunning && !batchPausedForLogin) {
                        pauseBatchForRenderedLoginSurface(which, reason)
                    }
                    sessionState.text = "○ ${which.displayName} 로그인 화면 감지"
                    status.text = "${which.displayName} 로그인 폼을 실제 DOM에서 감지했습니다. 저장된 계정이 있으면 현재 화면에서 자동 로그인합니다."
                    if (credentialVault.has(which.wireName)) {
                        attemptSavedCredentialLogin(which, reason)
                    } else if (startupCredentialPromptedProvider != which) {
                        startupCredentialPromptedProvider = which
                        showCredentialDialog(which, continueAfterSave = true)
                    }
                }
            }, delay)
        }
    }

    private fun attemptSavedCredentialLogin(which: ProviderId, reason: String) {
        if (provider != which) return
        val now = System.currentTimeMillis()
        if (credentialAutoLoginInFlight && now - credentialAutoLoginLastAttemptAtMs < 6_000L) return
        if (now - credentialAutoLoginLastAttemptAtMs < 900L) return
        val credentials = runCatching { credentialVault.load(which.wireName) }.getOrNull() ?: return

        probeLoginSurface(which) { probe ->
            if (!probe.optBoolean("detected", false)) return@probeLoginSurface
            val surfaceKey = which.wireName + "|" + runtimeSafePath(webView.url)
            if (surfaceKey != credentialLoginSurfaceKey) {
                credentialLoginSurfaceKey = surfaceKey
                credentialLoginSurfaceAttempts = 0
            }
            if (probe.optBoolean("credentialError", false) && credentialLoginSurfaceAttempts > 0) {
                if (credentialAutoLoginLastResult != "credential-error") credentialAutoLoginFailures += 1
                credentialAutoLoginLastResult = "credential-error"
                credentialAutoLoginLastProvider = which.wireName
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                credentialAwaitingLoginExitProvider = null
                sessionState.text = "△ ${which.displayName} 저장 계정 로그인 오류 감지"
                status.text = "저장된 계정으로 로그인한 뒤 오류 문구가 감지되어 반복 제출을 중지했습니다. 계정 설정을 확인해주세요."
                return@probeLoginSurface
            }
            if (credentialLoginSurfaceAttempts >= 2) {
                sessionState.text = "△ ${which.displayName} 자동 로그인 재시도 한도 도달"
                return@probeLoginSurface
            }

            credentialAutoLoginInFlight = true
            credentialAutoLoginLastAttemptAtMs = System.currentTimeMillis()
            credentialAutoLoginAttempts += 1
            credentialLoginSurfaceAttempts += 1
            credentialAwaitingLoginExitProvider = which
            val userJs = JSONObject.quote(credentials.username)
            val passJs = JSONObject.quote(credentials.password)
            val script = """
                (function(){
                  try {
                    function visible(el){ if(!el) return false; var s=getComputedStyle(el); if(s.display==='none'||s.visibility==='hidden'||s.opacity==='0') return false; var r=el.getBoundingClientRect(); return r.width>0&&r.height>0; }
                    function setValue(el,value){
                      var proto=Object.getPrototypeOf(el), d=null;
                      while(proto&&!d){d=Object.getOwnPropertyDescriptor(proto,'value');proto=Object.getPrototypeOf(proto);}
                      if(d&&d.set) d.set.call(el,value); else el.value=value;
                      el.focus();
                      ['input','change','keyup','blur'].forEach(function(t){el.dispatchEvent(new Event(t,{bubbles:true}));});
                    }
                    function roots(doc){var out=[doc];try{var all=doc.querySelectorAll('*');for(var i=0;i<all.length;i++)if(all[i].shadowRoot)out.push(all[i].shadowRoot);}catch(e){}return out;}
                    var docs=[document]; try{var fs=document.querySelectorAll('iframe,frame');for(var f=0;f<fs.length;f++)try{if(fs[f].contentDocument)docs.push(fs[f].contentDocument);}catch(e){}}catch(e){}
                    var selected=null;
                    for(var d=0;d<docs.length&&!selected;d++){
                      var rs=roots(docs[d]);
                      for(var r=0;r<rs.length&&!selected;r++){
                        var root=rs[r], passes=[];try{passes=Array.from(root.querySelectorAll('input[type=password]')).filter(visible);}catch(e){}
                        for(var p=0;p<passes.length&&!selected;p++){
                          var pass=passes[p], form=pass.form||pass.closest('form'), base=form||root, users=[];
                          try{users=Array.from(base.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                          if(!users.length)try{users=Array.from(root.querySelectorAll('input:not([type=password]):not([type=hidden]):not([type=checkbox]):not([type=radio]):not([type=submit]):not([type=button])')).filter(visible);}catch(e){}
                          function score(el){var meta=((el.name||'')+' '+(el.id||'')+' '+(el.placeholder||'')+' '+(el.autocomplete||'')).toLowerCase(),n=0;if(/아이디|user|login|member|email|account/.test(meta))n+=50;if(/\bid\b/.test(meta))n+=25;if((el.autocomplete||'').toLowerCase()==='username')n+=80;if(/search|검색/.test(meta))n-=120;if(form&&el.form===form)n+=100;return n;}
                          users.sort(function(a,b){return score(b)-score(a);}); var user=users[0]||null; if(!user)continue;
                          var controls=[];try{controls=Array.from((form||root).querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                          if(!controls.length)try{controls=Array.from(root.querySelectorAll('button,input[type=submit],input[type=button],a,[role=button]')).filter(visible);}catch(e){}
                          function label(el){return ((el.innerText||el.value||el.textContent||el.getAttribute('aria-label')||'')+'').replace(/\s+/g,' ').trim();}
                          var submit=controls.find(function(el){return /^(로그인|로그인하기|log\s*in|sign\s*in)$/i.test(label(el));})||null;
                          selected={user:user,pass:pass,form:form,submit:submit};
                        }
                      }
                    }
                    if(!selected) return 'fields-not-found';
                    setValue(selected.user,$userJs); setValue(selected.pass,$passJs);
                    // Jinhak's current login is UI-driven; prefer the rendered login control
                    // before native form submission so framework click handlers execute.
                    if(selected.submit){ selected.submit.focus(); selected.submit.click(); return 'submitted-click'; }
                    if(selected.form&&typeof selected.form.requestSubmit==='function'){ selected.form.requestSubmit(); return 'submitted-form'; }
                    try{selected.pass.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));selected.pass.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',keyCode:13,which:13,bubbles:true}));return 'submitted-enter';}catch(e){}
                    return 'submit-not-found';
                  } catch(e) { return 'error'; }
                })();
            """.trimIndent()
            webView.evaluateJavascript(script) { encoded ->
                credentialAutoLoginInFlight = false
                val result = decodeJsString(encoded).take(80)
                credentialAutoLoginLastResult = result
                credentialAutoLoginLastProvider = which.wireName
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                if (result.startsWith("submitted")) {
                    credentialAutoLoginSubmissions += 1
                } else {
                    credentialAutoLoginFailures += 1
                }
                recordRuntimeEvent("credential-auto-login-attempt", JSONObject()
                    .put("provider", which.wireName)
                    .put("reason", reason.take(40))
                    .put("result", result)
                    .put("loginSurfaceDetected", true)
                    .put("attemptOnSurface", credentialLoginSurfaceAttempts)
                    .put("credentialStored", true)
                    .put("credentialExported", false))
                sessionState.text = if (result.startsWith("submitted")) "● ${which.displayName} 자동 로그인 제출됨" else "△ ${which.displayName} 자동 로그인: $result"
                if (!result.startsWith("submitted")) credentialAwaitingLoginExitProvider = null
                handler.postDelayed({
                    checkSessionState { needsLogin, authenticated ->
                        if (authenticated) {
                            credentialLoginSurfaceAttempts = 0
                            val url = webView.url.orEmpty()
                            if (url.isNotBlank()) runCatching { sessionVault.captureAuthenticated(which.wireName, url, VERSION) }
                            if (batchRunning && batchPausedForLogin) resumeAfterLogin()
                            if (startupLoginPreflightActive && provider == which) {
                                val generation = startupLoginPollGeneration
                                onStartupProviderAuthenticated(which, generation)
                            }
                        } else if (needsLogin) {
                            scheduleLoginSurfaceDetection(which, "post-submit")
                            if (which == ProviderId.JINHAK) scheduleJinhakLoginRecovery("post-submit-needs-login")
                        } else if (which == ProviderId.JINHAK) {
                            scheduleJinhakLoginRecovery("post-submit-provider-verification")
                        }
                    }
                }, 1_100L)
            }
        }
    }

    private fun startAutomaticLoginAndCollectionSequence(trigger: String) {
        if (startupLoginPreflightActive) return
        if (unifiedRunning || batchRunning) {
            Toast.makeText(this, "진행 중인 수집이 있어 자동 로그인 준비를 시작할 수 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        startupLoginPreflightActive = true
        startupLoginPreflightVerified = false
        startupLoginStage = "adiga-check"
        startupLoginOpenAttempted = false
        startupLoginTrigger = trigger.take(40)
        startupLoginAdigaRestoredLease = false
        startupLoginJinhakRestoredLease = false
        startupLoginAdigaAuthenticated = false
        startupLoginJinhakAuthenticated = false
        startupLoginUiOpenCount = 0
        startupLoginVerifiedAtMs = 0L
        startupSessionPreflightBypassed = false
        startupCredentialPromptedProvider = null
        credentialLoginSurfaceKey = ""
        credentialLoginSurfaceAttempts = 0
        credentialAwaitingLoginExitProvider = null
        credentialLoginSurfaceDetections = 0
        credentialAutoLoginSubmissions = 0
        credentialAutoLoginSuccesses = 0
        credentialAutoLoginFailures = 0
        credentialAutoLoginLastResult = ""
        credentialAutoLoginLastProvider = ""
        credentialAutoLoginLastAtMs = 0L
        loginRouteFallbackPauses = 0
        loginRouteFallbackCredentialPrompts = 0
        jinhakAuthVerifiedForBatch = false
        jinhakCoreBootstrapState = "auth-preflight"
        startupJinhakProtectedProbeAttempted = false
        jinhakProtectedCoreStablePasses = 0
        jinhakTransitionAuthGateActive = false
        jinhakLoginRecoveryGeneration += 1
        jinhakLoginRecoveryPolls = 0
        jinhakReauthCycles = 0
        jinhakAuthVerificationFailures = 0
        jinhakTransitionAuthChecks = 0
        jinhakLastCoreVerifiedAtMs = 0L
        jinhakLastAuthEvidence = "none"
        jinhakSessionKeepAliveTicks = 0
        jinhakSessionKeepAliveBackgroundTicks = 0
        jinhakSessionExtensionClicks = 0
        jinhakOriginInferredMissionTargets = 0
        jinhakExternalNavigationsBlocked = 0

        // v0.9.2: restore the encrypted provider session bundles first. When both are
        // present, do not navigate through the login-preflight UI at all. Server-side
        // expiry is still handled by the existing batch login-pause/recovery path.
        val storedAdiga = runCatching { sessionVault.restore(ProviderId.ADIGA.wireName) }.getOrNull()
        val storedJinhak = runCatching { sessionVault.restore(ProviderId.JINHAK.wireName) }.getOrNull()
        startupLoginAdigaRestoredLease = storedAdiga?.restored == true
        startupLoginJinhakRestoredLease = storedJinhak?.restored == true
        if (startupLoginAdigaRestoredLease && startupLoginJinhakRestoredLease) {
            CookieManager.getInstance().flush()
            staleSessionLeaseBypassesPrevented += 1
            startupSessionPreflightBypassed = false
            startupLoginStage = "stored-session-verification-required"
            sessionState.text = "△ 암호화 세션 복원 · 서버 인증 재검증 필요"
            status.text = "저장된 세션은 복원했지만 인증 성공으로 간주하지 않습니다. 보호 경로에서 실제 인증 상태를 확인합니다."
            recordRuntimeEvent("startup-stored-session-verification-required", JSONObject()
                .put("trigger", startupLoginTrigger)
                .put("adigaRestored", true)
                .put("jinhakRestored", true)
                .put("bypassPrevented", true)
                .put("credentialStoredLocally", credentialVault.has(ProviderId.ADIGA.wireName) || credentialVault.has(ProviderId.JINHAK.wireName))
                .put("credentialExported", false)
                .put("sessionSecretStoredLocally", true)
                .put("sessionSecretExported", false))
        }

        startupLoginPollGeneration += 1
        unifiedButton.text = "자동 로그인 취소"
        recordRuntimeEvent("startup-login-sequence-start", JSONObject()
            .put("trigger", startupLoginTrigger)
            .put("credentialStorage", false)
            .put("providerOrder", JSONArray().put("adiga").put("jinhak")))
        beginStartupLoginProvider(ProviderId.ADIGA)
    }

    private fun cancelStartupLoginPreflight(reason: String) {
        if (!startupLoginPreflightActive) return
        startupLoginPreflightActive = false
        startupLoginPreflightVerified = false
        startupLoginStage = "cancelled"
        startupLoginOpenAttempted = false
        startupLoginPollGeneration += 1
        unifiedButton.text = "자동 로그인 + 통합 수집"
        status.text = "자동 로그인 준비가 취소되었습니다. 다시 시작하면 어디가→진학사 로그인 확인 후 수집합니다."
        recordRuntimeEvent("startup-login-sequence-cancel", JSONObject().put("reason", reason.take(80)))
    }

    private fun beginStartupLoginProvider(which: ProviderId) {
        if (!startupLoginPreflightActive) return
        provider = which
        startupLoginStage = if (which == ProviderId.ADIGA) "adiga-check" else "jinhak-check"
        startupLoginOpenAttempted = false
        startupAuthIndeterminatePolls = 0
        startupLoginPollGeneration += 1
        val generation = startupLoginPollGeneration
        localRunId = localStore.latestResumableRun(which.wireName)
        CookieManager.getInstance().flush()
        val lease = runCatching { sessionVault.restore(which.wireName) }.getOrNull()
        if (which == ProviderId.ADIGA) {
            startupLoginAdigaRestoredLease = lease?.restored == true
        } else {
            startupLoginJinhakRestoredLease = lease?.restored == true
        }
        sessionState.text = if (lease?.restored == true) {
            "● ${which.displayName} 암호화 세션 복원 · 유효성 확인 중"
        } else {
            "○ ${which.displayName} 로그인 확인 중"
        }
        status.text = if (which == ProviderId.ADIGA) {
            "자동 준비 1/3 · 어디가 세션을 확인합니다. 저장 세션은 서버 응답으로 다시 검증합니다."
        } else {
            "자동 준비 2/3 · 진학사 로그인 상태를 확인하고 필요하면 수시저장소 보호 경로로 검증합니다."
        }
        recordRuntimeEvent("startup-login-provider-begin", JSONObject()
            .put("provider", which.wireName)
            .put("restoredLease", lease?.restored == true)
            .put("generation", generation))
        webView.loadUrl(which.homeUrl)
    }

    private fun handleStartupLoginPreflightPageFinished(url: String) {
        if (!startupLoginPreflightActive) return
        val expectedProvider = provider
        val generation = startupLoginPollGeneration
        runtimeLastSafePath = runtimeSafePath(url)
        handler.postDelayed({
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@postDelayed
            evaluateStartupLoginState(expectedProvider, generation)
        }, LOGIN_PREFLIGHT_DOM_SETTLE_MS)
    }

    private fun evaluateStartupLoginState(expectedProvider: ProviderId, generation: Int) {
        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return
        checkSessionState { needsLogin, authenticated ->
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@checkSessionState
            if (authenticated) {
                onStartupProviderAuthenticated(expectedProvider, generation)
                return@checkSessionState
            }
            probeLoginSurface(expectedProvider) { probe ->
                if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@probeLoginSurface
                if (probe.optBoolean("detected", false)) {
                    startupAuthIndeterminatePolls = 0
                    sessionState.text = "○ ${expectedProvider.displayName} 로그인 화면 감지"
                    if (credentialVault.has(expectedProvider.wireName)) {
                        status.text = "${expectedProvider.displayName} 로그인 화면이 실제로 감지되어 저장 계정으로 자동 로그인합니다."
                        attemptSavedCredentialLogin(expectedProvider, "startup-login-surface")
                    } else if (startupCredentialPromptedProvider != expectedProvider) {
                        startupCredentialPromptedProvider = expectedProvider
                        status.text = "${expectedProvider.displayName} 로그인 화면이 감지되었습니다. 자동로그인 정보를 한 번 저장해주세요."
                        showCredentialDialog(expectedProvider, continueAfterSave = true)
                    }
                    scheduleStartupLoginPoll(expectedProvider, generation)
                    return@probeLoginSurface
                }

                // v0.9.7: an indeterminate home page is never enough to approve the Jinhak
                // collection bootstrap. Verify a protected, read-only Susi route. If that
                // route redirects to login, keep the browser there and wait for credentials or
                // manual login; never advance the crawl and never mark the protected target failed.
                startupAuthIndeterminatePolls += 1
                if (startupAuthIndeterminatePolls >= 2) {
                    val currentUrl = webView.url.orEmpty()
                    if (isProviderLoginUrl(expectedProvider, currentUrl)) {
                        if (expectedProvider == ProviderId.JINHAK) {
                            jinhakLoginRecoveryPolls += 1
                            jinhakProtectedCoreStablePasses = 0
                            if (jinhakCoreBootstrapState != "login-route-wait") {
                                loginRouteFallbackPauses += 1
                                jinhakReauthCycles += 1
                            }
                            jinhakAuthVerifiedForBatch = false
                            jinhakCoreBootstrapState = "login-route-wait"
                        } else {
                            loginRouteFallbackPauses += 1
                        }
                        recordRuntimeEvent("startup-login-route-wait", JSONObject()
                            .put("provider", expectedProvider.wireName)
                            .put("safePath", runtimeSafePath(currentUrl))
                            .put("renderedSurfaceDetected", false)
                            .put("proactiveLoginNavigation", false))
                        sessionState.text = "○ ${expectedProvider.displayName} 로그인 경로 감지 · 인증 대기"
                        if (credentialVault.has(expectedProvider.wireName)) {
                            status.text = "로그인 경로가 확인되었습니다. 현재 화면을 유지하며 저장 계정 자동입력용 로그인 폼 렌더링을 기다립니다."
                            scheduleLoginSurfaceDetection(expectedProvider, "startup-login-route-fallback")
                        } else if (startupCredentialPromptedProvider != expectedProvider) {
                            startupCredentialPromptedProvider = expectedProvider
                            loginRouteFallbackCredentialPrompts += 1
                            status.text = "로그인이 필요합니다. 이 기기에만 암호화 저장할 자동로그인 정보를 입력해주세요."
                            showCredentialDialog(expectedProvider, continueAfterSave = true)
                        }
                        scheduleStartupLoginPoll(expectedProvider, generation)
                        return@probeLoginSurface
                    }

                    if (expectedProvider == ProviderId.ADIGA) {
                        recordRuntimeEvent("startup-login-provider-deferred", JSONObject()
                            .put("provider", expectedProvider.wireName)
                            .put("reason", "public-baseline-no-login-surface")
                            .put("forcedNavigation", false))
                        startupLoginPollGeneration += 1
                        startupLoginOpenAttempted = false
                        sessionState.text = "△ 어디가 로그인 미확정 · 공개 기준자료 수집은 가능"
                        status.text = "어디가는 공개 기준자료 수집을 유지하고, 진학사 보호 경로 인증 검증으로 넘어갑니다."
                        handler.postDelayed({ if (startupLoginPreflightActive) beginStartupLoginProvider(ProviderId.JINHAK) }, 200L)
                        return@probeLoginSurface
                    }

                    val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
                    val currentCanonical = canonicalizeBatchUrl(currentUrl)
                    val probeCanonical = canonicalizeBatchUrl(coreProbe)
                    if (startupJinhakProtectedProbeAttempted && probeCanonical.isNotBlank() && currentCanonical == probeCanonical && !needsLogin && !isProviderLoginUrl(expectedProvider, currentUrl)) {
                        jinhakProtectedCoreStablePasses += 1
                        if (jinhakProtectedCoreStablePasses >= JINHAK_CORE_AUTH_STABLE_PASSES) {
                            jinhakAuthVerifiedForBatch = true
                            jinhakCoreBootstrapState = "protected-route-authenticated"
                            jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
                            jinhakLastAuthEvidence = "protected-core-stable"
                            recordRuntimeEvent("jinhak-protected-auth-probe-success", JSONObject()
                                .put("safePath", runtimeSafePath(currentUrl))
                                .put("loginUrl", false)
                                .put("stablePasses", jinhakProtectedCoreStablePasses))
                            onStartupProviderAuthenticated(expectedProvider, generation)
                        } else {
                            scheduleStartupLoginPoll(expectedProvider, generation)
                        }
                        return@probeLoginSurface
                    } else if (expectedProvider == ProviderId.JINHAK) {
                        jinhakProtectedCoreStablePasses = 0
                    }
                    if (!startupJinhakProtectedProbeAttempted && coreProbe.isNotBlank()) {
                        startupJinhakProtectedProbeAttempted = true
                        startupAuthIndeterminatePolls = 0
                        startupLoginStage = "jinhak-protected-auth-probe"
                        jinhakCoreBootstrapState = "protected-route-probe"
                        recordRuntimeEvent("jinhak-protected-auth-probe-start", JSONObject()
                            .put("safePath", runtimeSafePath(coreProbe))
                            .put("readOnly", true)
                            .put("proactiveLoginNavigation", false))
                        sessionState.text = "△ 진학사 인증 미확정 · 수시저장소 보호 경로 확인"
                        status.text = "로그인 URL을 강제로 열지 않고 수시저장소를 읽기 전용으로 열어 서버 인증 상태를 검증합니다."
                        webView.loadUrl(coreProbe)
                        return@probeLoginSurface
                    }
                    if (startupJinhakProtectedProbeAttempted && startupAuthIndeterminatePolls >= 4 && coreProbe.isNotBlank()) {
                        startupAuthIndeterminatePolls = 0
                        recordRuntimeEvent("jinhak-protected-auth-probe-retry", JSONObject()
                            .put("safePath", runtimeSafePath(coreProbe))
                            .put("readOnly", true))
                        webView.loadUrl(coreProbe)
                        return@probeLoginSurface
                    }
                }
                sessionState.text = if (needsLogin) "○ 로그인 필요 신호 감지 · 로그인 폼 렌더링 대기" else "△ 로그인 상태 확인 중 · 현재 화면 유지"
                status.text = "${expectedProvider.displayName} 현재 화면을 유지합니다. 실제 로그인 폼이 감지될 때만 자동 로그인을 실행합니다."
                scheduleStartupLoginPoll(expectedProvider, generation)
            }
        }
    }

    private fun scheduleStartupLoginPoll(expectedProvider: ProviderId, generation: Int) {
        handler.postDelayed({
            if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return@postDelayed
            evaluateStartupLoginState(expectedProvider, generation)
        }, LOGIN_PREFLIGHT_POLL_MS)
    }

    private fun onStartupProviderAuthenticated(expectedProvider: ProviderId, generation: Int) {
        if (!startupLoginPreflightActive || provider != expectedProvider || generation != startupLoginPollGeneration) return
        if (expectedProvider == ProviderId.ADIGA) {
            startupLoginAdigaAuthenticated = true
        } else {
            startupLoginJinhakAuthenticated = true
            jinhakAuthVerifiedForBatch = true
            if (jinhakLastAuthEvidence == "none") jinhakLastAuthEvidence = "rendered-authenticated-control"
            if (jinhakLastCoreVerifiedAtMs == 0L && canonicalizeBatchUrl(webView.url.orEmpty()) == canonicalizeBatchUrl(JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty())) {
                jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
                jinhakLastAuthEvidence = "protected-core-stable"
            }
            jinhakCoreBootstrapState = "authenticated"
        }
        startupLoginPollGeneration += 1
        startupLoginOpenAttempted = false
        val currentUrl = webView.url.orEmpty()
        if (currentUrl.isNotBlank()) runCatching { sessionVault.captureAuthenticated(expectedProvider.wireName, currentUrl, VERSION) }
        recordRuntimeEvent("startup-login-provider-authenticated", JSONObject()
            .put("provider", expectedProvider.wireName)
            .put("credentialStoredLocally", credentialVault.has(expectedProvider.wireName)).put("credentialExported", false).put("sessionSecretStoredLocally", true).put("sessionSecretExported", false))
        if (expectedProvider == ProviderId.ADIGA) {
            sessionState.text = "● 어디가 로그인 확인 완료"
            status.text = "자동 준비 1/3 완료 · 진학사 로그인 확인으로 이동합니다."
            handler.postDelayed({
                if (startupLoginPreflightActive) beginStartupLoginProvider(ProviderId.JINHAK)
            }, 250L)
        } else {
            sessionState.text = "● 진학사 로그인 확인 완료"
            startupLoginPreflightActive = false
            startupLoginPreflightVerified = true
            startupLoginVerifiedAtMs = System.currentTimeMillis()
            startupLoginStage = "verified"
            startupLoginPollGeneration += 1
            unifiedButton.text = "통합 수집 시작 중"
            status.text = "자동 준비 3/3 · 어디가·진학사 로그인 확인 완료. 통합 수집을 자동 시작합니다."
            recordRuntimeEvent("startup-login-sequence-verified", JSONObject()
                .put("trigger", startupLoginTrigger)
                .put("bothProvidersAuthenticated", startupLoginAdigaAuthenticated && startupLoginJinhakAuthenticated)
                .put("jinhakAuthenticatedForBatch", jinhakAuthVerifiedForBatch)
                .put("credentialStoredLocally", credentialVault.has(expectedProvider.wireName)).put("credentialExported", false).put("sessionSecretStoredLocally", true).put("sessionSecretExported", false))
            handler.postDelayed({
                if (!unifiedRunning && !batchRunning && startupLoginPreflightVerified) {
                    startUnifiedCollectionAuthenticated()
                }
            }, 300L)
        }
    }

    private fun startUnifiedCollection() {
        if (!startupLoginPreflightVerified) {
            startAutomaticLoginAndCollectionSequence("manual-start")
            return
        }
        startUnifiedCollectionAuthenticated()
    }

    private fun startUnifiedCollectionAuthenticated() {
        if (batchRunning) {
            Toast.makeText(this, "현재 개별 수집을 먼저 종료한 뒤 통합 수집을 시작하세요.", Toast.LENGTH_LONG).show()
            return
        }
        val sessionId = localStore.beginOrResumeUnifiedSession(VERSION)
        unifiedSessionId = sessionId
        unifiedRunning = true
        unifiedPhase = "adiga"
        unifiedPendingAdigaStart = true
        unifiedPendingJinhakStart = false
        unifiedJinhakAutoCapture = false
        unifiedJinhakCapturedPages.clear()
        unifiedAutoCaptureScheduled = false
        unifiedButton.text = "통합 수집 종료"
        localStore.updateUnifiedSession(sessionId, "adiga", "running", "user-start")
        localStore.recordSyncState(
            sessionId, UnifiedSyncState.PRECHECK.name, null,
            JSONObject()
                .put("collectorVersion", VERSION)
                .put("loginPreflight", JSONObject()
                    .put("verified", startupLoginAdigaAuthenticated && startupLoginJinhakAuthenticated)
                    .put("collectionBootstrapReady", startupLoginPreflightVerified)
                    .put("bypassedByStoredSession", startupSessionPreflightBypassed)
                    .put("adigaAuthenticated", startupLoginAdigaAuthenticated)
                    .put("jinhakAuthenticated", startupLoginJinhakAuthenticated)
                    .put("adigaRestoredLease", startupLoginAdigaRestoredLease)
                    .put("jinhakRestoredLease", startupLoginJinhakRestoredLease)
                    .put("loginUiOpenCount", startupLoginUiOpenCount)
                    .put("verifiedAtMs", startupLoginVerifiedAtMs)
                    .put("passwordStored", false)
                    .put("sessionSecretStoredLocally", startupLoginAdigaRestoredLease || startupLoginJinhakRestoredLease)
                    .put("sessionSecretExported", false)
                    .put("adigaCredentialStored", credentialVault.has(ProviderId.ADIGA.wireName))
                    .put("jinhakCredentialStored", credentialVault.has(ProviderId.JINHAK.wireName))
                    .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                    .put("loginSurfaceDetectionsAtBootstrap", credentialLoginSurfaceDetections)
                    .put("credentialAutoLoginSubmissionsAtBootstrap", credentialAutoLoginSubmissions)
                    .put("credentialAutoLoginSuccessesAtBootstrap", credentialAutoLoginSuccesses)
                    .put("staleSessionLeaseBypassesPrevented", staleSessionLeaseBypassesPrevented)
                    .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                    .put("loginRouteFallbackCredentialPrompts", loginRouteFallbackCredentialPrompts)
                    .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                    .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                    .put("jinhakLastAuthEvidence", jinhakLastAuthEvidence)
                    .put("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                    .put("jinhakLoginRecoveryPolls", jinhakLoginRecoveryPolls)
                    .put("jinhakReauthCycles", jinhakReauthCycles)
                    .put("credentialExported", false)),
            false
        )
        localStore.recordSyncState(sessionId, UnifiedSyncState.ADIGA_PUBLIC_SYNC.name, ProviderId.ADIGA.wireName, JSONObject().put("mode", "legacy-local-first-until-deterministic-planner-activation"), false)
        persistRuntimeCheckpoint(forceResume = true)

        provider = ProviderId.ADIGA
        localRunId = localStore.beginOrResume(ProviderId.ADIGA.wireName, VERSION)
        localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.ADIGA.wireName, runId) }
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        batchButton.text = "어디가 통합 수집 준비"
        diagnosticButton.text = "어디가 진단 로그 전송"
        status.text = "통합 수집 1/2 · 어디가 전국 공식 입시정보 resume/audit 준비 중…"

        val seed = ProviderRegistry.adapter(ProviderId.ADIGA).seedUrls().firstOrNull()
        if (seed.isNullOrBlank()) {
            finishUnifiedCollection("adiga-seed-missing")
            return
        }
        webView.loadUrl(seed)
    }

    private fun transitionUnifiedToJinhak(adigaReason: String) {
        if (!unifiedRunning || unifiedPhase != "adiga") return
        val sessionId = unifiedSessionId ?: return
        unifiedPhase = "jinhak"
        unifiedPendingAdigaStart = false
        unifiedPendingJinhakStart = true
        unifiedJinhakAutoCapture = false
        unifiedAutoCaptureScheduled = false
        unifiedJinhakCapturedPages.clear()
        jinhakBatchStartCount = 0
        jinhakNormalizedMissionSeedContexts.clear()
        jinhakNormalizedIdentitySeedKeys.clear()
        jinhakNormalizedCandidateBindingKeys.clear()
        jinhakNormalizedAmbiguousBindings = 0
        jinhakTransitionAuthGateActive = true
        jinhakAuthVerifiedForBatch = false
        jinhakProtectedCoreStablePasses = 0
        jinhakTransitionAuthChecks += 1
        jinhakCoreBootstrapState = "transition-core-revalidate"
        jinhakLastAuthEvidence = "transition-revalidation-pending"
        jinhakLoginRecoveryGeneration += 1

        provider = ProviderId.JINHAK
        localRunId = localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION)
        localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId) }
        localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$adigaReason")
        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY.name, ProviderId.JINHAK.wireName, JSONObject().put("authorizedConnectorActive", false), false)
        localStore.recordSyncState(sessionId, UnifiedSyncState.JINHAK_USER_SESSION_MISSION.name, ProviderId.JINHAK.wireName,
            JSONObject().put("observationFirst", true).put("userStartedSessionMission", true).put("boundedSameProviderTraversal", true).put("maxPages", MAX_JINHAK_AUTONAV_PAGES), false)
        persistRuntimeCheckpoint(forceResume = true)
        CookieManager.getInstance().flush()
        sessionState.text = "세션 상태 확인 중"
        batchButton.text = "진학사 자동 탐색 준비"
        diagnosticButton.text = "진학사 전체 분석 전송"
        unifiedButton.text = "통합 수집 종료"
        status.text = "통합 수집 2/2 · 진학사 보호 경로 인증을 다시 확인한 뒤 저장대학 미션을 시작합니다."
        val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull() ?: ProviderId.JINHAK.homeUrl
        currentBatchTarget = canonicalizeBatchUrl(coreProbe)
        persistJinhakAuthDiagnostics("transition-auth-probe-start")
        webView.loadUrl(coreProbe)
    }

    private fun persistJinhakAuthDiagnostics(trigger: String) {
        val sessionId = unifiedSessionId ?: return
        if (provider != ProviderId.JINHAK && unifiedPhase != "jinhak") return
        val secondsSinceCoreVerified = if (jinhakLastCoreVerifiedAtMs > 0L) {
            (System.currentTimeMillis() - jinhakLastCoreVerifiedAtMs).coerceAtLeast(0L) / 1000.0
        } else JSONObject.NULL
        runCatching {
            localStore.recordSyncState(
                sessionId,
                "JINHAK_AUTH_DIAGNOSTICS",
                ProviderId.JINHAK.wireName,
                JSONObject()
                    .put("trigger", trigger.take(80))
                    .put("safePath", runtimeSafePath(webView.url))
                    .put("currentTargetSafePath", runtimeSafePath(currentBatchTarget))
                    .put("authVerifiedForBatch", jinhakAuthVerifiedForBatch)
                    .put("coreBootstrapState", jinhakCoreBootstrapState)
                    .put("lastAuthEvidence", jinhakLastAuthEvidence)
                    .put("lastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                    .put("secondsSinceCoreVerified", secondsSinceCoreVerified)
                    .put("transitionAuthGateActive", jinhakTransitionAuthGateActive)
                    .put("batchRunning", batchRunning)
                    .put("batchPausedForLogin", batchPausedForLogin)
                    .put("loginRecoveryPolls", jinhakLoginRecoveryPolls)
                    .put("reauthCycles", jinhakReauthCycles)
                    .put("authVerificationFailures", jinhakAuthVerificationFailures)
                    .put("transitionAuthChecks", jinhakTransitionAuthChecks)
                    .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                    .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
                    .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                    .put("credentialAutoLoginSubmissions", credentialAutoLoginSubmissions)
                    .put("credentialAutoLoginSuccesses", credentialAutoLoginSuccesses)
                    .put("credentialAutoLoginFailures", credentialAutoLoginFailures)
                    .put("credentialAutoLoginLastResult", credentialAutoLoginLastResult.take(80))
                    .put("sessionKeepAliveTicks", jinhakSessionKeepAliveTicks)
                    .put("sessionKeepAliveBackgroundTicks", jinhakSessionKeepAliveBackgroundTicks)
                    .put("sessionExtensionClicks", jinhakSessionExtensionClicks)
                    .put("credentialExported", false)
                    .put("sessionSecretExported", false),
                batchPausedForLogin || jinhakTransitionAuthGateActive,
                false
            )
        }
    }

    private fun scheduleJinhakLoginRecovery(reason: String) {
        if (provider != ProviderId.JINHAK) return
        val generation = ++jinhakLoginRecoveryGeneration
        handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, 120L)
    }

    private fun pollJinhakLoginRecovery(reason: String, generation: Int) {
        if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return
        val recoveryActive = startupLoginPreflightActive || jinhakTransitionAuthGateActive || (batchRunning && batchPausedForLogin)
        if (!recoveryActive) return
        jinhakLoginRecoveryPolls += 1
        val currentUrl = webView.url.orEmpty()
        if (isProviderLoginUrl(ProviderId.JINHAK, currentUrl)) {
            jinhakProtectedCoreStablePasses = 0
            if (jinhakCoreBootstrapState !in setOf("login-route-wait", "transition-login-wait", "batch-login-route-wait", "keepalive-login-recovery")) {
                loginRouteFallbackPauses += 1
                jinhakReauthCycles += 1
            }
            jinhakAuthVerifiedForBatch = false
            if (jinhakTransitionAuthGateActive) jinhakCoreBootstrapState = "transition-login-wait"
            else if (batchRunning) jinhakCoreBootstrapState = "batch-login-route-wait"
            persistJinhakAuthDiagnostics("$reason-login-route")
            probeLoginSurface(ProviderId.JINHAK) { probe ->
                if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return@probeLoginSurface
                if (probe.optBoolean("detected", false)) {
                    if (credentialVault.has(ProviderId.JINHAK.wireName)) {
                        attemptSavedCredentialLogin(ProviderId.JINHAK, "persistent-$reason")
                    } else if (startupCredentialPromptedProvider != ProviderId.JINHAK) {
                        startupCredentialPromptedProvider = ProviderId.JINHAK
                        loginRouteFallbackCredentialPrompts += 1
                        showCredentialDialog(ProviderId.JINHAK, continueAfterSave = true)
                    }
                }
                handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
            }
            return
        }

        val coreProbe = JinhakSiteTopology.missionSeeds().firstOrNull().orEmpty()
        val currentCanonical = canonicalizeBatchUrl(currentUrl)
        val coreCanonical = canonicalizeBatchUrl(coreProbe)
        if (coreCanonical.isBlank()) {
            jinhakAuthVerificationFailures += 1
            jinhakCoreBootstrapState = "core-auth-probe-missing"
            persistJinhakAuthDiagnostics("$reason-core-probe-missing")
            return
        }
        if (currentCanonical != coreCanonical) {
            jinhakProtectedCoreStablePasses = 0
            jinhakCoreBootstrapState = "recovery-core-probe-navigation"
            persistJinhakAuthDiagnostics("$reason-open-core-probe")
            webView.loadUrl(coreProbe)
            handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
            return
        }

        checkSessionState { needsLogin, _ ->
            if (provider != ProviderId.JINHAK || generation != jinhakLoginRecoveryGeneration) return@checkSessionState
            val nowUrl = webView.url.orEmpty()
            if (needsLogin || isProviderLoginUrl(ProviderId.JINHAK, nowUrl)) {
                jinhakProtectedCoreStablePasses = 0
                jinhakAuthVerifiedForBatch = false
                jinhakCoreBootstrapState = "core-probe-login-required"
                persistJinhakAuthDiagnostics("$reason-core-probe-login-required")
                scheduleLoginSurfaceDetection(ProviderId.JINHAK, "persistent-$reason")
                handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
                return@checkSessionState
            }
            jinhakProtectedCoreStablePasses += 1
            if (jinhakProtectedCoreStablePasses < JINHAK_CORE_AUTH_STABLE_PASSES) {
                jinhakCoreBootstrapState = "core-probe-stability-check"
                persistJinhakAuthDiagnostics("$reason-core-stability-${jinhakProtectedCoreStablePasses}")
                handler.postDelayed({ pollJinhakLoginRecovery(reason, generation) }, JINHAK_LOGIN_RECOVERY_POLL_MS)
                return@checkSessionState
            }
            completeJinhakVerifiedAuth(reason)
        }
    }

    private fun completeJinhakVerifiedAuth(reason: String) {
        if (provider != ProviderId.JINHAK) return
        jinhakAuthVerifiedForBatch = true
        jinhakCoreBootstrapState = "protected-core-verified"
        jinhakLastCoreVerifiedAtMs = System.currentTimeMillis()
        jinhakLastAuthEvidence = "protected-core-stable"
        jinhakProtectedCoreStablePasses = 0
        if (credentialAwaitingLoginExitProvider == ProviderId.JINHAK) {
            credentialAwaitingLoginExitProvider = null
            credentialLoginSurfaceKey = ""
            credentialLoginSurfaceAttempts = 0
            if (credentialAutoLoginLastResult.startsWith("submitted")) {
                credentialAutoLoginSuccesses += 1
                credentialAutoLoginLastResult = "success-protected-core-verified"
                credentialAutoLoginLastProvider = ProviderId.JINHAK.wireName
                credentialAutoLoginLastAtMs = System.currentTimeMillis()
                recordRuntimeEvent("credential-auto-login-success", JSONObject()
                    .put("provider", ProviderId.JINHAK.wireName)
                    .put("successes", credentialAutoLoginSuccesses)
                    .put("verification", "protected-core-stable")
                    .put("credentialExported", false))
            }
        }
        runCatching { sessionVault.captureAuthenticated(ProviderId.JINHAK.wireName, webView.url.orEmpty(), VERSION) }
        persistJinhakAuthDiagnostics("$reason-auth-verified")
        ++jinhakLoginRecoveryGeneration

        when {
            startupLoginPreflightActive -> {
                val generation = startupLoginPollGeneration
                onStartupProviderAuthenticated(ProviderId.JINHAK, generation)
            }
            jinhakTransitionAuthGateActive -> {
                jinhakTransitionAuthGateActive = false
                unifiedPendingJinhakStart = false
                status.text = "진학사 보호 경로 인증 재검증 완료 · 수시저장소 미션을 시작합니다."
                if (unifiedRunning && unifiedPhase == "jinhak" && !batchRunning) startBatch()
            }
            batchRunning && batchPausedForLogin -> resumeBatchAfterVerifiedJinhakAuth(reason)
        }
    }

    private fun resumeBatchAfterVerifiedJinhakAuth(reason: String) {
        if (!batchRunning || provider != ProviderId.JINHAK) return
        batchPausedForLogin = false
        showBatchCover()
        sessionState.text = "● 진학사 인증 복구 · 동일 수집 target 재개"
        val retry = currentBatchTarget
        persistJinhakAuthDiagnostics("$reason-resume-target")
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)
            else loadNextBatchPage()
        }, 180L)
    }

    private fun handleJinhakTransitionAuthGate(url: String) {
        if (!unifiedRunning || unifiedPhase != "jinhak" || provider != ProviderId.JINHAK || !jinhakTransitionAuthGateActive || batchRunning) return
        runtimeLastSafePath = runtimeSafePath(url)
        scheduleJinhakLoginRecovery("transition-auth-gate")
    }

    private fun scheduleUnifiedJinhakAutoCapture(url: String) {
        if (!unifiedRunning || unifiedPhase != "jinhak" || provider != ProviderId.JINHAK || !unifiedJinhakAutoCapture) return
        if (unifiedAutoCaptureScheduled) return
        val canonical = canonicalizeBatchUrl(url)
        if (canonical.isBlank()) return
        unifiedAutoCaptureScheduled = true
        handler.postDelayed({
            unifiedAutoCaptureScheduled = false
            if (!unifiedRunning || unifiedPhase != "jinhak" || provider != ProviderId.JINHAK) return@postDelayed
            checkSessionState { needsLogin, _ ->
                if (needsLogin) {
                    status.text = "통합 수집 2/2 · 진학사 로그인 후 페이지를 열면 자동 수집을 재개합니다."
                    return@checkSessionState
                }
                collectCurrentPage(autoUnified = true)
            }
        }, 900L)
    }

    private fun finishUnifiedCollection(reason: String) {
        if (unifiedFinishInProgress) return
        unifiedFinishInProgress = true
        try {
            val sessionId = unifiedSessionId ?: localStore.latestUnifiedSession()
            if (batchRunning) stopBatchForUnifiedFinish("unified-$reason")

            unifiedRunning = false
            unifiedJinhakAutoCapture = false
            unifiedPendingAdigaStart = false
            unifiedPendingJinhakStart = false
            unifiedAutoCaptureScheduled = false
            unifiedPhase = "completed"
            startupLoginPreflightVerified = false
            startupLoginPreflightActive = false
            startupLoginStage = "idle"
            startupLoginPollGeneration += 1
            jinhakAbsoluteTargetKey = ""
            ++jinhakAbsoluteTargetGeneration

            if (sessionId == null) {
                unifiedButton.text = "자동 로그인 + 통합 수집"
                status.text = "종료할 통합 수집 세션이 없습니다."
                return
            }
            localStore.updateUnifiedSession(sessionId, "completed", "completed", reason)
            getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE).edit().putBoolean("resumeUnified", false).apply()

            val summary = localStore.unifiedStatus(sessionId)
            lastJson = JSONObject()
                .put("schemaVersion", 2)
                .put("type", "admission-unified-session-summary")
                .put("session", summary)
                .put("fullExportMaterializedInMemory", false)
                .put("fullExport", "Use JSON 저장; records are streamed from SQLite to the destination file.")
                .toString(2)
            showPreview(lastJson)
            unifiedButton.text = "자동 로그인 + 통합 수집"
            pendingUnifiedExportSessionId = sessionId
            cloudOffload.sendDiagnostic(
                "unified", VERSION,
                JSONObject(summary.toString())
                    .put("trigger", "unified-finish")
                    .put("containsRawAdmissionRecords", false)
                    .put("memorySafeFinish", true)
            ) { }
            recordRuntimeEvent("unified-finish-memory-safe", JSONObject()
                .put("reason", reason.take(120))
                .put("sessionIdPresent", true))
            status.text = "통합 수집 종료 완료 · 전체 데이터는 SQLite에 보존됨 · JSON 저장 시 메모리에 올리지 않고 스트리밍합니다."
        } catch (t: Throwable) {
            recordRuntimeEvent("unified-finish-failure", JSONObject()
                .put("exceptionClass", t.javaClass.name.take(160)), synchronous = true)
            status.text = "통합 수집 종료 처리 중 오류가 기록되었습니다. 앱을 다시 열면 체크포인트에서 복구합니다."
        } finally {
            unifiedFinishInProgress = false
        }
    }

    private fun stopBatchForUnifiedFinish(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        batchReadinessPolling = false
        disarmBatchNavigationWatchdog()
        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("unified-finish")
        jinhakAbsoluteTargetKey = ""
        ++jinhakAbsoluteTargetGeneration
        runCatching { webView.stopLoading() }
        hideBatchCover()
        stopCollectionKeepAlive()
        batchQueue.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        pendingBatchPageAction = null
        activeBatchPageAction = null
        currentBatchTarget = null
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else if (provider == ProviderId.JINHAK && currentAdapter().supportsUserSessionMissionTraversal) "진학사 목적형 탐색" else "현재 화면 정리"
        localRunId?.let { localStore.markRun(it, "stopped", reason) }
        recordRuntimeEvent("batch-lightweight-stop", JSONObject().put("reason", reason.take(120)))
    }

    private fun isAdigaBlockingErrorMessage(message: String?): Boolean {
        val text = message?.replace(Regex("\\s+"), " ")?.trim().orEmpty()
        if (text.isBlank()) return false
        return Regex("(페이지.{0,12}오류|오류.{0,12}발생|일시적.{0,12}오류|처리.{0,12}오류|서버.{0,12}오류|500|server\\s*error|internal\\s*server\\s*error)", RegexOption.IGNORE_CASE)
            .containsMatchIn(text)
    }

    private fun handleAdigaBlockingDialog(message: String?) {
        if (!batchRunning || provider != ProviderId.ADIGA) return
        val compactMessage = message?.replace(Regex("\\s+"), " ")?.trim()?.take(180).orEmpty()
        val action = activeBatchPageAction ?: pendingBatchPageAction
        activeBatchPageAction = null
        pendingBatchPageAction = null
        batchSkipSnapshotUntilMs = System.currentTimeMillis() + 1800L

        if (action != null) {
            val key = pageActionKey(action)
            batchPageActionQueued.remove(key)
            batchPageActionFailed.add(key)
            batchErrors.put(JSONObject()
                .put("url", action.baseUrl)
                .put("type", "site-blocking-dialog")
                .put("page", action.page)
                .put("totalPages", action.totalPages)
                .put("familyKey", action.familyKey)
                .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
                .put("retryCount", action.retry)
                .put("message", compactMessage))
            localRunId?.let { runId ->
                localStore.markPage(
                    runId, action.familyKey, action.requestedYear,
                    action.page, action.totalPages, "error", action.retry, "site-blocking-dialog"
                )
                localStore.markDocument(runId, canonicalizeBatchUrl(action.baseUrl), "error", action.retry, "site-blocking-dialog")
            }
        } else {
            val navKey = canonicalizeBatchUrl(webView.url ?: currentBatchTarget.orEmpty())
            if (navKey.isNotBlank()) {
                batchVisited.add(navKey)
                batchErrors.put(JSONObject()
                    .put("url", navKey)
                    .put("type", "site-blocking-dialog")
                    .put("message", compactMessage))
                localRunId?.let { runId ->
                    localStore.markDocument(runId, navKey, "error", 0, "site-blocking-dialog")
                }
            }
        }
        status.text = "어디가 페이지 오류창 자동 차단: 오류를 체크포인트에 남기고 다음 페이지로 진행합니다."
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin) loadNextBatchPage()
        }, 220L)
    }

    private fun startBatch() {
        if (startupLoginPreflightActive) {
            Toast.makeText(this, "로그인 준비가 끝난 뒤 수집이 자동 시작됩니다.", Toast.LENGTH_SHORT).show()
            return
        }
        val preserveJinhakMissionState = provider == ProviderId.JINHAK && unifiedRunning && jinhakBatchStartCount > 0
        if (provider == ProviderId.JINHAK) {
            jinhakBatchStartCount += 1
            recordRuntimeEvent("jinhak-batch-start", JSONObject()
                .put("count", jinhakBatchStartCount)
                .put("preserveMissionState", preserveJinhakMissionState))
        }
        val url = webView.url
        if (url.isNullOrBlank() || !isProviderUrl(url)) {
            Toast.makeText(this, "먼저 어디가 또는 진학사에서 수집 시작 위치를 여세요.", Toast.LENGTH_LONG).show()
            return
        }

        if (provider == ProviderId.ADIGA && ADIGA_RETRY_SUSPENDED && !unifiedRunning) {
            status.text = "어디가 복구는 현재 보류 중입니다. 진학사 분석 버전 검증 후 한밭대 381쪽을 우선 재시도합니다."
            Toast.makeText(this, "어디가 재시도는 진학사 분석 이후 진행합니다.", Toast.LENGTH_LONG).show()
            return
        }

        val userSessionMissionTraversal = provider == ProviderId.JINHAK && currentAdapter().supportsUserSessionMissionTraversal
        if (!currentAdapter().supportsBatchCrawl && !userSessionMissionTraversal) {
            status.text = "현재 공급자는 단일 화면 분석 모드입니다."
            collectCurrentPage()
            return
        }

        batchQueue.clear()
        batchVisited.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        batchPageActionVisited.clear()
        batchPageActionFailed.clear()
        batchPaginationPlanned.clear()
        batchListFingerprints.clear()
        batchLastTableSignatures.clear()
        batchBootstrapSearchAttempted.clear()
        batchReadinessPolling = false
        pendingBatchPageAction = null
        activeBatchPageAction = null
        batchSnapshots = JSONArray()
        batchRecords = JSONArray()
        batchResources = JSONArray()
        batchErrors = JSONArray()
        batchRetryEvents = JSONArray()
        batchDuplicateYearViews = JSONArray()
        batchRunning = true
        showBatchCover()
        startCollectionKeepAlive()
        batchPausedForLogin = false
        batchCollecting = false
        batchPageCount = 0
        batchPaginationRetries = 0
        batchCloudPlansPending = 0
        batchCloudResumePlans = 0
        batchCloudPagesScheduled = 0
        batchCloudPagesSkipped = 0
        batchCloudPagesDeferred = 0
        batchContextRecoveries = 0
        batchSessionSyncRetries = 0
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        batchLocalResumePlans = 0
        batchLocalPagesScheduled = 0
        batchLocalPagesSkipped = 0
        batchLocalRecordsPersisted = 0
        batchAuditPagesScheduled = 0
        batchUniversityDiscoveryPagesScheduled = 0
        batchPersistedPageSignatureOwners.clear()
        jinhakAgentActionSeen.clear()
        jinhakExpandedNavigationStates.clear()
        jinhakRepeatedNavigationStateSkips = 0
        jinhakUniqueNavigationStates = 0
        jinhakAgentActionInFlight = false
        jinhakAgentActionsExecuted = 0
        jinhakMissionActionsExecuted = 0
        jinhakGenericActionsExecuted = 0
        jinhakReferenceRouteCaptureCounts.clear()
        jinhakReferenceRepeatSkips = 0
        jinhakNoProgressFences = 0
        jinhakCoreScopeBlockedUrls = 0
        jinhakCoreScopeBlockedLaneCounts.clear()
        if (provider == ProviderId.JINHAK && jinhakAuthVerifiedForBatch) {
            jinhakCoreBootstrapState = "batch-core-start"
        }
        jinhakLastMeaningfulProgressAtMs = if (provider == ProviderId.JINHAK) System.currentTimeMillis() else 0L
        jinhakLastLiveDiagnosticsAtMs = 0L
        ++jinhakProgressFenceGeneration
        jinhakMissionContext = null
        jinhakReportBridgeContext = null
        jinhakMissionOriginRoute = ""
        jinhakMissionNeedsReturn = false
        jinhakApplicationBoundActions = 0
        jinhakApplicationMissionReturns = 0
        if (!preserveJinhakMissionState) {
            jinhakMissionCoverage.clear()
            jinhakMissionTargetLedger.clear()
        }
        jinhakActiveMissionTargetId = null
        jinhakSlowLaneMissionTargetIds.clear()
        jinhakMissionAnchorDiscoveredKeys.clear()
        jinhakMissionAnchorPromotedKeys.clear()
        jinhakMissionAnchorParsedKeys.clear()
        jinhakMissionAnchorStructuredKeys.clear()
        jinhakMissionBindingSourceKeys.clear()
        jinhakMissionBindingSourceCounts.clear()
        jinhakMissionAnchorSelectedKeys.clear()
        jinhakMissionAnchorClickedKeys.clear()
        if (!preserveJinhakMissionState) jinhakReportConfirmedKeys.clear()
        jinhakMissionAnchorActionsExecuted = 0
        jinhakConsentGatePending = false
        jinhakConsentResumePending = false
        jinhakConsentGatesEncountered = 0
        jinhakConsentGatesResolved = 0
        jinhakMissionBootstrapStartedAtMs = if (provider == ProviderId.JINHAK) System.currentTimeMillis() else 0L
        jinhakFirstPopulatedStorageAtMs = 0L
        jinhakUnboundSavedApplicationObservations = 0
        jinhakLastAgentActionLabel = ""
        jinhakLastAgentActionOriginRoute = ""
        jinhakLastAgentActionMissionContext = null
        jinhakSlowLaneEscalated = 0
        jinhakSlowLaneCompleted = 0
        jinhakSlowLaneFailed = 0
        jinhakSlowLaneUserActionRequired = 0
        jinhakSlowLaneCompletedDurationMs = 0L
        jinhakSlowLaneMaxDurationMs = 0L
        jinhakReportBridgeContext = null
        jinhakReportBridgeArmed = 0
        jinhakReportBridgeApplied = 0
        jinhakReportBridgeConfirmed = 0
        jinhakMissionAnchorActionsAttempted = 0
        jinhakAnchorRejectReasons.clear()
        jinhakSlowLaneFailureReasons.clear()
        if (::slowLanePool.isInitialized) {
            slowLanePool.cancelAll("new-batch-reset")
            slowLanePool.setMaxActiveWorkers(JinhakSlowLanePool.DEFAULT_MAX_WORKERS)
        }
        cloudFrontierTaskIds.clear()
        cloudFrontierClaimInProgress = false
        cloudFrontierClaimAttempts = 0
        cloudFrontierPublished = 0
        cloudFrontierClaimed = 0
        cloudFrontierCompleted = 0
        cloudFrontierCompletionFailed = 0
        batchSkipSnapshotUntilMs = 0L
        jinhakAbsoluteTargetKey = ""
        ++jinhakAbsoluteTargetGeneration
        disarmBatchNavigationWatchdog()
        currentBatchTarget = if (provider == ProviderId.JINHAK) {
            canonicalizeBatchUrl(currentAdapter().seedUrls().firstOrNull() ?: url)
        } else canonicalizeBatchUrl(url)
        batchButton.text = "일괄 수집 중지"
        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            localRunId = localStore.beginOrResume(provider.wireName, VERSION)
            unifiedSessionId?.takeIf { unifiedRunning }?.let { sessionId ->
                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, provider.wireName, runId) }
            }
            status.text = if (unifiedRunning) {
                "통합 수집 1/2 · 어디가 Local-First 수집 시작 / run ${localRunId?.take(8)}…"
            } else {
                "Local-First 수집 시작: Cloudflare 호출 없음 / run ${localRunId?.take(8)}…"
            }
            beginBatchNavigation(null)
        } else {
            status.text = "현재 공급자는 로컬 단일 페이지 모드"
            beginBatchNavigation(null)
        }
    }

    private fun prepareCloudRecoveryAndStart(runId: String?) {
        if (runId.isNullOrBlank() || !cloudOffload.isConfigured()) {
            beginBatchNavigation(runId)
            return
        }
        status.text = "Cloud 전체 미완료 체크포인트 확인 중…"
        cloudOffload.pendingPages { result ->
            runOnUiThread {
                if (!batchRunning) return@runOnUiThread
                val response = result.getOrNull()
                if (response != null) {
                    val scheduled = enqueueGlobalPendingRecovery(response)
                    batchCloudPagesDeferred = response.optJSONArray("deferred")?.length() ?: 0
                    status.text = "Cloud 전역 복구: ${scheduled}쪽 우선 재시도 / ${batchCloudPagesDeferred}쪽 cooldown 보류"
                } else {
                    status.text = "Cloud 전역 복구 조회 실패: 기존 목록 resume-plan으로 계속"
                }
                beginBatchNavigation(runId)
            }
        }
    }

    private fun beginBatchNavigation(runId: String?) {
        if (provider == ProviderId.JINHAK) armJinhakProgressFence()
        enqueueProviderSeeds()
        cloudOffload.probeFrontier { available ->
            runOnUiThread {
                if (available) {
                    status.text = "Cloud frontier 연결됨: 링크 계획·중복제거·재시도를 클라우드와 동기화합니다."
                }
            }
        }
        if (runId != null && batchPageActions.isEmpty()) {
            status.text = "Cloud 체크포인트 연결: ${runId.take(8)}… / 기본 정보영역 ${batchQueue.size}개 탐색"
        } else if (runId == null) {
            status.text = "로컬 안전모드: 기본 정보영역 ${batchQueue.size}개 탐색"
        }
        checkSessionState { needsLogin, _ ->
            if (needsLogin) {
                pauseBatchForLogin()
            } else if (batchPageActions.isNotEmpty()) {
                loadNextBatchPage()
            } else {
                val startUrl = currentBatchTarget
                if (!startUrl.isNullOrBlank()) webView.loadUrl(startUrl)
                else loadNextBatchPage()
            }
        }
    }

    private fun enqueueGlobalPendingRecovery(response: JSONObject): Int {
        val retry = response.optJSONArray("retry") ?: JSONArray()
        var scheduled = 0
        for (i in 0 until retry.length()) {
            val item = retry.optJSONObject(i) ?: continue
            val familyKey = item.optString("familyKey")
            val page = item.optInt("page", -1)
            if (familyKey.isBlank() || page < 1) continue
            val requestedYear = if (item.isNull("requestedYear")) null else item.optInt("requestedYear").takeIf { it > 0 }
            val totalPages = item.optInt("totalPages", page).coerceAtLeast(page)
            val baseUrl = recoveryUrlForPending(familyKey, requestedYear) ?: continue
            val action = BatchPageAction(
                baseUrl = baseUrl,
                page = page,
                familyKey = familyKey,
                requestedYear = requestedYear,
                totalPages = totalPages,
                pageSize = 0,
                totalItems = 0,
                retry = 0
            )
            val key = pageActionKey(action)
            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue
            if (batchPageActionQueued.add(key)) {
                batchPageActions.addFirst(action)
                scheduled += 1
            }
        }
        batchCloudPagesScheduled += scheduled
        return scheduled
    }

    private fun recoveryUrlForPending(familyKey: String, requestedYear: Int?): String? {
        if (provider != ProviderId.ADIGA) return null
        val raw = if (familyKey.startsWith("http://") || familyKey.startsWith("https://")) {
            familyKey
        } else {
            "https://www.adiga.kr" + if (familyKey.startsWith("/")) familyKey else "/$familyKey"
        }
        return if (requestedYear != null) withQueryParameter(raw, "searchSyr", requestedYear.toString()) else raw
    }

    private fun isJinhakLowValueReferencePageType(pageType: String): Boolean = pageType in setOf(
        "jinhak-recommended-university",
        "jinhak-admission-strategy",
        "jinhak-admission-knowledge",
        "jinhak-admission-feature",
        "jinhak-editorial-content",
        "jinhak-media-content",
        "jinhak-home",
        "jinhak-other"
    )

    private fun noteJinhakMeaningfulProgress(reason: String, forceDiagnostics: Boolean = false) {
        if (provider != ProviderId.JINHAK) return
        jinhakLastMeaningfulProgressAtMs = System.currentTimeMillis()
        recordRuntimeEvent("jinhak-meaningful-progress", JSONObject()
            .put("reason", reason.take(80))
            .put("safePath", runtimeSafePath(webView.url ?: currentBatchTarget ?: "")))
        persistLiveJinhakDiagnostics(reason, forceDiagnostics)
    }

    private fun persistLiveJinhakDiagnostics(trigger: String, force: Boolean = false) {
        if (provider != ProviderId.JINHAK || !unifiedRunning || unifiedPhase != "jinhak") return
        val sessionId = unifiedSessionId ?: return
        val now = System.currentTimeMillis()
        if (!force && now - jinhakLastLiveDiagnosticsAtMs < JINHAK_LIVE_DIAGNOSTIC_MIN_INTERVAL_MS) return
        jinhakLastLiveDiagnosticsAtMs = now
        val slowStats = if (::slowLanePool.isInitialized) slowLanePool.stats() else null
        val sinceProgress = if (jinhakLastMeaningfulProgressAtMs > 0L) {
            ((now - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L)) / 1000.0
        } else null
        localStore.recordSyncState(
            sessionId,
            "JINHAK_CRAWL_DIAGNOSTICS",
            ProviderId.JINHAK.wireName,
            JSONObject()
                .put("live", true)
                .put("trigger", trigger.take(80))
                .put("attemptedSnapshots", batchPageCount)
                .put("successfulSnapshots", batchSnapshots.length())
                .put("errorEvents", batchErrors.length())
                .put("agentActionsExecuted", jinhakAgentActionsExecuted)
                .put("missionActionsExecuted", jinhakMissionActionsExecuted)
                .put("genericActionsExecuted", jinhakGenericActionsExecuted)
                .put("missionActionLimit", MAX_JINHAK_MISSION_ACTIONS)
                .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS)
                .put("applicationAnchorActionsPromoted", jinhakMissionAnchorPromotedKeys.size)
                .put("applicationAnchorStructuredBindings", jinhakMissionAnchorStructuredKeys.size)
                .put("normalizedApplicationIdentitySeeds", jinhakNormalizedIdentitySeedKeys.size)
                .put("normalizedApplicationCandidateBindings", jinhakNormalizedCandidateBindingKeys.size)
                .put("normalizedApplicationAmbiguousBindings", jinhakNormalizedAmbiguousBindings)
                        .put("originInferredMissionTargets", jinhakOriginInferredMissionTargets)
                        .put("externalNavigationsBlocked", jinhakExternalNavigationsBlocked)
                .put("jinhakBatchStartCount", jinhakBatchStartCount)
                .put("applicationAnchorActionsParsed", jinhakMissionAnchorParsedKeys.size)
                .put("applicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                .put("applicationAnchorActionsClicked", jinhakMissionAnchorClickedKeys.size)
                .put("applicationAnchorReportConfirmed", jinhakReportConfirmedKeys.size)
                .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
                .put("missionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("referenceRoutesTracked", jinhakReferenceRouteCaptureCounts.size)
                .put("referenceRepeatSkips", jinhakReferenceRepeatSkips)
                .put("noProgressFences", jinhakNoProgressFences)
                .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
                .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                .put("credentialAutoLoginSubmissions", credentialAutoLoginSubmissions)
                .put("credentialAutoLoginSuccesses", credentialAutoLoginSuccesses)
                .put("credentialAutoLoginFailures", credentialAutoLoginFailures)
                .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                .put("loginRouteFallbackCredentialPrompts", loginRouteFallbackCredentialPrompts)
                .put("staleSessionLeaseBypassesPrevented", staleSessionLeaseBypassesPrevented)
                .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                .put("jinhakCoreScopeBlockedUrls", jinhakCoreScopeBlockedUrls)
                .put("jinhakCoreScopeBlockedLanes", JSONObject(jinhakCoreScopeBlockedLaneCounts as Map<*, *>))
                .put("secondsSinceMeaningfulProgress", sinceProgress ?: JSONObject.NULL)
                .put("activeMissionTarget", jinhakActiveMissionTargetId != null)
                .put("slowLaneRunning", slowStats?.running ?: 0)
                .put("slowLaneQueued", slowStats?.queued ?: 0)
                .put("safePath", runtimeSafePath(webView.url ?: currentBatchTarget ?: "")),
            false,
            updateOrchestrator = false
        )
    }

    private fun armJinhakProgressFence() {
        if (provider != ProviderId.JINHAK) return
        if (jinhakLastMeaningfulProgressAtMs == 0L) jinhakLastMeaningfulProgressAtMs = System.currentTimeMillis()
        val generation = ++jinhakProgressFenceGeneration
        val poller = object : Runnable {
            override fun run() {
                if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakProgressFenceGeneration) return
                val now = System.currentTimeMillis()
                val elapsed = now - jinhakLastMeaningfulProgressAtMs
                if (elapsed >= JINHAK_NO_PROGRESS_FENCE_MS) {
                    val slowWork = ::slowLanePool.isInitialized && slowLanePool.hasWork()
                    val ledgerOutstanding = jinhakMissionTargetLedger.outstandingCount()
                    if (ledgerOutstanding == 0 && !slowWork && !jinhakAgentActionInFlight && !batchCollecting) {
                        val stalled = canonicalizeBatchUrl(webView.url ?: currentBatchTarget ?: "")
                        jinhakNoProgressFences += 1
                        batchErrors.put(JSONObject()
                            .put("type", "jinhak-no-progress-fence")
                            .put("safePath", runtimeSafePath(stalled))
                            .put("elapsedMs", elapsed))
                        localRunId?.let { runId ->
                            if (stalled.isNotBlank()) localStore.markDocument(runId, stalled, "error", 0, "jinhak-no-progress-fence")
                        }
                        if (stalled.isNotBlank()) {
                            batchVisited.add(stalled)
                            batchQueued.remove(stalled)
                        }
                        currentBatchTarget = null
                        pendingBatchPageAction = null
                        activeBatchPageAction = null
                        batchCollecting = false
                        batchNavigationWatchdogRecovery = false
                        jinhakAbsoluteTargetKey = ""
                        ++jinhakAbsoluteTargetGeneration
                        ++jinhakStallWatchdogGeneration
                        runCatching { webView.stopLoading() }
                        jinhakLastMeaningfulProgressAtMs = now
                        recordRuntimeEvent("jinhak-no-progress-fence", JSONObject()
                            .put("safePath", runtimeSafePath(stalled))
                            .put("elapsedMs", elapsed)
                            .put("referencePageType", lastJinhakDigest.optString("pageType")))
                        persistLiveJinhakDiagnostics("no-progress-fence", force = true)
                        status.text = "60초 동안 새 수집 진전이 없어 현재 일반 탐색 페이지를 종료하고 다음 대상으로 진행합니다."
                        handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 220L)
                    } else {
                        // Mission/slow-worker work owns the target. Existing 35s slow-lane fences
                        // remain authoritative; expose the stalled state without stealing ownership.
                        persistLiveJinhakDiagnostics("progress-wait-mission", force = true)
                    }
                } else {
                    persistLiveJinhakDiagnostics("progress-heartbeat")
                }
                handler.postDelayed(this, JINHAK_PROGRESS_FENCE_POLL_MS)
            }
        }
        handler.postDelayed(poller, JINHAK_PROGRESS_FENCE_POLL_MS)
    }

    private fun armBatchNavigationWatchdog(expectedUrl: String) {
        if (provider == ProviderId.JINHAK) {
            armJinhakStallWatchdog(expectedUrl)
            return
        }
        val generation = ++batchNavigationWatchdogGeneration
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || generation != batchNavigationWatchdogGeneration) return@postDelayed
            val current = webView.url ?: expectedUrl
            val sameDocument = canonicalizeBatchUrl(current) == canonicalizeBatchUrl(expectedUrl) || sameBatchDocument(current, expectedUrl)
            if (!sameDocument) return@postDelayed
            batchNavigationWatchdogRecovery = true
            batchNavigationWatchdogGeneration += 1
            status.text = "페이지 로딩 지연 감지: 현재 DOM으로 안전하게 계속합니다."
            if (::batchCover.isInitialized) {
                batchCover.text = "입시정보 수집 계속 중\n\n페이지 로딩이 오래 걸려 현재 상태를 평가한 뒤 다음 항목으로 진행합니다.\n${safeDisplayUrl(current)}"
            }
            runCatching { webView.stopLoading() }
            handler.postDelayed({
                if (!batchRunning || batchPausedForLogin || batchCollecting) return@postDelayed
                scheduleBatchSnapshot()
            }, 250L)
        }, BATCH_NAVIGATION_TIMEOUT_MS)
    }

    private fun disarmBatchNavigationWatchdog() {
        batchNavigationWatchdogGeneration += 1
        jinhakStallWatchdogGeneration += 1
    }

    private fun armJinhakStallWatchdog(expectedUrl: String) {
        val generation = ++jinhakStallWatchdogGeneration
        val expectedSafe = runtimeSafePath(expectedUrl)
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakStallWatchdogGeneration) return@postDelayed
            val probe = """
                (function(){
                  try{
                    var t=String(document.title||'').trim();
                    var b=(document.body&&document.body.innerText?document.body.innerText:'').replace(/\s+/g,' ').trim();
                    var rs=String(document.readyState||'');
                    var err=/(404\s*Not\s*Found|500\s*(?:Internal\s*Server\s*Error)?|웹페이지를\s*사용할\s*수\s*없|net::ERR_|일시적인\s*오류)/i.test(t+' '+b.slice(0,8000));
                    return JSON.stringify({readyState:rs,textLength:b.length,error:err,titleLength:t.length});
                  }catch(e){return JSON.stringify({readyState:'error',textLength:0,error:true,titleLength:0});}
                })();
            """.trimIndent()
            webView.evaluateJavascript(probe) { encoded ->
                if (!batchRunning || provider != ProviderId.JINHAK || generation != jinhakStallWatchdogGeneration) return@evaluateJavascript
                val state = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()
                val meaningful = state.optInt("textLength", 0) >= 80 || state.optInt("titleLength", 0) >= 3
                if (meaningful && !state.optBoolean("error", false)) {
                    jinhakRecoveredStalls += 1
                    recordRuntimeEvent("jinhak-soft-stall-recovered", JSONObject()
                        .put("safePath", runtimeSafePath(webView.url ?: expectedUrl))
                        .put("readyState", state.optString("readyState"))
                        .put("textLength", state.optInt("textLength")))
                    status.text = "진학사 로딩 지연 복구: 렌더된 DOM을 수집하고 다음 페이지로 진행합니다."
                    // The 24s hard timer belongs to the same stalled navigation. Once a
                    // meaningful DOM is accepted at 12s, invalidate that hard timer so it
                    // cannot race the snapshot parser and skip a valid page.
                    ++jinhakStallWatchdogGeneration
                    batchNavigationWatchdogRecovery = true
                    runCatching { webView.stopLoading() }
                    handler.postDelayed({
                        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
                        batchNavigationWatchdogRecovery = false
                        if (!batchCollecting) collectSnapshotForBatch()
                    }, 220L)
                }
            }
        }, JINHAK_SOFT_STALL_MS)

        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK || generation != jinhakStallWatchdogGeneration) return@postDelayed
            val stalled = canonicalizeBatchUrl(webView.url ?: currentBatchTarget ?: expectedUrl)
            jinhakConsecutiveStalls += 1
            jinhakRecoveredStalls += 1
            recordRuntimeEvent("jinhak-hard-stall-skip", JSONObject()
                .put("safePath", runtimeSafePath(stalled.ifBlank { expectedUrl }))
                .put("consecutive", jinhakConsecutiveStalls)
                .put("expectedSafePath", expectedSafe))
            localRunId?.let { runId ->
                if (stalled.isNotBlank()) localStore.markDocument(runId, stalled, "error", 0, "jinhak-navigation-stall")
            }
            if (stalled.isNotBlank()) batchVisited.add(stalled)
            batchErrors.put(JSONObject()
                .put("type", "jinhak-navigation-stall")
                .put("safePath", runtimeSafePath(stalled.ifBlank { expectedUrl })))
            currentBatchTarget = null
            pendingBatchPageAction = null
            activeBatchPageAction = null
            batchCollecting = false
            batchNavigationWatchdogRecovery = false
            ++jinhakStallWatchdogGeneration
            runCatching { webView.stopLoading() }
            status.text = if (jinhakConsecutiveStalls >= MAX_JINHAK_CONSECUTIVE_STALLS) {
                "진학사 연속 로딩 지연 ${jinhakConsecutiveStalls}회: 문제 페이지를 격리하고 큐를 계속 진행합니다."
            } else {
                "진학사 로딩 중단 페이지 건너뜀: 다음 탐색 대상으로 계속합니다."
            }
            handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 280L)
        }, JINHAK_HARD_STALL_MS)
    }

    private fun armJinhakAbsoluteTargetWatchdog(expectedUrl: String) {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return
        val target = canonicalizeBatchUrl(currentBatchTarget ?: expectedUrl)
        if (target.isBlank()) return
        val key = RecordUtils.sha256(target)
        if (key == jinhakAbsoluteTargetKey) return
        jinhakAbsoluteTargetKey = key
        val generation = ++jinhakAbsoluteTargetGeneration
        val startedAt = System.currentTimeMillis()
        recordRuntimeEvent("jinhak-target-start", JSONObject()
            .put("targetSafePath", runtimeSafePath(target))
            .put("currentSafePath", runtimeSafePath(expectedUrl)))

        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return@postDelayed
            if (generation != jinhakAbsoluteTargetGeneration || key != jinhakAbsoluteTargetKey) return@postDelayed
            val activeTarget = canonicalizeBatchUrl(currentBatchTarget ?: target)
            if (RecordUtils.sha256(activeTarget) != key) return@postDelayed

            val current = canonicalizeBatchUrl(webView.url ?: expectedUrl)
            val mission = jinhakLastAgentActionMissionContext ?: jinhakMissionContext
            val actionLabel = jinhakLastAgentActionLabel.takeIf { it.isNotBlank() }
            val actionOrigin = jinhakLastAgentActionOriginRoute.takeIf { it.isNotBlank() } ?: target
            val laneHint = jinhakSlowLaneHint(target, actionLabel)
            val priority = jinhakSlowLanePriority(laneHint, target)
            val task = JinhakSlowLanePool.Task(
                id = RecordUtils.sha256(listOf(target, actionOrigin, actionLabel ?: "", mission?.identityKey ?: "", startedAt.toString()).joinToString("|")),
                targetUrl = target,
                originUrl = actionOrigin,
                actionLabel = actionLabel,
                missionContext = jinhakReportBridgeContext?.let { JSONObject(it.toString()) } ?: mission?.toJson(),
                laneHint = laneHint,
                priority = priority,
                reason = "foreground-35s-slow-escalation"
            )
            val accepted = ::slowLanePool.isInitialized && slowLanePool.enqueue(task)
            val ledgerTargetForSlowLane = jinhakActiveMissionTargetId
            if (accepted) {
                if (ledgerTargetForSlowLane != null) {
                    jinhakMissionTargetLedger.markDeferred(ledgerTargetForSlowLane)
                    jinhakSlowLaneMissionTargetIds[task.id] = ledgerTargetForSlowLane
                    jinhakActiveMissionTargetId = null
                }
                jinhakSlowLaneEscalated += 1
                recordRuntimeEvent("jinhak-slow-lane-escalated", JSONObject()
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("currentSafePath", runtimeSafePath(current))
                    .put("elapsedMs", System.currentTimeMillis() - startedAt)
                    .put("laneHint", laneHint)
                    .put("priority", priority)
                    .put("missionBound", mission?.identityKey != null))
                localRunId?.let { runId -> localStore.markDocument(runId, target, "slow-lane", 0, null) }
            } else {
                if (ledgerTargetForSlowLane != null) {
                    jinhakMissionTargetLedger.markFailed(ledgerTargetForSlowLane, "slow-lane-queue-full")
                    if (jinhakActiveMissionTargetId == ledgerTargetForSlowLane) jinhakActiveMissionTargetId = null
                }
                jinhakSlowLaneFailed += 1
                batchErrors.put(JSONObject()
                    .put("type", "jinhak-slow-lane-queue-full")
                    .put("targetSafePath", runtimeSafePath(target))
                    .put("currentSafePath", runtimeSafePath(current)))
                localRunId?.let { runId -> localStore.markDocument(runId, target, "error", 0, "jinhak-slow-lane-queue-full") }
            }

            // The main browser is now free to continue. A slow worker owns the deferred target.
            batchVisited.add(target)
            batchQueued.remove(target)
            batchCollecting = false
            batchNavigationWatchdogRecovery = false
            batchReadinessPolling = false
            pendingBatchPageAction = null
            activeBatchPageAction = null
            currentBatchTarget = null
            ++jinhakStallWatchdogGeneration
            jinhakAbsoluteTargetKey = ""
            ++jinhakAbsoluteTargetGeneration
            runCatching { webView.stopLoading() }
            status.text = if (accepted) {
                "35초 경과: 느린 페이지를 병렬 slow worker로 넘기고 메인 탐색은 계속합니다."
            } else {
                "35초 경과: slow worker 대기열이 가득 차 해당 페이지를 오류로 기록하고 계속합니다."
            }
            handler.postDelayed({
                if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK) loadNextBatchPage()
            }, 220L)
        }, JINHAK_SLOW_ESCALATION_MS)
    }

    private fun jinhakSlowLaneHint(target: String, actionLabel: String?): String {
        val material = (target + " " + (actionLabel ?: "")).lowercase()
        return when {
            Regex("실제\\s*합격자|actual|passdata").containsMatchIn(material) -> "actual-admit"
            Regex("모의\\s*지원|mock").containsMatchIn(material) -> "mock-support"
            Regex("합격\\s*예측|predict").containsMatchIn(material) -> "current-prediction"
            Regex("성적|환산|score|minimum|최저").containsMatchIn(material) -> "score-analysis"
            Regex("입시\\s*결과|univ-major|univ-info|경쟁률").containsMatchIn(material) -> "university-result"
            Regex("입시\\s*전략|strategy|knowledge").containsMatchIn(material) -> "strategy"
            else -> "reference"
        }
    }

    private fun jinhakSlowLanePriority(lane: String, target: String): Int = when (lane) {
        "actual-admit" -> 120
        "mock-support" -> 116
        "current-prediction" -> 112
        "score-analysis" -> 106
        "university-result" -> 100
        "strategy" -> 70
        else -> if (JinhakSiteTopology.isCoreMissionRoute(target)) 92 else 40
    }

    private fun handleJinhakSlowLaneCompleted(
        task: JinhakSlowLanePool.Task,
        snapshot: JSONObject,
        stats: JinhakSlowLanePool.ResultStats
    ) {
        if (provider != ProviderId.JINHAK) return
        val session = snapshot.optJSONObject("session") ?: JSONObject()
        val gate = snapshot.optJSONObject("interactionGate") ?: JSONObject()
        if (session.optBoolean("needsLogin", false) || gate.optBoolean("requiresUserAction", false)) {
            jinhakSlowLaneUserActionRequired += 1
            handleJinhakSlowLaneFailed(task, "slow-lane-user-action-required", stats)
            return
        }
        runCatching {
            val adapter = ProviderRegistry.adapter(ProviderId.JINHAK)
            snapshot.put("providerPageType", adapter.classify(snapshot))
            task.missionContext?.let { snapshot.put("missionApplicationContext", JSONObject(it.toString())) }
            snapshot.put("collectionTransport", "concurrent-slow-lane")
            snapshot.put("slowLane", JSONObject()
                .put("workerId", stats.workerId)
                .put("elapsedMs", stats.elapsedMs)
                .put("progressEvents", stats.progressEvents)
                .put("replayUsed", stats.replayUsed)
                .put("laneHint", task.laneHint)
                .put("laneSatisfied", stats.laneSatisfied))

            val records = adapter.normalize(snapshot)
            val runId = localRunId ?: localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION).also { localRunId = it }
            val stored = localStore.storeRecords(runId, ProviderId.JINHAK.wireName, records)
            batchLocalRecordsPersisted += stored
            val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url", task.targetUrl)))
            localStore.markDocument(runId, task.targetUrl, "completed")
            if (navKey.isNotBlank()) localStore.markDocument(runId, navKey, "completed")
            cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "completed", null) { ok -> if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1 } }

            val mission = JinhakApplicationMission.fromJson(task.missionContext)
            val missionKey = mission?.identityKey
            val pageType = snapshot.optString("providerPageType")
            val resolvedLane = JinhakApplicationMission.laneForPageType(pageType).takeIf { it != "reference" } ?: task.laneHint
            if (missionKey != null && resolvedLane != "reference") {
                jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(resolvedLane)
            }
            jinhakSlowLaneMissionTargetIds.remove(task.id)?.let { targetId ->
                val pageLane = JinhakApplicationMission.laneForPageType(pageType)
                if (!jinhakMissionTargetLedger.markConfirmed(targetId, missionKey, pageLane)) {
                    jinhakMissionTargetLedger.markFailed(targetId, "slow-lane-report-unconfirmed")
                }
            }

            val capturedAt = Instant.now().toString()
            val digest = buildJinhakDigest(snapshot, records, runId, capturedAt)
            lastJinhakDigest = digest
            unifiedSessionId?.takeIf { unifiedRunning && unifiedPhase == "jinhak" }?.let { sessionId ->
                localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId)
                val safeRoute = runtimeSafePath(snapshot.optString("url", task.targetUrl))
                val explicitContext = ObservationEvidence.explicitContextFromDigest(digest)
                localStore.storeUnifiedAnalysisCapture(
                    sessionId = sessionId,
                    provider = ProviderId.JINHAK.wireName,
                    pageKey = RecordUtils.sha256(listOf(task.id, navKey, missionKey ?: "").joinToString("|")),
                    pageType = pageType,
                    payload = digest
                )
                localStore.storeObservationEvidence(
                    sessionId = sessionId,
                    runId = runId,
                    provider = ProviderId.JINHAK.wireName,
                    safeRouteKey = safeRoute,
                    pageTypeGuess = pageType,
                    pageTypeConfidence = if (pageType == "jinhak-other") 0.25 else 0.90,
                    authStateClass = "authenticated",
                    explicitContext = explicitContext,
                    evidence = digest,
                    captureVersion = VERSION
                )
                localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)
            }
            batchSnapshots.put(snapshotForLocalExport(snapshot))
            batchPageCount += 1
            jinhakSlowLaneCompleted += 1
            noteJinhakMeaningfulProgress("slow-lane-completed", forceDiagnostics = true)
            jinhakSlowLaneCompletedDurationMs += stats.elapsedMs
            if (stats.elapsedMs > jinhakSlowLaneMaxDurationMs) jinhakSlowLaneMaxDurationMs = stats.elapsedMs
            recordRuntimeEvent("jinhak-slow-lane-completed", JSONObject()
                .put("targetSafePath", runtimeSafePath(task.targetUrl))
                .put("pageType", pageType)
                .put("lane", resolvedLane)
                .put("elapsedMs", stats.elapsedMs)
                .put("progressEvents", stats.progressEvents)
                .put("records", records.length())
                .put("missionBound", missionKey != null))
        }.onFailure { error ->
            handleJinhakSlowLaneFailed(task, "slow-lane-persist-failure:${error.javaClass.simpleName}", stats)
            return
        }
        if (batchRunning && !batchPausedForLogin) handler.postDelayed({ loadNextBatchPage() }, 80L)
    }

    private fun handleJinhakSlowLaneFailed(
        task: JinhakSlowLanePool.Task,
        reason: String,
        stats: JinhakSlowLanePool.ResultStats
    ) {
        jinhakSlowLaneMissionTargetIds.remove(task.id)?.let { targetId ->
            jinhakMissionTargetLedger.markFailed(targetId, reason)
        }
        jinhakSlowLaneFailed += 1
        val failureClass = reason.substringBefore(':').take(80)
        jinhakSlowLaneFailureReasons[failureClass] = (jinhakSlowLaneFailureReasons[failureClass] ?: 0) + 1
        batchErrors.put(JSONObject()
            .put("type", reason.take(120))
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("source", "concurrent-slow-lane")
            .put("laneHint", task.laneHint)
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))
        localRunId?.let { runId -> localStore.markDocument(runId, task.targetUrl, "error", 0, reason.take(120)) }
        cloudFrontierTaskIds.remove(task.targetUrl)?.let { taskId -> cloudOffload.completeFrontier(taskId, "error", reason.take(120)) { ok -> if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1 } }
        recordRuntimeEvent("jinhak-slow-lane-failed", JSONObject()
            .put("targetSafePath", runtimeSafePath(task.targetUrl))
            .put("reason", reason.take(120))
            .put("elapsedMs", stats.elapsedMs)
            .put("progressEvents", stats.progressEvents))
        if (batchRunning && !batchPausedForLogin) handler.postDelayed({ loadNextBatchPage() }, 80L)
    }

    private fun showBatchCover() {
        if (!::batchCover.isInitialized) return
        batchCover.text = "입시정보 수집 중\n\n로그인된 브라우저 자체가 수집 엔진으로 동작합니다.\n페이지 이동은 이 화면 뒤에서 처리됩니다."
        batchCover.visibility = View.VISIBLE
        batchCover.bringToFront()
    }

    private fun hideBatchCover() {
        if (::batchCover.isInitialized) batchCover.visibility = View.GONE
    }

    private fun confirmStopBatch() {
        AlertDialog.Builder(this)
            .setTitle("일괄 수집을 중지할까요?")
            .setMessage("현재까지 수집한 결과는 보존됩니다. 실수로 누른 경우 '계속 수집'을 선택하세요.")
            .setNegativeButton("계속 수집", null)
            .setPositiveButton("중지") { _, _ -> stopBatch("사용자 중지") }
            .show()
    }

    private fun stopBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        if (::slowLanePool.isInitialized) slowLanePool.cancelAll("batch-stopped")
        webView.stopLoading()
        hideBatchCover()
        stopCollectionKeepAlive()
        batchQueue.clear()
        batchQueued.clear()
        batchPageActions.clear()
        batchPageActionQueued.clear()
        batchReadinessPolling = false
        pendingBatchPageAction = null
        activeBatchPageAction = null
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else if (provider == ProviderId.JINHAK && currentAdapter().supportsUserSessionMissionTraversal) "진학사 목적형 탐색" else "현재 화면 정리"
        status.text = "일괄 수집 중지: $reason"
        localRunId?.let { localStore.markRun(it, "stopped", reason) }
        if (batchSnapshots.length() > 0 || localRunId != null) finalizeBatchJson("stopped")
        jinhakAbsoluteTargetKey = ""
        ++jinhakAbsoluteTargetGeneration
    }

    private fun pauseBatchForRenderedLoginSurface(which: ProviderId, reason: String) {
        if (!batchRunning || batchPausedForLogin || provider != which) return
        batchRenderedLoginSurfacePauses += 1
        batchPausedForLogin = true
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        hideBatchCover()
        sessionState.text = "○ ${which.displayName} 로그인 화면 감지 · 자동 로그인 중"
        status.text = "현재 수집 대상을 보존한 채 로그인 처리를 기다립니다. 로그인 성공 후 같은 대상을 다시 엽니다."
        recordRuntimeEvent(
            "rendered-login-surface-batch-pause",
            JSONObject()
                .put("provider", which.wireName)
                .put("reason", reason.take(40))
                .put("currentTarget", runtimeSafePath(currentBatchTarget))
                .put("proactiveLoginNavigation", false)
        )
    }

    private fun continueBatchAfterRenderedLoginGuard(url: String, attempt: Int) {
        if (!batchRunning || batchPausedForLogin) return
        val expectedProvider = provider
        probeLoginSurface(expectedProvider) { probe ->
            if (!batchRunning || batchPausedForLogin || provider != expectedProvider) return@probeLoginSurface
            if (probe.optBoolean("detected", false)) {
                pauseBatchForRenderedLoginSurface(expectedProvider, "batch-page-finished")
                if (credentialVault.has(expectedProvider.wireName)) {
                    attemptSavedCredentialLogin(expectedProvider, "batch-login-surface")
                } else if (startupCredentialPromptedProvider != expectedProvider) {
                    startupCredentialPromptedProvider = expectedProvider
                    showCredentialDialog(expectedProvider, continueAfterSave = true)
                }
                return@probeLoginSurface
            }
            // A login-looking URL is only a reason to wait briefly for SPA hydration; it
            // is never treated as proof of logout and never triggers navigation by itself.
            if (isProviderLoginUrl(expectedProvider, url) && attempt < 3) {
                val delay = when (attempt) { 0 -> 250L; 1 -> 650L; else -> 1_200L }
                handler.postDelayed({ continueBatchAfterRenderedLoginGuard(url, attempt + 1) }, delay)
                return@probeLoginSurface
            }
            if (isProviderLoginUrl(expectedProvider, url)) {
                loginRouteFallbackPauses += 1
                batchPausedForLogin = true
                batchCollecting = false
                batchNavigationWatchdogRecovery = false
                batchCloudFinalCheckInProgress = false
                disarmBatchNavigationWatchdog()
                hideBatchCover()
                if (expectedProvider == ProviderId.JINHAK) {
                    jinhakAuthVerifiedForBatch = false
                    jinhakCoreBootstrapState = "batch-login-route-wait"
                }
                recordRuntimeEvent("login-route-fallback-batch-pause", JSONObject()
                    .put("provider", expectedProvider.wireName)
                    .put("currentTarget", runtimeSafePath(currentBatchTarget))
                    .put("loginSafePath", runtimeSafePath(url))
                    .put("renderedSurfaceDetected", false)
                    .put("proactiveLoginNavigation", false))
                sessionState.text = "○ ${expectedProvider.displayName} 로그인 경로 감지 · 수집 대상 보존"
                if (credentialVault.has(expectedProvider.wireName)) {
                    status.text = "현재 수집 대상을 보존했습니다. 로그인 화면이 늦게 렌더링되어도 계속 감지해 자동로그인 후 동일 target을 재개합니다."
                    if (expectedProvider == ProviderId.JINHAK) scheduleJinhakLoginRecovery("batch-login-route-fallback")
                    else scheduleLoginSurfaceDetection(expectedProvider, "batch-login-route-fallback")
                } else if (startupCredentialPromptedProvider != expectedProvider) {
                    startupCredentialPromptedProvider = expectedProvider
                    loginRouteFallbackCredentialPrompts += 1
                    status.text = "로그인이 필요합니다. 계정정보는 이 기기에만 암호화 저장되며 현재 수집 target은 유지됩니다."
                    showCredentialDialog(expectedProvider, continueAfterSave = true)
                } else {
                    status.text = "로그인 화면에서 인증을 완료하면 동일 수집 target을 자동으로 다시 엽니다."
                }
                return@probeLoginSurface
            }
            disarmBatchNavigationWatchdog()
            if (batchNavigationWatchdogRecovery) {
                batchNavigationWatchdogRecovery = false
                return@probeLoginSurface
            }
            val pending = pendingBatchPageAction
            if (pending != null && sameBatchDocument(url, pending.baseUrl)) {
                executePendingBatchPageAction()
            } else {
                scheduleBatchSnapshot()
            }
        }
    }

    private fun pauseBatchForLogin(autoOpenLogin: Boolean = true) {
        batchPausedForLogin = true
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        hideBatchCover()
        if (autoOpenLogin) {
            sessionState.text = "○ 로그인 갱신 필요"
            status.text = "백그라운드 수집 일시정지: 메인 로그인 갱신 후 자동으로 계속합니다."
        } else {
            sessionState.text = "△ 수집 세션 재동기화 필요"
            status.text = "수집 세션 자동 동기화 실패: 로그인 세션 확인/갱신 후 계속을 눌러주세요."
        }
        batchButton.text = "일괄 수집 중지"
        if (autoOpenLogin) handler.postDelayed({ refreshSessionOrOpenLogin() }, 150)
    }

    private fun recoverCollectorSessionOrPause() {
        if (!batchRunning) return
        CookieManager.getInstance().flush()
        checkSessionState { needsLogin, authenticated ->
            if (!batchRunning) return@checkSessionState
            batchSessionSyncRetries = 0
            if (needsLogin) {
                pauseBatchForLogin(autoOpenLogin = true)
                return@checkSessionState
            }
            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = if (authenticated) "● 로그인 유지 / 동일 수집 브라우저" else "△ 로그인 판정 미확정 / 동일 브라우저 재시도"
            val retry = currentBatchTarget
            handler.postDelayed({
                if (!batchRunning || batchPausedForLogin) return@postDelayed
                if (!retry.isNullOrBlank() && isProviderUrl(retry)) webView.loadUrl(retry)
                else loadNextBatchPage()
            }, 250)
        }
    }

    private fun resumeAfterLogin() {
        if (provider == ProviderId.JINHAK && batchRunning && batchPausedForLogin && jinhakConsentGatePending) {
            // User must choose consent/decline and confirm inside the provider UI.  This button
            // only resumes observation; it never clicks or selects either provider choice.
            jinhakConsentGatePending = false
            jinhakConsentResumePending = true
            batchPausedForLogin = false
            showBatchCover()
            sessionState.text = "△ 진학사 동의 선택 확인 중"
            status.text = "사용자 선택 후 진학사 화면을 다시 확인합니다. 선택값은 Collector가 읽거나 변경하지 않습니다."
            handler.postDelayed({
                if (batchRunning && !batchPausedForLogin && provider == ProviderId.JINHAK && !batchCollecting) scheduleBatchSnapshot()
            }, 650L)
            return
        }
        if (!batchRunning || !batchPausedForLogin) {
            checkSessionState()
            return
        }
        checkSessionState { needsLogin, authenticated ->
            if (needsLogin || !authenticated) {
                Toast.makeText(this, "로그인 상태가 아직 확인되지 않습니다.", Toast.LENGTH_SHORT).show()
                return@checkSessionState
            }
            batchPausedForLogin = false
            if (provider == ProviderId.JINHAK) {
                jinhakAuthVerifiedForBatch = true
                jinhakCoreBootstrapState = "batch-auth-recovered"
            }
            showBatchCover()
            sessionState.text = "● 로그인 복구 / 동일 수집 브라우저"
            val retry = currentBatchTarget
            if (!retry.isNullOrBlank() && isProviderUrl(retry)) {
                status.text = "로그인 복구 완료: 중단 지점 재시도"
                webView.loadUrl(retry)
            } else {
                loadNextBatchPage()
            }
        }
    }

    private fun scheduleBatchSnapshot() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return
        val skipWait = batchSkipSnapshotUntilMs - System.currentTimeMillis()
        if (skipWait > 0L) {
            handler.postDelayed({ scheduleBatchSnapshot() }, skipWait + 80L)
            return
        }

        // Pagination actions already wait for AJAX after fnSearch(N). Do not run the
        // first-page bootstrap logic here, because the legitimate last page may
        // contain only one row.
        val activeAction = activeBatchPageAction
        if (activeAction != null) {
            pollPaginationActionReadiness(activeAction, attempt = 0)
            return
        }

        val url = canonicalizeBatchUrl(webView.url ?: "")
        if (currentAdapter().isDynamicListPage(url)) {
            if (batchReadinessPolling) return
            batchReadinessPolling = true
            pollAdigaDynamicListReadiness(url, attempt = 0, afterBootstrap = false)
        } else {
            handler.postDelayed({ collectSnapshotForBatch() }, 650)
        }
    }


    private fun pollPaginationActionReadiness(action: BatchPageAction, attempt: Int) {
        if (!batchRunning || batchPausedForLogin || batchCollecting || activeBatchPageAction == null) return
        val js = """
            (function(){
              try{
                var body=(document.body&&document.body.innerText?document.body.innerText:'').slice(0,20000);
                var title=String(document.title||'');
                var error=/(404\s*Not\s*Found|500\s*(?:Internal\s*Server\s*Error)?|서비스\s*처리\s*중\s*오류|일시적인\s*오류가\s*발생|웹페이지를\s*사용할\s*수\s*없|net::ERR_)/i.test(title+' '+body);
                var table=document.querySelector('table,[role=table]');
                var rows=table?table.querySelectorAll('tr,[role=row]').length:0;
                var tableText=table?(table.innerText||table.textContent||'').replace(/\s+/g,' ').trim().slice(0,30000):'';
                return JSON.stringify({error:error,rows:rows,tableText:tableText});
              }catch(e){return JSON.stringify({error:false,rows:0,tableText:''});}
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            if (!batchRunning || batchPausedForLogin || activeBatchPageAction == null) return@evaluateJavascript
            try {
                val obj = JSONObject(decodeJsString(encoded))
                val isError = obj.optBoolean("error", false)
                val rows = obj.optInt("rows", 0)
                val tableText = obj.optString("tableText")
                val signature = if (tableText.isNotBlank()) RecordUtils.sha256(tableText) else ""
                val previous = batchLastTableSignatures[action.baseUrl]
                val changed = signature.isNotBlank() && (previous == null || previous != signature)
                if (isError || (rows > 1 && changed) || attempt >= 12) {
                    collectSnapshotForBatch()
                } else {
                    handler.postDelayed({ pollPaginationActionReadiness(action, attempt + 1) }, 250)
                }
            } catch (_: Exception) {
                if (attempt >= 12) collectSnapshotForBatch()
                else handler.postDelayed({ pollPaginationActionReadiness(action, attempt + 1) }, 250)
            }
        }
    }

    private fun pollAdigaDynamicListReadiness(baseUrl: String, attempt: Int, afterBootstrap: Boolean) {
        if (!batchRunning || batchPausedForLogin || batchCollecting) {
            batchReadinessPolling = false
            return
        }
        val current = canonicalizeBatchUrl(webView.url ?: "")
        if (current != baseUrl && !sameBatchDocument(current, baseUrl)) {
            batchReadinessPolling = false
            scheduleBatchSnapshot()
            return
        }

        val js = """
            (function(){
              try{
                var text=(document.body&&document.body.innerText?document.body.innerText:'').replace(/\s+/g,' ');
                var m=text.match(/총\s*([0-9,]+)\s*건/);
                var total=m?parseInt(m[1].replace(/,/g,''),10):-1;
                var table=document.querySelector('table,[role=table]');
                var rows=table?table.querySelectorAll('tr,[role=row]').length:0;
                var noResult=/검색결과가\s*없습니다/.test(text);
                return JSON.stringify({
                  total:isNaN(total)?-1:total,
                  rows:rows,
                  noResult:noResult,
                  canFnSearch:(typeof window.fnSearch==='function')
                });
              }catch(e){
                return JSON.stringify({total:-1,rows:0,noResult:false,canFnSearch:false});
              }
            })();
        """.trimIndent()

        webView.evaluateJavascript(js) { encoded ->
            if (!batchRunning || batchPausedForLogin) {
                batchReadinessPolling = false
                return@evaluateJavascript
            }
            try {
                val obj = JSONObject(decodeJsString(encoded))
                val total = obj.optInt("total", -1)
                val rows = obj.optInt("rows", 0)
                val visibleDataRows = (rows - 1).coerceAtLeast(0)
                val ready = total > 0 && visibleDataRows > 0 &&
                    (total <= visibleDataRows || visibleDataRows >= 5)

                if (ready) {
                    batchReadinessPolling = false
                    status.text = "동적 목록 준비 완료: 총 ${total}건"
                    handler.postDelayed({ collectSnapshotForBatch() }, 250)
                    return@evaluateJavascript
                }

                val maxAttempts = if (afterBootstrap) 18 else 12
                if (attempt < maxAttempts) {
                    status.text = "동적 목록 로딩 대기: ${attempt + 1}/$maxAttempts"
                    handler.postDelayed({
                        pollAdigaDynamicListReadiness(baseUrl, attempt + 1, afterBootstrap)
                    }, 450)
                    return@evaluateJavascript
                }

                val canFnSearch = obj.optBoolean("canFnSearch", false)
                if (!afterBootstrap && canFnSearch && batchBootstrapSearchAttempted.add(baseUrl)) {
                    status.text = "초기 검색 실행 후 목록 재대기"
                    webView.evaluateJavascript(
                        "(function(){try{window.fnSearch(1);return true;}catch(e){return false;}})();"
                    ) {
                        handler.postDelayed({
                            pollAdigaDynamicListReadiness(baseUrl, attempt = 0, afterBootstrap = true)
                        }, 900)
                    }
                    return@evaluateJavascript
                }

                batchReadinessPolling = false
                status.text = "동적 목록 준비 시간 초과: 현재 상태 그대로 안전 수집"
                collectSnapshotForBatch()
            } catch (_: Exception) {
                batchReadinessPolling = false
                handler.postDelayed({ collectSnapshotForBatch() }, 250)
            }
        }
    }

    private fun isJinhakKnownStructuredPageType(pageType: String): Boolean = pageType in setOf(
        "jinhak-early-storage",
        "jinhak-prediction-report",
        "jinhak-mock-support-report",
        "jinhak-actual-admit-report",
        "jinhak-score-calc-report",
        "jinhak-sat-minimum",
        "jinhak-student-basic",
        "jinhak-university-search",
        "jinhak-admission-knowledge",
        "jinhak-recommended-university",
        "jinhak-university-admission-info"
    )

    private fun collectCurrentPage(autoUnified: Boolean = false) {
        status.text = if (provider == ProviderId.JINHAK) "진학사 현재 화면의 카드·표·세부 설명·예측지표를 전체 분석 중…" else "현재 페이지의 표·헤더·카드·입시정보를 구조적으로 수집 중…"
        collectSnapshot { snapshot ->
            if (snapshot == null) return@collectSnapshot
            val pageType = snapshot.optString("providerPageType")
            val knownStructuredType = provider != ProviderId.JINHAK || isJinhakKnownStructuredPageType(pageType)
            if (provider == ProviderId.JINHAK && autoUnified && !knownStructuredType) {
                recordRuntimeEvent("jinhak-unclassified-observation-preserved", JSONObject()
                    .put("pageType", pageType.take(80))
                    .put("safePath", runtimeSafePath(snapshot.optString("url"))))
            }
            val records = normalizeSnapshot(snapshot)
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
            var localStats = JSONObject()
            var stored = 0
            if (provider == ProviderId.JINHAK) {
                val runId = localStore.beginOrResume(provider.wireName, VERSION)
                localRunId = runId
                stored = localStore.storeRecords(runId, provider.wireName, records)
                localStore.markDocument(runId, canonicalizeBatchUrl(snapshot.optString("url")), "completed")
                localStats = localStore.stats(runId)
                lastJinhakDigest = buildJinhakDigest(snapshot, records, runId, collectedAt)
                val safeRouteKey = runtimeSafePath(snapshot.optString("url"))
                val explicitContext = ObservationEvidence.explicitContextFromDigest(lastJinhakDigest)
                val sessionObj = snapshot.optJSONObject("session") ?: JSONObject()
                val authStateClass = when {
                    sessionObj.optBoolean("needsLogin", false) -> "auth-required"
                    sessionObj.optBoolean("authenticated", false) -> "authenticated"
                    else -> "unknown"
                }
                val observationId = localStore.storeObservationEvidence(
                    sessionId = unifiedSessionId,
                    runId = runId,
                    provider = ProviderId.JINHAK.wireName,
                    safeRouteKey = safeRouteKey,
                    pageTypeGuess = pageType,
                    pageTypeConfidence = if (knownStructuredType) 0.95 else 0.45,
                    authStateClass = authStateClass,
                    explicitContext = explicitContext,
                    evidence = lastJinhakDigest,
                    captureVersion = VERSION
                )
                lastJinhakDigest.put("observationId", observationId)
                probeJinhakOfficialCapabilities(unifiedSessionId, pageType, safeRouteKey)
                if (unifiedRunning && unifiedPhase == "jinhak") {
                    unifiedSessionId?.let { sessionId ->
                        localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId)
                        val localPageKey = RecordUtils.sha256(canonicalizeBatchUrl(snapshot.optString("url")))
                        localStore.storeUnifiedAnalysisCapture(
                            sessionId = sessionId,
                            provider = ProviderId.JINHAK.wireName,
                            pageKey = localPageKey,
                            pageType = snapshot.optString("providerPageType"),
                            payload = lastJinhakDigest
                        )
                        localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)
                    persistLiveJinhakDiagnostics("capture")
                        unifiedJinhakCapturedPages.add(localPageKey)
                        // The bundle is already privacy-sanitized by buildJinhakDigest.
                        // One explicit unified-session start authorizes these user-viewed page captures.
                        cloudOffload.sendDiagnostic(
                            "jinhak", VERSION,
                            JSONObject(lastJinhakDigest.toString())
                                .put("trigger", "unified-user-viewed-page")
                                .put("unifiedSessionId", sessionId)
                        ) { }
                    }
                }
            }
            val out = JSONObject()
                .put("collectorVersion", VERSION)
                .put("provider", provider.wireName)
                .put("collectedAt", collectedAt)
                .put("mode", if (provider == ProviderId.JINHAK) "jinhak-analysis" else "single-page")
                .put("session", snapshot.optJSONObject("session") ?: JSONObject())
                .put("localStoredThisCapture", stored)
                .put("localStats", localStats)
                .put("records", records)
                .put("snapshots", JSONArray().put(stripNavigationLinksForExport(snapshot)))
                .put("resourceLinks", snapshot.optJSONArray("resourceLinks") ?: JSONArray())
            lastJson = out.toString(2)
            showPreview(lastJson)
            status.text = if (provider == ProviderId.JINHAK) {
                "진학사 전체 분석 준비 완료: 이번 ${records.length()}개 / 로컬 누적 ${localStats.optInt("records", records.length())}개 / 필요 시 '진학사 전체 분석 전송'"
            } else {
                "현재 페이지 수집 완료: 구조화 레코드 ${records.length()}개"
            }
        }
    }

    private fun probeJinhakOfficialCapabilities(sessionId: String?, pageType: String, safeRouteKey: String) {
        if (provider != ProviderId.JINHAK || !::webView.isInitialized) return
        webView.evaluateJavascript(JinhakCapabilityProbe.javascript()) { encoded ->
            val raw = runCatching { decodeJsString(encoded) }.getOrNull() ?: return@evaluateJavascript
            val snapshot = runCatching { JinhakCapabilityProbe.parse(raw) }.getOrNull() ?: return@evaluateJavascript
            if (snapshot.capabilities.isEmpty()) return@evaluateJavascript

            val grouped = snapshot.capabilities.groupBy { capability ->
                when (capability.kind) {
                    "structured-export" -> ProviderCapability.AUTHORIZED_EXPORT_IMPORT.name
                    "report-output", "download", "email-report" -> ProviderCapability.AUTHORIZED_REPORT_IMPORT.name
                    else -> "VISIBLE_OFFICIAL_OUTPUT"
                }
            }
            for ((capability, items) in grouped) {
                val evidence = JSONArray()
                items.forEach { item ->
                    evidence.put(JSONObject()
                        .put("kind", item.kind)
                        .put("label", item.label)
                        .put("evidenceClass", item.evidenceClass))
                }
                localStore.storeProviderCapabilityEvidence(
                    sessionId = sessionId,
                    provider = ProviderId.JINHAK.wireName,
                    capability = capability,
                    status = "candidate-visible-official-ui",
                    safeRouteKey = safeRouteKey,
                    evidence = JSONObject()
                        .put("pageType", pageType)
                        .put("controls", evidence)
                )
            }
            recordRuntimeEvent("jinhak-official-output-capability-observed", JSONObject()
                .put("pageType", pageType.take(80))
                .put("safePath", safeRouteKey.take(300))
                .put("controls", snapshot.capabilities.size)
                .put("structuredExportSignal", snapshot.hasStructuredExportSignal)
                .put("reportOutputSignal", snapshot.hasReportOutputSignal))
        }
    }

    private fun sanitizeJinhakAnalysisText(value: String, maxLen: Int): String {
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

        val highValuePage = snapshot.optString("providerPageType") in setOf(
            "jinhak-early-storage", "jinhak-prediction-report", "jinhak-mock-support-report",
            "jinhak-actual-admit-report", "jinhak-score-calc-report", "jinhak-sat-minimum"
        )
        val textBudgetLimit = if (batchRunning && provider == ProviderId.JINHAK && !highValuePage) 32_000 else 180_000
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
            .put("analysisRelevance", if (isJinhakKnownStructuredPageType(snapshot.optString("providerPageType"))) "known-structured-type" else "unclassified-potential-value")
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

    private fun sendLatestJinhakAnalysisDigest() {
        if (lastJinhakDigest.length() == 0) {
            Toast.makeText(this, "먼저 진학사에서 분석할 화면을 열고 '현재 진학사 화면 전체 분석·누적'을 눌러주세요.", Toast.LENGTH_LONG).show()
            return
        }
        status.text = "진학사 전체 분석 번들 전송 중… DOM·URL·쿠키·로그인 자격정보·폼 값은 보내지 않습니다."
        cloudOffload.sendDiagnostic("jinhak", VERSION, JSONObject(lastJinhakDigest.toString()).put("trigger", "manual-analysis")) { result ->
            runOnUiThread {
                if (result.isSuccess) {
                    status.text = "진학사 전체 분석 전송 완료: ${result.getOrNull()?.take(8) ?: "unknown"}…"
                    Toast.makeText(this, "진학사 전체 분석 전송 완료", Toast.LENGTH_SHORT).show()
                } else {
                    status.text = "진학사 전체 분석 전송 실패: ${result.exceptionOrNull()?.message ?: "unknown"}"
                    Toast.makeText(this, "진학사 전체 분석 전송 실패", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun collectSnapshotForBatch() {
        if (!batchRunning || batchPausedForLogin || batchCollecting) return
        batchCollecting = true
        collectSnapshot(webView) { snapshot ->
            batchCollecting = false
            if (!batchRunning || snapshot == null) return@collectSnapshot
            stabilizeBatchSnapshotContext(snapshot)

            val activeAction = activeBatchPageAction
            val collectionPage = activeAction?.page ?: 1
            snapshot.put("collectionPage", collectionPage)
            if (activeAction != null) {
                snapshot.put("collectionPagination", JSONObject()
                    .put("page", activeAction.page)
                    .put("totalPages", activeAction.totalPages)
                    .put("pageSize", activeAction.pageSize)
                    .put("totalItems", activeAction.totalItems)
                    .put("familyKey", activeAction.familyKey)
                    .put("requestedYear", activeAction.requestedYear ?: JSONObject.NULL)
                    .put("retry", activeAction.retry))
            }

            val navigationKey = snapshot.optString("navigationKey")
            if (navigationKey.isNotBlank()) batchVisited.add(navigationKey)
            batchPageCount += 1

            val pageState = snapshot.optJSONObject("pageState") ?: JSONObject()
            if (pageState.optBoolean("isError", false)) {
                val errorType = pageState.optString("errorType", "page-error")
                if (activeAction != null && activeAction.retry < MAX_PAGE_RETRIES) {
                    activeBatchPageAction = null
                    schedulePageActionRetry(activeAction, errorType)
                    return@collectSnapshot
                }

                if (activeAction != null) {
                    batchPageActionFailed.add(pageActionKey(activeAction))
                    activeBatchPageAction = null
                }
                val error = JSONObject()
                    .put("url", snapshot.optString("url"))
                    .put("type", errorType)
                    .put("title", snapshot.optString("title"))
                if (activeAction != null) {
                    error.put("page", activeAction.page)
                        .put("totalPages", activeAction.totalPages)
                        .put("familyKey", activeAction.familyKey)
                        .put("requestedYear", activeAction.requestedYear ?: JSONObject.NULL)
                        .put("retryCount", activeAction.retry)
                }
                batchErrors.put(error)
                localRunId?.let { runId ->
                    val key = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                    localStore.markDocument(runId, key, "error", activeAction?.retry ?: 0, errorType)
                    if (activeAction != null) {
                        localStore.markPage(
                            runId, activeAction.familyKey, activeAction.requestedYear,
                            activeAction.page, activeAction.totalPages, "error", activeAction.retry, errorType
                        )
                    }
                }
                status.text = if (activeAction != null) {
                    "목록 ${activeAction.page}/${activeAction.totalPages}쪽 최종 실패 / 다음 페이지 계속"
                } else {
                    "오류 페이지 건너뜀: $errorType / 계속 탐색 중"
                }
                handler.postDelayed({ loadNextBatchPage() }, 300)
                return@collectSnapshot
            }

            val session = snapshot.optJSONObject("session") ?: JSONObject()
            if (session.optBoolean("needsLogin", false)) {
                if (activeAction != null) {
                    pendingBatchPageAction = activeAction
                    activeBatchPageAction = null
                }
                recoverCollectorSessionOrPause()
                return@collectSnapshot
            }
            batchSessionSyncRetries = 0

            if (provider == ProviderId.JINHAK) {
                val gate = snapshot.optJSONObject("interactionGate") ?: JSONObject()
                if (gate.optBoolean("requiresUserAction", false)) {
                    pauseJinhakForConsent(snapshot)
                    return@collectSnapshot
                }
                if (jinhakConsentResumePending) {
                    jinhakConsentResumePending = false
                    jinhakConsentGatesResolved += 1
                    unifiedSessionId?.let { sessionId ->
                        localStore.recordSyncState(
                            sessionId,
                            UnifiedSyncState.JINHAK_USER_SESSION_MISSION.name,
                            ProviderId.JINHAK.wireName,
                            JSONObject().put("resumedAfterUserConsentGate", true),
                            false
                        )
                    }
                    recordRuntimeEvent("jinhak-user-consent-resolved", JSONObject()
                        .put("safePath", runtimeSafePath(snapshot.optString("url"))))
                }
                val pageTypeForBridge = snapshot.optString("providerPageType")
                val effectiveMissionJson = JinhakReportContextBridge.resolve(
                    pageTypeForBridge,
                    jinhakMissionContext,
                    jinhakReportBridgeContext
                )
                effectiveMissionJson?.let { missionJson ->
                    snapshot.put("missionApplicationContext", missionJson)
                    if (JinhakReportContextBridge.isReportPageType(pageTypeForBridge) && missionJson.has("reportBridgeActionToken")) {
                        jinhakReportBridgeApplied += 1
                        val bridgeMission = JinhakApplicationMission.fromJson(missionJson)
                        val lane = JinhakApplicationMission.laneForPageType(pageTypeForBridge)
                        val confirmationKey = RecordUtils.sha256(listOf(
                            bridgeMission?.identityKey ?: "",
                            lane,
                            missionJson.optString("reportBridgeActionToken"),
                            runtimeSafePath(snapshot.optString("url"))
                        ).joinToString("|"))
                        if (bridgeMission?.identityKey != null && lane != "reference" && jinhakReportConfirmedKeys.add(confirmationKey)) {
                            jinhakReportBridgeConfirmed += 1
                            val ledgerConfirmed = jinhakMissionTargetLedger.markConfirmed(
                                jinhakActiveMissionTargetId,
                                bridgeMission.identityKey,
                                lane
                            )
                            if (ledgerConfirmed) {
                                noteJinhakMeaningfulProgress("mission-target-confirmed", forceDiagnostics = true)
                                recordRuntimeEvent("jinhak-mission-target-confirmed", JSONObject()
                                    .put("applicationIdentityHash", bridgeMission.identityKey.take(24))
                                    .put("lane", lane)
                                    .put("safePath", runtimeSafePath(snapshot.optString("url"))))
                                jinhakActiveMissionTargetId = null
                            }
                        }
                    }
                }
            }
            val plan = if (activeAction == null) currentAdapter().paginationPlan(snapshot) else null
            val duplicateOfYear = plan?.let { duplicateYearViewOf(it) }
            if (duplicateOfYear != null && plan != null) {
                val copy = stripNavigationLinksForExport(snapshot)
                copy.put("duplicateYearView", JSONObject()
                    .put("skippedYear", plan.requestedYear ?: JSONObject.NULL)
                    .put("duplicateOfYear", duplicateOfYear)
                    .put("familyKey", plan.familyKey)
                    .put("totalItems", plan.totalItems))
                batchSnapshots.put(copy)
                batchDuplicateYearViews.put(JSONObject()
                    .put("familyKey", plan.familyKey)
                    .put("skippedYear", plan.requestedYear ?: JSONObject.NULL)
                    .put("duplicateOfYear", duplicateOfYear)
                    .put("totalItems", plan.totalItems))
                status.text = "중복 연도 목록 생략: ${plan.requestedYear} → $duplicateOfYear (${plan.totalItems}건 동일)"
                handler.postDelayed({ loadNextBatchPage() }, 250)
                return@collectSnapshot
            }

            if (plan != null) registerListFingerprint(plan)

            val pageRecords = normalizeSnapshot(snapshot)
            if (provider == ProviderId.JINHAK) {
                jinhakConsecutiveStalls = 0
                val pageTypeNow = snapshot.optString("providerPageType")
                if (pageTypeNow == "jinhak-early-storage" && jinhakFirstPopulatedStorageAtMs == 0L) {
                    var populated = false
                    for (ri in 0 until pageRecords.length()) {
                        val r = pageRecords.optJSONObject(ri) ?: continue
                        if (r.optString("recordType") == "jinhak-saved-application-prediction" &&
                            r.optString("applicationIdentityKey").isNotBlank() && r.optString("applicationIdentityKey") != "null") {
                            populated = true
                            break
                        }
                    }
                    if (populated) jinhakFirstPopulatedStorageAtMs = System.currentTimeMillis()
                }
                val discoveredAnchors = snapshot.optJSONArray("missionAnchorDiscovery") ?: JSONArray()
                for (ai in 0 until discoveredAnchors.length()) {
                    val a = discoveredAnchors.optJSONObject(ai) ?: continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorDiscoveredKeys.add(key)
                }
                val promotedAnchors = snapshot.optJSONArray("missionAgentActions") ?: JSONArray()
                for (ai in 0 until promotedAnchors.length()) {
                    val a = promotedAnchors.optJSONObject(ai) ?: continue
                    val key = RecordUtils.sha256(listOf(a.optString("label"), a.optString("contextText")).joinToString("|"))
                    jinhakMissionAnchorPromotedKeys.add(key)
                    val bindingSource = a.optString("applicationBindingSource", "unknown").ifBlank { "unknown" }.take(40)
                    val sourceKey = RecordUtils.sha256("$key|$bindingSource")
                    if (jinhakMissionBindingSourceKeys.add(sourceKey)) {
                        jinhakMissionBindingSourceCounts[bindingSource] = (jinhakMissionBindingSourceCounts[bindingSource] ?: 0) + 1
                    }
                    val structuredUniversity = a.optString("applicationUniversity").trim()
                    val structuredDepartment = a.optString("applicationDepartment").trim()
                    if (structuredUniversity.isNotBlank() && structuredDepartment.isNotBlank()) {
                        jinhakMissionAnchorStructuredKeys.add(key)
                    }
                }
                val rawMissionCandidates = JinhakAgentNavigator.candidates(snapshot)
                val normalizedMissionSeeds = jinhakMissionContextsFromNormalizedRecords(pageRecords)
                normalizedMissionSeeds.forEach { context ->
                    val identity = context.identityKey ?: return@forEach
                    jinhakNormalizedMissionSeedContexts[identity] = context
                    jinhakNormalizedIdentitySeedKeys.add(identity)
                    if (pageTypeNow == "jinhak-early-storage") {
                        jinhakMissionCoverage.getOrPut(identity) { linkedSetOf() }.add("saved-application")
                    }
                }
                val parsedMissionCandidates = bindJinhakCandidatesFromNormalizedRecords(
                    rawMissionCandidates,
                    jinhakNormalizedMissionSeedContexts.values.toList()
                )
                val ledgerOrigin = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                val originInferred = parsedMissionCandidates.count { candidate ->
                    JinhakMissionLaneSequencer.laneForLabel(candidate.label, candidate.kind) == "reference" &&
                        JinhakMissionLaneSequencer.laneForCandidateAtOrigin(candidate.label, candidate.kind, ledgerOrigin, pageTypeNow) != "reference" &&
                        candidate.applicationContext?.identityKey != null
                }
                if (originInferred > 0) jinhakOriginInferredMissionTargets += originInferred
                val ledgerAdded = if (pageTypeNow == "jinhak-recommended-university") {
                    recordRuntimeEvent("jinhak-recommendation-ledger-suppressed", JSONObject()
                        .put("safePath", runtimeSafePath(ledgerOrigin))
                        .put("candidateCount", parsedMissionCandidates.size))
                    0
                } else {
                    jinhakMissionTargetLedger.capture(ledgerOrigin, parsedMissionCandidates, pageTypeNow)
                }
                if (ledgerAdded > 0) {
                    noteJinhakMeaningfulProgress("mission-target-captured", forceDiagnostics = true)
                    recordRuntimeEvent("jinhak-mission-targets-captured", JSONObject()
                        .put("added", ledgerAdded)
                        .put("pending", jinhakMissionTargetLedger.pendingCount())
                        .put("safePath", runtimeSafePath(ledgerOrigin)))
                }
                parsedMissionCandidates.filter { it.promotedMissionAction && it.applicationContext?.identityKey != null }.forEach { candidate ->
                    val key = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
                    jinhakMissionAnchorParsedKeys.add(key)
                }
                val mission = JinhakApplicationMission.fromJson(snapshot.optJSONObject("missionApplicationContext")) ?: jinhakMissionContext
                val missionKey = mission?.identityKey
                if (missionKey != null) {
                    val lane = JinhakApplicationMission.laneForPageType(snapshot.optString("providerPageType"))
                    if (lane != "reference") jinhakMissionCoverage.getOrPut(missionKey) { linkedSetOf() }.add(lane)
                }
                // Saved-application records themselves seed the coverage ledger even before a report is opened.
                for (ri in 0 until pageRecords.length()) {
                    val r = pageRecords.optJSONObject(ri) ?: continue
                    val key = r.optString("applicationIdentityKey").takeIf { it.isNotBlank() && it != "null" } ?: continue
                    if (r.optString("recordType") == "jinhak-saved-application-prediction") {
                        jinhakMissionCoverage.getOrPut(key) { linkedSetOf() }.add("saved-application")
                    }
                }
                jinhakUnboundSavedApplicationObservations += (0 until pageRecords.length()).count { idx ->
                    pageRecords.optJSONObject(idx)?.optString("recordType") == "jinhak-application-unbound-observation"
                }
            }
            var jinhakExpansionStateKey: String? = null
            var jinhakExpandOutgoingLinks = true
            var jinhakAllowAgentAction = true
            if (provider == ProviderId.JINHAK && unifiedRunning && unifiedPhase == "jinhak") {
                val sessionId = unifiedSessionId
                val runId = localRunId ?: localStore.beginOrResume(ProviderId.JINHAK.wireName, VERSION).also { localRunId = it }
                if (sessionId != null) {
                    localStore.attachUnifiedProviderRun(sessionId, ProviderId.JINHAK.wireName, runId)
                    val capturedAt = Instant.now().toString()
                    val digest = buildJinhakDigest(snapshot, pageRecords, runId, capturedAt)
                    lastJinhakDigest = digest
                    val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                    val pageKey = RecordUtils.sha256(navKey)
                    val safeRoute = runtimeSafePath(snapshot.optString("url"))
                    val explicitContext = ObservationEvidence.explicitContextFromDigest(digest)
                    val expansionIdentity = ObservationEvidence.identity(
                        ProviderId.JINHAK.wireName, safeRoute, explicitContext, digest
                    )
                    jinhakExpansionStateKey = expansionIdentity.observationId
                    jinhakExpandOutgoingLinks = jinhakExpandedNavigationStates.add(expansionIdentity.observationId)
                    val routeCaptureCount = (jinhakReferenceRouteCaptureCounts[safeRoute] ?: 0) + 1
                    jinhakReferenceRouteCaptureCounts[safeRoute] = routeCaptureCount
                    val lowValueReference = isJinhakLowValueReferencePageType(snapshot.optString("providerPageType"))
                    if (lowValueReference) {
                        jinhakAllowAgentAction = false
                    }
                    if (lowValueReference && routeCaptureCount > MAX_JINHAK_REFERENCE_ROUTE_CAPTURES &&
                        jinhakMissionTargetLedger.outstandingCount() == 0 && jinhakMissionContext?.identityKey == null) {
                        jinhakExpandOutgoingLinks = false
                        jinhakAllowAgentAction = false
                        jinhakReferenceRepeatSkips += 1
                        recordRuntimeEvent("jinhak-reference-route-repeat-skip", JSONObject()
                            .put("safePath", safeRoute)
                            .put("pageType", snapshot.optString("providerPageType"))
                            .put("captureCount", routeCaptureCount))
                    }
                    if (jinhakExpandOutgoingLinks) {
                        jinhakUniqueNavigationStates += 1
                        noteJinhakMeaningfulProgress("unique-navigation-state")
                    } else {
                        jinhakRepeatedNavigationStateSkips += 1
                        recordRuntimeEvent("jinhak-repeat-state-expansion-skip", JSONObject()
                            .put("safePath", safeRoute)
                            .put("pageType", snapshot.optString("providerPageType")))
                    }
                    localStore.storeUnifiedAnalysisCapture(
                        sessionId = sessionId,
                        provider = ProviderId.JINHAK.wireName,
                        pageKey = pageKey,
                        pageType = snapshot.optString("providerPageType"),
                        payload = digest
                    )
                    val batchPageType = snapshot.optString("providerPageType")
                    val batchSession = snapshot.optJSONObject("session") ?: JSONObject()
                    val batchAuthState = when {
                        batchSession.optBoolean("needsLogin", false) -> "auth-required"
                        batchSession.optBoolean("authenticated", false) -> "authenticated"
                        else -> "unknown"
                    }
                    localStore.storeObservationEvidence(
                        sessionId = sessionId,
                        runId = runId,
                        provider = ProviderId.JINHAK.wireName,
                        safeRouteKey = runtimeSafePath(snapshot.optString("url")),
                        pageTypeGuess = batchPageType,
                        pageTypeConfidence = if (batchPageType == "jinhak-other") 0.25 else 0.85,
                        authStateClass = batchAuthState,
                        explicitContext = ObservationEvidence.explicitContextFromDigest(digest),
                        evidence = digest,
                        captureVersion = VERSION
                    )
                    localStore.updateUnifiedSession(sessionId, "jinhak", "running", null)
                }
            }
            if (activeAction != null && LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
                val duplicateOwner = persistedDuplicatePageOwner(activeAction, pageRecords)
                if (duplicateOwner != null && duplicateOwner != activeAction.page) {
                    activeBatchPageAction = null
                    status.text = "페이지 ${activeAction.page} 내용이 기존 ${duplicateOwner}쪽과 동일함: stale 판정 / 최대 ${MAX_PAGE_RETRIES}회만 재시도"
                    schedulePageActionRetry(activeAction, "stale-pagination-content")
                    return@collectSnapshot
                }
            }

            batchSnapshots.put(snapshotForLocalExport(snapshot))
            tableFingerprint(snapshot)?.let { batchLastTableSignatures[canonicalizeBatchUrl(snapshot.optString("url"))] = it }
            // SQLite is authoritative for long crawls. Jinhak pages can be substantially larger
            // than Adiga list rows, so never duplicate their normalized records in RAM.
            val keepRecordsInMemory = !(LOCAL_FIRST_BETA && (
                provider == ProviderId.JINHAK || snapshot.optString("providerPageType") == "adiga-university-detail"
            ))
            if (keepRecordsInMemory) RecordUtils.appendUniqueRecords(batchRecords, pageRecords)
            localRunId?.let { runId ->
                batchLocalRecordsPersisted += localStore.storeRecords(runId, provider.wireName, pageRecords)
                val navKey = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
                localStore.markDocument(runId, navKey, "completed")
                cloudFrontierTaskIds.remove(navKey)?.let { taskId ->
                    cloudOffload.completeFrontier(taskId, "completed", null) { ok ->
                        if (ok) cloudFrontierCompleted += 1 else cloudFrontierCompletionFailed += 1
                    }
                }
                when {
                    activeAction != null -> localStore.markPage(
                        runId, activeAction.familyKey, activeAction.requestedYear,
                        activeAction.page, activeAction.totalPages, "completed", activeAction.retry
                    )
                    plan != null -> localStore.markPage(
                        runId, plan.familyKey, plan.requestedYear,
                        1, plan.totalPages, "completed", 0
                    )
                }
            }
            if (activeAction != null) rememberAcceptedPageSignature(activeAction, pageRecords)
            RecordUtils.appendUniqueResources(batchResources, snapshot.optJSONArray("resourceLinks") ?: JSONArray())

            // v0.4.0 only followed links from page 1 because pagination actions skipped
            // discovery. University-list pagination is safe and bounded (220 universities),
            // so collect detail URLs from every university-list page as well.
            val pageType = snapshot.optString("providerPageType")
            if (activeAction == null || pageType == "adiga-university-list") {
                if (provider != ProviderId.JINHAK || jinhakExpandOutgoingLinks) {
                    enqueueDiscoveredLinks(snapshot.optJSONArray("navigationLinks") ?: JSONArray())
                }
            }
            if (activeAction == null) {
                if (plan != null) enqueueCalculatedPageActions(snapshot, plan)
            } else {
                batchPageActionVisited.add(pageActionKey(activeAction))
                activeBatchPageAction = null
            }

            if (provider == ProviderId.JINHAK && activeAction == null && jinhakAllowAgentAction && maybeExecuteJinhakAgentAction(snapshot, jinhakExpansionStateKey)) {
                return@collectSnapshot
            }
            if (provider == ProviderId.JINHAK && activeAction == null && maybeReturnToJinhakMissionOrigin(snapshot)) {
                return@collectSnapshot
            }

            status.text = if (activeAction != null) {
                "목록 ${activeAction.page}/${activeAction.totalPages}쪽 완료 / 시도 $batchPageCount / 오류 ${batchErrors.length()} / 레코드 ${batchRecords.length()}"
            } else {
                "일괄 수집: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 오류 ${batchErrors.length()} / URL대기 ${batchQueue.size} / 페이지대기 ${batchPageActions.size} / 레코드 ${batchRecords.length()}"
            }

            if (batchPageCount >= MAX_BATCH_PAGES) {
                finishBatch("page-limit")
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 350)
            }
        }
    }

    private fun snapshotForLocalExport(snapshot: JSONObject): JSONObject {
        val lightweight = LOCAL_FIRST_BETA && (
            provider == ProviderId.JINHAK ||
                (provider == ProviderId.ADIGA && snapshot.optString("providerPageType") == "adiga-university-detail")
        )
        if (!lightweight) return stripNavigationLinksForExport(snapshot)
        // Full Jinhak analysis is already persisted in unified_analysis_captures and normalized
        // records are in SQLite. Keep only a tiny batch diagnostic copy in RAM.
        return JSONObject()
            .put("title", snapshot.optString("title"))
            .put("url", snapshot.optString("url"))
            .put("collectedAt", snapshot.optString("collectedAt"))
            .put("providerPageType", snapshot.optString("providerPageType"))
            .put("collectionPage", snapshot.optInt("collectionPage", 1))
            .put("pageState", snapshot.optJSONObject("pageState") ?: JSONObject())
            .put("listMeta", snapshot.optJSONObject("listMeta") ?: JSONObject())
            .put("discovery", snapshot.optJSONObject("discovery") ?: JSONObject())
    }

    private fun pageAuditCacheKey(familyKey: String, requestedYear: Int?): String =
        "$familyKey|year=${requestedYear ?: "unknown"}"

    private fun stableRecordMaterial(obj: JSONObject): String = listOf(
        obj.optString("recordType"),
        obj.optString("university"),
        obj.optString("department"),
        obj.optString("admission"),
        obj.optString("rawEvidence")
    ).joinToString("|")

    private fun normalizedPageSignature(records: JSONArray): String? {
        if (records.length() == 0) return null
        val parts = mutableListOf<String>()
        for (i in 0 until records.length()) {
            records.optJSONObject(i)?.let { parts += stableRecordMaterial(it) }
        }
        if (parts.isEmpty()) return null
        return RecordUtils.sha256(parts.sorted().joinToString("\n"))
    }

    private fun persistedPageSignatureOwners(action: BatchPageAction): MutableMap<String, Int> {
        val runId = localRunId ?: return linkedMapOf()
        val cacheKey = pageAuditCacheKey(action.familyKey, action.requestedYear)
        batchPersistedPageSignatureOwners[cacheKey]?.let { return it }

        val familyPath = action.familyKey.substringBefore('?')
        val grouped = linkedMapOf<Int, MutableList<String>>()
        val stored = localStore.loadRecords(runId)
        for (i in 0 until stored.length()) {
            val obj = stored.optJSONObject(i) ?: continue
            val source = obj.optString("sourcePage")
            if (!source.contains(familyPath)) continue
            if (action.requestedYear != null) {
                if (obj.isNull("year") || obj.optInt("year", -1) != action.requestedYear) continue
            }
            val page = obj.optInt("sourcePageNumber", -1)
            if (page < 1) continue
            grouped.getOrPut(page) { mutableListOf() }.add(stableRecordMaterial(obj))
        }
        val owners = linkedMapOf<String, Int>()
        for ((page, parts) in grouped) {
            if (parts.isNotEmpty()) owners[RecordUtils.sha256(parts.sorted().joinToString("\n"))] = page
        }
        batchPersistedPageSignatureOwners[cacheKey] = owners
        return owners
    }

    private fun persistedPagesWithRecords(runId: String, familyKey: String, requestedYear: Int?): Set<Int> {
        val familyPath = familyKey.substringBefore('?')
        val pages = linkedSetOf<Int>()
        val stored = localStore.loadRecords(runId)
        for (i in 0 until stored.length()) {
            val obj = stored.optJSONObject(i) ?: continue
            if (!obj.optString("sourcePage").contains(familyPath)) continue
            if (requestedYear != null) {
                if (obj.isNull("year") || obj.optInt("year", -1) != requestedYear) continue
            }
            val page = obj.optInt("sourcePageNumber", -1)
            if (page >= 1) pages.add(page)
        }
        return pages
    }

    private fun persistedDuplicatePageOwner(action: BatchPageAction, records: JSONArray): Int? {
        val signature = normalizedPageSignature(records) ?: return null
        return persistedPageSignatureOwners(action)[signature]
    }

    private fun rememberAcceptedPageSignature(action: BatchPageAction, records: JSONArray) {
        val signature = normalizedPageSignature(records) ?: return
        persistedPageSignatureOwners(action)[signature] = action.page
    }


    private fun pauseJinhakForConsent(snapshot: JSONObject) {
        if (provider != ProviderId.JINHAK || !batchRunning) return
        if (!jinhakConsentGatePending) jinhakConsentGatesEncountered += 1
        jinhakConsentGatePending = true
        jinhakConsentResumePending = false
        batchPausedForLogin = true
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        disarmBatchNavigationWatchdog()
        hideBatchCover()
        sessionState.text = "○ 진학사 사용자 동의 선택 필요"
        status.text = "진학사에서 학생부 AI진단 점수 활용 동의를 직접 선택하고 확인한 뒤 '로그인/동의 후 계속'을 누르세요. Collector는 동의/미동의를 자동 선택하지 않습니다."
        unifiedSessionId?.let { sessionId ->
            localStore.recordSyncState(
                sessionId,
                UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED.name,
                ProviderId.JINHAK.wireName,
                JSONObject()
                    .put("gateType", snapshot.optJSONObject("interactionGate")?.optString("type") ?: "provider-consent")
                    .put("safePath", runtimeSafePath(snapshot.optString("url")))
                    .put("missionBound", jinhakMissionContext?.identityKey != null),
                true
            )
        }
        recordRuntimeEvent("jinhak-user-consent-required", JSONObject()
            .put("safePath", runtimeSafePath(snapshot.optString("url")))
            .put("missionBound", jinhakMissionContext?.identityKey != null))
    }

    private fun maybeExecuteJinhakAgentAction(snapshot: JSONObject, expansionStateKey: String?): Boolean {
        if (!batchRunning || batchPausedForLogin || provider != ProviderId.JINHAK) return false
        if (jinhakAgentActionInFlight) return false
        val route = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        fun actionKeyFor(action: JinhakAgentNavigator.Candidate): String = RecordUtils.sha256(
            "${expansionStateKey ?: runtimeSafePath(route)}|${JinhakAgentNavigator.key(route, action)}"
        )

        val liveCandidates = JinhakAgentNavigator.candidates(snapshot)
        val candidates = liveCandidates.filterNot { jinhakAgentActionSeen.contains(actionKeyFor(it)) }
        val currentMissionKey = jinhakMissionContext?.identityKey
        val covered = currentMissionKey?.let { jinhakMissionCoverage[it]?.toSet() }.orEmpty()
        val atMissionOrigin = currentMissionKey != null && jinhakMissionOriginRoute.isNotBlank() &&
            canonicalizeBatchUrl(route) == canonicalizeBatchUrl(jinhakMissionOriginRoute)

        jinhakMissionTargetLedger.reconcileCoveredLanes(currentMissionKey, covered)
        var ledgerTarget = when {
            atMissionOrigin && currentMissionKey != null ->
                jinhakMissionTargetLedger.nextPendingAtOrigin(route, currentMissionKey, covered)
            currentMissionKey == null ->
                jinhakMissionTargetLedger.nextPendingAtOrigin(route, null, emptySet())
            else -> null
        }
        var exhaustedCurrentMission = false

        val selection = when {
            ledgerTarget != null -> JinhakMissionLaneSequencer.Selection(
                candidate = ledgerTarget!!.candidate(),
                missionExhaustedAtOrigin = false,
                requestedLane = ledgerTarget!!.lane
            )
            atMissionOrigin && currentMissionKey != null && jinhakMissionTargetLedger.hasMission(currentMissionKey) -> {
                exhaustedCurrentMission = true
                ledgerTarget = jinhakMissionTargetLedger.nextPendingAtOrigin(route, null, emptySet())
                if (ledgerTarget != null) {
                    JinhakMissionLaneSequencer.Selection(
                        candidate = ledgerTarget!!.candidate(),
                        missionExhaustedAtOrigin = true,
                        requestedLane = ledgerTarget!!.lane
                    )
                } else {
                    // All captured application targets at this origin are resolved. Only now may
                    // generic read-only navigation resume; application-bound live anchors are not
                    // re-selected outside the persistent ledger.
                    val genericPool = candidates.filter { it.applicationContext?.identityKey == null }
                    val generic = JinhakMissionLaneSequencer.choose(genericPool, null, emptySet(), false)
                    JinhakMissionLaneSequencer.Selection(generic.candidate, true, generic.requestedLane)
                }
            }
            currentMissionKey == null && jinhakMissionTargetLedger.hasActionablePending() ->
                JinhakMissionLaneSequencer.Selection(null, false, "reference")
            else -> JinhakMissionLaneSequencer.choose(candidates, currentMissionKey, covered, atMissionOrigin)
        }

        if ((selection.missionExhaustedAtOrigin || exhaustedCurrentMission) && currentMissionKey != null) {
            recordRuntimeEvent("jinhak-application-mission-lanes-exhausted", JSONObject()
                .put("applicationIdentityHash", currentMissionKey.take(24))
                .put("coverageLanes", covered.size)
                .put("ledgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("safePath", runtimeSafePath(route)))
            jinhakMissionContext = null
            jinhakReportBridgeContext = null
            jinhakMissionOriginRoute = ""
            jinhakMissionNeedsReturn = false
        }

        val candidate = selection.candidate ?: return false
        val ledgerTargetIdForAction = ledgerTarget?.targetId
        val missionBudgetedAction = ledgerTargetIdForAction != null || candidate.applicationContext?.identityKey != null
        if (missionBudgetedAction) {
            if (jinhakMissionActionsExecuted >= MAX_JINHAK_MISSION_ACTIONS) {
                jinhakMissionTargetLedger.failAllPending("mission-action-limit")
                recordRuntimeEvent("jinhak-mission-target-limit", JSONObject()
                    .put("missionLimit", MAX_JINHAK_MISSION_ACTIONS)
                    .put("missionExecuted", jinhakMissionActionsExecuted)
                    .put("genericExecuted", jinhakGenericActionsExecuted)
                    .put("ledger", jinhakMissionTargetLedger.summary()))
                return false
            }
        } else if (jinhakGenericActionsExecuted >= MAX_JINHAK_GENERIC_ACTIONS) {
            return false
        }
        jinhakActiveMissionTargetId = ledgerTargetIdForAction
        if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markAttempted(ledgerTargetIdForAction)

        if (candidate.kind == "mission-link-navigation") {
            val selectedKey = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
            jinhakMissionAnchorSelectedKeys.add(selectedKey)
        }
        val actionKey = actionKeyFor(candidate)
        jinhakAgentActionSeen.add(actionKey)

        val actionMission = candidate.applicationContext
        if (actionMission?.identityKey != null) {
            if (jinhakMissionContext?.identityKey != actionMission.identityKey) {
                jinhakMissionContext = actionMission
                jinhakMissionOriginRoute = ledgerTarget?.originRoute ?: route
            }
            jinhakMissionNeedsReturn = true
            jinhakApplicationBoundActions += 1
            jinhakMissionCoverage.getOrPut(actionMission.identityKey) { linkedSetOf() }.add("saved-application")
            recordRuntimeEvent("jinhak-application-mission-start", JSONObject()
                .put("applicationIdentityHash", actionMission.identityKey.take(24))
                .put("missionPriority", candidate.missionPriority)
                .put("requestedLane", selection.requestedLane)
                .put("ledgerTarget", ledgerTargetIdForAction != null)
                .put("safePath", runtimeSafePath(route)))
        } else if (jinhakMissionContext?.identityKey != null) {
            // A report tab may not repeat the application card. The already-bound mission stays active.
            jinhakMissionNeedsReturn = true
        }

        jinhakLastAgentActionLabel = candidate.label
        jinhakLastAgentActionOriginRoute = route
        jinhakLastAgentActionMissionContext = actionMission ?: jinhakMissionContext
        val bridgeMission = jinhakLastAgentActionMissionContext
        if (bridgeMission?.identityKey != null && JinhakReportContextBridge.isReportAction(candidate.label, candidate.kind)) {
            jinhakReportBridgeContext = JinhakReportContextBridge.arm(
                bridgeMission,
                runtimeSafePath(route),
                candidate.label,
                candidate.kind
            )
            jinhakReportBridgeArmed += 1
        }
        jinhakAgentActionInFlight = true
        jinhakAgentActionsExecuted += 1
        if (missionBudgetedAction) jinhakMissionActionsExecuted += 1 else jinhakGenericActionsExecuted += 1
        if (candidate.kind == "mission-link-navigation") jinhakMissionAnchorActionsAttempted += 1
        currentBatchTarget = route.ifBlank { currentBatchTarget }
        status.text = "진학사 미션 ${jinhakMissionActionsExecuted}/$MAX_JINHAK_MISSION_ACTIONS · 일반 ${jinhakGenericActionsExecuted}/$MAX_JINHAK_GENERIC_ACTIONS · ${candidate.label.take(48)} · ledger ${jinhakMissionTargetLedger.pendingCount()}대기"
        recordRuntimeEvent("jinhak-agent-action", JSONObject()
            .put("safePath", runtimeSafePath(route))
            .put("label", candidate.label.take(80))
            .put("kind", candidate.kind)
            .put("ledgerTarget", ledgerTargetIdForAction != null)
            .put("applicationBound", jinhakMissionContext?.identityKey != null))

        webView.evaluateJavascript(JinhakAgentNavigator.executionScript(candidate)) { encoded ->
            val result = runCatching { JSONObject(decodeJsString(encoded)) }.getOrNull() ?: JSONObject()
            jinhakAgentActionInFlight = false
            if (!batchRunning || batchPausedForLogin) return@evaluateJavascript
            if (!result.optBoolean("ok", false)) {
                val rejectReason = result.optString("reason", "unknown-agent-action-failure").take(80)
                jinhakAnchorRejectReasons[rejectReason] = (jinhakAnchorRejectReasons[rejectReason] ?: 0) + 1
                if (ledgerTargetIdForAction != null) {
                    jinhakMissionTargetLedger.markFailed(ledgerTargetIdForAction, rejectReason)
                    if (jinhakActiveMissionTargetId == ledgerTargetIdForAction) jinhakActiveMissionTargetId = null
                }
                recordRuntimeEvent("jinhak-agent-action-rejected", JSONObject()
                    .put("safePath", runtimeSafePath(route))
                    .put("label", candidate.label.take(80))
                    .put("kind", candidate.kind)
                    .put("ledgerTarget", ledgerTargetIdForAction != null)
                    .put("reason", rejectReason)
                    .put("primaryReason", result.optString("primaryReason").take(80)))
                if (candidate.kind == "mission-link-navigation") jinhakReportBridgeContext = null
            }
            if (result.optBoolean("ok", false)) {
                if (ledgerTargetIdForAction != null) jinhakMissionTargetLedger.markClicked(ledgerTargetIdForAction)
                noteJinhakMeaningfulProgress("agent-click", forceDiagnostics = true)
                if (candidate.kind == "mission-link-navigation") {
                    jinhakMissionAnchorActionsExecuted += 1
                    val clickedKey = RecordUtils.sha256(listOf(candidate.label, candidate.applicationContext?.identityKey ?: "").joinToString("|"))
                    jinhakMissionAnchorClickedKeys.add(clickedKey)
                }
                handler.postDelayed({
                    if (!batchRunning || batchPausedForLogin || batchCollecting) return@postDelayed
                    scheduleBatchSnapshot()
                }, 1100L)
            } else if (ledgerTargetIdForAction != null) {
                // Stay on the origin and immediately evaluate the next captured target instead of
                // falling through to the generic URL frontier.
                handler.postDelayed({
                    if (batchRunning && !batchPausedForLogin && !batchCollecting) scheduleBatchSnapshot()
                }, 160L)
            } else {
                handler.postDelayed({ loadNextBatchPage() }, 120L)
            }
        }
        return true
    }


    private fun maybeReturnToJinhakMissionOrigin(snapshot: JSONObject): Boolean {
        val mission = jinhakMissionContext ?: return false
        if (!jinhakMissionNeedsReturn || mission.identityKey == null || jinhakMissionOriginRoute.isBlank()) return false
        val origin = jinhakMissionOriginRoute
        val current = canonicalizeBatchUrl(snapshot.optString("navigationKey", snapshot.optString("url")))
        jinhakApplicationMissionReturns += 1
        recordRuntimeEvent("jinhak-application-mission-return", JSONObject()
            .put("applicationIdentityHash", mission.identityKey.take(24))
            .put("fromSafePath", runtimeSafePath(current))
            .put("toSafePath", runtimeSafePath(origin))
            .put("coverageLanes", jinhakMissionCoverage[mission.identityKey]?.size ?: 0))
        // v0.8.6 keeps the same application mission and its target ledger active while
        // returning to the saved-application origin. A clicked target that never produced a
        // confirmed report is closed explicitly so it cannot block the remaining ledger.
        val returningTargetId = jinhakActiveMissionTargetId
        if (returningTargetId != null && jinhakMissionTargetLedger.stateOf(returningTargetId) == JinhakMissionTargetLedger.State.CLICKED) {
            jinhakMissionTargetLedger.markFailed(returningTargetId, "report-unconfirmed")
        }
        jinhakActiveMissionTargetId = null
        jinhakReportBridgeContext = null
        jinhakMissionNeedsReturn = false
        currentBatchTarget = origin
        status.text = "지원안 리포트 탐색 종료: 수시저장소 카드로 복귀해 다음 미션을 계속합니다."
        handler.postDelayed({
            if (!batchRunning || batchPausedForLogin) return@postDelayed
            if (webView.canGoBack() && current != origin) webView.goBack() else webView.loadUrl(origin)
        }, 180L)
        return true
    }

    private fun loadNextBatchPage() {
        if (!batchRunning || batchPausedForLogin) return
        if (batchCloudPlansPending > 0) {
            status.text = "Cloud resume 계획 확인 중: ${batchCloudPlansPending}개 목록"
            handler.postDelayed({ loadNextBatchPage() }, 180)
            return
        }

        if (provider == ProviderId.JINHAK) {
            val preferredIdentity = jinhakMissionContext?.identityKey
            if (jinhakMissionTargetLedger.hasActionablePending()) {
                val origin = jinhakMissionTargetLedger.originForNextPending(preferredIdentity)
                if (!origin.isNullOrBlank()) {
                    val current = canonicalizeBatchUrl(webView.url ?: "")
                    val canonicalOrigin = canonicalizeBatchUrl(origin)
                    currentBatchTarget = canonicalOrigin
                    status.text = "지원안 ledger 우선 처리: ${jinhakMissionTargetLedger.pendingCount()}개 target 대기"
                    if (current == canonicalOrigin) {
                        if (!batchCollecting && !jinhakAgentActionInFlight) scheduleBatchSnapshot()
                    } else {
                        webView.loadUrl(canonicalOrigin)
                    }
                    return
                }
            }
            // Deferred mission targets are still outstanding. Do not let editorial/media/frontier
            // work overtake them while a slow worker owns the report.
            if (jinhakMissionTargetLedger.outstandingCount() > 0 && ::slowLanePool.isInitialized && slowLanePool.hasWork()) {
                val slow = slowLanePool.stats()
                status.text = "지원안 ledger 병렬 처리 대기: slow ${slow.running} · 대기 ${slow.queued} · outstanding ${jinhakMissionTargetLedger.outstandingCount()}"
                handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 700L)
                return
            }
        }

        while (batchPageActions.isNotEmpty()) {
            val action = batchPageActions.removeFirst()
            val key = pageActionKey(action)
            batchPageActionQueued.remove(key)
            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue

            val current = canonicalizeBatchUrl(webView.url ?: "")
            pendingBatchPageAction = action
            currentBatchTarget = action.baseUrl
            status.text = pageActionStatus(action, "탐색 준비")

            if (current == action.baseUrl) {
                executePendingBatchPageAction()
            } else {
                webView.loadUrl(action.baseUrl)
            }
            return
        }

        while (batchQueue.isNotEmpty()) {
            val nextRaw = batchQueue.removeFirst()
            val next = canonicalizeBatchUrl(nextRaw)
            batchQueued.remove(next)
            if (next.isBlank() || batchVisited.contains(next) || !isProviderUrl(next)) continue
            jinhakMissionContext = null
        jinhakReportBridgeContext = null
            jinhakMissionOriginRoute = ""
            jinhakMissionNeedsReturn = false
            jinhakLastAgentActionLabel = ""
            jinhakLastAgentActionOriginRoute = ""
            jinhakLastAgentActionMissionContext = null
            currentBatchTarget = next
            status.text = "다음 입시정보 페이지 탐색: ${safeDisplayUrl(next)}"
            webView.loadUrl(next)
            return
        }
        if (!cloudFrontierClaimInProgress && cloudFrontierClaimAttempts < MAX_CLOUD_FRONTIER_CLAIM_ATTEMPTS) {
            cloudFrontierClaimInProgress = true
            cloudFrontierClaimAttempts += 1
            cloudOffload.claimFrontier(provider.wireName, 40) { result ->
                runOnUiThread {
                    cloudFrontierClaimInProgress = false
                    if (!batchRunning || batchPausedForLogin) return@runOnUiThread
                    val tasks = result.getOrNull() ?: JSONArray()
                    var added = 0
                    for (i in 0 until tasks.length()) {
                        val item = tasks.optJSONObject(i) ?: continue
                        val url = canonicalizeBatchUrl(item.optString("url"))
                        val taskId = item.optString("taskId")
                        if (url.isBlank() || taskId.isBlank() || !isBatchNavigableProviderUrl(url)) continue
                        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) {
                            recordJinhakCoreScopeBlock(url)
                            continue
                        }
                        if (!batchVisited.contains(url) && batchQueued.add(url)) {
                            batchQueue.addLast(url)
                            cloudFrontierTaskIds[url] = taskId
                            added += 1
                        }
                    }
                    cloudFrontierClaimed += added
                    if (added > 0) {
                        cloudFrontierClaimAttempts = 0
                        status.text = "Cloud frontier에서 ${added}개 탐색 작업 인계: 로그인된 브라우저 에이전트가 계속 처리합니다."
                        handler.postDelayed({ loadNextBatchPage() }, 80L)
                    } else {
                        handler.postDelayed({ loadNextBatchPage() }, 80L)
                    }
                }
            }
            return
        }
        if (provider == ProviderId.JINHAK && ::slowLanePool.isInitialized && slowLanePool.hasWork()) {
            val slow = slowLanePool.stats()
            status.text = "메인 탐색 완료 · slow worker ${slow.running}개 처리 / ${slow.queued}개 대기: 병렬 작업 종료 후 최종 저장합니다."
            handler.postDelayed({ if (batchRunning && !batchPausedForLogin) loadNextBatchPage() }, 900L)
            return
        }
        if (LOCAL_FIRST_BETA && (provider == ProviderId.ADIGA || provider == ProviderId.JINHAK)) verifyLocalCompletionOrFinish()
        else verifyCloudCompletionOrFinish()
    }

    private fun verifyLocalCompletionOrFinish() {
        if (!batchRunning || batchPausedForLogin) return
        if (provider == ProviderId.JINHAK && jinhakMissionTargetLedger.outstandingCount() > 0) {
            val outstanding = jinhakMissionTargetLedger.outstandingCount()
            val terminalized = jinhakMissionTargetLedger.failAllOutstanding("completion-fence-stranded-target")
            batchErrors.put(JSONObject()
                .put("type", "jinhak-mission-ledger-completion-fence")
                .put("outstandingBeforeFence", outstanding)
                .put("terminalized", terminalized))
            recordRuntimeEvent("jinhak-mission-ledger-completion-fence", JSONObject()
                .put("outstandingBeforeFence", outstanding)
                .put("terminalized", terminalized)
                .put("ledger", jinhakMissionTargetLedger.summary()))
            finishBatch("completed-with-local-errors")
            return
        }
        val runId = localRunId
        if (runId == null) {
            finishBatch("completed")
            return
        }
        val unresolved = localStore.unresolvedCount(runId)
        if (unresolved > 0) finishBatch("completed-with-local-errors")
        else finishBatch("completed")
    }

    private fun verifyCloudCompletionOrFinish(drainAttempt: Int = 0) {
        if (!batchRunning || batchPausedForLogin) return
        if (!cloudOffload.isConfigured()) {
            finishBatch("completed")
            return
        }
        if (batchCloudFinalCheckInProgress) return
        batchCloudFinalCheckInProgress = true
        status.text = "Cloud Queue 및 전체 체크포인트 최종 검증 중…"
        cloudOffload.status { statusResult ->
            runOnUiThread {
                if (!batchRunning) {
                    batchCloudFinalCheckInProgress = false
                    return@runOnUiThread
                }
                val run = statusResult.getOrNull()?.optJSONObject("run")
                val uploaded = run?.optInt("uploaded_chunks", 0) ?: 0
                val processed = run?.optInt("processed_chunks", 0) ?: 0
                if (run != null && processed < uploaded && drainAttempt < 20) {
                    batchCloudFinalCheckInProgress = false
                    status.text = "Cloud Queue 반영 대기: $processed/$uploaded"
                    handler.postDelayed({ verifyCloudCompletionOrFinish(drainAttempt + 1) }, 500L)
                    return@runOnUiThread
                }
                cloudOffload.pendingPages { pendingResult ->
                    runOnUiThread {
                        batchCloudFinalCheckInProgress = false
                        if (!batchRunning) return@runOnUiThread
                        val response = pendingResult.getOrNull()
                        if (response == null) {
                            finishBatch("cloud-verification-failed")
                            return@runOnUiThread
                        }
                        val deferred = response.optJSONArray("deferred") ?: JSONArray()
                        batchCloudPagesDeferred = deferred.length()
                        val scheduled = enqueueGlobalPendingRecovery(response)
                        if (scheduled > 0) {
                            status.text = "Cloud 미완료 ${scheduled}쪽을 완료 판정 전에 우선 복구합니다."
                            handler.postDelayed({ loadNextBatchPage() }, 120L)
                            return@runOnUiThread
                        }
                        if (batchCloudPagesDeferred > 0) {
                            finishBatch("completed-with-deferred-errors")
                        } else {
                            finishBatch("completed")
                        }
                    }
                }
            }
        }
    }

    private fun executePendingBatchPageAction() {
        if (!batchRunning || batchPausedForLogin) return
        val action = pendingBatchPageAction ?: return
        pendingBatchPageAction = null

        val key = pageActionKey(action)
        if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) {
            handler.postDelayed({ loadNextBatchPage() }, 100)
            return
        }

        val js = currentAdapter().paginationScript(action.page)
        if (js.isNullOrBlank()) {
            recordPaginationFailure(action, "pagination-action-unavailable")
            handler.postDelayed({ loadNextBatchPage() }, 150)
            return
        }

        activeBatchPageAction = action
        status.text = pageActionStatus(action, if (action.retry > 0) "재시도 ${action.retry}/$MAX_PAGE_RETRIES" else "백그라운드 이동 중")
        val yearPrelude = action.requestedYear?.let { expectedYear ->
            """(function(){var n=document.querySelectorAll('[name=searchSyr],#searchSyr');for(var i=0;i<n.length;i++){try{n[i].value='$expectedYear';}catch(e){}}})();"""
        } ?: ""
        webView.evaluateJavascript(yearPrelude + js) { result ->
            if (result != "true") {
                activeBatchPageAction = null
                if (action.retry < MAX_PAGE_RETRIES) {
                    schedulePageActionRetry(action, "pagination-action-unavailable")
                } else {
                    recordPaginationFailure(action, "pagination-action-unavailable")
                    handler.postDelayed({ loadNextBatchPage() }, 150)
                }
            } else {
                handler.postDelayed({
                    if (batchRunning && !batchPausedForLogin && !batchCollecting && pendingBatchPageAction == null) {
                        scheduleBatchSnapshot()
                    }
                }, 2200)
            }
        }
    }

    private fun schedulePageActionRetry(action: BatchPageAction, reason: String) {
        // Central retry circuit-breaker. Every caller, including stale-content recovery,
        // must pass through this guard so one bad page can never pin the whole batch.
        if (action.retry >= MAX_PAGE_RETRIES) {
            recordPaginationFailure(action, reason)
            activeBatchPageAction = null
            pendingBatchPageAction = null
            status.text = pageActionStatus(action, "재시도 상한 도달: 오류로 보존 후 다음 페이지 진행")
            handler.postDelayed({ loadNextBatchPage() }, 250L)
            return
        }

        val retry = action.copy(retry = action.retry + 1)
        batchPaginationRetries += 1
        batchRetryEvents.put(JSONObject()
            .put("familyKey", action.familyKey)
            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
            .put("page", action.page)
            .put("attempt", retry.retry)
            .put("maxAttempts", MAX_PAGE_RETRIES)
            .put("reason", reason))
        pendingBatchPageAction = retry
        activeBatchPageAction = null
        currentBatchTarget = retry.baseUrl
        status.text = pageActionStatus(retry, "재시도 대기 ($reason)")
        val delay = 1200L + (retry.retry * 1000L)
        handler.postDelayed({
            if (batchRunning && !batchPausedForLogin) webView.loadUrl(retry.baseUrl)
        }, delay)
    }

    private fun recordPaginationFailure(action: BatchPageAction, type: String) {
        batchPageActionFailed.add(pageActionKey(action))
        val error = JSONObject()
            .put("url", action.baseUrl)
            .put("type", type)
            .put("page", action.page)
            .put("totalPages", action.totalPages)
            .put("familyKey", action.familyKey)
            .put("requestedYear", action.requestedYear ?: JSONObject.NULL)
            .put("retryCount", action.retry)
        batchErrors.put(error)
        localRunId?.let { runId ->
            localStore.markPage(
                runId, action.familyKey, action.requestedYear,
                action.page, action.totalPages, "error", action.retry, type
            )
            localStore.markDocument(runId, canonicalizeBatchUrl(action.baseUrl), "error", action.retry, type)
        }
    }

    private fun pageActionStatus(action: BatchPageAction, suffix: String): String {
        val year = action.requestedYear?.let { " $it" } ?: ""
        val label = when {
            action.familyKey.contains("classUnivView") -> "학과정보"
            action.familyKey.contains("univView") -> "대학정보"
            action.familyKey.contains("admssUnivView") -> "전형정보"
            else -> "목록"
        }
        return "$label$year ${action.page}/${action.totalPages}쪽 $suffix"
    }

    private fun pageActionKey(action: BatchPageAction): String =
        "${action.familyKey}|year=${action.requestedYear ?: "unknown"}|page=${action.page}"

    private fun sameBatchDocument(a: String, b: String): Boolean {
        return try {
            val ua = Uri.parse(a)
            val ub = Uri.parse(b)
            ua.host.equals(ub.host, ignoreCase = true) && ua.path == ub.path
        } catch (_: Exception) { false }
    }

    private fun queryYearFromUrl(url: String?): Int? {
        if (url.isNullOrBlank()) return null
        return try { Uri.parse(url).getQueryParameter("searchSyr")?.toIntOrNull() } catch (_: Exception) { null }
    }

    private fun withQueryParameter(url: String, key: String, value: String): String {
        return try {
            val uri = Uri.parse(url)
            val builder = uri.buildUpon().clearQuery()
            for (name in uri.queryParameterNames) {
                if (name == key) continue
                for (v in uri.getQueryParameters(name)) builder.appendQueryParameter(name, v)
            }
            builder.appendQueryParameter(key, value).build().toString()
        } catch (_: Exception) { url }
    }

    private fun stabilizeBatchSnapshotContext(snapshot: JSONObject) {
        if (provider != ProviderId.ADIGA) return
        val rawUrl = snapshot.optString("url")
        if (!currentAdapter().isDynamicListPage(rawUrl)) return
        if (queryYearFromUrl(rawUrl) != null) return

        val expectedYear = activeBatchPageAction?.requestedYear
            ?: pendingBatchPageAction?.requestedYear
            ?: queryYearFromUrl(currentBatchTarget)
        if (expectedYear == null) {
            snapshot.put("collectionContextError", "missing-searchSyr")
            return
        }

        val restoredUrl = withQueryParameter(rawUrl, "searchSyr", expectedYear.toString())
        snapshot.put("url", restoredUrl)
        snapshot.put("navigationKey", restoredUrl)
        snapshot.put("collectionContextRecovered", true)
        snapshot.put("collectionExpectedYear", expectedYear)
        currentBatchTarget = restoredUrl
        batchContextRecoveries += 1
    }

    private fun startCollectionKeepAlive() {
        runCatching { startForegroundService(Intent(this, CollectionKeepAliveService::class.java)) }
        handler.removeCallbacks(sessionKeepAlive)
        handler.postDelayed(sessionKeepAlive, 5_000L)
    }

    private fun stopCollectionKeepAlive() {
        runCatching { stopService(Intent(this, CollectionKeepAliveService::class.java)) }
        if (!unifiedRunning && !startupLoginPreflightActive && !jinhakTransitionAuthGateActive) {
            handler.removeCallbacks(sessionKeepAlive)
        }
    }

    private fun canonicalizeBatchUrl(url: String): String {
        if (url.isBlank()) return ""
        return try {
            val uri = Uri.parse(url)
            val host = uri.host ?: return ""
            val builder = Uri.Builder()
                .scheme(uri.scheme ?: "https")
                .authority(host)
                .path(uri.path ?: "/")

            val forbidden = Regex("token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential", RegexOption.IGNORE_CASE)
            val names = uri.queryParameterNames
            for (name in names) {
                if (forbidden.containsMatchIn(name)) continue
                for (value in uri.getQueryParameters(name)) builder.appendQueryParameter(name, value)
            }
            builder.build().toString()
        } catch (_: Exception) {
            url.substringBefore('#')
        }
    }

    private fun sendLatestLocalDiagnostic(manual: Boolean) {
        val runId = localRunId ?: localStore.latestRun(provider.wireName)
        if (runId.isNullOrBlank()) {
            if (manual) Toast.makeText(this, "전송할 로컬 수집 로그가 없습니다.", Toast.LENGTH_LONG).show()
            return
        }
        val diagnostic = localStore.diagnosticSnapshot(runId)
            .put("trigger", if (manual) "manual" else "batch-finish")
            .put("segment", JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulSnapshots", batchSnapshots.length())
                .put("errorEvents", batchErrors.length())
                .put("paginationActionsCompleted", batchPageActionVisited.size)
                .put("paginationActionsFailed", batchPageActionFailed.size)
                .put("paginationRetries", batchPaginationRetries)
                .put("localPagesScheduled", batchLocalPagesScheduled)
                .put("localPagesSkipped", batchLocalPagesSkipped)
                .put("localRecordsPersisted", batchLocalRecordsPersisted))
        if (manual) status.text = "진단 로그 전송 중… 원본 입시자료는 전송하지 않습니다."
        cloudOffload.sendDiagnostic(provider.wireName, VERSION, diagnostic) { result ->
            runOnUiThread {
                if (result.isSuccess) {
                    val id = result.getOrNull()?.take(8) ?: "unknown"
                    status.text = "진단 로그 전송 완료: $id… / 원본 레코드·로그인 정보 미전송"
                    if (manual) Toast.makeText(this, "진단 로그 전송 완료", Toast.LENGTH_SHORT).show()
                } else if (manual) {
                    status.text = "진단 로그 전송 실패: ${result.exceptionOrNull()?.message ?: "unknown"}"
                    Toast.makeText(this, "진단 로그 전송 실패", Toast.LENGTH_LONG).show()
                }
            }
        }
    }

    private fun finishBatch(reason: String) {
        batchRunning = false
        batchPausedForLogin = false
        batchCollecting = false
        batchNavigationWatchdogRecovery = false
        batchCloudFinalCheckInProgress = false
        disarmBatchNavigationWatchdog()
        webView.stopLoading()
        hideBatchCover()
        stopCollectionKeepAlive()
        batchButton.text = if (currentAdapter().supportsBatchCrawl) "접근 가능 정보 일괄 수집" else if (provider == ProviderId.JINHAK && currentAdapter().supportsUserSessionMissionTraversal) "진학사 목적형 탐색" else "현재 화면 정리"
        val effectiveReason = if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            reason
        } else if (reason == "completed" && batchCloudPagesDeferred > 0) {
            "completed-with-deferred-errors"
        } else reason
        localRunId?.let { runId ->
            val runState = if (effectiveReason == "completed" && localStore.unresolvedCount(runId) == 0) "completed" else "incomplete"
            localStore.markRun(runId, runState, effectiveReason)
        }
        finalizeBatchJson(effectiveReason)
        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            // Telemetry is sent only after the crawl has stopped, never per page.
            sendLatestLocalDiagnostic(manual = false)
        }
        if (!LOCAL_FIRST_BETA && effectiveReason == "completed" && batchCloudPagesDeferred == 0) {
            cloudOffload.finish(
                reason = effectiveReason,
                summary = JSONObject()
                    .put("attemptedPages", batchPageCount)
                    .put("successfulPages", batchSnapshots.length())
                    .put("errorPages", batchErrors.length())
                    .put("records", batchRecords.length())
                    .put("paginationRetries", batchPaginationRetries)
                    .put("cloudResumePlans", batchCloudResumePlans)
                    .put("cloudPagesScheduled", batchCloudPagesScheduled)
                    .put("cloudPagesSkipped", batchCloudPagesSkipped)
                    .put("cloudPagesDeferred", batchCloudPagesDeferred)
            )
        }
        status.text = when {
            LOCAL_FIRST_BETA && effectiveReason == "completed-with-local-errors" ->
                "Local-First 1차 순회 종료: 미해결 오류는 로컬에 저장됨 / 다음 실행에서 해당 지점만 재개합니다."
            LOCAL_FIRST_BETA && effectiveReason == "completed" ->
                "어디가 로컬 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 재시도 $batchPaginationRetries / 로컬 레코드 ${localRunId?.let { localStore.stats(it).optInt("records") } ?: batchRecords.length()}"
            effectiveReason == "cloud-verification-failed" ->
                "로컬 수집 종료: Cloud 최종 완결성 확인 실패 / 서버 run은 닫지 않고 유지합니다."
            batchCloudPagesDeferred > 0 ->
                "수집 종료: 서버 오류 ${batchCloudPagesDeferred}쪽은 Cloud에 보류 / 전체 완료로 확정하지 않습니다."
            else ->
                "일괄 수집 완료: 시도 $batchPageCount / 성공 ${batchSnapshots.length()} / 최종오류 ${batchErrors.length()} / 재시도 $batchPaginationRetries / 레코드 ${batchRecords.length()}"
        }
        if (unifiedRunning && unifiedPhase == "adiga" && provider == ProviderId.ADIGA) {
            val sessionId = unifiedSessionId
            if (sessionId != null) {
                localRunId?.let { runId -> localStore.attachUnifiedProviderRun(sessionId, ProviderId.ADIGA.wireName, runId) }
                localStore.updateUnifiedSession(sessionId, "jinhak", "running", "adiga:$effectiveReason")
            }
            handler.postDelayed({ transitionUnifiedToJinhak(effectiveReason) }, 350L)
        }
        else if (unifiedRunning && unifiedPhase == "jinhak" && provider == ProviderId.JINHAK) {
            val sessionId = unifiedSessionId
            if (sessionId != null) {
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
                        .put("missionActionsExecuted", jinhakMissionActionsExecuted)
                        .put("genericActionsExecuted", jinhakGenericActionsExecuted)
                        .put("missionActionLimit", MAX_JINHAK_MISSION_ACTIONS)
                        .put("genericActionLimit", MAX_JINHAK_GENERIC_ACTIONS)
                        .put("referenceRoutesTracked", jinhakReferenceRouteCaptureCounts.size)
                        .put("referenceRepeatSkips", jinhakReferenceRepeatSkips)
                        .put("noProgressFences", jinhakNoProgressFences)
                        .put("secondsSinceMeaningfulProgress", if (jinhakLastMeaningfulProgressAtMs > 0L) (System.currentTimeMillis() - jinhakLastMeaningfulProgressAtMs).coerceAtLeast(0L) / 1000.0 else JSONObject.NULL)
                        .put("loginSurfaceDetections", credentialLoginSurfaceDetections)
                        .put("credentialAutoLoginAttempts", credentialAutoLoginAttempts)
                        .put("credentialAutoLoginSubmissions", credentialAutoLoginSubmissions)
                        .put("credentialAutoLoginSuccesses", credentialAutoLoginSuccesses)
                        .put("credentialAutoLoginFailures", credentialAutoLoginFailures)
                        .put("credentialAutoLoginLastResult", credentialAutoLoginLastResult.take(80))
                        .put("credentialAutoLoginLastProvider", credentialAutoLoginLastProvider.take(20))
                        .put("credentialAutoLoginLastAtMs", credentialAutoLoginLastAtMs)
                        .put("batchRenderedLoginSurfacePauses", batchRenderedLoginSurfacePauses)
                        .put("crossVersionResumeBlocks", crossVersionResumeBlocks)
                        .put("staleSessionLeaseBypassesPrevented", staleSessionLeaseBypassesPrevented)
                        .put("loginRouteFallbackPauses", loginRouteFallbackPauses)
                        .put("loginRouteFallbackCredentialPrompts", loginRouteFallbackCredentialPrompts)
                        .put("jinhakAuthVerifiedForBatch", jinhakAuthVerifiedForBatch)
                        .put("jinhakCoreBootstrapState", jinhakCoreBootstrapState)
                        .put("jinhakLastAuthEvidence", jinhakLastAuthEvidence)
                        .put("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)
                        .put("jinhakLoginRecoveryPolls", jinhakLoginRecoveryPolls)
                        .put("jinhakReauthCycles", jinhakReauthCycles)
                        .put("jinhakAuthVerificationFailures", jinhakAuthVerificationFailures)
                        .put("jinhakTransitionAuthChecks", jinhakTransitionAuthChecks)
                        .put("jinhakSessionKeepAliveTicks", jinhakSessionKeepAliveTicks)
                        .put("jinhakSessionKeepAliveBackgroundTicks", jinhakSessionKeepAliveBackgroundTicks)
                        .put("jinhakSessionExtensionClicks", jinhakSessionExtensionClicks)
                        .put("jinhakCoreScopeBlockedUrls", jinhakCoreScopeBlockedUrls)
                        .put("jinhakCoreScopeBlockedLanes", JSONObject(jinhakCoreScopeBlockedLaneCounts as Map<*, *>))
                        .put("applicationBoundAgentActions", jinhakApplicationBoundActions)
                        .put("applicationMissionReturns", jinhakApplicationMissionReturns)
                        .put("applicationMissionIdentities", jinhakMissionCoverage.size)
                        .put("missionBootstrapAtMs", jinhakMissionBootstrapStartedAtMs)
                        .put("secondsToFirstPopulatedStorage", if (jinhakMissionBootstrapStartedAtMs > 0L && jinhakFirstPopulatedStorageAtMs > 0L) (jinhakFirstPopulatedStorageAtMs - jinhakMissionBootstrapStartedAtMs) / 1000.0 else JSONObject.NULL)
                        .put("applicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                        .put("applicationAnchorActionsPromoted", jinhakMissionAnchorPromotedKeys.size)
                        .put("applicationAnchorStructuredBindings", jinhakMissionAnchorStructuredKeys.size)
                        .put("normalizedApplicationIdentitySeeds", jinhakNormalizedIdentitySeedKeys.size)
                        .put("normalizedApplicationCandidateBindings", jinhakNormalizedCandidateBindingKeys.size)
                        .put("normalizedApplicationAmbiguousBindings", jinhakNormalizedAmbiguousBindings)
                        .put("originInferredMissionTargets", jinhakOriginInferredMissionTargets)
                        .put("externalNavigationsBlocked", jinhakExternalNavigationsBlocked)
                        .put("jinhakBatchStartCount", jinhakBatchStartCount)
                .put("normalizedApplicationIdentitySeeds", jinhakNormalizedIdentitySeedKeys.size)
                .put("normalizedApplicationCandidateBindings", jinhakNormalizedCandidateBindingKeys.size)
                .put("normalizedApplicationAmbiguousBindings", jinhakNormalizedAmbiguousBindings)
                        .put("originInferredMissionTargets", jinhakOriginInferredMissionTargets)
                        .put("externalNavigationsBlocked", jinhakExternalNavigationsBlocked)
                .put("jinhakBatchStartCount", jinhakBatchStartCount)
                        .put("applicationAnchorBindingSources", JSONObject(jinhakMissionBindingSourceCounts as Map<*, *>))
                        .put("applicationAnchorActionsParsed", jinhakMissionAnchorParsedKeys.size)
                        .put("applicationAnchorActionsSelected", jinhakMissionAnchorSelectedKeys.size)
                        .put("applicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                        .put("applicationAnchorActionsClicked", jinhakMissionAnchorClickedKeys.size)
                        .put("applicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                        .put("applicationAnchorReportConfirmed", jinhakReportConfirmedKeys.size)
                        .put("applicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                        .put("reportBridgeArmed", jinhakReportBridgeArmed)
                        .put("reportBridgeApplied", jinhakReportBridgeApplied)
                        .put("reportBridgeConfirmed", jinhakReportBridgeConfirmed)
                        .put("consentGatesEncountered", jinhakConsentGatesEncountered)
                        .put("consentGatesResolved", jinhakConsentGatesResolved)
                        .put("unboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                        .put("slowLaneEscalated", jinhakSlowLaneEscalated)
                        .put("slowLaneCompleted", jinhakSlowLaneCompleted)
                        .put("slowLaneAverageCompletedMs", if (jinhakSlowLaneCompleted > 0) jinhakSlowLaneCompletedDurationMs / jinhakSlowLaneCompleted else JSONObject.NULL)
                        .put("slowLaneMaxCompletedMs", jinhakSlowLaneMaxDurationMs)
                        .put("slowLaneFailed", jinhakSlowLaneFailed)
                        .put("slowLaneFailureReasons", JSONObject(jinhakSlowLaneFailureReasons as Map<*, *>))
                        .put("slowLaneUserActionRequired", jinhakSlowLaneUserActionRequired)
                        .put("slowLaneProgressExtensions", if (::slowLanePool.isInitialized) slowLanePool.stats().progressExtensions else 0)
                        .put("slowLaneReplayAttempts", if (::slowLanePool.isInitialized) slowLanePool.stats().replayAttempts else 0)
                        .put("slowLaneReplaySuccesses", if (::slowLanePool.isInitialized) slowLanePool.stats().replaySuccesses else 0)
                        .put("slowLaneMaxActiveWorkers", if (::slowLanePool.isInitialized) slowLanePool.stats().maxActiveWorkers else 0)
                        .put("applicationMissionCoverage", JSONObject().apply {
                            val lanes = listOf("saved-application", "current-prediction", "mock-support", "actual-admit", "university-result", "score-analysis", "strategy")
                            for (lane in lanes) put(lane, jinhakMissionCoverage.values.count { it.contains(lane) })
                            put("fourOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 4 })
                            put("sixOrMoreLanes", jinhakMissionCoverage.values.count { it.size >= 6 })
                        })
                        .put("missionTargetLedger", jinhakMissionTargetLedger.summary())
                        .put("missionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                        .put("missionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                        .put("cloudFrontierPublished", cloudFrontierPublished)
                        .put("cloudFrontierClaimed", cloudFrontierClaimed)
                        .put("cloudFrontierCompleted", cloudFrontierCompleted)
                        .put("cloudFrontierCompletionFailed", cloudFrontierCompletionFailed)
                        .put("cloudFrontierOutstanding", (cloudFrontierClaimed - cloudFrontierCompleted).coerceAtLeast(0)),
                    false
                )
            }
            handler.postDelayed({ finishUnifiedCollection("jinhak:$effectiveReason") }, 350L)
        }
    }

    private fun finalizeBatchJson(reason: String) {
        val localStats = localRunId?.let { localStore.stats(it) } ?: JSONObject()
        val persistedRecordCount = localStats.optInt("records", batchRecords.length())
        val persistedRecords = if (LOCAL_FIRST_BETA) JSONArray() else (localRunId?.let { localStore.loadRecords(it) } ?: batchRecords)
        val out = JSONObject()
            .put("collectorVersion", VERSION)
            .put("provider", provider.wireName)
            .put("collectedAt", Instant.now().toString())
            .put("mode", "batch")
            .put("completion", reason)
            .put("summary", JSONObject()
                .put("attemptedPages", batchPageCount)
                .put("successfulPages", batchSnapshots.length())
                .put("errorPages", batchErrors.length())
                .put("records", persistedRecordCount)
                .put("resourceLinks", batchResources.length())
                .put("paginationActionsCompleted", batchPageActionVisited.size)
                .put("paginationActionsFailed", batchPageActionFailed.size)
                .put("paginationRetries", batchPaginationRetries)
                .put("paginationPlans", batchPaginationPlanned.size)
                .put("cloudResumePlans", batchCloudResumePlans)
                .put("cloudPagesScheduled", batchCloudPagesScheduled)
                .put("cloudPagesSkipped", batchCloudPagesSkipped)
                .put("cloudPagesDeferred", batchCloudPagesDeferred)
                .put("contextRecoveries", batchContextRecoveries)
                .put("collectionTransport", "authenticated-webview-covered")
                .put("duplicateYearViewsSkipped", batchDuplicateYearViews.length())
                .put("dynamicSearchBootstraps", batchBootstrapSearchAttempted.size)
                .put("localResumePlans", batchLocalResumePlans)
                .put("localPagesScheduled", batchLocalPagesScheduled)
                .put("localPagesSkipped", batchLocalPagesSkipped)
                .put("localRecordsPersistedThisSegment", batchLocalRecordsPersisted)
                .put("localAuditPagesScheduled", batchAuditPagesScheduled)
                .put("universityDiscoveryPagesScheduled", batchUniversityDiscoveryPagesScheduled)
                .put("jinhakAgentActionsExecuted", jinhakAgentActionsExecuted)
                .put("jinhakMissionActionsExecuted", jinhakMissionActionsExecuted)
                .put("jinhakGenericActionsExecuted", jinhakGenericActionsExecuted)
                .put("jinhakReferenceRepeatSkips", jinhakReferenceRepeatSkips)
                .put("jinhakOriginInferredMissionTargets", jinhakOriginInferredMissionTargets)
                .put("jinhakExternalNavigationsBlocked", jinhakExternalNavigationsBlocked)
                .put("jinhakNoProgressFences", jinhakNoProgressFences)
                .put("jinhakApplicationBoundActions", jinhakApplicationBoundActions)
                .put("jinhakApplicationMissionReturns", jinhakApplicationMissionReturns)
                .put("jinhakApplicationMissionIdentities", jinhakMissionCoverage.size)
                .put("jinhakMissionTargetLedger", jinhakMissionTargetLedger.summary())
                .put("jinhakMissionTargetLedgerPending", jinhakMissionTargetLedger.pendingCount())
                .put("jinhakMissionTargetLedgerOutstanding", jinhakMissionTargetLedger.outstandingCount())
                .put("jinhakApplicationAnchorActionsDiscovered", jinhakMissionAnchorDiscoveredKeys.size)
                .put("jinhakApplicationAnchorActionsAttempted", jinhakMissionAnchorActionsAttempted)
                .put("jinhakApplicationAnchorActionsExecuted", jinhakMissionAnchorActionsExecuted)
                .put("jinhakApplicationAnchorRejectReasons", JSONObject(jinhakAnchorRejectReasons as Map<*, *>))
                .put("jinhakReportBridgeArmed", jinhakReportBridgeArmed)
                .put("jinhakReportBridgeApplied", jinhakReportBridgeApplied)
                .put("jinhakConsentGatesEncountered", jinhakConsentGatesEncountered)
                .put("jinhakConsentGatesResolved", jinhakConsentGatesResolved)
                .put("jinhakUnboundSavedApplicationObservations", jinhakUnboundSavedApplicationObservations)
                .put("jinhakSlowLaneEscalated", jinhakSlowLaneEscalated)
                .put("jinhakSlowLaneCompleted", jinhakSlowLaneCompleted)
                .put("jinhakSlowLaneAverageCompletedMs", if (jinhakSlowLaneCompleted > 0) jinhakSlowLaneCompletedDurationMs / jinhakSlowLaneCompleted else JSONObject.NULL)
                .put("jinhakSlowLaneMaxCompletedMs", jinhakSlowLaneMaxDurationMs)
                .put("jinhakSlowLaneFailed", jinhakSlowLaneFailed)
                .put("jinhakSlowLaneUserActionRequired", jinhakSlowLaneUserActionRequired)
                .put("jinhakSlowLaneProgressExtensions", if (::slowLanePool.isInitialized) slowLanePool.stats().progressExtensions else 0)
                .put("jinhakSlowLaneReplayAttempts", if (::slowLanePool.isInitialized) slowLanePool.stats().replayAttempts else 0)
                .put("jinhakSlowLaneReplaySuccesses", if (::slowLanePool.isInitialized) slowLanePool.stats().replaySuccesses else 0)
                .put("jinhakSlowLaneMaxActiveWorkers", if (::slowLanePool.isInitialized) slowLanePool.stats().maxActiveWorkers else 0)
                .put("jinhakSecondsToFirstPopulatedStorage", if (jinhakMissionBootstrapStartedAtMs > 0L && jinhakFirstPopulatedStorageAtMs > 0L) (jinhakFirstPopulatedStorageAtMs - jinhakMissionBootstrapStartedAtMs) / 1000.0 else JSONObject.NULL)
                .put("jinhakUniqueNavigationStates", jinhakUniqueNavigationStates)
                .put("jinhakRepeatedNavigationStateSkips", jinhakRepeatedNavigationStateSkips)
                .put("cloudFrontierPublished", cloudFrontierPublished)
                .put("cloudFrontierClaimed", cloudFrontierClaimed)
                .put("cloudFrontierCompleted", cloudFrontierCompleted)
                .put("cloudFrontierCompletionFailed", cloudFrontierCompletionFailed)
                        .put("cloudFrontierOutstanding", (cloudFrontierClaimed - cloudFrontierCompleted).coerceAtLeast(0))
                .put("sessionLease", sessionVault.summary(provider.wireName)?.toJson() ?: JSONObject.NULL))
            .put("localFirst", JSONObject()
                .put("enabled", LOCAL_FIRST_BETA)
                .put("cloudRequestsDuringBatch", 0)
                .put("snapshotScope", "current-process-segment")
                .put("stats", localStats))
            .put("errors", batchErrors)
            .put("retryEvents", batchRetryEvents)
            .put("duplicateYearViews", batchDuplicateYearViews)
            .put("cloudOffload", JSONObject().put("mode", "disabled-during-v0.4.0-local-first"))
            .put("recordsMaterializedInMemory", !LOCAL_FIRST_BETA)
            .put("records", persistedRecords)
            .put("snapshots", batchSnapshots)
            .put("resourceLinks", batchResources)
        lastJson = out.toString(2)
        showPreview(lastJson)
    }

    private fun collectSnapshot(callback: (JSONObject?) -> Unit) = collectSnapshot(webView, callback)

    private fun collectSnapshot(target: WebView, callback: (JSONObject?) -> Unit) {
        val js = SnapshotScript.build()
        target.evaluateJavascript(js) { encoded ->
            try {
                val raw = decodeJsString(encoded)
                val obj = JSONObject(raw)
                obj.put("providerPageType", currentAdapter().classify(obj))
                val session = obj.optJSONObject("session") ?: JSONObject()
                sessionState.text = when {
                    session.optBoolean("authenticated", false) -> "● 로그인 유지됨"
                    session.optBoolean("needsLogin", false) -> "○ 로그인 갱신 필요"
                    else -> "△ 로그인 상태 미확정"
                }
                callback(obj)
            } catch (e: Exception) {
                status.text = "수집 실패: ${e.message}"
                callback(null)
            }
        }
    }


    private fun jinhakMissionContextsFromNormalizedRecords(records: JSONArray): List<JinhakApplicationMission.Context> {
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

    private fun normalizeSnapshot(snapshot: JSONObject): JSONArray =
        currentAdapter().normalize(snapshot)

    private fun enqueueProviderSeeds() {
        for (rawUrl in currentAdapter().seedUrls()) {
            val url = canonicalizeBatchUrl(rawUrl)
            if (url.isBlank() || !isProviderUrl(url) || batchVisited.contains(url) || batchQueued.contains(url)) continue
            if (provider == ProviderId.JINHAK && !isJinhakDefaultCoreQueueUrl(url)) continue
            val runId = localRunId
            if (runId != null && !currentAdapter().isDynamicListPage(url) && localStore.isDocumentCompleted(runId, url)) continue
            batchQueued.add(url)
            batchQueue.addLast(url)
        }
    }

    private fun recordJinhakCoreScopeBlock(url: String) {
        if (provider != ProviderId.JINHAK) return
        val lane = JinhakSiteTopology.lane(url).wireName
        jinhakCoreScopeBlockedUrls += 1
        jinhakCoreScopeBlockedLaneCounts[lane] = (jinhakCoreScopeBlockedLaneCounts[lane] ?: 0) + 1
    }

    private fun isJinhakDefaultCoreQueueUrl(url: String): Boolean {
        if (provider != ProviderId.JINHAK) return true
        val allowed = JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)
        if (!allowed) recordJinhakCoreScopeBlock(url)
        return allowed
    }

    private fun enqueueDiscoveredLinks(links: JSONArray) {
        val frontierBatch = JSONArray()
        for (i in 0 until links.length()) {
            val obj = links.optJSONObject(i) ?: continue
            val url = canonicalizeBatchUrl(obj.optString("url"))
            if (url.isBlank() || !isBatchNavigableProviderUrl(url)) continue
            if (!isJinhakDefaultCoreQueueUrl(url)) continue
            enqueueDiscoveredUrl(url)
            frontierBatch.put(url)
            historicalMirrorUrl(url)?.let { mirror ->
                enqueueDiscoveredUrl(mirror)
                frontierBatch.put(mirror)
            }
            if (batchQueue.size + batchVisited.size >= MAX_BATCH_PAGES * 2) break
        }
        if (frontierBatch.length() > 0) {
            cloudOffload.publishFrontier(
                provider = provider.wireName,
                urls = frontierBatch,
                sourceSafePath = runtimeSafePath(webView.url),
                publicFetchEligible = provider == ProviderId.ADIGA
            ) { accepted ->
                if (accepted > 0) cloudFrontierPublished += accepted
            }
        }
    }

    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (provider == ProviderId.JINHAK && !JinhakSiteTopology.isDefaultSusiCoreTraversalUrl(url)) return
        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return
        if (batchVisited.contains(url)) return
        val runId = localRunId
        if (runId != null && localStore.isDocumentCompleted(runId, url)) return
        if (batchQueued.add(url)) {
            if (provider == ProviderId.JINHAK && JinhakSiteTopology.isCoreMissionRoute(url)) {
                batchQueue.addFirst(url)
            } else {
                batchQueue.addLast(url)
            }
        }
    }

    private fun historicalMirrorUrl(url: String): String? {
        if (provider != ProviderId.ADIGA) return null
        return try {
            val uri = Uri.parse(url)
            if (uri.path != "/ucp/uvt/uni/univDetailSelection.do") return null
            if (uri.getQueryParameter("searchSyr") != "2027") return null
            val code = uri.getQueryParameter("unvCd")?.trim().orEmpty()
            if (!Regex("^0[0-9]{6}$").matches(code)) return null
            canonicalizeBatchUrl(withQueryParameter(url, "searchSyr", "2026"))
        } catch (_: Exception) { null }
    }

    private fun tableFingerprint(snapshot: JSONObject): String? {
        val tables = snapshot.optJSONArray("tables") ?: return null
        if (tables.length() == 0) return null
        val rows = tables.optJSONObject(0)?.optJSONArray("rows") ?: return null
        if (rows.length() == 0) return null
        return RecordUtils.sha256(rows.toString())
    }

    private fun enqueueCalculatedPageActions(snapshot: JSONObject, plan: PaginationPlan) {
        val baseUrl = canonicalizeBatchUrl(snapshot.optString("url"))
        if (baseUrl.isBlank() || !isProviderUrl(baseUrl) || plan.totalPages <= 1) return
        val planKey = "${plan.familyKey}|year=${plan.requestedYear ?: "unknown"}|${plan.totalItems}|${plan.pageSize}|${plan.totalPages}"
        if (!batchPaginationPlanned.add(planKey)) return

        if (LOCAL_FIRST_BETA && provider == ProviderId.ADIGA) {
            val runId = localRunId
            if (runId == null) {
                enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())
                return
            }
            val localPlan = localStore.resumePlan(runId, plan.familyKey, plan.requestedYear, plan.totalPages)
            val pages = linkedSetOf<Int>()
            pages.addAll(localPlan.retry)
            pages.addAll(localPlan.missing)

            // Checkpoint state alone is insufficient: v0.4.0 proved that a stale AJAX
            // response could be marked completed while another page's rows were stored.
            // Re-open any checkpoint that has no persisted row evidence, plus neighbors
            // so stale-content detection has a reference page on either side.
            val evidencePages = persistedPagesWithRecords(runId, plan.familyKey, plan.requestedYear)
            val evidenceMissing = (2..plan.totalPages).filter { it !in evidencePages }
            for (page in evidenceMissing) {
                for (candidate in (page - 1)..(page + 1)) {
                    if (candidate in 2..plan.totalPages) pages.add(candidate)
                }
            }
            batchAuditPagesScheduled += evidenceMissing.size

            // v0.4.0 already has all 220 university summary rows, but only page 1 links
            // were followed. Revisit the 21 remaining 2027 university-list pages solely
            // to discover detail URLs; completed detail documents are still skipped.
            if (plan.familyKey.contains("/ucp/uvt/uni/univView.do") && plan.requestedYear == 2027) {
                val discoveryPages = (2..plan.totalPages).toList()
                pages.addAll(discoveryPages)
                batchUniversityDiscoveryPagesScheduled += discoveryPages.size
            }

            val sortedPages = pages.distinct().sorted()
            batchLocalResumePlans += 1
            batchLocalPagesScheduled += sortedPages.size
            batchLocalPagesSkipped += (plan.totalPages - 1 - sortedPages.size).coerceAtLeast(0)
            status.text = "Local audit/resume: ${sortedPages.size}쪽 수집 / 증거누락 ${evidenceMissing.size}쪽 / 대학상세 발견 ${batchUniversityDiscoveryPagesScheduled}쪽"
            enqueuePageActions(baseUrl, plan, sortedPages)
            return
        }
        if (!cloudOffload.isConfigured()) {
            enqueuePageActions(baseUrl, plan, (2..plan.totalPages).toList())
            return
        }

        batchCloudPlansPending += 1
        cloudOffload.resumePlan(plan.familyKey, plan.requestedYear, plan.totalPages) { result ->
            runOnUiThread {
                batchCloudPlansPending = (batchCloudPlansPending - 1).coerceAtLeast(0)
                if (!batchRunning) return@runOnUiThread

                val response = result.getOrNull()
                val pages = linkedSetOf<Int>()
                if (response != null && !(response.optBoolean("truncated", false) && plan.totalPages > 500)) {
                    val missing = response.optJSONArray("missing") ?: JSONArray()
                    for (i in 0 until missing.length()) {
                        val page = missing.optInt(i, -1)
                        if (page in 2..plan.totalPages) pages.add(page)
                    }
                    val retry = response.optJSONArray("retry") ?: JSONArray()
                    for (i in 0 until retry.length()) {
                        val page = retry.optJSONObject(i)?.optInt("page", -1) ?: -1
                        if (page in 2..plan.totalPages) pages.add(page)
                    }
                    val deferred = response.optJSONArray("deferred") ?: JSONArray()
                    batchCloudResumePlans += 1
                    batchCloudPagesScheduled += pages.size
                    batchCloudPagesDeferred += deferred.length()
                    val skipped = (plan.totalPages - 1 - pages.size).coerceAtLeast(0)
                    batchCloudPagesSkipped += skipped
                    status.text = if (deferred.length() > 0) {
                        "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 건너뜀 / 서버오류 ${deferred.length()}쪽 보류"
                    } else {
                        "Cloud resume: ${pages.size}쪽 재수집 / ${skipped}쪽 완료로 건너뜀"
                    }
                    enqueuePageActions(baseUrl, plan, pages.sorted())
                } else {
                    val fallback = (2..plan.totalPages).toList()
                    enqueuePageActions(baseUrl, plan, fallback)
                    status.text = "Cloud resume 확인 실패: 전체 페이지 안전 수집으로 전환"
                }

                handler.postDelayed({ loadNextBatchPage() }, 120)
            }
        }
    }

    private fun enqueuePageActions(baseUrl: String, plan: PaginationPlan, pages: Collection<Int>) {
        for (page in pages) {
            if (page !in 2..plan.totalPages) continue
            val action = BatchPageAction(
                baseUrl = baseUrl,
                page = page,
                familyKey = plan.familyKey,
                requestedYear = plan.requestedYear,
                totalPages = plan.totalPages,
                pageSize = plan.pageSize,
                totalItems = plan.totalItems
            )
            val key = pageActionKey(action)
            if (batchPageActionVisited.contains(key) || batchPageActionFailed.contains(key)) continue
            if (batchPageActionQueued.add(key)) batchPageActions.addLast(action)
        }
    }

    private fun duplicateYearViewOf(plan: PaginationPlan): Int? {
        val previous = batchListFingerprints[plan.familyKey] ?: return null
        val year = plan.requestedYear ?: return null
        val previousYear = previous.requestedYear ?: return null
        if (year >= previousYear) return null
        val identical = previous.totalItems == plan.totalItems &&
            previous.pageSize == plan.pageSize &&
            previous.fingerprint == plan.firstPageFingerprint
        return if (identical) previousYear else null
    }

    private fun registerListFingerprint(plan: PaginationPlan) {
        val current = batchListFingerprints[plan.familyKey]
        val incoming = ListFingerprint(
            requestedYear = plan.requestedYear,
            totalItems = plan.totalItems,
            pageSize = plan.pageSize,
            fingerprint = plan.firstPageFingerprint
        )
        if (current == null) {
            batchListFingerprints[plan.familyKey] = incoming
            return
        }
        val currentYear = current.requestedYear
        val incomingYear = incoming.requestedYear
        if (currentYear == null || (incomingYear != null && incomingYear > currentYear)) {
            batchListFingerprints[plan.familyKey] = incoming
        }
    }

    private fun stripNavigationLinksForExport(snapshot: JSONObject): JSONObject {
        val copy = JSONObject(snapshot.toString())
        copy.remove("navigationLinks")
        copy.remove("pageActions")
        copy.remove("navigationKey")
        return copy
    }

    private fun isBatchNavigableProviderUrl(url: String): Boolean = currentAdapter().isBatchNavigable(url)

    private fun isProviderUrl(url: String): Boolean = currentAdapter().accepts(url)

    private fun safeDisplayUrl(url: String): String {
        return try {
            val u = Uri.parse(url)
            buildString {
                append(u.scheme ?: "https")
                append("://")
                append(u.host ?: "")
                append(u.path ?: "")
            }
        } catch (_: Exception) {
            url.substringBefore('?')
        }
    }

    private fun decodeJsString(encoded: String?): String {
        if (encoded == null || encoded == "null") return "{}"
        return (JSONTokener(encoded).nextValue() as? String) ?: "{}"
    }

    private fun showPreview(json: String) {
        preview.text = if (json.length <= PREVIEW_LIMIT) json else {
            json.take(PREVIEW_LIMIT) + "\n\n… 미리보기 생략 (${json.length - PREVIEW_LIMIT}자). JSON 저장 시 전체 데이터가 저장됩니다."
        }
    }

    private fun saveJson() {
        val candidateSession = unifiedSessionId ?: localStore.latestUnifiedSession()
        val useUnifiedStream = candidateSession?.let {
            val s = localStore.unifiedStatus(it)
            s.optString("status") in setOf("running", "completed")
        } ?: false
        pendingUnifiedExportSessionId = if (useUnifiedStream) candidateSession else null

        if (!useUnifiedStream && lastJson.isBlank()) {
            Toast.makeText(this, "먼저 페이지 또는 일괄 수집을 실행하세요.", Toast.LENGTH_SHORT).show()
            return
        }
        val intent = Intent(Intent.ACTION_CREATE_DOCUMENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "application/json"
            val prefix = if (useUnifiedStream) "admission-unified" else "admission-${provider.wireName}"
            putExtra(Intent.EXTRA_TITLE, "$prefix-v${VERSION}-${System.currentTimeMillis()}.json")
        }
        startActivityForResult(intent, SAVE_JSON_REQUEST)
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        if (requestCode == SAVE_JSON_REQUEST && resultCode == RESULT_OK) {
            val uri: Uri = data?.data ?: return
            val streamSession = pendingUnifiedExportSessionId
            pendingUnifiedExportSessionId = null
            status.text = if (streamSession != null) "통합 JSON 스트리밍 저장 중…" else "JSON 저장 중…"
            Thread {
                val result = runCatching {
                    contentResolver.openOutputStream(uri)?.bufferedWriter()?.use { writer ->
                        if (streamSession != null) localStore.writeUnifiedExport(streamSession, writer)
                        else writer.write(lastJson)
                    } ?: error("output-stream-unavailable")
                }
                runOnUiThread {
                    status.text = if (result.isSuccess) {
                        if (streamSession != null) "통합 JSON 스트리밍 저장 완료" else "JSON 저장 완료"
                    } else {
                        "JSON 저장 실패: ${result.exceptionOrNull()?.javaClass?.simpleName ?: "unknown"}"
                    }
                }
            }.start()
        }
    }

    override fun onResume() {
        super.onResume()
        handler.removeCallbacks(sessionKeepAlive)
        handler.postDelayed(sessionKeepAlive, 45_000L)
    }

    override fun onPause() {
        handler.removeCallbacks(sessionKeepAlive)
        if (unifiedRunning || batchRunning || startupLoginPreflightActive || jinhakTransitionAuthGateActive) {
            handler.postDelayed(sessionKeepAlive, 5_000L)
        }
        CookieManager.getInstance().flush()
        super.onPause()
    }

    override fun onStop() {
        CookieManager.getInstance().flush()
        super.onStop()
    }

    @Deprecated("Deprecated in Java")
    override fun onBackPressed() {
        if (webView.canGoBack()) webView.goBack() else super.onBackPressed()
    }

    override fun onDestroy() {
        if (::slowLanePool.isInitialized) slowLanePool.destroy()
        handler.removeCallbacksAndMessages(null)
        CookieManager.getInstance().flush()
        stopCollectionKeepAlive()
        cloudOffload.shutdown()
        localStore.close()
        if (::webView.isInitialized) {
            webView.stopLoading()
            webView.destroy()
        }
        super.onDestroy()
    }
}
