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
            api.baseUrl = urlInput.text.toString().trim()
            Toast.makeText(this, "Leader URL saved", Toast.LENGTH_SHORT).show()
            finish()
        }
    }
}
