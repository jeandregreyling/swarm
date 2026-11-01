package com.swarm.hive

import org.json.JSONException
import org.json.JSONObject
import org.json.JSONTokener

/** DEOS Executes layer: classifies raw APEX output. Never throws. */
object ApexToolValidator {

    fun parse(raw: String): ApexOutput {
        val text = raw.trim()
        if (text.isEmpty()) return ApexOutput.Malformed("Empty response.")
        if (!isToolAttempt(text)) return ApexOutput.Reply(text)
        return try { validate(text) } catch (e: JSONException) { ApexOutput.Malformed("Invalid JSON: ${e.message}") }
    }

    private fun isToolAttempt(text: String): Boolean =
        text.startsWith("{") || text.startsWith("[") || text.startsWith("```") ||
            ("\"arguments\"" in text && "{" in text)

    private fun validate(text: String): ApexOutput {
        val tokener = JSONTokener(text)
        val root = tokener.nextValue() as? JSONObject
            ?: return ApexOutput.Malformed("Tool payload must be one bare JSON object: no markdown, no surrounding text.")
        if (tokener.more()) return ApexOutput.Malformed("Unexpected text after the JSON object.")
        root.keys().asSequence().firstOrNull { it != "name" && it != "arguments" }
            ?.let { return ApexOutput.Malformed("Unexpected top-level key '$it'.") }
        val name = root.optString("name")
        val schema = ApexPayloadBuilder.toolParameters(name)
            ?: return ApexOutput.Malformed("Unknown tool '$name'. Allowed: ${ApexPayloadBuilder.toolNames()}.")
        val args = when (val a = root.opt("arguments")) {
            null -> JSONObject()
            is JSONObject -> a
            is String -> JSONObject(a)
            else -> return ApexOutput.Malformed("'arguments' must be a JSON object.")
        }
        ApexArgumentChecker.firstViolation(args, schema)?.let { return ApexOutput.Malformed(it) }
        return ApexOutput.ToolCall(name, args)
    }
}
