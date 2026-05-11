package com.swarm.seven

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity

class SettingsActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_settings)

        val api = SwarmApi(this)
        val urlInput = findViewById<EditText>(R.id.leaderUrlInput)
        val saveBtn = findViewById<Button>(R.id.saveButton)

        urlInput.setText(api.baseUrl)

        saveBtn.setOnClickListener {
            val raw = urlInput.text.toString().trim()
            if (raw.isEmpty()) {
                Toast.makeText(this, "URL cannot be empty", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (!raw.startsWith("http://") && !raw.startsWith("https://")) {
                Toast.makeText(this, "URL must start with http:// or https://", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            if (raw.endsWith("/")) {
                urlInput.setText(raw.removeSuffix("/"))
                Toast.makeText(this, "Trailing slash removed", Toast.LENGTH_SHORT).show()
                return@setOnClickListener
            }
            api.baseUrl = raw
            Toast.makeText(this, "Leader URL saved", Toast.LENGTH_SHORT).show()
            finish()
        }
    }
}