from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
collector = ROOT / "app/src/main/java/com/admissionhub/collector/competition/CompetitionBrowserCollector.kt"
policy = ROOT / "app/src/main/java/com/admissionhub/collector/competition/CompetitionBrowserPolicy.kt"
main = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
gradle = ROOT / "app/build.gradle.kts"
manifest = ROOT / "app/src/main/AndroidManifest.xml"

def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        return text
    if old not in text:
        raise SystemExit(f"missing patch anchor: {label}")
    return text.replace(old, new, 1)

c = collector.read_text()
c = replace_once(
    c,
    "import android.app.Activity\n",
    "import android.app.Activity\nimport android.app.AlertDialog\n",
    "AlertDialog import",
)
c = replace_once(
    c,
    "import android.webkit.CookieManager\n",
    "import android.webkit.CookieManager\nimport android.webkit.WebChromeClient\n",
    "WebChromeClient import",
)
c = replace_once(
    c,
    "    private var challengeChecks = 0\n    private var pageGeneration = 0\n",
    "    private var challengeChecks = 0\n    private var challengeDialog: AlertDialog? = null\n    private var challengeVisibleSinceMs = 0L\n    private var pageGeneration = 0\n",
    "challenge fields",
)
c = replace_once(
    c,
    "        running = false\n        pageGeneration += 1\n        handler.removeCallbacksAndMessages(null)\n        webView?.let { view ->\n",
    "        running = false\n        pageGeneration += 1\n        handler.removeCallbacksAndMessages(null)\n        challengeDialog?.setOnCancelListener(null)\n        challengeDialog?.dismiss()\n        challengeDialog = null\n        challengeVisibleSinceMs = 0L\n        webView?.let { view ->\n",
    "destroy challenge dialog",
)
c = replace_once(
    c,
    "        challengeChecks = 0\n        val generation = ++pageGeneration\n",
    "        challengeChecks = 0\n        challengeVisibleSinceMs = 0L\n        val generation = ++pageGeneration\n",
    "reset challenge clock",
)
old_challenge = '''            if (payload.optBoolean("challenge", false)) {
                challengeChecks += 1
                if (challengeChecks <= CompetitionBrowserPolicy.MAX_CHALLENGE_RECHECKS) {
                    onStatus("경쟁률 수집 · ${target.university} 브라우저 안전 접속 확인 대기")
                    handler.postDelayed(
                        { probeRenderedPage(target, generation) },
                        CompetitionBrowserPolicy.CHALLENGE_RECHECK_MS,
                    )
                } else {
                    onStatus("경쟁률 수집 · ${target.university} 안전 접속 확인 미해제 · 이번 주기 건너뜀")
                    moveNextTarget()
                }
                return@evaluateJavascript
            }
'''
new_challenge = '''            if (payload.optBoolean("challenge", false)) {
                challengeChecks += 1
                if (challengeVisibleSinceMs == 0L) challengeVisibleSinceMs = System.currentTimeMillis()
                if (challengeDialog == null) showChallengeDialog(target, generation)
                val elapsed = System.currentTimeMillis() - challengeVisibleSinceMs
                if (elapsed < CompetitionBrowserPolicy.USER_CHALLENGE_TIMEOUT_MS) {
                    onStatus("경쟁률 수집 · ${target.university} 사용자 안전 접속 확인 필요")
                    handler.postDelayed(
                        { probeRenderedPage(target, generation) },
                        CompetitionBrowserPolicy.CHALLENGE_VISIBLE_RECHECK_MS,
                    )
                } else {
                    onStatus("경쟁률 수집 · ${target.university} 안전 접속 확인 시간 초과 · 이번 주기 건너뜀")
                    restoreHiddenWebView()
                    moveNextTarget()
                }
                return@evaluateJavascript
            }

            if (challengeDialog != null) {
                restoreHiddenWebView()
                onStatus("경쟁률 수집 · ${target.university} 안전 접속 확인 완료 · 공개 표 분석 중")
            }
'''
c = replace_once(c, old_challenge, new_challenge, "visible challenge flow")

