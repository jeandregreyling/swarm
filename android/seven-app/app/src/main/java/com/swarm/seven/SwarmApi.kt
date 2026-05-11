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

    var hiveToken: String
        get() = prefs.getString("hive_token", "") ?: ""
        set(value) = prefs.edit().putString("hive_token", value).apply()

    fun sendChat(message: String): Result<String> {
        return try {
            val body = JSONObject().apply {
                put("message", message)
                put("agent", "seven")
            }.toString().toRequestBody(jsonType)

            val request = Request.Builder()
                .url("$baseUrl/api/chat")
                .post(body)
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                val raw = response.body?.string() ?: return Result.failure(IOException("Empty response"))
                val json = try {
                    JSONObject(raw)
                } catch (e: Exception) {
                    return Result.failure(IOException("Malformed server response"))
                }
                Result.success(json.optString("response", "No response"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun enrol(nodeId: String, label: String): Result<String> {
        return try {
            val body = JSONObject().apply {
                put("node_id", nodeId)
                put("label", label)
                put("platform", "android")
            }.toString().toRequestBody(jsonType)
            val request = Request.Builder()
                .url("$baseUrl/api/hive/enrol")
                .post(body)
                .build()
            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                val json = JSONObject(response.body?.string() ?: "{}")
                val token = json.optString("token", "")
                if (token.isNotBlank()) hiveToken = token
                Result.success(json.optString("node_id", nodeId))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun postTelemetry(payload: JSONObject): Result<String> {
        return try {
            val requestBuilder = Request.Builder()
                .url("$baseUrl/api/hive/telemetry")
                .post(payload.toString().toRequestBody(jsonType))
            if (hiveToken.isNotBlank()) requestBuilder.header("X-Hive-Token", hiveToken)
            client.newCall(requestBuilder.build()).execute().use { response ->
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                Result.success(payload.optString("node_id"))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun leaderHealth(): Result<Boolean> {
        return try {
            val request = Request.Builder()
                .url("$baseUrl/_health")
                .build()
            client.newCall(request).execute().use { response ->
                Result.success(response.isSuccessful)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun listNodes(): Result<List<HiveNode>> {
        return try {
            val request = Request.Builder()
                .url("$baseUrl/api/hive/nodes")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                val raw = response.body?.string() ?: return Result.failure(IOException("Empty response"))
                val json = try {
                    JSONObject(raw)
                } catch (e: Exception) {
                    return Result.failure(IOException("Malformed server response"))
                }
                val nodes = json.optJSONArray("nodes") ?: JSONArray()
                val result = (0 until nodes.length()).map { i ->
                    val n = nodes.getJSONObject(i)
                    HiveNode(
                        nodeId = n.optString("node_id"),
                        platform = n.optString("platform"),
                        ageS = n.optInt("age_s", -1),
                        capabilities = n.optJSONObject("telemetry")?.optJSONArray("capabilities")?.let { arr ->
                            (0 until arr.length()).map { j -> arr.optString(j) }
                        } ?: emptyList()
                    )
                }
                Result.success(result)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun submitJob(kind: String, payload: JSONObject, capabilityReq: String? = null): Result<String> {
        return try {
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
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                val raw = response.body?.string() ?: return Result.failure(IOException("Empty response"))
                val json = try {
                    JSONObject(raw)
                } catch (e: Exception) {
                    return Result.failure(IOException("Malformed server response"))
                }
                Result.success(json.optString("job_id", ""))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }
}

data class HiveNode(
    val nodeId: String,
    val platform: String,
    val ageS: Int,
    val capabilities: List<String>
)
