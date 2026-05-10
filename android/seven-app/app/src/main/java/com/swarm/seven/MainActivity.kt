package com.swarm.seven

import android.content.Intent
import android.os.Bundle
import android.widget.EditText
import android.widget.ImageButton
import androidx.appcompat.app.AppCompatActivity
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.appbar.MaterialToolbar
import com.google.android.material.floatingactionbutton.FloatingActionButton
import kotlinx.coroutines.*

class MainActivity : AppCompatActivity() {
    private lateinit var chatAdapter: ChatAdapter
    private lateinit var recyclerView: RecyclerView
    private lateinit var inputField: EditText
    private val scope = CoroutineScope(Dispatchers.Main + Job())
    private val api = SwarmApi(this)

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
        findViewById<ImageButton>(R.id.sendButton).setOnClickListener {
            sendMessage()
        }

        // Welcome message
        chatAdapter.addMessage(ChatMessage(
            text = "Seven online. Swarm active. What do you need?",
            isUser = false
        ))
    }

    private fun sendMessage() {
        val text = inputField.text.toString().trim()
        if (text.isEmpty()) return

        chatAdapter.addMessage(ChatMessage(text = text, isUser = true))
        inputField.text.clear()
        recyclerView.scrollToPosition(chatAdapter.itemCount - 1)

        scope.launch {
            try {
                val response = withContext(Dispatchers.IO) {
                    api.sendChat(text)
                }
                chatAdapter.addMessage(ChatMessage(
                    text = response,
                    isUser = false
                ))
                recyclerView.scrollToPosition(chatAdapter.itemCount - 1)
            } catch (e: Exception) {
                chatAdapter.addMessage(ChatMessage(
                    text = "Error: ${e.message}",
                    isUser = false
                ))
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        scope.cancel()
    }
}
