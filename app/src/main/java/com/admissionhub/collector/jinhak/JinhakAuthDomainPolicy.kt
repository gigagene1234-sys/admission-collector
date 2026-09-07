package com.admissionhub.collector.jinhak

/**
 * Pure decision policy for v0.10.2 auth-domain separation.
 *
 * A provider-wide login failure and a target-specific redirect are different domains.
 * A repeated redirect for the same target after a recent protected-core proof is therefore
 * quarantined as a target failure instead of forcing another global re-authentication cycle.
 */
object JinhakAuthDomainPolicy {
    enum class RedirectDecision { GLOBAL_REAUTH, TARGET_QUARANTINE }

    fun redirectDecision(
        redirectCycles: Int,
        threshold: Int,
        protectedCoreFresh: Boolean
    ): RedirectDecision = if (
        protectedCoreFresh && threshold > 0 && redirectCycles >= threshold
    ) RedirectDecision.TARGET_QUARANTINE else RedirectDecision.GLOBAL_REAUTH

    /** Never drop an active mission owner merely because a report/generic action has no ledger id. */
    fun preserveMissionOwner(currentOwner: String?, candidateLedgerTarget: String?): String? =
        candidateLedgerTarget ?: currentOwner

    /** Generic exploration is legal only after all persistent mission work is terminal. */
    fun allowGenericNavigation(missionOutstanding: Int): Boolean = missionOutstanding <= 0
}
