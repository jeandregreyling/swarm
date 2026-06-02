package com.swarm.hive

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.PorterDuff
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import org.json.JSONArray
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * MainActivity — minimal one-screen UI:
 *   • Leader URL input (e.g. http://100.87.66.45:5050)
 *   • Optional node-id override (suggestion pre-filled)
 *   • [Connect] runs enrolment + persists token + starts the service
 *   • Status line tells the user whether telemetry is flowing
 *
 * Everything in this activity is intentionally synchronous-looking
 * (button click → background thread → main-thread UI update). No
 * coroutines, no view binding, no DI: the surface is small enough that
 * the boilerplate of those tools would hurt readability.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val DEFAULT_LEADER = "http://100.87.66.45:5050"
        private const val SAMSUNG_POTATO_NODE_ID = "potato-2"
    }

    private lateinit var prefs: HivePrefs
    private lateinit var leaderField: EditText
    private lateinit var nodeIdField: EditText
    private lateinit var statusView: TextView
    private lateinit var statusDot: View
    private lateinit var runtimeSummaryView: TextView
    private lateinit var farmSummaryView: TextView
    private lateinit var refreshButton: Button
    private lateinit var gpuProofButton: Button
    private lateinit var modelSummaryView: TextView
    private lateinit var chatInput: EditText
    private lateinit var chatResponseView: TextView
    private lateinit var modelsButton: Button
    private lateinit var prevModelButton: Button
    private lateinit var nextModelButton: Button
    private lateinit var sendChatButton: Button
    private val leaderModels = mutableListOf<String>()
    private var selectedModelIndex = 0

    private val notifPermLauncher =
        registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) {
            // Result ignored; FGS still runs without the permission, the
            // notification just won't render visibly on Android 13+.
        }

    /** Status dot colours by state. Keeps refreshStatus / onConnectClicked
     *  from caring about how the dot is tinted. */
    private enum class State { Idle, Working, Live, Error }

    private fun setStatus(text: String, state: State) {
        statusView.text = text
        val color = ContextCompat.getColor(
            this,
            when (state) {
                State.Idle    -> R.color.status_idle
                State.Working -> R.color.status_warn
                State.Live    -> R.color.status_ok
                State.Error   -> R.color.status_err
            }
        )
        // setColorFilter on the background drawable tints just the dot
        // without recreating it (drawable is shared across instances so
        // we mutate() defensively).
        statusDot.background?.mutate()?.setColorFilter(color, PorterDuff.Mode.SRC_IN)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = HivePrefs(this)

        leaderField = findViewById(R.id.field_leader)
        nodeIdField = findViewById(R.id.field_node_id)
        statusView  = findViewById(R.id.status)
        statusDot   = findViewById(R.id.status_dot)
        runtimeSummaryView = findViewById(R.id.runtime_summary)
        farmSummaryView = findViewById(R.id.farm_summary)
        refreshButton = findViewById(R.id.btn_refresh)
        gpuProofButton = findViewById(R.id.btn_gpu_proof)
        modelSummaryView = findViewById(R.id.model_summary)
        chatInput = findViewById(R.id.chat_input)
        chatResponseView = findViewById(R.id.chat_response)
        modelsButton = findViewById(R.id.btn_models)
        prevModelButton = findViewById(R.id.btn_prev_model)
        nextModelButton = findViewById(R.id.btn_next_model)
        sendChatButton = findViewById(R.id.btn_send_chat)

        val join = parseJoinIntent(intent?.data)
        leaderField.setText(join?.leader ?: prefs.leader)
        nodeIdField.setText(join?.nodeId ?: prefs.nodeId.ifBlank { prefs.suggestNodeId() })
        refreshStatus()

        findViewById<Button>(R.id.btn_connect).setOnClickListener { onConnectClicked() }
        findViewById<Button>(R.id.btn_stop).setOnClickListener {
            AgentLauncher.stop(this)
            setStatus(getString(R.string.status_stopped), State.Idle)
            refreshRuntimeCard()
        }
        refreshButton.setOnClickListener { refreshFarmStatus() }
        gpuProofButton.setOnClickListener { submitGpuProof() }
        modelsButton.setOnClickListener { refreshModels() }
        prevModelButton.setOnClickListener { selectModel(-1) }
        nextModelButton.setOnClickListener { selectModel(1) }
        sendChatButton.setOnClickListener { sendLeaderChat() }

        // Wire keyboard return keys: leader's Next jumps to node id,
        // node id's Done triggers Connect. Without this the on-screen
        // keyboard's enter key does nothing on Android.
        leaderField.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_NEXT) {
                nodeIdField.requestFocus()
                true
            } else false
        }
        nodeIdField.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                hideKeyboard()
                onConnectClicked()
                true
            } else false
        }
        chatInput.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_SEND) {
                hideKeyboard()
                sendLeaderChat()
                true
            } else false
        }

        ensureNotificationPermission()
        refreshRuntimeCard()

        // Dedicated potato-slate mode: the Samsung should join the farm
        // without manual typing after a reinstall or clean-up.
        if (join != null) {
            connect(join.leader, join.nodeId)
        } else if (prefs.leader.isBlank() || prefs.token.isBlank()) {
            val leader = normalizeLeaderUrl(DEFAULT_LEADER)
            val nodeId = if (Build.MANUFACTURER.equals("samsung", ignoreCase = true)) {
                SAMSUNG_POTATO_NODE_ID
            } else {
                prefs.suggestNodeId()
            }
            leaderField.setText(leader)
            nodeIdField.setText(nodeId)
            connect(leader, nodeId)
        } else {
            AgentLauncher.start(this)
            refreshFarmStatus()
            refreshModels()
        }
    }

    override fun onNewIntent(intent: android.content.Intent?) {
        super.onNewIntent(intent)
        val join = parseJoinIntent(intent?.data) ?: return
        leaderField.setText(join.leader)
        nodeIdField.setText(join.nodeId ?: nodeIdField.text.toString())
        connect(join.leader, join.nodeId ?: nodeIdField.text.toString())
    }

    private data class JoinRequest(val leader: String, val nodeId: String?)

    private fun parseJoinIntent(uri: Uri?): JoinRequest? {
        if (uri == null || uri.scheme != "swarmhive" || uri.host != "join") return null
        val leader = normalizeLeaderUrl(uri.getQueryParameter("leader").orEmpty())
        if (leader.isBlank()) return null
        val nodeId = uri.getQueryParameter("node_id")
            ?.trim()
            ?.takeIf { it.isNotBlank() }
        return JoinRequest(leader, nodeId)
    }

    private fun hideKeyboard() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as? InputMethodManager
        val focused = currentFocus ?: leaderField
        imm?.hideSoftInputFromWindow(focused.windowToken, 0)
    }

    private fun onConnectClicked() {
        val rawLeader = leaderField.text.toString().trim()
        val leader = normalizeLeaderUrl(rawLeader)
        val preferred = nodeIdField.text.toString().trim().ifEmpty { null }
        if (leader.isBlank()) {
            Toast.makeText(this, R.string.toast_leader_required, Toast.LENGTH_SHORT).show()
            return
        }
        leaderField.setText(leader)  // show the cleaned-up form back to the user
        connect(leader, preferred)
    }

    private fun connect(leader: String, preferred: String?) {
        setStatus(getString(R.string.status_enrolling), State.Working)
        thread(name = "hive-enrol") {
            val res = EnrolmentClient.enrol(leader, preferred)
            runOnUiThread {
                if (res == null) {
                    setStatus(getString(R.string.status_enrol_failed), State.Error)
                    return@runOnUiThread
                }
                prefs.leader = res.leader
                prefs.nodeId = res.nodeId
                prefs.token  = res.token
                nodeIdField.setText(res.nodeId)
                AgentLauncher.start(this)
                setStatus(getString(R.string.status_running, res.nodeId), State.Live)
                refreshRuntimeCard()
                refreshFarmStatus()
                refreshModels()
            }
        }
    }

    private fun refreshStatus() {
        when {
            !prefs.isConfigured ->
                setStatus(getString(R.string.status_idle), State.Idle)
            prefs.token.isBlank() ->
                setStatus(getString(R.string.status_needs_enrol), State.Working)
            else ->
                setStatus(getString(R.string.status_running, prefs.nodeId), State.Live)
        }
    }

    private fun refreshRuntimeCard() {
        val telemetryAge = ageLabel(prefs.lastTelemetryTs)
        val jobAge = ageLabel(prefs.lastJobTs)
        val tokenState = if (prefs.token.isBlank()) "missing token" else "token ready"
        runtimeSummaryView.text = buildString {
            append("Leader: ").append(prefs.leader.ifBlank { "not set" })
            append("\nNode: ").append(prefs.nodeId.ifBlank { "not enrolled" })
            append(" · ").append(tokenState)
            append("\nTelemetry: ")
            append(prefs.lastTelemetrySummary.ifBlank { "not posted yet" })
            if (telemetryAge.isNotBlank()) append(" · ").append(telemetryAge)
            append("\nLast job: ")
            append(prefs.lastJobSummary.ifBlank { "no job completed yet" })
            if (jobAge.isNotBlank()) append(" · ").append(jobAge)
        }
    }

    private fun refreshFarmStatus() {
        val leader = prefs.leader.ifBlank { normalizeLeaderUrl(leaderField.text.toString()) }
        if (leader.isBlank()) {
            farmSummaryView.text = getString(R.string.farm_summary_empty)
            return
        }
        setStatus(getString(R.string.status_refreshing), State.Working)
        thread(name = "hive-refresh") {
            val summary = try {
                val nodes = getJson(leader, "/api/hive/nodes")
                val jobs = getJson(leader, "/api/hive/jobs")
                val models = getJson(leader, "/api/localai/status")
                formatFarmSummary(nodes, jobs, models)
            } catch (e: Exception) {
                "Leader check failed: ${e.message}"
            }
            runOnUiThread {
                farmSummaryView.text = summary
                refreshRuntimeCard()
                refreshStatus()
            }
        }
    }

    private fun submitGpuProof() {
        val leader = prefs.leader.ifBlank { normalizeLeaderUrl(leaderField.text.toString()) }
        val nodeId = prefs.nodeId.ifBlank { nodeIdField.text.toString().trim() }
        if (leader.isBlank() || nodeId.isBlank()) {
            Toast.makeText(this, R.string.toast_leader_required, Toast.LENGTH_SHORT).show()
            return
        }
        gpuProofButton.isEnabled = false
        setStatus(getString(R.string.status_refreshing), State.Working)
        thread(name = "hive-gpu-proof") {
            val summary = try {
                val payload = JSONObject().apply {
                    put("kind", "tiny.gpu.benchmark")
                    put("capability_req", "swarm.gpu.capsule")
                    put("node_id", nodeId)
                    put("payload", JSONObject().apply {
                        put("target_node", nodeId)
                        put("packet_profile", "single-hive-node")
                        put("quantization", "shader-float")
                        put("benchmark_sizes", JSONArray().also { arr ->
                            listOf(4, 16, 64, 128).forEach { arr.put(it) }
                        })
                        put("model_capsule", defaultModelCapsule())
                    })
                }
                val submitted = postJson(leader, "/api/hive/jobs/submit", payload)
                val jobId = submitted.optString("job_id", "queued")
                "GPU proof queued: $jobId\nThe foreground service will claim it on the next tick."
            } catch (e: Exception) {
                "GPU proof failed: ${e.message}"
            }
            runOnUiThread {
                farmSummaryView.text = summary
                gpuProofButton.isEnabled = true
                setStatus(getString(R.string.status_gpu_submitted), State.Live)
                refreshRuntimeCard()
            }
        }
    }

    private fun refreshModels() {
        val leader = prefs.leader.ifBlank { normalizeLeaderUrl(leaderField.text.toString()) }
        if (leader.isBlank()) {
            modelSummaryView.text = getString(R.string.model_summary_empty)
            return
        }
        modelsButton.isEnabled = false
        thread(name = "hive-models") {
            val summary = try {
                val modelsJson = getJson(leader, "/api/localai/ollama/models")
                val models = modelsJson.optJSONArray("models") ?: JSONArray()
                leaderModels.clear()
                for (i in 0 until models.length()) {
                    val item = models.optJSONObject(i)
                    val name = item?.optString("name") ?: models.optString(i)
                    if (name.isNotBlank()) leaderModels.add(name)
                }
                if (selectedModelIndex !in leaderModels.indices) selectedModelIndex = 0
                modelSummaryText()
            } catch (e: Exception) {
                "Models unavailable: ${e.message}"
            }
            runOnUiThread {
                modelSummaryView.text = summary
                modelsButton.isEnabled = true
            }
        }
    }

    private fun selectModel(delta: Int) {
        if (leaderModels.isEmpty()) {
            refreshModels()
            return
        }
        selectedModelIndex = (selectedModelIndex + delta + leaderModels.size) % leaderModels.size
        modelSummaryView.text = modelSummaryText()
    }

    private fun modelSummaryText(): String {
        if (leaderModels.isEmpty()) return "No Ollama models available."
        val selected = leaderModels[selectedModelIndex]
        val list = leaderModels.take(5).joinToString(", ")
        val more = if (leaderModels.size > 5) " +${leaderModels.size - 5}" else ""
        return "Selected: $selected\nAvailable: $list$more"
    }

    private fun sendLeaderChat() {
        val leader = prefs.leader.ifBlank { normalizeLeaderUrl(leaderField.text.toString()) }
        val prompt = chatInput.text.toString().trim()
        if (leader.isBlank()) {
            Toast.makeText(this, R.string.toast_leader_required, Toast.LENGTH_SHORT).show()
            return
        }
        if (prompt.isBlank()) return
        val model = leaderModels.getOrNull(selectedModelIndex) ?: "qwen:latest"
        sendChatButton.isEnabled = false
        setStatus(getString(R.string.status_chatting), State.Working)
        chatResponseView.text = "Sending to $model..."
        thread(name = "hive-chat") {
            val response = try {
                val res = postJson(
                    leader,
                    "/api/localai/ollama/chat",
                    JSONObject().apply {
                        put("model", model)
                        put("message", prompt)
                    },
                    readTimeoutMs = 150_000,
                )
                val answer = res.optString("answer", "").ifBlank { res.optString("error", "No response") }
                "Model: ${res.optString("model", model)}\n\n$answer"
            } catch (e: Exception) {
                "Chat failed: ${e.message}"
            }
            runOnUiThread {
                chatResponseView.text = response
                sendChatButton.isEnabled = true
                refreshStatus()
            }
        }
    }

    private fun getJson(leader: String, path: String): JSONObject {
        val conn = (URL(leader.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            connectTimeout = 8_000
            readTimeout = 8_000
            setRequestProperty("Accept", "application/json")
        }
        return readJsonResponse(conn)
    }

    private fun postJson(
        leader: String,
        path: String,
        payload: JSONObject,
        readTimeoutMs: Int = 8_000,
    ): JSONObject {
        val conn = (URL(leader.trimEnd('/') + path).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            doOutput = true
            connectTimeout = 8_000
            readTimeout = readTimeoutMs
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            if (prefs.token.isNotBlank()) setRequestProperty("X-Hive-Token", prefs.token)
        }
        conn.outputStream.use { os: OutputStream ->
            os.write(payload.toString().toByteArray(Charsets.UTF_8))
        }
        return readJsonResponse(conn)
    }

    private fun readJsonResponse(conn: HttpURLConnection): JSONObject {
        val code = conn.responseCode
        val body = (if (code in 200..299) conn.inputStream else conn.errorStream)
            ?.let { BufferedReader(InputStreamReader(it)).use { r -> r.readText() } }
            ?: ""
        conn.disconnect()
        if (code !in 200..299) throw IllegalStateException("HTTP $code: ${body.take(120)}")
        return if (body.isBlank()) JSONObject() else JSONObject(body)
    }

    private fun formatFarmSummary(
        nodesJson: JSONObject,
        jobsJson: JSONObject,
        modelsJson: JSONObject? = null,
    ): String {
        val nodes = nodesJson.optJSONArray("nodes") ?: JSONArray()
        val jobs = jobsJson.optJSONArray("jobs") ?: JSONArray()
        var live = 0
        var thisNode: JSONObject? = null
        val roster = mutableListOf<String>()
        for (i in 0 until nodes.length()) {
            val n = nodes.optJSONObject(i) ?: continue
            val offline = n.optBoolean("offline", true)
            if (!offline) live += 1
            if (n.optString("node_id") == prefs.nodeId) thisNode = n
            if (roster.size < 5) {
                val age = n.optInt("age_s", -1)
                val state = if (!offline) {
                    if (age >= 0) "live ${age}s" else "live"
                } else {
                    "offline"
                }
                roster.add("${n.optString("node_id", "node")} $state")
            }
        }
        var latestJob: JSONObject? = null
        for (i in 0 until jobs.length()) {
            val j = jobs.optJSONObject(i) ?: continue
            if (j.optString("node_id") == prefs.nodeId) {
                latestJob = j
                break
            }
        }
        val telemetry = thisNode?.optJSONObject("telemetry")
        val caps = telemetry?.optJSONArray("capabilities")
        val age = thisNode?.optInt("age_s", -1) ?: -1
        val modelSummary = formatModelSummary(modelsJson)
        return buildString {
            append("Farm: ").append(live).append("/").append(nodes.length()).append(" live")
            append("\nThis node: ").append(thisNode?.optString("node_id", prefs.nodeId) ?: prefs.nodeId.ifBlank { "unknown" })
            append(if (thisNode?.optBoolean("offline", true) == false) " live" else " offline")
            if (age >= 0) append(" · ").append(age).append("s ago")
            append("\nCapabilities: ").append(formatCaps(caps))
            append("\nNodes: ").append(roster.joinToString(" · ").ifBlank { "none" })
            append("\nModels: ").append(modelSummary)
            append("\nLatest job: ")
            if (latestJob == null) {
                append("none")
            } else {
                append(latestJob!!.optString("kind", "job"))
                append(" · ").append(latestJob!!.optString("status", "unknown"))
                val result = latestJob!!.optJSONObject("result")
                val runner = result?.optString("runner", "") ?: ""
                if (runner.isNotBlank()) append(" · ").append(runner)
                val probe = result?.optJSONObject("gpu_probe")
                val renderer = probe?.optString("renderer", "") ?: ""
                if (renderer.isNotBlank()) append(" · ").append(renderer)
                val score = probe?.optInt("capacity_score", -1) ?: -1
                if (score >= 0) append(" score ").append(score)
            }
        }
    }

    private fun formatModelSummary(modelsJson: JSONObject?): String {
        if (modelsJson == null) return "unavailable"
        val ollama = modelsJson.optJSONObject("ollama")
        val running = ollama?.optBoolean("running", false) ?: false
        val models = ollama?.optJSONArray("models") ?: JSONArray()
        if (!running) return "Ollama offline"
        if (models.length() == 0) return "Ollama online, no models listed"
        val names = mutableListOf<String>()
        var totalGb = 0.0
        for (i in 0 until models.length()) {
            val item = models.optJSONObject(i) ?: continue
            val name = item.optString("name")
            if (name.isNotBlank() && names.size < 4) names.add(name)
            val size = item.optDouble("size_gb", 0.0)
            if (size > 0.0) totalGb += size
        }
        val more = if (models.length() > names.size) " +${models.length() - names.size}" else ""
        val size = if (totalGb > 0.0) " · ${Math.round(totalGb * 10.0) / 10.0}GB" else ""
        return "${models.length()} Ollama · ${names.joinToString(", ")}$more$size"
    }

    private fun formatCaps(caps: JSONArray?): String {
        if (caps == null || caps.length() == 0) return "none"
        val out = mutableListOf<String>()
        for (i in 0 until caps.length()) {
            val cap = caps.optString(i)
                .removePrefix("inference.")
                .removePrefix("swarm.")
                .removePrefix("seven-app.")
                .replace('.', ' ')
            if (cap.isNotBlank()) out.add(cap)
        }
        return out.joinToString(", ")
    }

    private fun defaultModelCapsule(): JSONObject = JSONObject().apply {
        put("capsule_id", "swarm-golden-linear-v1")
        put("model", "swarm-linear-4x4")
        put("input", JSONArray().also { arr ->
            listOf(0.18, 0.41, 0.73, 1.0).forEach { arr.put(it) }
        })
        put("weights", JSONArray().also { arr ->
            listOf(
                0.62, 0.10, 0.24, 0.02,
                0.12, 0.58, 0.16, 0.04,
                0.08, 0.18, 0.70, 0.02,
                0.20, 0.14, 0.18, 0.48,
            ).forEach { arr.put(it) }
        })
    }

    private fun ageLabel(ts: Long): String {
        if (ts <= 0L) return ""
        val age = (System.currentTimeMillis() / 1000L - ts).coerceAtLeast(0L)
        return when {
            age < 60 -> "${age}s ago"
            age < 3600 -> "${age / 60}m ago"
            else -> "${age / 3600}h ago"
        }
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    /**
     * Tolerate sloppy leader URLs: bare IP+port, missing scheme, trailing
     * slash, accidental whitespace. Returns a cleaned http(s)://host:port
     * with no trailing slash, or empty string if even that can't be done.
     */
    private fun normalizeLeaderUrl(input: String): String {
        var s = input.trim()
        if (s.isEmpty()) return ""
        // Add scheme if the user pasted just "100.87.66.45:5050" or "host".
        if (!s.startsWith("http://", ignoreCase = true) &&
            !s.startsWith("https://", ignoreCase = true)) {
            s = "http://$s"
        }
        return s.trimEnd('/')
    }
}
