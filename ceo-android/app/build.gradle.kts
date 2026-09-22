plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
}

val devKeystorePath = System.getenv("CEO_DEV_KEYSTORE_PATH")
val devKeystorePassword = System.getenv("CEO_DEV_KEYSTORE_PASSWORD") ?: "ceo-dev-lab-only"
val devKeyAlias = System.getenv("CEO_DEV_KEY_ALIAS") ?: "ceo-dev-lab"
val devKeyPassword = System.getenv("CEO_DEV_KEY_PASSWORD") ?: devKeystorePassword

android {
    namespace = "ai.ceo.android"
    compileSdk = 36

    defaultConfig {
        applicationId = "ai.ceo.android"
        minSdk = 26
        targetSdk = 36
        versionCode = 11
        versionName = "0.9.0-alpha1"

        buildConfigField(
            "String",
            "UPDATE_MANIFEST_URL",
            "\"https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-android-updates/ceo-android/releases/stable.json\""
        )
        buildConfigField("String", "UPDATE_CHANNEL", "\"stable\"")
    }

    signingConfigs {
        if (!devKeystorePath.isNullOrBlank()) {
            create("devLab") {
                storeFile = file(devKeystorePath)
                storePassword = devKeystorePassword
                keyAlias = devKeyAlias
                keyPassword = devKeyPassword
                storeType = "PKCS12"
            }
        }
    }

    buildTypes {
        debug {
            if (!devKeystorePath.isNullOrBlank()) {
                signingConfig = signingConfigs.getByName("devLab")
            }
            applicationIdSuffix = ".dev"
            versionNameSuffix = "-dev"
            buildConfigField(
                "String",
                "UPDATE_MANIFEST_URL",
                "\"https://raw.githubusercontent.com/danisuarezinef-ai/investment-intelligence-radar/ceo-android-updates/ceo-android/releases/dev.json\""
            )
            buildConfigField("String", "UPDATE_CHANNEL", "\"dev\"")
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
    }

    buildFeatures {
        compose = true
        buildConfig = true
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.17.0")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation("androidx.compose.material3:material3:1.4.0")
    implementation("androidx.compose.ui:ui:1.11.4")
    implementation("androidx.compose.ui:ui-tooling-preview:1.11.4")
    debugImplementation("androidx.compose.ui:ui-tooling:1.11.4")
    implementation("androidx.work:work-runtime-ktx:2.11.2")

    testImplementation("junit:junit:4.13.2")
}
