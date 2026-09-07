from pathlib import Path
import re

ROOT = Path('.')
MAIN = ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
POLICY = ROOT / 'app/src/main/java/com/admissionhub/collector/hub/HubFirstLayoutPolicy.kt'
TEST = ROOT / 'app/src/test/java/com/admissionhub/collector/hub/HubFirstLayoutPolicyTest.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly one match, found {count}')
    return text.replace(old, new, 1)

main = MAIN.read_text()
gradle = GRADLE.read_text()
manifest = MANIFEST.read_text()

for token in [
    'private const val VERSION = "0.11.0"',
    'private const val BUILD_CODE = 111000',
    'private lateinit var hubDashboardScroll: HorizontalScrollView',
    'private fun renderHubDashboard(model: JSONObject)',
    'private fun startPreferredHubCollection()',
    'private fun runLocalRebindOnly(trigger: String)',
]:
    if token not in main:
        raise SystemExit('v0.11.0 precondition failed: ' + token)
if 'versionCode = 111000' not in gradle or 'versionName = "0.11.0"' not in gradle:
    raise SystemExit('v0.11.0 Gradle precondition failed')
if 'Admission Hub v0.11 Six-Card Dashboard' not in manifest:
    raise SystemExit('v0.11.0 manifest precondition failed')

POLICY.parent.mkdir(parents=True, exist_ok=True)
TEST.parent.mkdir(parents=True, exist_ok=True)

POLICY.write_text(r'''package com.admissionhub.collector.hub

/** Pure responsive layout policy for the user-facing Hub. */
object HubFirstLayoutPolicy {
    fun columnsForWidthDp(widthDp: Int): Int = when {
        widthDp >= 900 -> 3
        widthDp >= 600 -> 2
        else -> 1
    }

    fun rowsForSix(widthDp: Int): Int {
        val columns = columnsForWidthDp(widthDp)
        return (6 + columns - 1) / columns
    }

    fun cardHeightDp(widthDp: Int): Int = when (columnsForWidthDp(widthDp)) {
        3 -> 164
        2 -> 176
        else -> 188
    }

    const val advancedToolsInitiallyVisible = false
}
''')

TEST.write_text(r'''package com.admissionhub.collector.hub

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class HubFirstLayoutPolicyTest {
    @Test
    fun usesThreeColumnsOnWideTablet() {
        assertEquals(3, HubFirstLayoutPolicy.columnsForWidthDp(1200))
        assertEquals(2, HubFirstLayoutPolicy.rowsForSix(1200))
        assertEquals(164, HubFirstLayoutPolicy.cardHeightDp(1200))
    }

    @Test
    fun degradesResponsivelyWithoutHorizontalSixCardStrip() {
        assertEquals(2, HubFirstLayoutPolicy.columnsForWidthDp(700))
        assertEquals(3, HubFirstLayoutPolicy.rowsForSix(700))
        assertEquals(1, HubFirstLayoutPolicy.columnsForWidthDp(420))
        assertEquals(6, HubFirstLayoutPolicy.rowsForSix(420))
    }

    @Test
    fun advancedCollectorToolsAreCollapsedByDefault() {
        assertFalse(HubFirstLayoutPolicy.advancedToolsInitiallyVisible)
    }
}
''')

main = main.replace('import android.widget.HorizontalScrollView\n', '')
main = replace_once(
    main,
    'import com.admissionhub.collector.hub.HubDashboardModel\n',
    'import com.admissionhub.collector.hub.HubDashboardModel\nimport com.admissionhub.collector.hub.HubFirstLayoutPolicy\n',
    'layout policy import'
)
main = replace_once(
    main,
    '''    private lateinit var hubDashboardStatus: TextView
    private lateinit var hubDashboardScroll: HorizontalScrollView
    private val hubDashboardCards = mutableListOf<TextView>()
''',
    '''    private lateinit var hubDashboardStatus: TextView
    private lateinit var hubDashboardGrid: LinearLayout
    private lateinit var hubAdvancedPanel: LinearLayout
    private lateinit var hubAdvancedToggle: Button
    private val hubDashboardCards = mutableListOf<TextView>()
''',
    'dashboard fields'
)

main = replace_once(main, 'private const val VERSION = "0.11.0"', 'private const val VERSION = "0.11.1"', 'version')
main = replace_once(main, 'private const val BUILD_CODE = 111000', 'private const val BUILD_CODE = 111010', 'build code')

gradle = replace_once(gradle, 'versionCode = 111000', 'versionCode = 111010', 'gradle code')
gradle = replace_once(gradle, 'versionName = "0.11.0"', 'versionName = "0.11.1"', 'gradle name')
manifest = replace_once(
    manifest,
    'android:label="Admission Hub v0.11 Six-Card Dashboard"',
    'android:label="Admission Hub v0.11.1 Hub-First Dashboard"',
    'manifest label'
)

