package com.swarm.seven

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.DiffUtil
import androidx.recyclerview.widget.ListAdapter
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.chip.ChipGroup
import com.google.android.material.chip.Chip

class NodesAdapter : ListAdapter<HiveNode, NodesAdapter.ViewHolder>(DiffCallback) {

    companion object DiffCallback : DiffUtil.ItemCallback<HiveNode>() {
        override fun areItemsTheSame(oldItem: HiveNode, newItem: HiveNode): Boolean =
            oldItem.nodeId == newItem.nodeId

        override fun areContentsTheSame(oldItem: HiveNode, newItem: HiveNode): Boolean =
            oldItem == newItem
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_node, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(getItem(position))
    }

    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val nodeId: TextView = itemView.findViewById(R.id.nodeId)
        private val platform: TextView = itemView.findViewById(R.id.platform)
        private val chipGroup: ChipGroup = itemView.findViewById(R.id.capabilities)

        fun bind(node: HiveNode) {
            nodeId.text = if (node.expected) "${node.nodeId} · expected" else node.nodeId
            platform.text = when {
                node.offline -> "${node.platform} \u2022 waiting for telemetry"
                node.ageS >= 0 -> "${node.platform} \u2022 ${node.ageS}s ago"
                else -> node.platform
            }
            chipGroup.removeAllViews()
            node.capabilities.forEach { cap ->
                val chip = Chip(itemView.context).apply {
                    text = cap.replace("inference.", "")
                    isCheckable = false
                }
                chipGroup.addView(chip)
            }
        }
    }
}