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
    private lateinit var sundialView: SundialView
    private lateinit var potatoStatusText: TextView
    private lateinit var potatoResourceText: TextView
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
        sundialView = findViewById(R.id.sundialView)
        potatoStatusText = findViewById(R.id.potatoStatusText)
        potatoResourceText = findViewById(R.id.potatoResourceText)

        sendButton.setOnClickListener {
            sendMessage()
        }
        statusButton.setOnClickListener {
            postStatusUpdate("Manual status update")
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
            text = "Seven online. This tablet should be a potato node, not just a chat window. Try: status update",
            isUser = false
        ))
        sundialView.setStatus(10, "Booting", "Checking leader")
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
                    append("What this means: Seven now knows this Samsung is potato-2 and can share resources through Hive jobs. Local LLMs are not inside the Android app yet; they run through Termux/Ollama with small models after we clear enough storage.")
                }
            }
            chatAdapter.setTyping(false)
            chatAdapter.addMessage(ChatMessage(message, isUser = false))
            recyclerView.scrollToPosition(chatAdapter.itemCount - 1)
            updatePotatoViews("Connected as ${sampler.nodeId()}")
            setSending(false)
        }
    }

    private fun refreshPotatoStatus(postTelemetry: Boolean) {
        updatePotatoViews("Checking ${sampler.nodeId()}...")
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
            updatePotatoViews(status.second, leaderOk = status.first)
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
        }
        val reported = api.reportJobResult(nodeId, job.jobId, result).getOrDefault(false)
        return if (reported) "${job.kind} -> $nodeId completed" else "${job.kind} -> $nodeId claimed"
    }

    private fun updatePotatoViews(status: String, leaderOk: Boolean = true) {
        val sample = sampler.sample()
        potatoStatusText.text = status
        potatoResourceText.text = "Caps: ${sample.capabilities.joinToString()} · RAM ${sample.memory.optLong("ram_free_mb", -1)}MB free/${sample.memory.optLong("ram_total_mb", -1)}MB · Battery ${sample.power.optInt("battery_pct", -1)}%"
        val free = sample.memory.optLong("ram_free_mb", 0)
        val total = sample.memory.optLong("ram_total_mb", 1).coerceAtLeast(1)
        val ramScore = ((free.toDouble() / total.toDouble()) * 25.0).toInt().coerceIn(0, 25)
        val batteryScore = if (sample.power.optInt("battery_pct", 0) >= 20) 20 else 6
        val capScore = 15 + sample.capabilities.count { it in setOf("inference.gpu", "inference.npu", "inference.tflite") } * 8
        val leaderScore = if (leaderOk) 25 else 0
        val score = (ramScore + batteryScore + capScore + leaderScore).coerceIn(0, 100)
        sundialView.setStatus(
            score,
            if (leaderOk) "Online" else "Degraded",
            "${sample.capabilities.size} caps · ${free}MB free",
        )
    }
}