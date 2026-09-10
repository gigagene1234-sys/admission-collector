from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MAIN = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = MAIN.read_text()


def one(old: str, new: str, label: str) -> None:
    global text
    count = text.count(old)
    if count == 0 and new in text:
        return
    if count != 1:
        raise SystemExit(f"{label}: expected one old anchor, found {count}")
    text = text.replace(old, new, 1)


def regex_one(pattern: str, repl: str, label: str) -> None:
    global text
    updated, count = re.subn(pattern, repl, text, count=1, flags=re.S)
    if count == 0 and repl.strip() in text:
        return
    if count != 1:
        raise SystemExit(f"{label}: expected one regex match, found {count}")
    text = updated


# Report traversal must win over the old v0.18.3 storage-only monitor.
one(
    "val rawMissionCandidates = if (JinhakStorageCompetitionPolicy.ENABLED) emptyList() else JinhakAgentNavigator.candidates(snapshot)",
    "val rawMissionCandidates = JinhakAgentNavigator.candidates(snapshot)",
    "enable-report-candidates",
)
one(
    '''            val jinhakStorageOnlySnapshot = provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&\n                snapshot.optString("providerPageType") == "jinhak-early-storage"\n            var jinhakExpandOutgoingLinks = !jinhakStorageOnlySnapshot\n            var jinhakAllowAgentAction = !jinhakStorageOnlySnapshot''',
    '''            val jinhakManualReportScope = provider == ProviderId.JINHAK && JinhakManualStorageReportPolicy.ENABLED\n            // v0.18.5 never expands the site's generic link graph. All autonomous movement is\n            // through JinhakAgentNavigator's same-card report actions / report-lane controls.\n            var jinhakExpandOutgoingLinks = !jinhakManualReportScope\n            var jinhakAllowAgentAction = true''',
    "disable-generic-link-expansion",
)
one(
    "jinhakExpandOutgoingLinks = jinhakExpandedNavigationStates.add(expansionIdentity.observationId)",
    "jinhakExpandOutgoingLinks = if (JinhakManualStorageReportPolicy.ENABLED) false else jinhakExpandedNavigationStates.add(expansionIdentity.observationId)",
    "keep-generic-expansion-disabled",
)

old_watch = '''        if (provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&\n            jinhakV0182ProtectedSessionVerified && batchSnapshots.length() > 0) {\n            scheduleV0183StorageCompetitionRefresh()\n            return\n        }'''
new_watch = '''        if (provider == ProviderId.JINHAK && JinhakManualStorageReportPolicy.ENABLED) {\n            // Manual-storage report mode is mission-driven. Do not enter the legacy storage-only\n            // periodic watcher while per-application report targets remain to be processed.\n        } else if (provider == ProviderId.JINHAK && JinhakStorageCompetitionPolicy.ENABLED &&\n            jinhakV0182ProtectedSessionVerified && batchSnapshots.length() > 0) {\n            scheduleV0183StorageCompetitionRefresh()\n            return\n        }'''
if old_watch in text:
    text = text.replace(old_watch, new_watch, 1)
elif new_watch not in text:
    raise SystemExit("disable-storage-only-watcher: anchor missing")

# Jinhak must never be treated as authenticated by the old generic session checker.
one(
    '''        if (provider == ProviderId.JINHAK) {\n            // v0.17.0: Jinhak authentication is server-owned. No DOM/login/logout heuristic is run.\n            callback?.invoke(false, true)\n            return\n        }''',
    '''        if (provider == ProviderId.JINHAK) {\n            // v0.18.5: Admission Hub does not infer Jinhak login state at all.\n            callback?.invoke(false, false)\n            return\n        }''',
    "no-jinhak-auth-inference",
)

# Do not measure, extend, or diagnose a Jinhak session in the keep-alive timer.
one(
    '''            } else if (active && provider == ProviderId.JINHAK) {\n                // v0.17.1: Jinhak session ownership belongs entirely to the user/browser.\n                // This timer records liveness only. It never checks, extends, rewrites, clicks,\n                // restores, captures, or otherwise changes the Jinhak authentication session.\n                jinhakSessionKeepAliveTicks += 1\n                if (!hasWindowFocus()) jinhakSessionKeepAliveBackgroundTicks += 1\n                persistJinhakAuthDiagnostics("user-owned-session-liveness-only")\n            }''',
    '''            } else if (active && provider == ProviderId.JINHAK) {\n                // v0.18.5: no Jinhak session keep-alive, measurement, or auth diagnostic exists.\n                // Browser/provider session behavior is entirely outside Admission Hub.\n            }''',
    "disable-jinhak-session-keepalive",
)

# On app creation, erase Admission Hub-owned Jinhak credential/auth-proof state. Browser cookies are
# deliberately untouched so the user can operate the provider site normally.
one(
    '''        configureWebView()\n        initializeProcessResumeJournal()\n        restoreJinhakAuthProofCheckpoint("activity-create")''',
    '''        configureWebView()\n        initializeProcessResumeJournal()\n        credentialVault.clear(ProviderId.JINHAK.wireName)\n        clearJinhakLegacyAuthState()''',
    "clear-auth-state-on-create",
)

