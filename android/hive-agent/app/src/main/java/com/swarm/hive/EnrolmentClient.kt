package com.swarm.hive

import android.content.Context
import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL

/**
 * EnrolmentClient — calls POST {leader}/api/hive/enrol with an optional
 * preferred node id. The leader returns the canonical node_id and a
 * token that subsequent telemetry posts must include in X-Hive-Token.
 *
 * Run on a worker thread; HttpURLConnection blocks. Returns null on any
 * failure (network, non-2xx, malformed response) so the caller can
 * surface a single error message without a crash dialog.
 */
object EnrolmentClient {

    private const val TAG = "HiveEnrol"

    data class Result(
        val nodeId: String,
        val leader: String,
        val token: String,
    )

    fun enrol(leader: String, preferredNodeId: String?): Result? {
        if (leader.isBlank()) return null
        val urlStr = leader.trimEnd('/') + "/api/hive/enrol"
        val body = JSONObject().apply {
            if (!preferredNodeId.isNullOrBlank()) put("node_id", preferredNodeId)
            put("platform", "android")
        }
        return try {
            val conn = (URL(urlStr).openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 8_000
                readTimeout = 8_000
                setRequestProperty("Content-Type", "application/json")
                setRequestProperty("Accept", "application/json")
            }
            conn.outputStream.use { os: OutputStream ->
                os.write(body.toString().toByteArray(Charsets.UTF_8))
            }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val text = stream
                ?.let { BufferedReader(InputStreamReader(it)).use { r -> r.readText() } }
                ?: ""
            conn.disconnect()
            if (code !in 200..299) {
                Log.w(TAG, "enrol http $code: ${text.take(200)}")
                return null
            }
            val j = JSONObject(text)
            Result(
                nodeId = j.optString("node_id"),
                leader = j.optString("leader", leader),
                token  = j.optString("token"),
            ).takeIf { it.nodeId.isNotBlank() && it.token.isNotBlank() }
        } catch (e: Exception) {
            Log.w(TAG, "enrol failed: ${e.javaClass.simpleName}: ${e.message}")
            null
        }
    }
}
