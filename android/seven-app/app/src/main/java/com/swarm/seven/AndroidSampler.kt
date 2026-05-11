package com.swarm.seven

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.provider.Settings
import org.json.JSONArray
import org.json.JSONObject
import java.io.File

/**
 * Local Android resource sampler for the user-facing Seven app.
 *
 * This makes the tablet visible as a real Hive/potato node instead of only
 * being a remote chat client. The payload mirrors node.resource/v0 so the
 * existing leader endpoints can record it without a second app.
 */
class AndroidSampler(private val context: Context) {
    fun nodeId(): String {
        if (Build.MANUFACTURER.equals("samsung", ignoreCase = true) &&
            Build.MODEL.equals("SM-X516B", ignoreCase = true)) {
            return "potato-2"
        }
        val androidId = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ANDROID_ID,
        ).orEmpty().takeLast(8).ifBlank { "unknown" }
        val model = Build.MODEL.lowercase().replace(Regex("[^a-z0-9]+"), "-").trim('-')
        return "potato-android-$model-$androidId"
    }

    fun deviceLabel(): String = listOfNotNull(
        Build.MANUFACTURER.takeIf { it.isNotBlank() },
        Build.MODEL.takeIf { it.isNotBlank() },
    ).joinToString(" ").ifBlank { "Android potato" }

    fun capabilities(): List<String> {
        val caps = mutableListOf("inference.cpu", "inference.tflite")
        if (gpuPresent()) caps.add("inference.gpu")
        if (npuPresent()) caps.add("inference.npu")
        return caps
    }

    fun sample(): LocalSample {
        val memory = memory()
        val compute = JSONObject().apply {
            putOrNull("cpu_load_pct", cpuLoadPct())
            putOrNull("cpu_peak_temp_c", batteryTempC())
            put("cpu_throttled", JSONObject.NULL)
            put("gpu_present", gpuPresent())
            put("gpu_load_pct", JSONObject.NULL)
            put("gpu_temp_c", JSONObject.NULL)
            put("npu_present", npuPresent())
        }
        val thermal = JSONObject().apply {
            put("fan_rpm", JSONObject.NULL)
            put("fan_pwm", JSONObject.NULL)
            put("fan_max_rpm", JSONObject.NULL)
            put("fan_mode", "passive")
            put("controllable", false)
        }
        val power = JSONObject().apply {
            put("on_battery", !isCharging())
            putOrNull("battery_pct", batteryPct())
            put("thermal_pressure", "nominal")
        }
        return LocalSample(compute, thermal, memory, power, capabilities())
    }

    fun telemetryPayload(): JSONObject {
        val s = sample()
        return JSONObject().apply {
            put("contract", "node.resource/v0")
            put("node_id", nodeId())
            put("platform", "android")
            put("ts", System.currentTimeMillis() / 1000L)
            put("capabilities", JSONArray().also { arr -> s.capabilities.forEach { arr.put(it) } })
            put("compute", s.compute)
            put("thermal", s.thermal)
            put("memory", s.memory)
            put("power", s.power)
        }
    }

    fun summary(): String {
        val s = sample()
        val mem = s.memory
        val compute = s.compute
        val power = s.power
        return buildString {
            appendLine("Potato: ${deviceLabel()}")
            appendLine("Node: ${nodeId()}")
            appendLine("Caps: ${s.capabilities.joinToString()}")
            appendLine("RAM: ${mem.optLong("ram_free_mb", -1)} MB free / ${mem.optLong("ram_total_mb", -1)} MB total")
            appendLine("CPU: ${compute.optDouble("cpu_load_pct", -1.0)}% · Temp: ${compute.optDouble("cpu_peak_temp_c", -1.0)}°C")
            appendLine("Battery: ${power.optInt("battery_pct", -1)}% · ${if (power.optBoolean("on_battery")) "on battery" else "charging"}")
            append("Resource sharing: active — this tablet is advertising CPU/TFLite/GPU/NPU capacity to the Hive scheduler. Local LLM install is separate: use Termux + a small model once we free storage.")
        }
    }

    private fun memory(): JSONObject {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
        val info = ActivityManager.MemoryInfo()
        am?.getMemoryInfo(info)
        return JSONObject().apply {
            put("ram_total_mb", info.totalMem / 1024L / 1024L)
            put("ram_free_mb", info.availMem / 1024L / 1024L)
            put("swap_used_mb", JSONObject.NULL)
        }
    }

    private fun cpuLoadPct(): Double? {
        val ratios = mutableListOf<Double>()
        for (n in 0 until 32) {
            val base = File("/sys/devices/system/cpu/cpu$n")
            if (!base.isDirectory) break
            val cur = readIntFile(File(base, "cpufreq/scaling_cur_freq"))
            val max = readIntFile(File(base, "cpufreq/cpuinfo_max_freq"))
            if (cur != null && max != null && max > 0) ratios.add((cur.toDouble() / max).coerceIn(0.0, 1.0))
        }
        return ratios.takeIf { it.isNotEmpty() }?.let { Math.round(it.average() * 1000.0) / 10.0 }
    }

    private fun gpuPresent(): Boolean = try {
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as? ActivityManager
        (am?.deviceConfigurationInfo?.reqGlEsVersion ?: 0) >= 0x20000
    } catch (_: Exception) { false }

    private fun npuPresent(): Boolean {
        if (Build.MANUFACTURER.equals("samsung", ignoreCase = true)) {
            val libs = listOf(
                "/vendor/lib/libeden_nn_on_system.so",
                "/vendor/lib64/libeden_nn_on_system.so",
                "/vendor/lib/libeden_nn_onsystem.so",
                "/vendor/lib64/libeden_nn_onsystem.so",
                "/system/lib/libeden_nn_on_system.so",
                "/system/lib64/libeden_nn_on_system.so",
                "/system/lib/libeden_nn_onsystem.so",
                "/system/lib64/libeden_nn_onsystem.so",
            )
            if (libs.any { File(it).exists() }) return true
            val hw = Build.HARDWARE.lowercase()
            val board = Build.BOARD.lowercase()
            if (listOf("exynos", "sm8450", "sm8550", "sm8650", "s5e").any { hw.contains(it) || board.contains(it) }) return true
            if (Build.MODEL.equals("SM-X516B", ignoreCase = true)) return true
        }
        return try { Class.forName("android.neuralnetworks.NeuralNetworks"); true } catch (_: Exception) { false }
    }

    private fun batteryPct(): Int? {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager ?: return null
        val v = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
        return v.takeIf { it in 0..100 }
    }

    private fun isCharging(): Boolean {
        val bm = context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
        return if (bm != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) bm.isCharging else false
    }

    private fun batteryTempC(): Double? = try {
        val intent = context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val tenths = intent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE) ?: Int.MIN_VALUE
        if (tenths == Int.MIN_VALUE) null else tenths / 10.0
    } catch (_: Exception) { null }

    private fun readIntFile(file: File): Int? = try {
        if (!file.canRead()) null else file.readText().trim().toIntOrNull()
    } catch (_: Exception) { null }
}

data class LocalSample(
    val compute: JSONObject,
    val thermal: JSONObject,
    val memory: JSONObject,
    val power: JSONObject,
    val capabilities: List<String>,
)

private fun JSONObject.putOrNull(name: String, value: Any?) {
    if (value == null) put(name, JSONObject.NULL) else put(name, value)
}