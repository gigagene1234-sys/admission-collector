from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

# Version bump only after v0.6.2 has been persisted.
for p in MAIN_FILES:
    m = p.read_text()
    m = m.replace('private const val VERSION = "0.6.2"', 'private const val VERSION = "0.6.3"', 1)
    m = m.replace('private const val BUILD_CODE = 10620', 'private const val BUILD_CODE = 10630', 1)
    p.write_text(m)

# Jinhak routing/classification hardening.
j = JINHAK.read_text()

# Exclude editorial/support/payment/account surfaces that otherwise consume the bounded
# crawler before it reaches actual admission-analysis pages.
old_block = '''            if (Regex("(?:logout|signout|member|mypage|my-page|account|payment|pay|coupon|refund|withdraw|profile|userinfo|customer|faq|qna|event|notice|privacy|terms)").containsMatchIn(full)) return false\n'''
new_block = '''            if (Regex("(?:logout|signout|member|mypage|my-page|account|payment|billing|purchase|order|spassdata|coupon|refund|withdraw|profile|userinfo|customer|faq|qna|event|notice|privacy|terms|jinhak-tv|univ-entrance-info|susi-special|story|news|clip)").containsMatchIn(full)) return false\n'''
if old_block not in j:
    raise SystemExit('v0.6.3 Jinhak blocked-surface anchor missing')
j = j.replace(old_block, new_block, 1)

# Replace broad whole-page menu-text classification with title/heading + URL structure.
old_class = '''        val url = snapshot.optString("url").lowercase()\n        val text = GenericAdmissionParser.collectText(snapshot)\n        val path = runCatching { URI(snapshot.optString("url")).path?.lowercase() ?: "/" }.getOrDefault("/")\n        val rootPage = path.isBlank() || path == "/" || path.endsWith("/index") || path.endsWith("/index.html")\n        val hasPrediction = text.contains("합격예측") || text.contains("모의지원") || Regex("[0-9]{1,2}\\s*칸").containsMatchIn(text)\n        val hasActual = Regex("(실제합격자\\s*(?:리포트|사례)|합격자\\s*리포트|전년도\\s*입시결과\\s*(?:리포트|상세))").containsMatchIn(text) ||\n            Regex("(actual|admitreport|resultreport|passcase)").containsMatchIn(url)\n        val dedicatedMinimum = url.contains("esatminuniv") ||\n            (Regex("(수능최저\\s*(검색|대학|조건)|최저학력기준\\s*(검색|대학))").containsMatchIn(text) && !hasPrediction)\n        val earlyStorage = text.contains("수시저장소") || text.contains("저장대학") || url.contains("storage") || url.contains("save")\n        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || text.contains("로그인") && text.contains("비밀번호") -> "jinhak-login"\n            rootPage -> "jinhak-home"\n            earlyStorage -> "jinhak-early-storage"\n            hasActual -> "jinhak-actual-admit-report"\n            text.contains("합격예측리포트") || text.contains("합격예측 리포트") || hasPrediction -> "jinhak-prediction-report"\n            url.contains("sapplysample") || text.contains("모의지원 리포트") || text.contains("모의지원리포트") -> "jinhak-mock-support-report"\n            text.contains("성적산출 리포트") || text.contains("성적산출리포트") -> "jinhak-score-calc-report"\n            dedicatedMinimum -> "jinhak-sat-minimum"\n            url.contains("infoview.aspx") -> "jinhak-student-basic"\n            url.contains("four-year-university/search") || text.contains("대학검색") -> "jinhak-university-search"\n            url.contains("/curation") || text.contains("큐레이션") -> "jinhak-curation"\n            text.contains("추천대학") -> "jinhak-recommended-university"\n            else -> "jinhak-other"\n        }\n'''
new_class = '''        val rawUrl = snapshot.optString("url")\n        val url = rawUrl.lowercase()\n        val text = GenericAdmissionParser.collectText(snapshot)\n        val path = runCatching { URI(rawUrl).path?.lowercase() ?: "/" }.getOrDefault("/")\n        val rootPage = path.isBlank() || path == "/" || path.endsWith("/index") || path.endsWith("/index.html")\n        val headingText = buildString {\n            append(snapshot.optString("title"))\n            val headings = snapshot.optJSONArray("context") ?: JSONArray()\n            for (i in 0 until minOf(headings.length(), 16)) {\n                append(' ').append(headings.optString(i))\n            }\n        }.replace(Regex("\\s+"), " ").trim()\n        val urlPrediction = Regex("(predict|prediction|possibility|report|analysis)").containsMatchIn(url)\n        val headingPrediction = Regex("(합격예측\\s*(?:리포트|결과)|모의지원\\s*(?:리포트|결과)|[0-9]{1,2}\\s*칸)").containsMatchIn(headingText)\n        val hasPrediction = urlPrediction || headingPrediction\n        val hasActual = Regex("(실제합격자\\s*(?:리포트|사례)|합격자\\s*리포트|전년도\\s*입시결과\\s*(?:리포트|상세))").containsMatchIn(headingText) ||\n            Regex("(actual|admitreport|resultreport|passcase)").containsMatchIn(url)\n        val dedicatedMinimum = url.contains("esatminuniv") || Regex("(수능최저|최저학력기준)").containsMatchIn(headingText)\n        val earlyStorage = Regex("(storage|save|저장소|저장대학)").containsMatchIn(url + " " + headingText)\n        val mockReport = url.contains("sapplysample") || Regex("모의지원\\s*리포트").containsMatchIn(headingText)\n        val scoreReport = Regex("(score|calc|성적산출\\s*리포트)").containsMatchIn(url + " " + headingText)\n        val universitySearch = url.contains("four-year-university/search") || Regex("대학검색").containsMatchIn(headingText)\n        val curation = url.contains("/curation") || Regex("큐레이션").containsMatchIn(headingText)\n        val recommended = Regex("추천대학").containsMatchIn(headingText)\n        return when {\n            Regex("(login|signin|member/login)").containsMatchIn(url) || Regex("로그인.*비밀번호").containsMatchIn(headingText) -> "jinhak-login"\n            rootPage -> "jinhak-home"\n            mockReport -> "jinhak-mock-support-report"\n            hasActual -> "jinhak-actual-admit-report"\n            dedicatedMinimum -> "jinhak-sat-minimum"\n            url.contains("infoview.aspx") -> "jinhak-student-basic"\n            scoreReport -> "jinhak-score-calc-report"\n            earlyStorage -> "jinhak-early-storage"\n            universitySearch -> "jinhak-university-search"\n            curation -> "jinhak-curation"\n            recommended -> "jinhak-recommended-university"\n            hasPrediction -> "jinhak-prediction-report"\n            else -> "jinhak-other"\n        }\n'''
if old_class not in j:
    raise SystemExit('v0.6.3 Jinhak classification block missing')
