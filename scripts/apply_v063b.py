from pathlib import Path

ROOT = Path('.')
MAIN_FILES = [ROOT / 'MainActivity.kt', ROOT / 'app/src/main/java/com/admissionhub/collector/MainActivity.kt']
JINHAK = ROOT / 'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
SNAP = ROOT / 'app/src/main/java/com/admissionhub/collector/capture/SnapshotScript.kt'
GRADLE = ROOT / 'app/build.gradle.kts'
MANIFEST = ROOT / 'app/src/main/AndroidManifest.xml'

for p in MAIN_FILES:
    m = p.read_text()
    if 'private const val VERSION = "0.6.2"' not in m:
        raise SystemExit(f'expected v0.6.2 main source missing: {p}')
    m = m.replace('private const val VERSION = "0.6.2"', 'private const val VERSION = "0.6.3"', 1)
    m = m.replace('private const val BUILD_CODE = 10620', 'private const val BUILD_CODE = 10630', 1)
    p.write_text(m)

j = JINHAK.read_text()
old_block = '            if (Regex("(?:logout|signout|member|mypage|my-page|account|payment|pay|coupon|refund|withdraw|profile|userinfo|customer|faq|qna|event|notice|privacy|terms)").containsMatchIn(full)) return false\n'
new_block = '            if (Regex("(?:logout|signout|member|mypage|my-page|account|payment|billing|purchase|order|spassdata|coupon|refund|withdraw|profile|userinfo|customer|faq|qna|event|notice|privacy|terms|jinhak-tv|univ-entrance-info|susi-special|story|news|clip)").containsMatchIn(full)) return false\n'
if old_block not in j:
    raise SystemExit('Jinhak blocked-surface anchor missing')
j = j.replace(old_block, new_block, 1)

start = j.index('    override fun classify(snapshot: JSONObject): String {')
end = j.index('    override fun normalize(snapshot: JSONObject): JSONArray {', start)
new_classify = r'''    override fun classify(snapshot: JSONObject): String {
        val rawUrl = snapshot.optString("url")
        val url = rawUrl.lowercase()
        val path = runCatching { URI(rawUrl).path?.lowercase() ?: "/" }.getOrDefault("/")
        val rootPage = path.isBlank() || path == "/" || path.endsWith("/index") || path.endsWith("/index.html")
        val headingText = buildString {
            append(snapshot.optString("title"))
            val headings = snapshot.optJSONArray("context") ?: JSONArray()
            for (i in 0 until minOf(headings.length(), 16)) {
                append(' ').append(headings.optString(i))
            }
        }.replace(Regex("\\s+"), " ").trim()

        // Global menus contain words such as 합격예측/수시저장소 on almost every page.
        // Classification therefore uses URL + title/heading context, never whole-page menu text.
        val mockReport = url.contains("sapplysample") || Regex("모의지원\\s*리포트").containsMatchIn(headingText)
        val hasActual = Regex("(실제합격자\\s*(?:리포트|사례)|합격자\\s*리포트|전년도\\s*입시결과\\s*(?:리포트|상세))").containsMatchIn(headingText) ||
            Regex("(actual|admitreport|resultreport|passcase)").containsMatchIn(url)
        val dedicatedMinimum = url.contains("esatminuniv") || Regex("(수능최저|최저학력기준)").containsMatchIn(headingText)
        val scoreReport = Regex("(score|calc)").containsMatchIn(url) || Regex("성적산출\\s*리포트").containsMatchIn(headingText)
        val earlyStorage = Regex("(storage|save)").containsMatchIn(url) || Regex("(수시|정시)?\\s*저장소|저장대학").containsMatchIn(headingText)
        val universitySearch = url.contains("four-year-university/search") || Regex("대학검색").containsMatchIn(headingText)
        val curation = url.contains("/curation") || Regex("큐레이션").containsMatchIn(headingText)
        val recommended = Regex("추천대학").containsMatchIn(headingText)
        val hasPrediction = Regex("(predict|prediction|possibility|admission-report|support-report)").containsMatchIn(url) ||
            Regex("(합격예측\\s*(?:리포트|결과)|[0-9]{1,2}\\s*칸)").containsMatchIn(headingText)

        return when {
            Regex("(login|signin|member/login)").containsMatchIn(url) || Regex("로그인.*비밀번호").containsMatchIn(headingText) -> "jinhak-login"
            rootPage -> "jinhak-home"
            mockReport -> "jinhak-mock-support-report"
            hasActual -> "jinhak-actual-admit-report"
            dedicatedMinimum -> "jinhak-sat-minimum"
            url.contains("infoview.aspx") -> "jinhak-student-basic"
            scoreReport -> "jinhak-score-calc-report"
            earlyStorage -> "jinhak-early-storage"
            universitySearch -> "jinhak-university-search"
            curation -> "jinhak-curation"
            recommended -> "jinhak-recommended-university"
            hasPrediction -> "jinhak-prediction-report"
            else -> "jinhak-other"
        }
    }

'''
j = j[:start] + new_classify + j[end:]
JINHAK.write_text(j)

