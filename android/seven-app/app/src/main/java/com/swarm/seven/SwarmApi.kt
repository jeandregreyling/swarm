package com.swarm.seven

import android.content.Context
import android.content.SharedPreferences
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.io.IOException
import java.util.concurrent.TimeUnit

class SwarmApi(context: Context) {
    private val prefs: SharedPreferences =
        context.getSharedPreferences("swarm_prefs", Context.MODE_PRIVATE)
    private val client = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .build()

    private val jsonType = "application/json; charset=utf-8".toMediaType()

    var baseUrl: String
        get() = prefs.getString("leader_url", "http://100.87.66.45:5050") ?: "http://100.87.66.45:5050"
        set(value) = prefs.edit().putString("leader_url", value).apply()

    fun sendChat(message: String): String {
        val body = JSONObject().apply {
            put("message", message)
            put("agent", "seven")
        }.toString().toRequestBody(jsonType)

        val request = Request.Builder()
            .url("$baseUrl/api/chat")
            .post(body)
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
            val json = JSONObject(response.body?.string() ?: "{}")
            return json.optString("response", "No response")
        }
    }

    fun listNodes(): List<HiveNode> {
        val request = Request.Builder()
            .url("$baseUrl/api/hive/nodes")
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
            val json = JSONObject(response.body?.string() ?: "{}")
            val nodes = json.optJSONArray("nodes") ?: JSONArray()
            return (0 until nodes.length()).map { i ->
                val n = nodes.getJSONObject(i)
                HiveNode(
                    nodeId = n.optString("node_id"),
                    platform = n.optString("platform"),
                    ageS = n.optInt("age_s", -1),
                    capabilities = n.optJSONObject("telemetry")?.optJSONArray("capabilities")?.let { arr ->
                        (0 until arr.length()).map { arr.getString(it) }
                    } ?: emptyList()
                )
            }
        }
    }

    fun submitJob(kind: String, payload: JSONObject, capabilityReq: String? = null): String {
        val body = JSONObject().apply {
            put("kind", kind)
            put("payload", payload)
            capabilityReq?.let { put("capability_req", it) }
        }.toString().toRequestBody(jsonType)

        val request = Request.Builder()
            .url("$baseUrl/api/hive/jobs/submit")
            .post(body)
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("HTTP ${response.code}")
            val json = JSONObject(response.body?.string() ?: "{}")
            return json.optString("job_id", "")
        }
    }
}

data class HiveNode(
    val nodeId: String,
    val platform: String,
    val ageS: Int,
    val capabilities: List<String>
)
