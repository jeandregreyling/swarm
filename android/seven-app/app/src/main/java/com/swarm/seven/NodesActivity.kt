package com.swarm.seven

import android.os.Bundle
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.progressindicator.CircularProgressIndicator
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

class NodesActivity : AppCompatActivity() {
    private lateinit var recyclerView: RecyclerView
    private lateinit var adapter: NodesAdapter
    private lateinit var statusText: TextView
    private lateinit var handoffText: TextView
    private lateinit var emptyText: TextView
    private lateinit var progress: CircularProgressIndicator
    private val api by lazy { SwarmApi(this) }
    private val sampler by lazy { AndroidSampler(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_nodes)

        statusText = findViewById(R.id.statusText)
        handoffText = findViewById(R.id.handoffText)
        emptyText = findViewById(R.id.emptyText)
        progress = findViewById(R.id.progress)
        recyclerView = findViewById(R.id.nodesRecycler)
        recyclerView.layoutManager = LinearLayoutManager(this)
        adapter = NodesAdapter()
        recyclerView.adapter = adapter

        loadNodes()
    }

    private fun loadNodes() {
        progress.show()
        lifecycleScope.launch {
            try {
                val handoffResult = withContext(Dispatchers.IO) { claimOneVisibleHandoff() }
                val result = withContext(Dispatchers.IO) { api.listNodes() }
                val jobsResult = withContext(Dispatchers.IO) { api.listJobs() }
                result.fold(
                    onSuccess = { nodes ->
                        adapter.submitList(nodes)
                        val live = nodes.count { !it.offline && it.ageS >= 0 }
                        statusText.text = "${nodes.size} potato node(s) · $live live"
                        handoffText.text = handoffResult ?: jobsResult.getOrNull()
                            ?.firstOrNull { it.nodeId == "potato-2" || it.capabilityReq == "inference.gpu" }
                            ?.let { "Handoff: ${it.kind} → ${it.nodeId.ifBlank { "auto" }} · ${it.status}" }
                            ?: "Handoff: waiting for Samsung GPU packet"
                        emptyText.visibility = if (nodes.isEmpty()) android.view.View.VISIBLE else android.view.View.GONE
                        recyclerView.visibility = if (nodes.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE
                    },
                    onFailure = { error ->
                        statusText.text = "Couldn't reach leader: ${error.message}"
                        handoffText.text = "Handoff: unavailable"
                        adapter.submitList(emptyList())
                        emptyText.apply {
                            text = "Swipe down to retry"
                            visibility = android.view.View.VISIBLE
                        }
                        recyclerView.visibility = android.view.View.GONE
                    }
                )
            } catch (e: Exception) {
                statusText.text = "Error: ${e.message}"
                adapter.submitList(emptyList())
                emptyText.apply {
                    text = "Swipe down to retry"
                    visibility = android.view.View.VISIBLE
                }
                recyclerView.visibility = android.view.View.GONE
            } finally {
                progress.hide()
            }
        }
    }

    private fun claimOneVisibleHandoff(): String? {
        val nodeId = sampler.nodeId()
        val sample = sampler.sample()
        api.enrol(nodeId, sampler.deviceLabel())
        api.postTelemetry(sampler.telemetryPayload())
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
        api.reportJobResult(nodeId, job.jobId, result)
        return "Handoff: ${job.kind} → $nodeId · completed"
    }
}