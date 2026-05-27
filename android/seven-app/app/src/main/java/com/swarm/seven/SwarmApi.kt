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
                        offline = n.optBoolean("offline", false),
                        expected = n.optBoolean("expected", false),
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

    fun listJobs(): Result<List<HiveJob>> {
        return try {
            val request = Request.Builder()
                .url("$baseUrl/api/hive/jobs")
                .build()

            client.newCall(request).execute().use { response ->
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                val raw = response.body?.string() ?: return Result.failure(IOException("Empty response"))
                val json = try {
                    JSONObject(raw)
                } catch (e: Exception) {
                    return Result.failure(IOException("Malformed server response"))
                }
                val jobs = json.optJSONArray("jobs") ?: JSONArray()
                val result = (0 until jobs.length()).map { i ->
                    val j = jobs.getJSONObject(i)
                    val jobResult = j.optJSONObject("result")
                    val gpuProbe = jobResult?.optJSONObject("gpu_probe")
                    val tinyModel = gpuProbe?.optJSONObject("tiny_model")
                    val capsule = gpuProbe?.optJSONObject("model_capsule")
                    val ladder = gpuProbe?.optJSONArray("benchmark_ladder")
                    HiveJob(
                        jobId = j.optString("job_id"),
                        nodeId = j.optString("node_id"),
                        kind = j.optString("kind"),
                        status = j.optString("status"),
                        capabilityReq = j.optString("capability_req"),
                        payload = j.optJSONObject("payload"),
                        runner = jobResult?.optString("runner", "") ?: "",
                        gpuProbeOk = gpuProbe?.optBoolean("ok", false) ?: false,
                        gpuRenderer = gpuProbe?.optString("renderer", "") ?: "",
                        tinyModel = tinyModel?.optString("model", "") ?: "",
                        tinyModelLatencyMs = tinyModel?.optDouble("latency_ms", -1.0) ?: -1.0,
                        capacityScore = gpuProbe?.optInt("capacity_score", -1) ?: -1,
                        benchmarkSummary = summarizeBenchmarkLadder(ladder),
                        capsuleId = capsule?.optString("capsule_id", "") ?: "",
                        capsuleModel = capsule?.optString("model", "") ?: "",
                        capsuleLatencyMs = capsule?.optDouble("latency_ms", -1.0) ?: -1.0,
                        capsuleOutputSummary = summarizeCapsuleOutput(capsule?.optJSONArray("output_rgba")),
                    )
                }
                Result.success(result)
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun submitJob(kind: String, payload: JSONObject, capabilityReq: String? = null, nodeId: String? = null): Result<String> {
        return try {
            val body = JSONObject().apply {
                put("kind", kind)
                put("payload", payload)
                capabilityReq?.let { put("capability_req", it) }
                nodeId?.let { put("node_id", it) }
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

    fun claimNextJob(nodeId: String, capabilities: List<String>): Result<HiveJob?> {
        return try {
            val body = JSONObject().apply {
                put("node_id", nodeId)
                put("capabilities", JSONArray().also { arr -> capabilities.forEach { arr.put(it) } })
            }.toString().toRequestBody(jsonType)
            val builder = Request.Builder()
                .url("$baseUrl/api/hive/jobs/next")
                .post(body)
            if (hiveToken.isNotBlank()) builder.header("X-Hive-Token", hiveToken)

            client.newCall(builder.build()).execute().use { response ->
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                val raw = response.body?.string() ?: return Result.failure(IOException("Empty response"))
                val json = JSONObject(raw)
                val job = json.optJSONObject("job") ?: return Result.success(null)
                Result.success(HiveJob(
                    jobId = job.optString("job_id"),
                    nodeId = nodeId,
                    kind = job.optString("kind"),
                    status = "claimed",
                    capabilityReq = "",
                    payload = job.optJSONObject("payload"),
                ))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    fun reportJobResult(nodeId: String, jobId: String, result: JSONObject): Result<Boolean> {
        return try {
            val body = JSONObject().apply {
                put("node_id", nodeId)
                put("job_id", jobId)
                put("result", result)
            }.toString().toRequestBody(jsonType)
            val builder = Request.Builder()
                .url("$baseUrl/api/hive/jobs/report")
                .post(body)
            if (hiveToken.isNotBlank()) builder.header("X-Hive-Token", hiveToken)

            client.newCall(builder.build()).execute().use { response ->
                if (!response.isSuccessful) throw IOException("Server returned HTTP ${response.code}")
                val json = JSONObject(response.body?.string() ?: "{}")
                Result.success(json.optBoolean("ok", false))
            }
        } catch (e: Exception) {
            Result.failure(e)
        }
    }

    private fun summarizeBenchmarkLadder(ladder: JSONArray?): String {
        if (ladder == null || ladder.length() == 0) return ""
        val bits = mutableListOf<String>()
        for (i in 0 until ladder.length()) {
            val row = ladder.optJSONObject(i) ?: continue
            val size = row.optInt("model_size", -1)
            val latency = row.optDouble("latency_ms", -1.0)
            if (size > 0 && latency >= 0.0) bits.add("${size}x$size ${latency}ms")
        }
        return bits.joinToString(" · ")
    }

    private fun summarizeCapsuleOutput(output: JSONArray?): String {
        if (output == null || output.length() == 0) return ""
        val values = mutableListOf<String>()
        for (i in 0 until output.length()) values.add(output.optInt(i).toString())
        return values.joinToString(prefix = "[", postfix = "]")
    }
}

data class HiveNode(
    val nodeId: String,
    val platform: String,
    val ageS: Int,
    val offline: Boolean,
    val expected: Boolean,
    val capabilities: List<String>
)

data class HiveJob(
    val jobId: String,
    val nodeId: String,
    val kind: String,
    val status: String,
    val capabilityReq: String,
    val payload: JSONObject? = null,
    val runner: String = "",
    val gpuProbeOk: Boolean = false,
    val gpuRenderer: String = "",
    val tinyModel: String = "",
    val tinyModelLatencyMs: Double = -1.0,
    val capacityScore: Int = -1,
    val benchmarkSummary: String = "",
    val capsuleId: String = "",
    val capsuleModel: String = "",
    val capsuleLatencyMs: Double = -1.0,
    val capsuleOutputSummary: String = "",
)