# Auth proof persistence/restoration is converted into destructive cleanup only.
regex_one(
    r'''    private fun persistJinhakAuthProofCheckpoint\(synchronous: Boolean = false\) \{.*?\n    \}\n\n    private fun restoreJinhakAuthProofCheckpoint\(trigger: String\): Boolean \{.*?\n    \}\n\n    private fun initializeProcessResumeJournal''',
    '''    private fun clearJinhakLegacyAuthState() {\n        val prefs = getSharedPreferences(RUNTIME_PREFS, MODE_PRIVATE)\n        prefs.edit()\n            .remove("jinhakAuthProofCollectorVersion")\n            .remove("jinhakRealAuthProbeResult")\n            .remove("jinhakRealAuthProbeVerifiedAtMs")\n            .remove("jinhakLastCoreVerifiedAtMs")\n            .remove("jinhakLastAuthEvidence")\n            .remove("jinhakAuthProofSafePath")\n            .apply()\n        jinhakAuthVerifiedForBatch = false\n        jinhakV0182ProtectedSessionVerified = false\n        jinhakUserSessionConfirmed = false\n        jinhakTransitionAuthGateActive = false\n        jinhakRealAuthProbeActive = false\n        jinhakRealAuthResumeGatePending = false\n        jinhakLastCoreVerifiedAtMs = 0L\n        jinhakRealAuthProbeVerifiedAtMs = 0L\n        jinhakLastAuthEvidence = "manual-browser-no-auth-inference"\n    }\n\n    private fun persistJinhakAuthProofCheckpoint(synchronous: Boolean = false) {\n        clearJinhakLegacyAuthState()\n    }\n\n    private fun restoreJinhakAuthProofCheckpoint(trigger: String): Boolean {\n        clearJinhakLegacyAuthState()\n        return false\n    }\n\n    private fun initializeProcessResumeJournal''',
    "replace-auth-proof-cache",
)

# Runtime checkpoint may persist crawl progress, never Jinhak auth proof.
one(
    '''                .putInt("errorCount", batchErrors.length())\n                .putString("jinhakAuthProofCollectorVersion", VERSION)\n                .putString("jinhakRealAuthProbeResult", jinhakRealAuthProbeResult.take(80))\n                .putLong("jinhakRealAuthProbeVerifiedAtMs", jinhakRealAuthProbeVerifiedAtMs)\n                .putLong("jinhakLastCoreVerifiedAtMs", jinhakLastCoreVerifiedAtMs)\n                .putString("jinhakLastAuthEvidence", jinhakLastAuthEvidence.take(80))\n                .putString("jinhakAuthProofSafePath", runtimeSafePath(webView.url).take(300))\n                .apply()''',
    '''                .putInt("errorCount", batchErrors.length())\n                .remove("jinhakAuthProofCollectorVersion")\n                .remove("jinhakRealAuthProbeResult")\n                .remove("jinhakRealAuthProbeVerifiedAtMs")\n                .remove("jinhakLastCoreVerifiedAtMs")\n                .remove("jinhakLastAuthEvidence")\n                .remove("jinhakAuthProofSafePath")\n                .apply()''',
    "remove-auth-proof-from-runtime-checkpoint",
)

# The old rendered-login guard must not ask for a user-session confirmation after storage is already
# visible. Route scope, not authentication state, is the only Jinhak batch gate.
regex_one(
    r'''    private fun continueBatchAfterRenderedLoginGuard\(url: String, attempt: Int\) \{\n        if \(!batchRunning \|\| batchPausedForLogin\) return\n        if \(provider == ProviderId\.JINHAK\) \{.*?\n            return\n        \}\n        val expectedProvider = provider''',
    '''    private fun continueBatchAfterRenderedLoginGuard(url: String, attempt: Int) {\n        if (!batchRunning || batchPausedForLogin) return\n        if (provider == ProviderId.JINHAK) {\n            val current = webView.url.orEmpty()\n            if (JinhakManualStorageReportPolicy.isAllowedMissionUrl(current)) {\n                scheduleBatchSnapshot()\n            } else {\n                batchPausedForLogin = false\n                stopBatch("jinhak-left-manual-storage-report-scope")\n                sessionState.text = "○ 수시 저장소 직접 재진입 필요"\n                status.text = "진학사 로그인/세션은 Admission Hub가 처리하지 않습니다. 수시 저장소로 직접 돌아오면 리포트 탐색을 다시 시작합니다."\n            }\n            return\n        }\n        val expectedProvider = provider''',
    "remove-session-confirmation-guard",
)

# Remove the user-facing auth-probe control; retain the field only for binary/source compatibility.
regex_one(
    r'''        realJinhakAuthProbeButton = Button\(this\)\.apply \{.*?\n        \}\n        actions3\.addView\(unifiedButton,''',
    '''        realJinhakAuthProbeButton = Button(this).apply {\n            text = "진학사 직접 탐색 안내"\n            setOnClickListener {\n                credentialVault.clear(ProviderId.JINHAK.wireName)\n                clearJinhakLegacyAuthState()\n                sessionState.text = "○ 직접 로그인 · 수시 저장소 대기"\n                status.text = "진학사 사이트에서 직접 로그인하고 수시 저장소까지 이동하세요. 저장소가 열리면 대학·학과별 리포트 탐색을 자동 시작합니다."\n            }\n        }\n        actions3.addView(unifiedButton,''',
    "remove-auth-probe-ui",
)

# Old hidden slow-lane captures must not claim an inferred authenticated state if any compatibility
# callback ever runs. Mission/report evidence remains user-viewed without auth classification.
text = text.replace('authStateClass = "authenticated",', 'authStateClass = "user-viewed-no-auth-inference",')

MAIN.write_text(text)