j = j.replace(old_class, new_class, 1)
JINHAK.write_text(j)

# Snapshot navigation: allow cross-origin only when both source and target are Jinhak
# subdomains. Adiga remains same-origin. This is needed because paid/prediction pages can
# live on a Jinhak subdomain different from www.jinhak.com.
s = SNAP.read_text()
old_full = '''      var u=new URL(raw,location.href);\n      if(u.origin!==location.origin) return '';\n      var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|sysReg|sysChg|userId|ipMac/i;\n'''
new_full = '''      var u=new URL(raw,location.href);\n      var currentHost=String(location.hostname||'').toLowerCase();\n      var targetHost=String(u.hostname||'').toLowerCase();\n      var currentJinhak=(currentHost==='jinhak.com'||/\\.jinhak\\.com$/.test(currentHost));\n      var targetJinhak=(targetHost==='jinhak.com'||/\\.jinhak\\.com$/.test(targetHost));\n      if(u.origin!==location.origin && !(currentJinhak&&targetJinhak)) return '';\n      var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|sysReg|sysChg|userId|ipMac/i;\n'''
if old_full not in s:
    raise SystemExit('v0.6.3 Snapshot fullNavigationUrl anchor missing')
s = s.replace(old_full, new_full, 1)

# The navigation loop also had a second same-origin gate after route parsing.
old_route_gate = '''    var ru;\n    try{ ru=new URL(route,location.href); }catch(e2){ continue; }\n    if(ru.origin!==location.origin) continue;\n    var sameArea=prefix && ru.pathname.split('/').filter(Boolean).slice(0,2).join('/')===prefix;\n'''
new_route_gate = '''    var ru;\n    try{ ru=new URL(route,location.href); }catch(e2){ continue; }\n    var ch=String(location.hostname||'').toLowerCase();\n    var rh=String(ru.hostname||'').toLowerCase();\n    var sameJinhakProvider=(ch==='jinhak.com'||/\\.jinhak\\.com$/.test(ch)) && (rh==='jinhak.com'||/\\.jinhak\\.com$/.test(rh));\n    if(ru.origin!==location.origin && !sameJinhakProvider) continue;\n    var sameArea=prefix && ru.pathname.split('/').filter(Boolean).slice(0,2).join('/')===prefix;\n'''
if old_route_gate not in s:
    raise SystemExit('v0.6.3 Snapshot navigation-loop origin gate missing')
s = s.replace(old_route_gate, new_route_gate, 1)
SNAP.write_text(s)

# Version metadata.
g = GRADLE.read_text().replace('versionCode = 10620', 'versionCode = 10630', 1).replace('versionName = "0.6.2"', 'versionName = "0.6.3"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text().replace('Admission Collector v0.6.2 Unified Autonomous Explorer', 'Admission Collector v0.6.3 Unified Autonomous Explorer', 1)
MANIFEST.write_text(mf)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirror mismatch after v0.6.3 patch')

print('v0.6.3 Jinhak subdomain traversal + structural classification patch applied')
