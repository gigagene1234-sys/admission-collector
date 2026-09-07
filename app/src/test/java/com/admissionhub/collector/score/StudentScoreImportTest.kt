package com.admissionhub.collector.score
import org.junit.Assert.*
import org.junit.Test

class StudentScoreImportTest {
    @Test fun missingGradesNeverBecomeZero() {
        val p = StudentScoreImport.parse(StudentScoreImport.TEMPLATE + "1,1,국어,국어,3,4,\n1,1,과학,물리학II,,3,A", 2027, true)
        assertEquals(3.0, p.getDouble("ownWeightedGrade"), 0.0001)
        assertTrue(p.getJSONArray("subjects").getJSONObject(1).isNull("grade")); assertEquals(1, p.getInt("ungradedRows"))
    }
    @Test fun missingCreditsHoldWeightedAverage() {
        val p = StudentScoreImport.parse(StudentScoreImport.TEMPLATE + "1,1,국어,국어,3,,\n1,1,수학,수학,4,4,", 2027, true)
        assertTrue(p.isNull("ownWeightedGrade")); assertEquals(1, p.getInt("missingCreditRows"))
    }
    @Test(expected = IllegalArgumentException::class) fun rejectsZeroGrade() { StudentScoreImport.parse(StudentScoreImport.TEMPLATE + "1,1,국어,국어,0,4,", 2027, true) }
    @Test(expected = IllegalArgumentException::class) fun rejectsDuplicateCourseInSameSemester() { StudentScoreImport.parse(StudentScoreImport.TEMPLATE + "1,1,국어,국어,3,4,\n1,1,국어,국어,4,4,", 2027, true) }
    @Test fun preservesSeparateSemestersAndQuotedNames() {
        val p = StudentScoreImport.parse(StudentScoreImport.TEMPLATE + "1,1,국어,\"독서,문법\",3,4,\n1,2,국어,\"독서,문법\",4,4,", 2027, false)
        assertEquals(2, p.getInt("rowCount")); assertFalse(p.getBoolean("completeTranscriptConfirmedByUser"))
    }
    @Test fun jsonImportWhitelistsOnlyTranscriptData() {
        val p = StudentScoreImport.parse("""{"academicYear":2027,"password":"dummy-not-real","slots":[1],"subjects":[{"gradeYear":1,"semester":1,"subject":"국어","grade":3,"credits":4,"cookie":"dummy"}]}""",2027,true)
        assertFalse(p.toString().contains("dummy")); assertFalse(p.has("slots"))
    }
    @Test fun changedGradesProduceNewFingerprint() {
        val a=StudentScoreImport.parse(StudentScoreImport.TEMPLATE+"1,1,국어,국어,3,4,",2027,true)
        val b=StudentScoreImport.parse(StudentScoreImport.TEMPLATE+"1,1,국어,국어,4,4,",2027,true)
        assertNotEquals(a.getString("fingerprint"),b.getString("fingerprint"))
    }
}
