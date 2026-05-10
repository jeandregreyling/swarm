package com.swarm.seven

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class ChatAdapter : RecyclerView.Adapter<ChatAdapter.ViewHolder>() {
    private val messages = mutableListOf<ChatMessage>()

    fun addMessage(msg: ChatMessage) {
        messages.add(msg)
        notifyItemInserted(messages.size - 1)
    }

    override fun getItemViewType(position: Int): Int =
        if (messages[position].isUser) 1 else 0

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val layout = if (viewType == 1) R.layout.item_chat_user else R.layout.item_chat_bot
        val view = LayoutInflater.from(parent.context).inflate(layout, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(messages[position])
    }

    override fun getItemCount(): Int = messages.size

    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val textView: TextView = itemView.findViewById(R.id.messageText)

        fun bind(msg: ChatMessage) {
            textView.text = msg.text
        }
    }
}

data class ChatMessage(val text: String, val isUser: Boolean)
