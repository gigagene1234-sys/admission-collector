package com.admissionhub.collector.jinhak

import java.net.URI

/**
 * v0.18.5 Jinhak runtime contract.
 *
 * Admission Hub does not own Jinhak authentication, credentials, auth proof, or session restore.
 * The user navigates the official site manually. Automation is armed only after the protected
 * Susi saved-application repository is already visible in the foreground WebView.
 *
 * From that point, autonomous navigation is application-centric rather than site-centric:
 * storage card -> same-card report action -> read-only report tabs -> return to storage.
 */
object JinhakManualStorageReportPolicy {
    const val ENABLED = true
    const val STORAGE_PATH = "/jh/high3/early/four-year-university/library"
    const val REPORT_PREFIX = "/jh/high3/early/four-year-university/report/"
    const val AUTH_OWNERSHIP = "user-browser-only"
    const val AUTO_LOGIN = false
    const val APP_SESSION_RESTORE = false
    const val AUTH_PROOF_CACHE = false
    const val GENERIC_SITE_CRAWL = false

    private val destructive = Regex(
        "원서\\s*접수|결제|구매|저장|삭제|탈퇴|로그아웃|회원정보|수정|등록|전송|제출|확정|취소|신청|지원하기|장바구니|쿠폰|동의|미동의",
        RegexOption.IGNORE_CASE
    )

    private val reportAction = Regex(
        "합격\\s*예측|합격\\s*안정성|모의\\s*지원|지원자\\s*분포|실제\\s*합격자|과거\\s*입시결과|입시\\s*결과|성적\\s*분석|성적\\s*산출|환산\\s*점수|리포트",
        RegexOption.IGNORE_CASE
    )

    fun isStorageEntry(rawUrl: String?): Boolean = path(rawUrl).trimEnd('/') == STORAGE_PATH

    fun isReportUrl(rawUrl: String?): Boolean = path(rawUrl).startsWith(REPORT_PREFIX)

    fun isAllowedMissionUrl(rawUrl: String?): Boolean = isStorageEntry(rawUrl) || isReportUrl(rawUrl)

    fun isReportActionLabel(label: String): Boolean {
        val normalized = label.replace(Regex("\\s+"), " ").trim()
        return normalized.isNotBlank() && !destructive.containsMatchIn(normalized) && reportAction.containsMatchIn(normalized)
    }

    fun shouldPromoteAction(rawUrl: String?, label: String, hasBoundApplication: Boolean): Boolean {
        if (!isReportActionLabel(label)) return false
        return when {
            isStorageEntry(rawUrl) -> hasBoundApplication
            isReportUrl(rawUrl) -> true
            else -> false
        }
    }

    fun stopReasonFor(rawUrl: String?): String = when {
        rawUrl.isNullOrBlank() -> "blank-route"
        isStorageEntry(rawUrl) -> "storage-ready"
        isReportUrl(rawUrl) -> "report-route"
        else -> "outside-storage-report-scope"
    }

    private fun path(rawUrl: String?): String {
        val value = rawUrl.orEmpty().trim()
        if (value.isBlank()) return ""
        return runCatching { URI(value).path.orEmpty().lowercase().replace('\\', '/') }.getOrDefault("")
    }
}
