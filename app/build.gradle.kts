val admissionSigningStore = System.getenv("ADMISSION_SIGNING_STORE_FILE")
val admissionSigningPassword = System.getenv("ADMISSION_SIGNING_PASSWORD")

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
        versionCode = 10930
        versionName = "0.9.3"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    signingConfigs {
        if (!admissionSigningStore.isNullOrBlank() && !admissionSigningPassword.isNullOrBlank()) {
            create("admissionStable") {
                storeFile = file(admissionSigningStore)
                storePassword = admissionSigningPassword
                keyAlias = "admission"
                keyPassword = admissionSigningPassword
            }
        }
    }

    buildTypes {
        debug {
            signingConfigs.findByName("admissionStable")?.let { signingConfig = it }
        }
        release {
            isMinifyEnabled = false
            signingConfigs.findByName("admissionStable")?.let { signingConfig = it }
        }
    }
}
