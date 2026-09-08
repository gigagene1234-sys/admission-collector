from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "app/src/main/java/com/admissionhub/collector/MainActivity.kt"
text = path.read_text()

old = "(JinhakGradeRouteFence.isHigh3(url) && lane == JinhakMissionLane.UNKNOWN)"
new = "(JinhakGradeRouteFence.isHigh3(url) && lane == com.admissionhub.collector.jinhak.JinhakMissionLane.UNKNOWN)"
if text.count(old) != 1:
    raise SystemExit(f"fully-qualified mission lane patch: expected 1 occurrence, got {text.count(old)}")
text = text.replace(old, new, 1)

old_recovery = '''        handler.postDelayed({
            jinhakV0166LowerGradeRecoveryPending = false
            if (provider != ProviderId.JINHAK) return@postDelayed
            val current = webView.url.orEmpty()
            if (JinhakGradeRouteFence.isBlockedLowerGrade(current) || current.isBlank() || current == "about:blank") {
                webView.visibility = View.INVISIBLE
                recordRuntimeEvent("jinhak-v0166-return-to-protected-high3", JSONObject()
                    .put("source", source.take(80))
                    .put("coreSafePath", runtimeSafePath(high3Core))
                    .put("automaticLowerGradeFollow", false))
                webView.loadUrl(high3Core)
            } else if (isProviderLoginUrl(ProviderId.JINHAK, current)) {
                // Login is user-owned. Do not create another automatic core/login loop here.
                webView.visibility = View.VISIBLE
                status.text = "진학사 고3 로그인 화면을 유지합니다. 로그인 완료 후 '사이트 로그인·동의 완료 후 계속'을 누르세요."
            }
        }, 160L)'''
new_recovery = '''        handler.postDelayed({
            jinhakV0166LowerGradeRecoveryPending = false
            if (provider != ProviderId.JINHAK) return@postDelayed
            // One forbidden redirect causes exactly one deterministic protected-high3 probe.
            // If authentication is not valid, that probe may return to the shared login page,
            // where v0.16.5/0.16.6 manual-login handling leaves the page visible and does not
            // automatically retry again. This breaks the old high3 -> lower-grade -> high3 loop.
            webView.visibility = View.INVISIBLE
            recordRuntimeEvent("jinhak-v0166-return-to-protected-high3", JSONObject()
                .put("source", source.take(80))
                .put("coreSafePath", runtimeSafePath(high3Core))
                .put("automaticLowerGradeFollow", false)
                .put("oneShot", true))
            webView.loadUrl(high3Core)
        }, 160L)'''
if text.count(old_recovery) != 1:
    raise SystemExit(f"one-shot protected high3 recovery patch: expected 1 occurrence, got {text.count(old_recovery)}")
text = text.replace(old_recovery, new_recovery, 1)

path.write_text(text)
print("v0.16.6 post-patch safety fixes applied")