anchor = '''    private fun moveNextTarget() {
        if (destroyed || !running) return
        pageGeneration += 1
        webView?.stopLoading()
        activeTargetIndex += 1
        handler.postDelayed({ loadActiveTarget() }, 500L)
    }
'''
insert = '''    private fun showChallengeDialog(target: CompetitionBrowserTarget, generation: Int) {
        if (destroyed || !running || generation != pageGeneration || challengeDialog != null) return
        val view = webView ?: return
        (view.parent as? ViewGroup)?.removeView(view)
        val container = FrameLayout(activity).apply {
            minimumHeight = (resources.displayMetrics.heightPixels * 0.68f).toInt()
            setPadding(12, 12, 12, 12)
        }
        container.addView(
            view,
            FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT,
            ),
        )
        val dialog = AlertDialog.Builder(activity)
            .setTitle("${target.university} · 안전 접속 확인")
            .setMessage(
                "진학어플라이가 사용자 브라우저 확인을 요구합니다. 아래 페이지에서 정상 보안 확인을 완료하면 경쟁률 표를 자동으로 읽고 이 창을 닫습니다. 로그인 정보·쿠키·세션 값은 서버로 전송하지 않습니다."
            )
            .setView(container)
            .setNegativeButton("이번 대학 건너뛰기", null)
            .create()
        challengeDialog = dialog
        dialog.setOnCancelListener {
            if (challengeDialog === dialog && !destroyed && running && generation == pageGeneration) {
                challengeDialog = null
                reattachToHiddenHost()
                onStatus("경쟁률 수집 · ${target.university} 사용자 확인 취소 · 이번 주기 건너뜀")
                moveNextTarget()
            }
        }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_NEGATIVE)?.setOnClickListener {
                if (!destroyed && running && generation == pageGeneration) {
                    restoreHiddenWebView()
                    onStatus("경쟁률 수집 · ${target.university} 사용자 선택으로 이번 주기 건너뜀")
                    moveNextTarget()
                }
            }
        }
        dialog.show()
        dialog.window?.setLayout(
            ViewGroup.LayoutParams.MATCH_PARENT,
            (activity.resources.displayMetrics.heightPixels * 0.90f).toInt(),
        )
        onStatus("경쟁률 수집 · ${target.university} 안전 접속 확인 창 표시")
    }

    private fun restoreHiddenWebView() {
        val dialog = challengeDialog
        challengeDialog = null
        challengeVisibleSinceMs = 0L
        dialog?.setOnCancelListener(null)
        reattachToHiddenHost()
        dialog?.dismiss()
    }

    private fun reattachToHiddenHost() {
        val view = webView ?: return
        (view.parent as? ViewGroup)?.removeView(view)
        if (!destroyed) {
            host.addView(
                view,
                FrameLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT,
                    ViewGroup.LayoutParams.MATCH_PARENT,
                ),
            )
        }
    }

    private fun moveNextTarget() {
        if (destroyed || !running) return
        restoreHiddenWebView()
        pageGeneration += 1
        webView?.stopLoading()
        activeTargetIndex += 1
        handler.postDelayed({ loadActiveTarget() }, 500L)
    }
'''
c = replace_once(c, anchor, insert, "challenge dialog methods")
c = replace_once(
    c,
    "        view.webViewClient = object : WebViewClient() {\n",
    "        view.webChromeClient = WebChromeClient()\n        view.webViewClient = object : WebViewClient() {\n",
    "WebChromeClient wiring",
)
collector.write_text(c)

p = policy.read_text()
p = replace_once(
    p,
    "    const val CHALLENGE_RECHECK_MS = 2_500L\n    const val MAX_CHALLENGE_RECHECKS = 6\n",
    "    const val CHALLENGE_RECHECK_MS = 2_500L\n    const val MAX_CHALLENGE_RECHECKS = 6\n    const val CHALLENGE_VISIBLE_RECHECK_MS = 1_500L\n    const val USER_CHALLENGE_TIMEOUT_MS = 180_000L\n",
    "visible challenge policy",
)
policy.write_text(p)

m = main.read_text()
m = m.replace('private const val VERSION = "0.13.1"', 'private const val VERSION = "0.13.3"')
m = m.replace('private const val BUILD_CODE = 113100', 'private const val BUILD_CODE = 113300')
main.write_text(m)

g = gradle.read_text().replace('versionCode = 113100', 'versionCode = 113300').replace('versionName = "0.13.1"', 'versionName = "0.13.3"')
gradle.write_text(g)

x = manifest.read_text().replace('Admission Hub v0.13.1 Live Competition', 'Admission Hub v0.13.3 Jinhak Visible Verify')
manifest.write_text(x)

print('v0.13.3 visible Jinhak challenge patch applied')
