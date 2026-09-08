package com.admissionhub.collector.jinhak

/**
 * Pure event classifier for Jinhak authentication.
 *
 * This state model has no WebView, DOM, timer, or navigation side effects. MainActivity receives
 * browser navigation events and decides one action from this classification. In particular,
 * lower-grade routes are terminal transport drops and member login is a passive wait state.
 */
object JinhakAuthEventState {
    const val SCHEMA_VERSION = 1

    enum class Event {
        LOWER_GRADE,
        GENERIC_PRODUCT_LOGIN,
        MEMBER_LOGIN,
        HIGH3,
        OTHER_JINHAK
    }

    enum class Action {
        DROP_REQUEST,
        OPEN_CANONICAL_HIGH3_AUTH_ONCE,
        WAIT_FOR_SERVER_RETURN,
        VERIFY_HIGH3_SESSION,
        OBSERVE_WITHOUT_NAVIGATION
    }

    fun classify(url: String): Event = when (JinhakHigh3AuthRoute.decision(url)) {
        JinhakHigh3AuthRoute.MainFrameDecision.BLOCK_LOWER_GRADE -> Event.LOWER_GRADE
        JinhakHigh3AuthRoute.MainFrameDecision.REWRITE_GENERIC_LOGIN -> Event.GENERIC_PRODUCT_LOGIN
        JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_CANONICAL_AUTH -> Event.MEMBER_LOGIN
        JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_HIGH3 -> Event.HIGH3
        JinhakHigh3AuthRoute.MainFrameDecision.ALLOW_OTHER_JINHAK -> Event.OTHER_JINHAK
    }

    fun action(url: String): Action = when (classify(url)) {
        Event.LOWER_GRADE -> Action.DROP_REQUEST
        Event.GENERIC_PRODUCT_LOGIN -> Action.OPEN_CANONICAL_HIGH3_AUTH_ONCE
        Event.MEMBER_LOGIN -> Action.WAIT_FOR_SERVER_RETURN
        Event.HIGH3 -> Action.VERIFY_HIGH3_SESSION
        Event.OTHER_JINHAK -> Action.OBSERVE_WITHOUT_NAVIGATION
    }
}
