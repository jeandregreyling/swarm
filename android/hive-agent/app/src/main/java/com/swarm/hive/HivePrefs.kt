package com.swarm.hive

import android.content.Context
import android.content.SharedPreferences
import android.os.Build

/**
 * HivePrefs — typed wrapper over SharedPreferences. Persists the few
 * pieces of config the agent needs to survive reboots: leader URL, the
 * assigned node id, the enrolment token, and the tick interval.
 *
 * Defaults are sensible-but-empty; the user must supply at least the
 * leader URL via MainActivity before the service does anything useful.
 * Stored under the standard app-private prefs file.
 */
class HivePrefs(ctx: Context) {

    private val sp: SharedPreferences =
        ctx.getSharedPreferences("hive_agent_prefs", Context.MODE_PRIVATE)

    var leader: String
        get() = sp.getString(K_LEADER, "") ?: ""
        set(v) = sp.edit().putString(K_LEADER, v).apply()

    var nodeId: String
        get() = sp.getString(K_NODE_ID, "") ?: ""
        set(v) = sp.edit().putString(K_NODE_ID, v).apply()

    var token: String
        get() = sp.getString(K_TOKEN, "") ?: ""
        set(v) = sp.edit().putString(K_TOKEN, v).apply()

    var intervalMs: Long
        get() = sp.getLong(K_INTERVAL_MS, 30_000L)
        set(v) = sp.edit().putLong(K_INTERVAL_MS, v).apply()

    /** True once the user has at least set a leader URL. */
    val isConfigured: Boolean
        get() = leader.isNotBlank()

    /**
     * Suggests a node id derived from the device build fingerprint.
     * Kept stable across app restarts; user can override in the UI.
     * We deliberately avoid ANDROID_ID — that requires runtime fields
     * we do not need and Android 10+ scopes it per-app-signature.
     */
    fun suggestNodeId(): String {
        val tag = (Build.MODEL ?: "android")
            .lowercase()
            .replace(Regex("[^a-z0-9]+"), "-")
            .trim('-')
            .ifEmpty { "device" }
        // Append a short hash of build fingerprint for uniqueness across
        // identical models on the same tailnet.
        val fp = (Build.FINGERPRINT ?: "")
        val short = Integer.toHexString(fp.hashCode()).padStart(8, '0').takeLast(8)
        return "android-$tag-$short"
    }

    companion object {
        private const val K_LEADER = "leader"
        private const val K_NODE_ID = "node_id"
        private const val K_TOKEN = "token"
        private const val K_INTERVAL_MS = "interval_ms"
    }
}
