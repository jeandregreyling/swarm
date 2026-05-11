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
    private lateinit var emptyText: TextView
    private lateinit var progress: CircularProgressIndicator
    private val api by lazy { SwarmApi(this) }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_nodes)

        statusText = findViewById(R.id.statusText)
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
                val result = withContext(Dispatchers.IO) { api.listNodes() }
                result.fold(
                    onSuccess = { nodes ->
                        adapter.submitList(nodes)
                        statusText.text = "${nodes.size} node(s) enrolled"
                        emptyText.visibility = if (nodes.isEmpty()) android.view.View.VISIBLE else android.view.View.GONE
                        recyclerView.visibility = if (nodes.isEmpty()) android.view.View.GONE else android.view.View.VISIBLE
                    },
                    onFailure = { error ->
                        statusText.text = "Couldn't reach leader: ${error.message}"
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
}