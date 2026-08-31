from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MAIN=ROOT/'app/src/main/java/com/admissionhub/collector/MainActivity.kt'
JINHAK=ROOT/'app/src/main/java/com/admissionhub/collector/provider/JinhakAdapter.kt'
GRADLE=ROOT/'app/build.gradle.kts'
MANIFEST=ROOT/'app/src/main/AndroidManifest.xml'

def one(text, old, new, label):
    c=text.count(old)
    if c!=1:
        raise SystemExit(f'{label}: expected 1 anchor, found {c}')
    return text.replace(old,new,1)

# Jinhak adapter: mission seeds + strategy-analysis records.
j=JINHAK.read_text()
j=one(j,
      'import com.admissionhub.collector.parser.RecordUtils\n',
      'import com.admissionhub.collector.parser.RecordUtils\nimport com.admissionhub.collector.jinhak.JinhakSiteTopology\nimport com.admissionhub.collector.jinhak.JinhakStrategyAnalyzer\n',
      'adapter imports')
j=one(j,
      '    override fun seedUrls(): List<String> = listOf("https://www.jinhak.com/")\n',
      '    override fun seedUrls(): List<String> = JinhakSiteTopology.missionSeeds()\n',
      'mission seeds')
j=one(j,
      '''        if (pageType == "jinhak-university-admission-info") {
            return normalizeUniversityAdmissionInfo(snapshot, observedAt)
        }

        // Observation-first does not mean parser-last. v0.7.1 preserved 200+ tables but
''',
      '''        if (pageType == "jinhak-university-admission-info") {
            return normalizeUniversityAdmissionInfo(snapshot, observedAt)
        }

        if (pageType == "jinhak-admission-strategy") {
            val strategy = JinhakStrategyAnalyzer.normalize(snapshot, observedAt)
            val evidence = normalizeTableEvidence(snapshot, pageType, observedAt)
            for (i in 0 until evidence.length()) strategy.put(evidence.optJSONObject(i))
            return RecordUtils.dedupe(strategy)
        }

        // Observation-first does not mean parser-last. v0.7.1 preserved 200+ tables but
''',
      'strategy analyzer integration')
JINHAK.write_text(j)

# MainActivity: mission-route priority queue and release identity.
m=MAIN.read_text()
m=one(m,
      'import com.admissionhub.collector.jinhak.JinhakAgentNavigator\n',
      'import com.admissionhub.collector.jinhak.JinhakAgentNavigator\nimport com.admissionhub.collector.jinhak.JinhakSiteTopology\n',
      'main topology import')
m=one(m,
      '        private const val VERSION = "0.8.0"\n        private const val BUILD_CODE = 10800\n',
      '        private const val VERSION = "0.8.1"\n        private const val BUILD_CODE = 10810\n',
      'version bump')
m=one(m,
      '''        status.text = "통합 수집 2/2 · 진학사 자동 크롤러 준비: 로그인 세션을 유지한 채 접근 가능한 화면을 자율 순회합니다."
''',
      '''        status.text = "통합 수집 2/2 · 진학사 목적형 분석 준비: 저장대학→합격예측→모의지원→실제합격자→대학입결→전략 순으로 우선 탐색합니다."
''',
      'mission status')
m=one(m,
      '''    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return
        if (batchVisited.contains(url)) return
        val runId = localRunId
        if (runId != null && localStore.isDocumentCompleted(runId, url)) return
        if (batchQueued.add(url)) batchQueue.addLast(url)
    }
''',
      '''    private fun enqueueDiscoveredUrl(url: String) {
        if (url.isBlank() || !isBatchNavigableProviderUrl(url)) return
        if (provider == ProviderId.JINHAK && batchQueued.size + batchVisited.size >= MAX_JINHAK_AUTONAV_PAGES) return
        if (batchVisited.contains(url)) return
        val runId = localRunId
        if (runId != null && localStore.isDocumentCompleted(runId, url)) return
        if (batchQueued.add(url)) {
            if (provider == ProviderId.JINHAK && JinhakSiteTopology.isCoreMissionRoute(url)) {
                batchQueue.addFirst(url)
            } else {
                batchQueue.addLast(url)
            }
        }
    }
''',
      'mission-priority queue')
MAIN.write_text(m)

# Build metadata.
g=GRADLE.read_text()
g=one(g,'        versionCode = 10800\n        versionName = "0.8.0"\n','        versionCode = 10810\n        versionName = "0.8.1"\n','gradle version')
GRADLE.write_text(g)

x=MANIFEST.read_text()
x=one(x,'android:label="Admission Collector v0.8.0 Session Agent Cloud"','android:label="Admission Collector v0.8.1 Jinhak Mission Analyst"','manifest label')
MANIFEST.write_text(x)

print('Applied v0.8.1 Jinhak mission-first navigation and strategy-analysis patch')
