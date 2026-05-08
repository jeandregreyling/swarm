// build.gradle.kts — project root, only declares the plugin versions.
//
// All real configuration lives in app/build.gradle.kts. Keeping this
// file minimal so plugin upgrades land in one place.
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "1.9.24" apply false
}
