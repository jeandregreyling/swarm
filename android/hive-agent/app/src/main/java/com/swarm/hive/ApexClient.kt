package com.swarm.hive

import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

/** Blocking HTTP transport to the local Vulkan llama-server. Call off the main thread. */
object ApexClient {
    private const val CONNECT_TIMEOUT_MS = 8_000
    private const val READ_TIMEOUT_MS = 180_000

    /** Returns APEX's raw output text; native `tool_calls` are re-encoded as tool JSON. */
    fun complete(payload: JSONObject): String {
        val conn = (URL(ApexPayloadBuilder.ENDPOINT).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = CONNECT_TIMEOUT_MS
            readTimeout = READ_TIMEOUT_MS
            setRequestProperty("Content-Type", "application/json")
        }
        try {
            conn.outputStream.use { it.write(payload.toString().toByteArray(Charsets.UTF_8)) }
            val code = conn.responseCode
            val stream = if (code in 200..299) conn.inputStream else conn.errorStream
            val body = stream?.bufferedReader()?.use { it.readText() }.orEmpty()
            if (code !in 200..299) throw IOException("APEX HTTP $code: ${body.take(200)}")
            val message = JSONObject(body).optJSONArray("choices")?.optJSONObject(0)?.optJSONObject("message")
                ?: throw IOException("APEX response missing choices[0].message")
            return nativeToolCall(message) ?: if (message.isNull("content")) "" else message.optString("content")
        } finally { conn.disconnect() }
    }

    // gpt-oss on /v1/chat/completions can return empty content with the call in tool_calls.
    private fun nativeToolCall(message: JSONObject): String? {
        val fn = message.optJSONArray("tool_calls")?.optJSONObject(0)?.optJSONObject("function") ?: return null
        return JSONObject().put("name", fn.optString("name")).put("arguments", fn.opt("arguments") ?: JSONObject()).toString()
    }
}