s = SNAP.read_text()
old_full = """      var u=new URL(raw,location.href);\n      if(u.origin!==location.origin) return '';\n      var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|sysReg|sysChg|userId|ipMac/i;\n"""
new_full = """      var u=new URL(raw,location.href);\n      var currentHost=String(location.hostname||'').toLowerCase();\n      var targetHost=String(u.hostname||'').toLowerCase();\n      var currentJinhak=(currentHost==='jinhak.com'||/\\.jinhak\\.com$/.test(currentHost));\n      var targetJinhak=(targetHost==='jinhak.com'||/\\.jinhak\\.com$/.test(targetHost));\n      if(u.origin!==location.origin && !(currentJinhak&&targetJinhak)) return '';\n      var badKey=/token|session|auth|csrf|transkey|captcha|password|passwd|secret|credential|sysReg|sysChg|userId|ipMac/i;\n"""
if old_full not in s:
    raise SystemExit('Snapshot fullNavigationUrl origin anchor missing')
s = s.replace(old_full, new_full, 1)

old_gate = """    var ru;\n    try{ ru=new URL(route,location.href); }catch(e2){ continue; }\n    if(ru.origin!==location.origin) continue;\n    var sameArea=prefix && ru.pathname.split('/').filter(Boolean).slice(0,2).join('/')===prefix;\n"""
new_gate = """    var ru;\n    try{ ru=new URL(route,location.href); }catch(e2){ continue; }\n    var ch=String(location.hostname||'').toLowerCase();\n    var rh=String(ru.hostname||'').toLowerCase();\n    var sameJinhakProvider=(ch==='jinhak.com'||/\\.jinhak\\.com$/.test(ch)) && (rh==='jinhak.com'||/\\.jinhak\\.com$/.test(rh));\n    if(ru.origin!==location.origin && !sameJinhakProvider) continue;\n    var sameArea=prefix && ru.pathname.split('/').filter(Boolean).slice(0,2).join('/')===prefix;\n"""
if old_gate not in s:
    raise SystemExit('Snapshot navigation-loop origin anchor missing')
s = s.replace(old_gate, new_gate, 1)
SNAP.write_text(s)

g = GRADLE.read_text()
g = g.replace('versionCode = 10620', 'versionCode = 10630', 1)
g = g.replace('versionName = "0.6.2"', 'versionName = "0.6.3"', 1)
GRADLE.write_text(g)

mf = MANIFEST.read_text()
mf = mf.replace('Admission Collector v0.6.2 Unified Autonomous Explorer', 'Admission Collector v0.6.3 Unified Autonomous Explorer', 1)
MANIFEST.write_text(mf)

if MAIN_FILES[0].read_text() != MAIN_FILES[1].read_text():
    raise SystemExit('MainActivity mirror mismatch after v0.6.3b patch')

print('v0.6.3b structural Jinhak classification + subdomain traversal patch applied')