old_banner = '''        hubDashboardStatus = TextView(this).apply {
            text = "대시보드 상태를 불러오는 중…"
            textSize = 16f
            setPadding(dp(12), dp(10), dp(12), dp(10))
            setOnClickListener { refreshHubDashboardFromStore("manual-banner-refresh") }
        }
'''
new_banner = '''        hubDashboardStatus = TextView(this).apply {
            text = "대시보드 상태를 불러오는 중…"
            textSize = 17f
            gravity = Gravity.CENTER_VERTICAL
            setTextColor(android.graphics.Color.WHITE)
            setBackgroundColor(android.graphics.Color.rgb(37, 52, 78))
            setPadding(dp(16), dp(12), dp(16), dp(12))
            setOnClickListener { refreshHubDashboardFromStore("manual-banner-refresh") }
        }
'''
main = replace_once(main, old_banner, new_banner, 'dashboard banner')

card_pattern = re.compile(
    r'''        val dashboardCardRow = LinearLayout\(this\)\.apply \{.*?        hubDashboardScroll = HorizontalScrollView\(this\)\.apply \{\n            isHorizontalScrollBarEnabled = true\n            addView\(dashboardCardRow\)\n        \}\n''',
    re.S,
)
card_replacement = '''        val dashboardWidthDp = resources.configuration.screenWidthDp.takeIf { it > 0 } ?: 720
        val dashboardColumns = HubFirstLayoutPolicy.columnsForWidthDp(dashboardWidthDp)
        val dashboardCardHeight = dp(HubFirstLayoutPolicy.cardHeightDp(dashboardWidthDp))
        hubDashboardGrid = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(dp(6), dp(6), dp(6), dp(8))
        }
        hubDashboardCards.clear()
        var cardIndex = 0
        while (cardIndex < 6) {
            val row = LinearLayout(this).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.TOP
            }
            repeat(dashboardColumns) {
                if (cardIndex < 6) {
                    val index = cardIndex
                    val card = TextView(this).apply {
                        text = "${index + 1}. 지원안 데이터 준비 중"
                        textSize = 16f
                        gravity = Gravity.TOP
                        minHeight = dashboardCardHeight
                        setPadding(dp(14), dp(14), dp(14), dp(14))
                        isClickable = true
                        isFocusable = true
                        setBackgroundColor(android.graphics.Color.rgb(246, 246, 246))
                        setOnClickListener { showHubDashboardCard(index + 1) }
                    }
                    hubDashboardCards.add(card)
                    row.addView(card, LinearLayout.LayoutParams(0, dashboardCardHeight, 1f).apply {
                        setMargins(dp(5), dp(5), dp(5), dp(5))
                    })
                    cardIndex += 1
                } else {
                    row.addView(View(this), LinearLayout.LayoutParams(0, dashboardCardHeight, 1f).apply {
                        setMargins(dp(5), dp(5), dp(5), dp(5))
                    })
                }
            }
            hubDashboardGrid.addView(row, LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT,
                LinearLayout.LayoutParams.WRAP_CONTENT
            ))
        }
'''
main, count = card_pattern.subn(card_replacement, main, count=1)
if count != 1:
    raise SystemExit(f'dashboard card strip replacement expected 1 match, found {count}')

old_root = '''        root.addView(tabs)
        root.addView(sessionRow)
        root.addView(actions1)
        root.addView(actions2)
        root.addView(actions3)
        root.addView(hubRow)
        root.addView(hubDashboardStatus)
        root.addView(hubDashboardScroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT))
        root.addView(status)
        root.addView(browserStack, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 3f))
        root.addView(scroll, LinearLayout.LayoutParams(LinearLayout.LayoutParams.MATCH_PARENT, 0, 2f))
        setContentView(root)
'''
new_root = '''        // Hub-first: the daily-use surface is status + six applications. Collector controls remain available,
        // but are deliberately collapsed behind an explicit advanced-tools action.
        actions3.removeView(unifiedButton)
        hubRow.removeView(hubManageButton)
        hubRow.removeView(hubRecoveryButton)

        val primaryActions = LinearLayout(this).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            setPadding(dp(4), dp(6), dp(4), dp(6))
        }
        primaryActions.addView(unifiedButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        primaryActions.addView(hubManageButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        primaryActions.addView(hubRecoveryButton, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))
        hubAdvancedToggle = Button(this).apply {
            text = "고급 도구"
        }
        primaryActions.addView(hubAdvancedToggle, LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, 1f))

        hubAdvancedPanel = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            visibility = if (HubFirstLayoutPolicy.advancedToolsInitiallyVisible) View.VISIBLE else View.GONE
            setPadding(dp(4), dp(4), dp(4), dp(8))
        }
        hubAdvancedPanel.addView(tabs)
        hubAdvancedPanel.addView(sessionRow)
        hubAdvancedPanel.addView(actions1)
        hubAdvancedPanel.addView(actions2)
        hubAdvancedPanel.addView(actions3)
        hubAdvancedPanel.addView(hubRow)
        hubAdvancedPanel.addView(status)
        hubAdvancedPanel.addView(browserStack, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            dp(320)
        ))
        hubAdvancedPanel.addView(scroll, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            dp(180)
        ))
        hubAdvancedToggle.setOnClickListener {
            val opening = hubAdvancedPanel.visibility != View.VISIBLE
            hubAdvancedPanel.visibility = if (opening) View.VISIBLE else View.GONE
            hubAdvancedToggle.text = if (opening) "고급 도구 닫기" else "고급 도구"
        }

        root.addView(hubDashboardStatus)
        root.addView(primaryActions)
        root.addView(hubDashboardGrid, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ))
        root.addView(hubAdvancedPanel, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        ))
        setContentView(root)
'''
main = replace_once(main, old_root, new_root, 'Hub-first root composition')

