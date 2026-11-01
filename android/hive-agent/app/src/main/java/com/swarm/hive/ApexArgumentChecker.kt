package com.swarm.hive

import org.json.JSONArray
import org.json.JSONObject

/** Checks tool arguments against the JSON-schema subset used by [ApexPayloadBuilder]. */
object ApexArgumentChecker {
    /** Returns a human-readable violation for APEX to correct, or null when valid. */
    fun firstViolation(args: JSONObject, schema: JSONObject): String? {
        val props = schema.optJSONObject("properties") ?: JSONObject()
        val required = schema.optJSONArray("required") ?: JSONArray()
        for (i in 0 until required.length()) {
            val key = required.getString(i)
            if (!args.has(key)) return "Missing required argument '$key'."
        }
        val strict = !schema.optBoolean("additionalProperties", true)
        for (key in args.keys()) {
            val spec = props.optJSONObject(key)
                ?: if (strict) return "Unknown argument '$key'." else continue
            val type = spec.optString("type")
            val value = args.get(key)
            if (!matchesType(value, type)) return "Argument '$key' must be of type $type."
            val allowed = spec.optJSONArray("enum") ?: continue
            if ((0 until allowed.length()).none { allowed.get(it) == value }) {
                return "Argument '$key' must be one of $allowed."
            }
        }
        return null
    }

    private fun matchesType(value: Any, type: String): Boolean = when (type) {
        "string" -> value is String
        "integer" -> value is Int || value is Long
        "number" -> value is Number
        "boolean" -> value is Boolean
        "object" -> value is JSONObject
        "array" -> value is JSONArray
        else -> true
    }
}
