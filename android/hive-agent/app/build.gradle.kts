// app/build.gradle.kts — Hive Agent module.
//
// minSdk 24 (Android 7.0): foreground services + JobScheduler are stable
// from there. The S9-FE target tablet runs Android 13 (API 33).
// targetSdk 34 (Android 14): required by Play Store policy in 2024+ and
// matches the foreground-service-type rules we use.
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// Load release signing creds from keystore.properties (gitignored).
// Falls back to the debug signing config when the file is absent so
// fresh checkouts can still build a debug APK without ceremony.
val keystorePropsFile = rootProject.file("keystore.properties")
val keystoreProps = Properties().apply {
    if (keystorePropsFile.exists()) {
        keystorePropsFile.inputStream().use { load(it) }
    }
}
val hasReleaseSigning = keystorePropsFile.exists() &&
    keystoreProps.getProperty("storeFile")?.isNotBlank() == true

android {
    namespace = "com.swarm.hive"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.swarm.hive"
        minSdk = 24
        targetSdk = 34
        versionCode = 4
        versionName = "0.2.1"
    }

    signingConfigs {
        if (hasReleaseSigning) {
            create("release") {
                storeFile = file(keystoreProps.getProperty("storeFile"))
                storePassword = keystoreProps.getProperty("storePassword")
                keyAlias = keystoreProps.getProperty("keyAlias")
                keyPassword = keystoreProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        debug {
            isMinifyEnabled = false
            isDebuggable = true
        }
        release {
            // Keep the APK simple; we are not shipping through Play.
            // No shrinking → no proguard surprises → no telemetry loop
            // disappearing into a dead-stripped class.
            isMinifyEnabled = false
            signingConfig = if (hasReleaseSigning) {
                signingConfigs.getByName("release")
            } else {
                // Debug-key fallback: still produces an installable APK
                // on a fresh checkout, but Play Console will reject it.
                signingConfigs.getByName("debug")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    // No view binding / compose / etc. — keep the APK small. The UI is a
    // single XML layout with two text fields and a button.
    buildFeatures {
        buildConfig = true
    }
}

dependencies {
    // Stdlib + just enough androidx for foreground service + lifecycle.
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.lifecycle:lifecycle-service:2.8.4")
    implementation("com.google.android.material:material:1.12.0")
    // No OkHttp / Retrofit / kotlinx.serialization on purpose:
    // HttpURLConnection + org.json are built into Android and keep the
    // APK under 2 MB.
}
