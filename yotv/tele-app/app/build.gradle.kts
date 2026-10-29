plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.yotv.tele"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.yotv.tele"
        minSdk = 23
        targetSdk = 35
        versionCode = 1
        versionName = "1.0"
    }

    // Llave fija para que cada versión nueva se instale encima de la anterior sin borrar nada.
    // Es solo para tu tele; no la uses para publicar apps.
    signingConfigs {
        create("tele") {
            storeFile = file("yotv.keystore")
            storePassword = "yotv-tele"
            keyAlias = "yotv"
            keyPassword = "yotv-tele"
        }
    }

    buildTypes {
        getByName("debug") { signingConfig = signingConfigs.getByName("tele") }
        getByName("release") {
            isMinifyEnabled = false
            signingConfig = signingConfigs.getByName("tele")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = "17" }
}

dependencies {
    implementation("androidx.media3:media3-exoplayer:1.5.1")
    implementation("androidx.media3:media3-ui:1.5.1")
}