# Make the single Hub banner authoritative even when advanced diagnostics are expanded.
status_anchor = '''        hubDashboardStatus.text = "${sync.optString("stateLabel", "대기")} · ${sync.optString("progressText", "진행 수치 대기")}$ageText\n지원 6장 ${summary.optInt("resolvable", 0)}/6 · 핵심자료 ${summary.optInt("fullCoreCoverage", 0)}/6 · $qualityText"

        val cards = model.optJSONArray("cards") ?: JSONArray()
'''
status_replacement = '''        hubDashboardStatus.text = "${sync.optString("stateLabel", "대기")} · ${sync.optString("progressText", "진행 수치 대기")}$ageText\n지원 6장 ${summary.optInt("resolvable", 0)}/6 · 핵심자료 ${summary.optInt("fullCoreCoverage", 0)}/6 · $qualityText"
        if (::sessionState.isInitialized) {
            sessionState.text = "통합 상태: ${sync.optString("stateLabel", "대기")} · ${sync.optString("progressText", "진행 수치 대기")}$ageText"
        }
        if (::hubState.isInitialized) {
            hubState.text = "지원 6장 ${summary.optInt("resolvable", 0)}/6 · 핵심자료 ${summary.optInt("fullCoreCoverage", 0)}/6 · $qualityText"
        }

        val cards = model.optJSONArray("cards") ?: JSONArray()
'''
main = replace_once(main, status_anchor, status_replacement, 'authoritative status mirror')

style_anchor = '''            val occupied = card.optBoolean("occupied", false)
            val resolvable = card.optBoolean("resolvable", false)
            view.text = when {
'''
style_replacement = '''            val occupied = card.optBoolean("occupied", false)
            val resolvable = card.optBoolean("resolvable", false)
            val qualityState = card.optString("qualityState", "unknown")
            view.setBackgroundColor(when {
                !occupied -> android.graphics.Color.rgb(247, 247, 247)
                !resolvable -> android.graphics.Color.rgb(255, 239, 239)
                qualityState == "accepted" -> android.graphics.Color.rgb(236, 247, 239)
                qualityState == "provisional" -> android.graphics.Color.rgb(255, 249, 226)
                qualityState == "provider-only" -> android.graphics.Color.rgb(242, 244, 247)
                else -> android.graphics.Color.rgb(246, 246, 246)
            })
            view.setTextColor(android.graphics.Color.rgb(32, 36, 43))
            view.text = when {
'''
main = replace_once(main, style_anchor, style_replacement, 'card quality styling')

# Give cards enough visual hierarchy for the upcoming score/decision layer.
main = replace_once(
    main,
    '''                    "${index + 1}. $university\n$department\n$subtitle\n\n$capacity · $coverage\n$official"
''',
    '''                    "${index + 1}. $university\n$department\n$subtitle\n\n$capacity\n$coverage\n$official"
''',
    'card text hierarchy'
)

MAIN.write_text(main)
GRADLE.write_text(gradle)
MANIFEST.write_text(manifest)

checks = {
    'version': 'private const val VERSION = "0.11.1"' in main and 'private const val BUILD_CODE = 111010' in main,
    'hub-first-grid': 'hubDashboardGrid' in main and 'HubFirstLayoutPolicy.columnsForWidthDp' in main,
    'advanced-collapsed': 'hubAdvancedPanel' in main and '고급 도구 닫기' in main,
    'primary-actions': 'primaryActions.addView(unifiedButton' in main and 'primaryActions.addView(hubManageButton' in main,
    'legacy-status-mirrored': '통합 상태:' in main,
    'webview-collapsed': 'hubAdvancedPanel.addView(browserStack' in main,
    'local-rebind-preserved': 'runLocalRebindOnly' in main and 'localRebindDecision' in main,
    'selected-six-preserved': 'startSelectedSixRecovery' in main,
    'no-auto-six': 'autoSelectTopSix' not in main,
}
failed = [k for k, v in checks.items() if not v]
if failed:
    raise SystemExit('v0.11.1 postcondition failure: ' + ', '.join(failed))
print('v0.11.1 Hub-first responsive dashboard patch applied')
