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
    private lateinit var progress: CircularProgressIndicator
    private val api by lazy { SwarmApi(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_nodes)

        statusText = findViewById(R.id.statusText)
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
                val nodes = withContext(Dispatchers.IO) { api.listNodes() }
                adapter.setNodes(nodes)
                statusText.text = "${nodes.size} node(s) enrolled"
            } catch (e: Exception) {
                statusText.text = "Error: ${e.message}"
            } finally {
                progress.hide()
            }
        }
    }
}
