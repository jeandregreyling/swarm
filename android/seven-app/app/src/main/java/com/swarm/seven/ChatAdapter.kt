package com.swarm.seven

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView

class ChatAdapter : RecyclerView.Adapter<ChatAdapter.ViewHolder>() {
    private val messages = mutableListOf<ChatMessage>()
    private var showTyping = false

    companion object {
        private const val VIEW_TYPE_BOT = 0
        private const val VIEW_TYPE_USER = 1
        private const val VIEW_TYPE_TYPING = 2
    }

    fun addMessage(msg: ChatMessage) {
        if (showTyping) {
            val typingPos = messages.size
            showTyping = false
            notifyItemRemoved(typingPos)
            messages.add(msg)
            notifyItemInserted(messages.size - 1)
        } else {
            messages.add(msg)
            val pos = messages.size - 1
            notifyItemInserted(pos)
        }
    }

    fun setTyping(typing: Boolean) {
        if (showTyping == typing) return
        if (typing) {
            showTyping = true
            notifyItemInserted(messages.size)
        } else {
            val pos = messages.size
            showTyping = false
            notifyItemRemoved(pos)
        }
    }

    override fun getItemViewType(position: Int): Int {
        if (showTyping && position == messages.size) return VIEW_TYPE_TYPING
        return if (messages[position].isUser) VIEW_TYPE_USER else VIEW_TYPE_BOT
    }

    override fun getItemCount(): Int = messages.size + if (showTyping) 1 else 0

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val layout = when (viewType) {
            VIEW_TYPE_USER -> R.layout.item_chat_user
            VIEW_TYPE_TYPING -> R.layout.item_chat_typing
            else -> R.layout.item_chat_bot
        }
        val view = LayoutInflater.from(parent.context).inflate(layout, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        if (showTyping && position == messages.size) {
            // Typing indicator — no text bind needed
            return
        }
        holder.bind(messages[position])
    }

    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val textView: TextView? = itemView.findViewById(R.id.messageText)

        fun bind(msg: ChatMessage) {
            textView?.text = msg.text
        }
    }
}

data class ChatMessage(val text: String, val isUser: Boolean)