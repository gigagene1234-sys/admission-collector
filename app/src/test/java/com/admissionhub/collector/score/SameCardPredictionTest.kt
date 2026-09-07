package com.admissionhub.collector.score
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SameCardPredictionTest {
    private fun candidate()=JSONObject().put("applicationIdentityKey","synthetic-a").put("university","가상대").put("department","가상공학과").put("admission","일반").put("academicYear",2027)
    private fun record()=JSONObject(candidate().toString()).put("year",2027)
        .put("recordType","jinhak-saved-application-prediction").put("contextSource","same-card-application-grammar").put("confidence","high")
        .put("universityContextSource","card-root").put("universityContextDepth",0).put("departmentContextDepth",-1)
        .put("rawEvidence","닫기5칸가상대[교과]일반가상공학과10명내 점수800점 (반영교과 3.25등급)모의지원자 평균 790점 (반영교과 3.30등급)리포트")
        .put("sourcePage","https://www.jinhak.com/jh/library").put("sourceRowFingerprint","synthetic-row")
        .put("observedAt","2026-09-07T00:00:00Z").put("metrics",JSONObject().put("metricSemanticsVersion",3).put("stabilityBars",5).put("myCalculatedScore",800))
    @Test fun explicitSingleCardPrefixWorksWithoutDepartmentDomAnnotation() { val m=SameCardPrediction.extract(candidate(),record());assertNotNull(m);assertEquals(3.25,m!!.getDouble("myReflectedGrade"),1e-9);assertFalse(m.getBoolean("officialConversionVerified")) }
    @Test fun adjacentCardIdentityNeverBinds() { assertNull(SameCardPrediction.extract(candidate(),record().put("rawEvidence","닫기5칸다른대[교과]일반가상공학과10명내 점수800점"))) }
    @Test fun changeUniversityPopupIsNotSingleCardEvidence() { assertNull(SameCardPrediction.extract(candidate(),record().put("rawEvidence",record().getString("rawEvidence")+"실제지원 대학선택"))) }
    @Test fun conflictingParsedAndLiteralNumbersAreRejected() { val r=record();r.getJSONObject("metrics").put("myCalculatedScore",999);assertNull(SameCardPrediction.extract(candidate(),r)) }
    @Test fun wrongYearIsRejected() { assertNull(SameCardPrediction.extract(candidate(),record().put("year",2026))) }
    @Test fun unboundPageReportsRemainUnstructured() { assertNull(SameCardPrediction.extract(candidate(),record().put("contextSource","page-context"))) }
}
