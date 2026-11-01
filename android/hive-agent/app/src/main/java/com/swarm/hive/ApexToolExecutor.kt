package com.swarm.hive

import android.content.Context
import org.json.JSONObject

/** Executes validated tool calls. Only tools registered in [ApexPayloadBuilder] are reachable. */
class ApexToolExecutor(ctx: Context, private val prefs: HivePrefs) {
    private val sampler = AndroidSampler(ctx.applicationContext)

    fun execute(call: ApexOutput.ToolCall): String = when (call.name) {
        ApexPayloadBuilder.TOOL_DEVICE_TELEMETRY -> deviceTelemetry(call.arguments.getString("section"))
        ApexPayloadBuilder.TOOL_NODE_STATUS -> nodeStatus()
        else -> throw IllegalArgumentException("No executor registered for '${call.name}'.")
    }

    private fun deviceTelemetry(section: String): String {
        val s = sampler.sample()
        return when (section) {
            "compute" -> s.compute
            "thermal" -> s.thermal
            "memory" -> s.memory
            "power" -> s.power
            else -> JSONObject()
                .put("compute", s.compute)
                .put("thermal", s.thermal)
                .put("memory", s.memory)
                .put("power", s.power)
        }.toString()
    }

    private fun nodeStatus(): String = JSONObject()
        .put("leader", prefs.leader)
        .put("node_id", prefs.nodeId)
        .put("last_telemetry", prefs.lastTelemetrySummary)
        .put("last_job", prefs.lastJobSummary)
        .toString()
}
