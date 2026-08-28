plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.admissionhub.collector"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.admissionhub.collector"
        minSdk = 26
        targetSdk = 35
        versionCode = 4
        versionName = "0.2.2"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
}
