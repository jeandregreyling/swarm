package com.swarm.seven

import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.TextView
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.chip.ChipGroup
import com.google.android.material.chip.Chip

class NodesAdapter : RecyclerView.Adapter<NodesAdapter.ViewHolder>() {
    private var nodes = listOf<HiveNode>()

    fun setNodes(newNodes: List<HiveNode>) {
        nodes = newNodes
        notifyDataSetChanged()
    }

    override fun onCreateViewHolder(parent: ViewGroup, viewType: Int): ViewHolder {
        val view = LayoutInflater.from(parent.context)
            .inflate(R.layout.item_node, parent, false)
        return ViewHolder(view)
    }

    override fun onBindViewHolder(holder: ViewHolder, position: Int) {
        holder.bind(nodes[position])
    }

    override fun getItemCount(): Int = nodes.size

    class ViewHolder(itemView: View) : RecyclerView.ViewHolder(itemView) {
        private val nodeId: TextView = itemView.findViewById(R.id.nodeId)
        private val platform: TextView = itemView.findViewById(R.id.platform)
        private val chipGroup: ChipGroup = itemView.findViewById(R.id.capabilities)

        fun bind(node: HiveNode) {
            nodeId.text = node.nodeId
            platform.text = "${node.platform} \u2022 ${node.ageS}s ago"
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
