package com.admissionhub.collector.jinhak

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class JinhakNativeAppBridgeTest {
    @Test
    fun packageIsExplicitAndNeverWildcarded() {
        assertTrue(JinhakNativeAppBridge.OFFICIAL_APP_PACKAGE == "com.jinhak.jinhakmobile.android")
    }

    @Test
    fun detectsSusiStorageMaterial() {
        assertTrue(JinhakNativeAppBridge.looksLikeSusiStorage("수시 저장 대학 내 지원 목록 경쟁률 모집인원"))
        assertTrue(JinhakNativeAppBridge.looksLikeSusiStorage("수시 지원 저장 학과 전형 현재 경쟁률 4.2:1"))
    }

    @Test
    fun rejectsLoginAndUnrelatedScreens() {
        assertFalse(JinhakNativeAppBridge.looksLikeSusiStorage("아이디\n비밀번호\n로그인"))
        assertFalse(JinhakNativeAppBridge.looksLikeSusiStorage("정시 대학 검색 입시 전략"))
        assertFalse(JinhakNativeAppBridge.looksLikeSusiStorage("수시 입시 전략 대학 정보"))
    }
}
