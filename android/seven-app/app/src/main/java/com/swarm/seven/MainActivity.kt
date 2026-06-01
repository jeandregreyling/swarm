package com.swarm.seven

import android.content.Intent
import android.os.Bundle
import android.view.inputmethod.EditorInfo
import android.widget.Button
import android.widget.EditText
import android.widget.ImageButton
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.appbar.MaterialToolbar
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class MainActivity : AppCompatActivity() {
    private lateinit var chatAdapter: ChatAdapter
    private lateinit var recyclerView: RecyclerView
    private lateinit var inputField: EditText
    private lateinit var sendButton: ImageButton
    private lateinit var statusButton: Button
    private lateinit var gpuModelButton: Button
    private lateinit var tabletSundialView: SundialView
    private lateinit var leaderSundialView: SundialView
    private lateinit var potatoStatusText: TextView
    private lateinit var potatoResourceText: TextView
    private lateinit var potatoFarmText: TextView
    private lateinit var handoffProofText: TextView
    private lateinit var tinyModelProofText: TextView
    private lateinit var leaderStatusText: TextView
    private lateinit var leaderResourceText: TextView
    private val api by lazy { SwarmApi(this) }
    private val sampler by lazy { AndroidSampler(this) }
    private var sending = false

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val toolbar = findViewById<MaterialToolbar>(R.id.toolbar)
        toolbar.setOnMenuItemClickListener { item ->
            when (item.itemId) {
                R.id.action_nodes -> {
                    startActivity(Intent(this, NodesActivity::class.java))
                    true
                }
                R.id.action_settings -> {
                    startActivity(Intent(this, SettingsActivity::class.java))
                    true
                }
                else -> false
            }
        }

        recyclerView = findViewById(R.id.chatRecycler)
        recyclerView.layoutManager = LinearLayoutManager(this).apply {
            stackFromEnd = true
        }
        chatAdapter = ChatAdapter()
        recyclerView.adapter = chatAdapter

        inputField = findViewById(R.id.messageInput)
        sendButton = findViewById(R.id.sendButton)
        statusButton = findViewById(R.id.statusButton)
        gpuModelButton = findViewById(R.id.gpuModelButton)
        tabletSundialView = findViewById(R.id.tabletSundialView)
        leaderSundialView = findViewById(R.id.leaderSundialView)
        potatoStatusText = findViewById(R.id.potatoStatusText)
        potatoResourceText = findViewById(R.id.potatoResourceText)
        potatoFarmText = findViewById(R.id.potatoFarmText)
        handoffProofText = findViewById(R.id.handoffProofText)
        tinyModelProofText = findViewById(R.id.tinyModelProofText)
        leaderStatusText = findViewById(R.id.leaderStatusText)
        leaderResourceText = findViewById(R.id.leaderResourceText)

        sendButton.setOnClickListener {
            sendMessage()
        }
        statusButton.setOnClickListener {
            postStatusUpdate("Manual capability refresh")
        }
        gpuModelButton.setOnClickListener {
            runGpuBenchmarkHandoff()
        }

        // Allow keyboard send action
        inputField.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                sendMessage()
                true
            } else {
                false
            }
        }

        // Welcome message
        chatAdapter.addMessage(ChatMessage(
            text = "Seven online. This tablet now shows live Samsung + Dell capability consoles above chat.",
            isUser = false
        ))
        tabletSundialView.setStatus(10, "Booting", "Samsung node")
        leaderSundialView.setStatus(10, "Booting", "Dell leader")
        refreshPotatoStatus(postTelemetry = true)
    }

    private fun sendMessage() {
        if (sending) return

        val text = inputField.text.toString().trim()
        if (text.isEmpty()) return

        chatAdapter.addMessage(ChatMessage(text = text, isUser = true))
        inputField.text.clear()
        recyclerView.scrollToPosition(chatAdapter.itemCount - 1)

        if (handleLocalPotatoCommand(text)) return

        setSending(true)
        chatAdapter.setTyping(true)

        lifecycleScope.launch {
            try {
                val result = withContext(Dispatchers.IO) {
                    api.sendChat(text)
                }
                result.fold(
                    onSuccess = { response ->
                        chatAdapter.setTyping(false)
                        chatAdapter.addMessage(ChatMessage(
                            text = response,
                            isUser = false
                        ))
                    },
                    onFailure = { error ->
                        chatAdapter.setTyping(false)
                        chatAdapter.addMessage(ChatMessage(
                            text = "Couldn't reach Seven: ${error.message}",
                            isUser = false
                        ))
                    }
                )
                recyclerView.scrollToPosition(chatAdapter.itemCount - 1)
            } catch (e: Exception) {
                chatAdapter.setTyping(false)
                chatAdapter.addMessage(ChatMessage(
                    text = "Error: ${e.message}",
                    isUser = false
                ))
            } finally {
                setSending(false)
            }
        }
    }

    private fun setSending(busy: Boolean) {
        sending = busy
        sendButton.isEnabled = !busy
        sendButton.alpha = if (busy) 0.4f else 1.0f
    }

    private fun handleLocalPotatoCommand(text: String): Boolean {
        val t = text.lowercase()
        val isStatus = listOf("status", "resource", "potato", "node", "update").any { t.contains(it) }
        if (!isStatus) return false
        postStatusUpdate("Status update posted for this tablet.")
        return true
    }

    private fun postStatusUpdate(prefix: String) {
        setSending(true)
        chatAdapter.setTyping(true)
        lifecycleScope.launch {
            val message = withContext(Dispatchers.IO) {
                val enrol = api.enrol(sampler.nodeId(), sampler.deviceLabel())
                val telemetry = api.postTelemetry(sampler.telemetryPayload())
                val handoff = claimOneHandoff()
                val health = api.leaderHealth()
                buildString {
                    appendLine(prefix)
                    appendLine(sampler.summary())
                    appendLine()
                    appendLine("Leader: ${api.baseUrl}")
                    appendLine("Enrolment: ${enrol.fold({ "ok ($it)" }, { "failed: ${it.message}" })}")
                    appendLine("Telemetry: ${telemetry.fold({ "posted" }, { "failed: ${it.message}" })}")
                    appendLine("Handoff: ${handoff ?: "no queued packet"}")
                    appendLine("Leader health: ${health.fold({ if (it) "online" else "degraded" }, { "failed: ${it.message}" })}")
                    appendLine()
                    append("What this means: Samsung is now a visible capability node with GPU probe evidence, and Dell/leader capability visibility is updated in the dashboard cards.")
                }
            }
            chatAdapter.setTyping(false)
            chatAdapter.addMessage(ChatMessage(message, isUser = false))
            recyclerView.scrollToPosition(chatAdapter.itemCount - 1)
            refreshFarmTile()
            setSending(false)
        }
    }

    private fun refreshPotatoStatus(postTelemetry: Boolean) {
        updateTabletViews("Checking ${sampler.nodeId()}...")
        lifecycleScope.launch {
            val status = withContext(Dispatchers.IO) {
                val enrol = api.enrol(sampler.nodeId(), sampler.deviceLabel())
                val telemetry = if (postTelemetry) api.postTelemetry(sampler.telemetryPayload()) else Result.success(sampler.nodeId())
                val handoff = if (postTelemetry) claimOneHandoff() else null
                val health = api.leaderHealth()
                val ok = enrol.isSuccess && telemetry.isSuccess && health.getOrDefault(false)
                ok to when {
                    handoff != null -> handoff
                    enrol.isSuccess && telemetry.isSuccess -> "Connected potato: ${sampler.nodeId()}"
                    else -> "Potato not fully connected"
                }
            }
            updateTabletViews(status.second, leaderOk = status.first)
            refreshFarmTile()
        }
    }

    private fun runGpuBenchmarkHandoff() {
        setSending(true)
        gpuModelButton.isEnabled = false
        handoffProofText.text = "GPU handoff: submitting Samsung capability test..."
        tinyModelProofText.text = "GPU benchmark: waiting for Samsung node claim..."
        lifecycleScope.launch {
            val message = withContext(Dispatchers.IO) {
                val nodeId = sampler.nodeId()
                api.enrol(nodeId, sampler.deviceLabel())
                api.postTelemetry(sampler.telemetryPayload())
                val submit = api.submitJob(
                    kind = "tiny.gpu.benchmark",
                    payload = org.json.JSONObject().apply {
                        put("target_node", nodeId)
                        put("packet_profile", "gpu-capacity-ladder")
                        put("quantization", "shader-float")
                        put("model_capsule", defaultModelCapsule())
                        put("benchmark_sizes", org.json.JSONArray().also { arr ->
                            listOf(4, 16, 64, 128).forEach { arr.put(it) }
                        })
                    },
                    capabilityReq = "seven-app.gpu.capsule",
                    nodeId = nodeId,
                )
                val claimed = claimOneHandoff()
                val latest = api.listJobs().getOrNull().orEmpty()
                    .firstOrNull { it.nodeId == nodeId && it.kind == "tiny.gpu.benchmark" }
                buildString {
                    appendLine("Samsung GPU capability test")
                    appendLine("Submit: ${submit.fold({ it }, { "failed: ${it.message}" })}")
                    appendLine("Claim: ${claimed ?: "no queued packet claimed"}")
                    append(formatJobProof(latest))
                }
            }
            chatAdapter.addMessage(ChatMessage(message, isUser = false))
            recyclerView.scrollToPosition(chatAdapter.itemCount - 1)
            refreshFarmTile()
            gpuModelButton.isEnabled = true
            setSending(false)
        }
    }

    private fun claimOneHandoff(): String? {
        val nodeId = sampler.nodeId()
        val sample = sampler.sample()
        val job = api.claimNextJob(nodeId, sample.capabilities).getOrNull() ?: return null
        val result = org.json.JSONObject().apply {
            put("ok", true)
            put("runner", "seven-app")
            put("kind", job.kind)
            put("gpu_present", sample.capabilities.contains("inference.gpu"))
            put("npu_present", sample.capabilities.contains("inference.npu"))
            put("capabilities", org.json.JSONArray().also { arr -> sample.capabilities.forEach { arr.put(it) } })
            put("packet_profile", "tiny-quantized")
            put("quantization", "int8-preferred")
            if (job.kind == "gpu.probe" || job.kind == "tflite.gpu" || job.kind == "tflite.inference" || job.kind == "tiny.gpu.model" || job.kind == "tiny.gpu.benchmark") {
                val payload = job.payload ?: org.json.JSONObject()
                val sizes = payload.optJSONArray("benchmark_sizes")?.let { arr ->
                    (0 until arr.length()).mapNotNull { idx -> arr.optInt(idx).takeIf { it > 0 } }
                }.orEmpty()
                val modelSize = payload.optInt("model_size", 4)
                put("gpu_probe", GpuProbe.run(modelSize = modelSize, benchmarkSizes = sizes, capsule = payload.optJSONObject("model_capsule")))
            }
        }
        val reported = api.reportJobResult(nodeId, job.jobId, result).getOrDefault(false)
        return if (reported) "${job.kind} -> $nodeId completed" else "${job.kind} -> $nodeId claimed"
    }

    private fun defaultModelCapsule(): org.json.JSONObject = org.json.JSONObject().apply {
        put("capsule_id", "swarm-golden-linear-v1")
        put("model", "swarm-linear-4x4")
        put("input", org.json.JSONArray().also { arr -> listOf(0.18, 0.41, 0.73, 1.0).forEach { arr.put(it) } })
        put("weights", org.json.JSONArray().also { arr ->
            listOf(
                0.62, 0.10, 0.24, 0.02,
                0.12, 0.58, 0.16, 0.04,
                0.08, 0.18, 0.70, 0.02,
                0.20, 0.14, 0.18, 0.48,
            ).forEach { arr.put(it) }
        })
    }

    private fun updateTabletViews(status: String, leaderOk: Boolean = true) {
        val sample = sampler.sample()
        potatoStatusText.text = status
        potatoResourceText.text = buildString {
            append("Samsung caps: ")
            append(sample.capabilities.joinToString { prettyCapability(it) })
            append("\nMemory: ")
            append(sample.memory.optLong("ram_free_mb", -1))
            append("MB free / ")
            append(sample.memory.optLong("ram_total_mb", -1))
            append("MB · Battery ")
            append(sample.power.optInt("battery_pct", -1))
            append("%")
        }
        val free = sample.memory.optLong("ram_free_mb", 0)
        val total = sample.memory.optLong("ram_total_mb", 1).coerceAtLeast(1)
        val ramScore = ((free.toDouble() / total.toDouble()) * 25.0).toInt().coerceIn(0, 25)
        val batteryScore = if (sample.power.optInt("battery_pct", 0) >= 20) 20 else 6
        val capScore = 15 + sample.capabilities.count { it in setOf("inference.gpu", "inference.npu", "inference.tflite") } * 8
        val leaderScore = if (leaderOk) 25 else 0
        val score = (ramScore + batteryScore + capScore + leaderScore).coerceIn(0, 100)
        tabletSundialView.setStatus(
            score,
            if (leaderOk) "Samsung ready" else "Leader degraded",
            "${sample.capabilities.size} caps · ${free}MB free",
        )
    }

    private fun refreshFarmTile() {
        lifecycleScope.launch {
            val farm = withContext(Dispatchers.IO) {
                val nodes = api.listNodes().getOrNull().orEmpty()
                val jobs = api.listJobs().getOrNull().orEmpty()
                val live = nodes.count { !it.offline && it.ageS >= 0 }
                val p2 = nodes.firstOrNull { it.nodeId == sampler.nodeId() }
                val leader = nodes.firstOrNull { it.nodeId != sampler.nodeId() } ?: nodes.firstOrNull()
                val modelSummary = api.leaderModelSummary().getOrDefault("Leader models: unavailable")
                val latest = jobs.firstOrNull {
                    it.nodeId == sampler.nodeId() &&
                        (it.kind == "tiny.gpu.benchmark" || it.kind == "tiny.gpu.model" || it.kind == "gpu.probe" || it.kind == "tflite.gpu")
                }
                val leaderCaps = leader?.capabilities?.joinToString { prettyCapability(it) } ?: "none advertised"
                val leaderScore = (45 + (leader?.capabilities?.size ?: 0) * 8 - if (leader?.offline == true) 35 else 0).coerceIn(0, 100)
                val leaderLabel = when {
                    leader == null -> "Unknown"
                    leader.offline -> "Offline"
                    leader.ageS in 0..90 -> "Live"
                    else -> "Stale"
                }
                Quintuple(
                    "Potato Farm: ${nodes.size} nodes · $live live · this ${p2?.nodeId ?: sampler.nodeId()} shares ${p2?.capabilities?.joinToString { c -> c.removePrefix("inference.") } ?: "local telemetry"}",
                    latest,
                    formatJobProof(latest),
                    "Leader: ${(leader?.nodeId ?: "unknown")} · $leaderLabel · caps ${leader?.capabilities?.size ?: 0}",
                    "Leader capabilities: $leaderCaps\n$modelSummary",
                    leaderScore,
                )
            }
            potatoFarmText.text = farm.first
            handoffProofText.text = "GPU handoff: ${farm.second?.kind ?: "waiting"} -> ${farm.second?.nodeId ?: sampler.nodeId()} · ${farm.second?.status ?: "no packet"}"
            tinyModelProofText.text = farm.third
            leaderStatusText.text = farm.fourth
            leaderResourceText.text = farm.fifth
            leaderSundialView.setStatus(farm.sixth, if (farm.sixth >= 65) "Leader ready" else "Leader limited", "Dell capability surface")
        }
    }

    private fun formatJobProof(job: HiveJob?): String {
        if (job == null) return "Tiny GPU model: no completed model packet yet."
        return if (job.gpuProbeOk) {
            val latency = if (job.tinyModelLatencyMs >= 0.0) " · ${job.tinyModelLatencyMs}ms model" else ""
            val score = if (job.capacityScore >= 0) " · score ${job.capacityScore}" else ""
            val ladder = if (job.benchmarkSummary.isNotBlank()) " · ${job.benchmarkSummary}" else ""
            val capsuleLatency = if (job.capsuleLatencyMs >= 0.0) " ${job.capsuleLatencyMs}ms" else ""
            val capsuleOutput = if (job.capsuleOutputSummary.isNotBlank()) " -> ${job.capsuleOutputSummary}" else ""
            val capsule = if (job.capsuleId.isNotBlank()) " · capsule ${job.capsuleId} ${job.capsuleModel.ifBlank { "model" }}$capsuleLatency$capsuleOutput" else ""
            "GPU benchmark: ${job.tinyModel.ifBlank { "loaded" }} on ${job.gpuRenderer.ifBlank { "GPU" }} via ${job.runner.ifBlank { "seven-app" }}$latency$score$ladder$capsule"
        } else {
            "GPU benchmark: ${job.kind} ${job.status}; waiting for GPU result."
        }
    }

    private fun prettyCapability(cap: String): String {
        return cap
            .removePrefix("inference.")
            .removePrefix("seven-app.")
            .replace('.', ' ')
            .replace('-', ' ')
            .split(' ')
            .filter { it.isNotBlank() }
            .joinToString(" ") { token -> token.replaceFirstChar { if (it.isLowerCase()) it.titlecase() else it.toString() } }
    }

    private data class Quintuple(
        val first: String,
        val second: HiveJob?,
        val third: String,
        val fourth: String,
        val fifth: String,
        val sixth: Int,
    )
}