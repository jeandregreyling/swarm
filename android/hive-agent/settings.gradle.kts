// settings.gradle.kts — top-level project includes
//
// The Hive Agent app is the only module. Keeping the project flat
// because we will likely never grow beyond one APK; the Hive runtime
// itself ships from the leader, this app only wraps the on-device loop.
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "swarm-hive-agent"
include(":app")
