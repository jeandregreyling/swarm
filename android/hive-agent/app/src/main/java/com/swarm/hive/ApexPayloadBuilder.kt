package com.swarm.hive

import org.json.JSONArray
import org.json.JSONObject

/**
 * ApexPayloadBuilder — the only place an APEX request body is assembled.
 *
 * DEOS architectural exception: this class is exempt from the 40-line limit
 * so the endpoint, system prompt, tool JSON schemas and payload shape are
 * defined together.
 *
 * Invariant: messages[0] is ALWAYS `role: system` with [APEX_SYSTEM_PROMPT].
 * The stored history (max [ApexMemoryRepository.HISTORY_LIMIT] rows) follows
 * beneath it. The prompt itself is never stored in SQLite.
 */
class ApexPayloadBuilder(private val memory: ApexMemoryRepository) {

    fun build(sessionId: String): JSONObject {
        val messages = JSONArray().put(message(ApexMemoryRepository.ROLE_SYSTEM, APEX_SYSTEM_PROMPT))
        memory.lastTurns(sessionId, ApexMemoryRepository.HISTORY_LIMIT)
            .filterNot { it.role == ApexMemoryRepository.ROLE_SYSTEM && it.content == APEX_SYSTEM_PROMPT }
            .forEach { messages.put(message(it.role, it.content)) }
        return JSONObject()
            .put("model", MODEL_ID)
            .put("messages", messages)
            .put("tools", toolSchemas())
            .put("stream", false)
            .put("temperature", TEMPERATURE)
            .put("max_tokens", MAX_TOKENS)
    }

    private fun message(role: String, content: String): JSONObject =
        JSONObject().put("role", role).put("content", content)

    companion object {
        // AMD host's Tailscale address; llama-server must bind 0.0.0.0:8080.
        const val ENDPOINT = "http://100.95.226.88:8080/v1/chat/completions"
        const val MODEL_ID = "gpt-oss:20B"
        private const val TEMPERATURE = 0.2
        private const val MAX_TOKENS = 1024

        const val APEX_SYSTEM_PROMPT =
            "You are APEX, the singular reasoning and execution node for the Friday's framework. \n" +
                "RULES:\n" +
                "1. You have access to tools defined in the JSON schema. When a user request requires a tool, you must output strictly valid JSON matching the schema. \n" +
                "2. Never output conversational filler, thoughts, or markdown formatting before or after the JSON tool payload.\n" +
                "3. Your identity is APEX. Rely entirely on the provided conversation history for context. Do not invent prior interactions."

        /** The exact shape APEX must emit as message content for a tool call. */
        const val TOOL_CALL_FORMAT = "{\"name\": \"<tool_name>\", \"arguments\": { ... }}"

        const val TOOL_DEVICE_TELEMETRY = "device_telemetry"
        const val TOOL_NODE_STATUS = "node_status"

        /** Tool registry: name → (description, JSON-schema parameters). */
        private val TOOLS: Map<String, Pair<String, JSONObject>> = linkedMapOf(
            TOOL_DEVICE_TELEMETRY to Pair(
                "Read live telemetry from this Android hive node.",
                JSONObject()
                    .put("type", "object")
                    .put(
                        "properties",
                        JSONObject().put(
                            "section",
                            JSONObject()
                                .put("type", "string")
                                .put("enum", JSONArray(listOf("compute", "thermal", "memory", "power", "all")))
                                .put("description", "Which telemetry block to return."),
                        ),
                    )
                    .put("required", JSONArray(listOf("section")))
                    .put("additionalProperties", false),
            ),
            TOOL_NODE_STATUS to Pair(
                "Report this node's leader URL, node id, and last telemetry/job summaries.",
                JSONObject()
                    .put("type", "object")
                    .put("properties", JSONObject())
                    .put("required", JSONArray())
                    .put("additionalProperties", false),
            ),
        )

        fun toolNames(): Set<String> = TOOLS.keys

        /** JSON-schema `parameters` for [name], or null if the tool is not registered. */
        fun toolParameters(name: String): JSONObject? = TOOLS[name]?.second

        /** OpenAI-compatible `tools` array sent to llama-server. */
        fun toolSchemas(): JSONArray {
            val arr = JSONArray()
            TOOLS.forEach { (name, spec) ->
                arr.put(
                    JSONObject()
                        .put("type", "function")
                        .put(
                            "function",
                            JSONObject()
                                .put("name", name)
                                .put("description", spec.first)
                                .put("parameters", spec.second),
                        )
                )
            }
            return arr
        }
    }
}
