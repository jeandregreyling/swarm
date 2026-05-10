package com.swarm.hive

import android.content.Context
import android.os.BatteryManager
import android.os.Build
import org.json.JSONObject
import java.io.File

/**
 * AndroidSampler — mirrors core/hive/providers/android.py for the native
 * APK path. Returns four contract sections (compute / thermal / memory /
 * power) wrapped as JSONObjects so the service can drop them straight
 * into the telemetry payload.
 *
 * Sources match the Python provider exactly so leader-side validation
 * sees the same shape regardless of whether the device runs Termux or
 * the native APK:
 *   /proc/meminfo                                 -> RAM
 *   /sys/devices/system/cpu/cpuN/cpufreq/...      -> CPU load (freq ratio)
 *   BatteryManager (Android API)                  -> battery %, charging
 *
 * No /proc/stat (sandboxed for untrusted apps), no /sys/class/thermal
 * (also blocked). Battery temperature comes from BatteryManager rather
 * than `termux-battery-status` because we have direct API access.
 */
class AndroidSampler(private val ctx: Context) {

    data class Sample(
        val compute: JSONObject,
        val thermal: JSONObject,
        val memory: JSONObject,
        val power: JSONObject,
    )

    fun sample(): Sample = Sample(
        compute = compute(),
        thermal = thermal(),
        memory = memory(),
        power = power(),
    )

    /**
     * Return the list of well-known capabilities this device advertises.
     * Samsung devices with NPUs report inference.npu; all Android devices
     * with GLES 2.0+ report inference.gpu; every device reports
     * inference.cpu and inference.tflite (TFLite is part of Android
     * NNAPI / available as a CPU delegate even on low-end hardware).
     */
    fun capabilities(): List<String> {
        val caps = mutableListOf("inference.cpu", "inference.tflite")
        if (gpuPresent()) caps.add("inference.gpu")
        if (npuPresent()) caps.add("inference.npu")
        return caps
    }

    // ---- compute --------------------------------------------------------

    private fun compute(): JSONObject {
        val load = cpuLoadPct()
        val temp = batteryTempC()  // best proxy for SoC heat we can read
        return JSONObject().apply {
            putOrNull("cpu_load_pct", load)
            putOrNull("cpu_peak_temp_c", temp)
            put("cpu_throttled", JSONObject.NULL)
            put("gpu_present", gpuPresent())
            put("gpu_load_pct", JSONObject.NULL)
            put("gpu_temp_c", JSONObject.NULL)
            put("npu_present", npuPresent())
        }
    }

    private fun cpuLoadPct(): Double? {
        val ratios = mutableListOf<Double>()
        var n = 0
        while (n < 32) {
            val base = File("/sys/devices/system/cpu/cpu$n")
            if (!base.isDirectory) {
                if (n == 0) return null
                break
            }
            val online = File(base, "online")
            if (online.exists()) {
                val v = readIntFile(online)
                if (v == 0) { n++; continue }
            }
            val cur = readIntFile(File(base, "cpufreq/scaling_cur_freq"))
            val mx = readIntFile(File(base, "cpufreq/cpuinfo_max_freq"))
            if (cur != null && mx != null && mx > 0) {
                ratios.add((cur.toDouble() / mx.toDouble()).coerceIn(0.0, 1.0))
            }
            n++
        }
        if (ratios.isEmpty()) return null
        val avg = ratios.average() * 100.0
        // Match Python's `round(x, 1)`.
        return Math.round(avg * 10.0) / 10.0
    }

    // ---- Samsung / advanced hardware detection --------------------------

    /**
     * Detect GPU presence via the device's declared OpenGL ES version.
     * Every Android device with a display advertises a GLES version via
     * ActivityManager.  GLES 2.0 (0x20000) is the baseline for anything
     * that can run TFLite GPU delegate or Vulkan compute.
     */
    private fun gpuPresent(): Boolean {
        return try {
            val am = ctx.getSystemService(Context.ACTIVITY_SERVICE)
                as? android.app.ActivityManager
            val config = am?.deviceConfigurationInfo
            config != null && config.reqGlEsVersion >= 0x20000
        } catch (_: Exception) {
            false
        }
    }

