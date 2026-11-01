package com.swarm.hive

import android.content.Context
import org.json.JSONObject
import com.swarm.hive.ApexMemoryRepository.Companion as Mem
/** Single-agent APEX node: SQLite memory → payload → llama-server → validate → execute. */
class ApexNode(ctx: Context, prefs: HivePrefs) {
    private val memory = ApexMemoryRepository(ctx)
    private val builder = ApexPayloadBuilder(memory)
    private val executor = ApexToolExecutor(ctx, prefs)

    /** Blocking; call off the main thread. Never throws, so the node cannot crash on bad output. */
    fun handle(sessionId: String, userText: String): String = try {
        memory.insertMessage(sessionId, Mem.ROLE_USER, userText)
        runLoop(sessionId)
    } catch (e: Exception) { "APEX unavailable: ${e.message}" }
    // Correction rows share the 5-message window; 2 retries keep the user turn in view.
    private fun runLoop(sessionId: String): String {
        repeat(MAX_SELF_CORRECTIONS + 1) {
            val raw = ApexClient.complete(builder.build(sessionId))
            when (val out = ApexToolValidator.parse(raw)) {
                is ApexOutput.Reply -> return out.text.also { memory.insertMessage(sessionId, Mem.ROLE_ASSISTANT, it) }
                is ApexOutput.ToolCall -> return runTool(sessionId, out)
                is ApexOutput.Malformed -> {
                    memory.insertMessage(sessionId, Mem.ROLE_ASSISTANT, raw.ifBlank { "(empty)" })
                    memory.insertMessage(sessionId, Mem.ROLE_SYSTEM, "TOOL_ERROR: ${out.error} Reply with exactly ${ApexPayloadBuilder.TOOL_CALL_FORMAT}")
                }
            }
        }
        return "APEX failed to emit a valid tool payload after $MAX_SELF_CORRECTIONS corrections."
    }
    private fun runTool(sessionId: String, call: ApexOutput.ToolCall): String {
        memory.insertMessage(sessionId, Mem.ROLE_ASSISTANT, JSONObject().put("name", call.name).put("arguments", call.arguments).toString())
        val result = try { executor.execute(call) } catch (e: Exception) { "TOOL_FAILED: ${e.message}" }
        memory.insertMessage(sessionId, Mem.ROLE_SYSTEM, "TOOL_RESULT ${call.name}: $result")
        return result
    }
    fun close() = memory.close()
    private companion object { const val MAX_SELF_CORRECTIONS = 2 }
}
