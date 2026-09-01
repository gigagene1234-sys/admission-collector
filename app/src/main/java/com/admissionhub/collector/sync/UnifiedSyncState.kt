package com.admissionhub.collector.sync

enum class UnifiedSyncState {
    PRECHECK,
    ADIGA_PUBLIC_SYNC,
    ADIGA_USER_SCORE_SYNC,
    JINHAK_CAPABILITY_DISCOVERY,
    JINHAK_AUTHORIZED_SYNC,
    JINHAK_USER_SESSION_MISSION,
    /** Legacy export compatibility only; new releases do not enter this state. */
    JINHAK_AUTONOMOUS_CRAWL,
    JINHAK_USER_CONSENT_REQUIRED,
    JINHAK_USER_VIEW_FALLBACK,
    CANONICAL_MERGE,
    QUALITY_AUDIT,
    HUB_PUBLISH,
    AUTH_REQUIRED,
    COMPLETE,
    FAILED
}

object UnifiedSyncTransitions {
    private val allowed = mapOf(
        UnifiedSyncState.PRECHECK to setOf(
            UnifiedSyncState.ADIGA_PUBLIC_SYNC,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.ADIGA_PUBLIC_SYNC to setOf(
            UnifiedSyncState.ADIGA_USER_SCORE_SYNC,
            UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.ADIGA_USER_SCORE_SYNC to setOf(
            UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY to setOf(
            UnifiedSyncState.JINHAK_AUTHORIZED_SYNC,
            UnifiedSyncState.JINHAK_USER_SESSION_MISSION,
            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.JINHAK_AUTHORIZED_SYNC to setOf(
            UnifiedSyncState.CANONICAL_MERGE,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.JINHAK_USER_SESSION_MISSION to setOf(
            UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED,
            UnifiedSyncState.CANONICAL_MERGE,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL to setOf(
            UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED,
            UnifiedSyncState.CANONICAL_MERGE,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED to setOf(
            UnifiedSyncState.JINHAK_USER_SESSION_MISSION,
            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,
            UnifiedSyncState.CANONICAL_MERGE,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK to setOf(
            UnifiedSyncState.CANONICAL_MERGE,
            UnifiedSyncState.AUTH_REQUIRED,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.CANONICAL_MERGE to setOf(
            UnifiedSyncState.QUALITY_AUDIT,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.QUALITY_AUDIT to setOf(
            UnifiedSyncState.HUB_PUBLISH,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.HUB_PUBLISH to setOf(
            UnifiedSyncState.COMPLETE,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.AUTH_REQUIRED to setOf(
            UnifiedSyncState.ADIGA_PUBLIC_SYNC,
            UnifiedSyncState.ADIGA_USER_SCORE_SYNC,
            UnifiedSyncState.JINHAK_CAPABILITY_DISCOVERY,
            UnifiedSyncState.JINHAK_AUTHORIZED_SYNC,
            UnifiedSyncState.JINHAK_USER_SESSION_MISSION,
            UnifiedSyncState.JINHAK_AUTONOMOUS_CRAWL,
            UnifiedSyncState.JINHAK_USER_CONSENT_REQUIRED,
            UnifiedSyncState.JINHAK_USER_VIEW_FALLBACK,
            UnifiedSyncState.FAILED
        ),
        UnifiedSyncState.COMPLETE to emptySet(),
        UnifiedSyncState.FAILED to setOf(UnifiedSyncState.PRECHECK)
    )

    fun canMove(from: UnifiedSyncState, to: UnifiedSyncState): Boolean =
        from == to || to in allowed.getValue(from)
}