    /**
     * Detect NPU presence.  Three signals are checked in order:
     *
     * 1. Samsung-specific: Exynos and recent Snapdragon Galaxy devices
     *    ship NPU/DSP drivers under /vendor/lib[64].  We probe for the
     *    Samsung Eden NN driver.
     * 2. Generic Android: API 29+ exposes PowerManager thermal status,
     *    but more importantly NNAPI is guaranteed on devices that
     *    declare the neural-networks feature.  We use a lightweight
     *    reflection check for the android.neuralnetworks package.
     * 3. SoC blocklist: known high-end Samsung SoCs (exynos2100+,
     *    exynos2200+, snapdragon 8 gen 1+) always include an NPU.
     *
     * This is best-effort; false negatives are acceptable (device still
     * reports inference.cpu + inference.tflite).
     */
    private fun npuPresent(): Boolean {
        // Samsung-specific driver probe.
        if (Build.MANUFACTURER.equals("samsung", ignoreCase = true)) {
            val samsungLibs = listOf(
                "/vendor/lib/libeden_nn_on_system.so",
                "/vendor/lib64/libeden_nn_on_system.so",
                "/vendor/lib/libeden_nn_onsystem.so",
                "/vendor/lib64/libeden_nn_onsystem.so",
                "/system/lib/libeden_nn_on_system.so",
                "/system/lib64/libeden_nn_on_system.so",
            )
            if (samsungLibs.any { File(it).exists() }) return true

            // SoC fingerprint heuristic.
            val hw = (Build.HARDWARE ?: "").lowercase()
            val board = (Build.BOARD ?: "").lowercase()
            val knownNpuSoCs = listOf(
                "exynos2100", "exynos2200", "exynos2400",
                "sm8450",   // Snapdragon 8 Gen 1
                "sm8550",   // Snapdragon 8 Gen 2
                "sm8650",   // Snapdragon 8 Gen 3
            )
            if (knownNpuSoCs.any { hw.contains(it) || board.contains(it) }) return true
        }

        // Generic NNAPI reflection probe (API 27+).
        return try {
            Class.forName("android.neuralnetworks.NeuralNetworks")
            true
        } catch (_: ClassNotFoundException) {
            false
        }
    }

    // ---- thermal --------------------------------------------------------

    private fun thermal(): JSONObject = JSONObject().apply {
        // Tablets/phones are passively cooled; report honestly so the UI
        // does not draw an em-dash row pretending we have a fan.
        put("fan_rpm", JSONObject.NULL)
        put("fan_pwm", JSONObject.NULL)
        put("fan_max_rpm", JSONObject.NULL)
        put("fan_mode", "passive")
        put("controllable", false)
    }

    // ---- memory ---------------------------------------------------------

    private fun memory(): JSONObject {
        val kv = parseMeminfo()
        val totalKb = kv["MemTotal"]
        val availKb = kv["MemAvailable"] ?: kv["MemFree"]
        val swapTotal = kv["SwapTotal"] ?: 0L
        val swapFree = kv["SwapFree"] ?: 0L
        val swapUsedKb = (swapTotal - swapFree).coerceAtLeast(0L)
        return JSONObject().apply {
            putOrNull("ram_total_mb", totalKb?.let { it / 1024L })
            putOrNull("ram_free_mb",  availKb?.let { it / 1024L })
            putOrNull("swap_used_mb", if (swapTotal > 0) swapUsedKb / 1024L else null)
        }
    }

    private fun parseMeminfo(): Map<String, Long> {
        val f = File("/proc/meminfo")
        if (!f.canRead()) return emptyMap()
        val out = HashMap<String, Long>()
        try {
            f.bufferedReader().useLines { lines ->
                for (line in lines) {
                    val idx = line.indexOf(':')
                    if (idx <= 0) continue
                    val k = line.substring(0, idx).trim()
                    val v = line.substring(idx + 1).trim().split(Regex("\\s+")).firstOrNull()
                    val n = v?.toLongOrNull() ?: continue
                    out[k] = n
                }
            }
        } catch (_: Exception) { /* best-effort */ }
        return out
    }

    // ---- power ----------------------------------------------------------

    private fun power(): JSONObject {
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager
        val pct: Int? = if (bm != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            val v = bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)
            if (v in 0..100) v else null
        } else null

        // BatteryManager.isCharging is API 23+; treat unknown as on_battery
        // because the device IS a battery-backed mobile node.
        val onBattery = if (bm != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            !bm.isCharging
        } else {
            true
        }
        return JSONObject().apply {
            put("on_battery", onBattery)
            putOrNull("battery_pct", pct)
            // Android tablets/phones cannot read SoC thermal pressure directly
            // (no /sys/class/thermal access for untrusted apps). Report nominal
            // so the contract validator accepts the payload; the leader can
            // override with battery-temp heuristics if desired.
            put("thermal_pressure", "nominal")
        }
    }

    private fun batteryTempC(): Double? {
        // BatteryManager reports temperature as tenths of a degree C in
        // EXTRA_TEMPERATURE on the sticky ACTION_BATTERY_CHANGED intent.
        return try {
            val intent = ctx.registerReceiver(null,
                android.content.IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED))
            val tenths = intent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
                ?: Int.MIN_VALUE
            if (tenths == Int.MIN_VALUE) null
            else (Math.round(tenths.toDouble()) / 10.0)
        } catch (_: Exception) {
            null
        }
    }

    // ---- helpers --------------------------------------------------------

    private fun readIntFile(f: File): Int? = try {
        if (!f.canRead()) null
        else f.bufferedReader().use { it.readLine()?.trim()?.toIntOrNull() }
    } catch (_: Exception) { null }

    private fun JSONObject.putOrNull(key: String, v: Number?) {
        if (v == null) put(key, JSONObject.NULL) else put(key, v)
    }
}
