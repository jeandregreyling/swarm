package com.swarm.hive

import org.json.JSONObject

/** Classified APEX output, produced by [ApexToolValidator.parse]. */
sealed class ApexOutput {
    data class ToolCall(val name: String, val arguments: JSONObject) : ApexOutput()
    data class Reply(val text: String) : ApexOutput()
    data class Malformed(val error: String) : ApexOutput()
}
