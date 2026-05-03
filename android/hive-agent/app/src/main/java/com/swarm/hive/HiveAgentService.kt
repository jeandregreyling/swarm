package com.swarm.hive

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.lifecycle.LifecycleService
import androidx.lifecycle.lifecycleScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicReference

/**
 * HiveAgentService — long-running foreground service that posts node
 * resource telemetry to the Swarm leader every [intervalMs] ms.
 *
 * Why a foreground service rather than WorkManager:
 *   - We want a steady cadence (default 30 s) that survives Doze. WM
 *     enforces a minimum 15-minute interval for periodic work.
 *   - The notification gives the user a constant "yes, this device is
 *     pooled" signal, which is the whole product story for the Hive.
 *
 * The service is also intentionally dumb: it does not store telemetry
 * locally, retry forever, or hold a persistent connection. Each tick is
 * an independent best-effort POST. If the leader is unreachable we log
 * and move on; the leader's roster will mark the node stale after 120 s.
 */
class HiveAgentService : LifecycleService() {

    companion object {
        private const val TAG = "HiveAgentService"
        private const val NOTIF_CHANNEL_ID = "hive_agent"
        private const val NOTIF_ID = 0x71BE  // arbitrary stable id

        const val EXTRA_LEADER = "leader"
        const val EXTRA_NODE_ID = "node_id"
        const val EXTRA_TOKEN = "token"
        const val EXTRA_INTERVAL_MS = "interval_ms"

        // Mirror the contract: see core/hive/contract.py CONTRACT_NAME.
        private const val CONTRACT_RESOURCE_V0 = "node.resource/v0"
    }

    private val running = AtomicReference(false)
    private lateinit var prefs: HivePrefs
    private lateinit var sampler: AndroidSampler

    override fun onCreate() {
        super.onCreate()
        prefs = HivePrefs(this)
        sampler = AndroidSampler(this)
        ensureNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        super.onStartCommand(intent, flags, startId)

        // Pull config: prefer intent extras (from MainActivity / boot
        // receiver path), fall back to persisted prefs (post-reboot).
        intent?.let { i ->
            i.getStringExtra(EXTRA_LEADER)?.let { prefs.leader = it }
            i.getStringExtra(EXTRA_NODE_ID)?.let { prefs.nodeId = it }
            i.getStringExtra(EXTRA_TOKEN)?.let { prefs.token = it }
            val iv = i.getLongExtra(EXTRA_INTERVAL_MS, -1L)
            if (iv > 0) prefs.intervalMs = iv
        }

        startForeground(NOTIF_ID, buildNotification("Connecting to ${prefs.leader}…"))

        if (running.compareAndSet(false, true)) {
            lifecycleScope.launch(Dispatchers.IO) { runLoop() }
        }
        // STICKY so Android brings us back if it kills the service.
        return START_STICKY
    }

    override fun onDestroy() {
        running.set(false)
        super.onDestroy()
    }

    override fun onBind(intent: Intent): IBinder? {
        super.onBind(intent)
        return null
    }

    // ---- main loop -------------------------------------------------------

    private suspend fun runLoop() {
        while (lifecycleScope.isActive && running.get()) {
            val intervalMs = prefs.intervalMs.coerceAtLeast(5_000L)
            val ok = tickOnce()
            updateNotification(if (ok) "Posted telemetry · every ${intervalMs/1000}s"
                                else "Leader unreachable · retrying")
            delay(intervalMs)
        }
    }

    private fun tickOnce(): Boolean {
        val leader = prefs.leader
        val nodeId = prefs.nodeId
        if (leader.isBlank() || nodeId.isBlank()) {
            Log.w(TAG, "tick skipped: missing leader/node_id")
            return false
        }

        // Brief wakelock around the network call so Doze cannot cut us off
        // mid-POST. Held only for this tick.
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        val wl = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "$TAG:tick")
        wl.setReferenceCounted(false)
        wl.acquire(15_000L)
        try {
            val payload = buildPayload(nodeId, sampler)
            return postTelemetry(leader, payload)
        } finally {
            if (wl.isHeld) wl.release()
        }
    }

    // ---- HTTP ------------------------------------------------------------

    private fun postTelemetry(leader: String, payload: JSONObject): Boolean {
        val urlStr = leader.trimEnd('/') + "/api/hive/telemetry"
        return try {
            val url = URL(urlStr)
            val conn = (url.openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 8_000
                readTimeout = 8_000
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Accept", "application/json")
                if (prefs.token.isNotBlank()) {
                    setRequestProperty("X-Hive-Token", prefs.token)
                }
            }
            conn.outputStream.use { os: OutputStream ->
                os.write(payload.toString().toByteArray(Charsets.UTF_8))
            }
            val code = conn.responseCode
            val body = (if (code in 200..299) conn.inputStream else conn.errorStream)
                ?.let { BufferedReader(InputStreamReader(it)).use { r -> r.readText() } }
                ?: ""
            conn.disconnect()
            if (code in 200..299) {
                Log.d(TAG, "tick ok ${payload.optLong("ts")}")
                true
            } else {
                Log.w(TAG, "tick http $code: ${body.take(200)}")
                false
            }
        } catch (e: Exception) {
            Log.w(TAG, "tick failed: ${e.javaClass.simpleName}: ${e.message}")
            false
        }
    }

    // ---- payload assembly -----------------------------------------------

    private fun buildPayload(nodeId: String, sampler: AndroidSampler): JSONObject {
        val sample = sampler.sample()
        val tsSec = System.currentTimeMillis() / 1000L
        return JSONObject().apply {
            put("contract", CONTRACT_RESOURCE_V0)
            put("node_id", nodeId)
            put("platform", "android")
            put("ts", tsSec)
            put("capabilities", org.json.JSONArray().apply { put("inference.cpu") })
            put("compute", sample.compute)
            put("thermal", sample.thermal)
            put("memory", sample.memory)
            put("power", sample.power)
        }
    }

    // ---- notification ----------------------------------------------------

    private fun ensureNotificationChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java) ?: return
        if (nm.getNotificationChannel(NOTIF_CHANNEL_ID) != null) return
        val ch = NotificationChannel(
            NOTIF_CHANNEL_ID,
            "Hive Agent",
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = "Posts node resource telemetry to the Swarm leader."
            setShowBadge(false)
        }
        nm.createNotificationChannel(ch)
    }

    private fun buildNotification(text: String): Notification {
        val openIntent = Intent(this, MainActivity::class.java)
        val pi = PendingIntent.getActivity(
            this, 0, openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
        return NotificationCompat.Builder(this, NOTIF_CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
            .setContentTitle("Swarm Hive Agent")
            .setContentText(text)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(pi)
            .build()
    }

    private fun updateNotification(text: String) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val nm = getSystemService(NotificationManager::class.java) ?: return
        nm.notify(NOTIF_ID, buildNotification(text))
    }
}
