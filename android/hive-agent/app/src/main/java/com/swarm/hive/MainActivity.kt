package com.swarm.hive

import android.Manifest
import android.content.pm.PackageManager
import android.graphics.PorterDuff
import android.os.Build
import android.os.Bundle
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputMethodManager
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import kotlin.concurrent.thread

/**
 * MainActivity — minimal one-screen UI:
 *   • Leader URL input (e.g. http://100.87.66.45:5050)
 *   • Optional node-id override (suggestion pre-filled)
 *   • [Connect] runs enrolment + persists token + starts the service
 *   • Status line tells the user whether telemetry is flowing
 *
 * Everything in this activity is intentionally synchronous-looking
 * (button click → background thread → main-thread UI update). No
 * coroutines, no view binding, no DI: the surface is small enough that
 * the boilerplate of those tools would hurt readability.
 */
class MainActivity : AppCompatActivity() {

    companion object {
        private const val DEFAULT_LEADER = "http://100.87.66.45:5050"
        private const val SAMSUNG_POTATO_NODE_ID = "potato-2"
    }

    private lateinit var prefs: HivePrefs
    private lateinit var leaderField: EditText
    private lateinit var nodeIdField: EditText
    private lateinit var statusView: TextView
    private lateinit var statusDot: View

    private val notifPermLauncher =
        registerForActivityResult(androidx.activity.result.contract.ActivityResultContracts.RequestPermission()) {
            // Result ignored; FGS still runs without the permission, the
            // notification just won't render visibly on Android 13+.
        }

    /** Status dot colours by state. Keeps refreshStatus / onConnectClicked
     *  from caring about how the dot is tinted. */
    private enum class State { Idle, Working, Live, Error }

    private fun setStatus(text: String, state: State) {
        statusView.text = text
        val color = ContextCompat.getColor(
            this,
            when (state) {
                State.Idle    -> R.color.status_idle
                State.Working -> R.color.status_warn
                State.Live    -> R.color.status_ok
                State.Error   -> R.color.status_err
            }
        )
        // setColorFilter on the background drawable tints just the dot
        // without recreating it (drawable is shared across instances so
        // we mutate() defensively).
        statusDot.background?.mutate()?.setColorFilter(color, PorterDuff.Mode.SRC_IN)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        prefs = HivePrefs(this)

        leaderField = findViewById(R.id.field_leader)
        nodeIdField = findViewById(R.id.field_node_id)
        statusView  = findViewById(R.id.status)
        statusDot   = findViewById(R.id.status_dot)

        leaderField.setText(prefs.leader)
        nodeIdField.setText(prefs.nodeId.ifBlank { prefs.suggestNodeId() })
        refreshStatus()

        findViewById<Button>(R.id.btn_connect).setOnClickListener { onConnectClicked() }
        findViewById<Button>(R.id.btn_stop).setOnClickListener {
            AgentLauncher.stop(this)
            setStatus(getString(R.string.status_stopped), State.Idle)
        }

        // Wire keyboard return keys: leader's Next jumps to node id,
        // node id's Done triggers Connect. Without this the on-screen
        // keyboard's enter key does nothing on Android.
        leaderField.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_NEXT) {
                nodeIdField.requestFocus()
                true
            } else false
        }
        nodeIdField.setOnEditorActionListener { _, actionId, _ ->
            if (actionId == EditorInfo.IME_ACTION_DONE) {
                hideKeyboard()
                onConnectClicked()
                true
            } else false
        }

        ensureNotificationPermission()

        // Dedicated potato-slate mode: the Samsung should join the farm
        // without manual typing after a reinstall or clean-up.
        if (prefs.leader.isBlank() || prefs.token.isBlank()) {
            val leader = DEFAULT_LEADER
            val nodeId = if (Build.MANUFACTURER.equals("samsung", ignoreCase = true)) {
                SAMSUNG_POTATO_NODE_ID
            } else {
                prefs.suggestNodeId()
            }
            leaderField.setText(leader)
            nodeIdField.setText(nodeId)
            connect(leader, nodeId)
        } else {
            AgentLauncher.start(this)
        }
    }

    private fun hideKeyboard() {
        val imm = getSystemService(INPUT_METHOD_SERVICE) as? InputMethodManager
        val focused = currentFocus ?: leaderField
        imm?.hideSoftInputFromWindow(focused.windowToken, 0)
    }

    private fun onConnectClicked() {
        val rawLeader = leaderField.text.toString().trim()
        val leader = normalizeLeaderUrl(rawLeader)
        val preferred = nodeIdField.text.toString().trim().ifEmpty { null }
        if (leader.isBlank()) {
            Toast.makeText(this, R.string.toast_leader_required, Toast.LENGTH_SHORT).show()
            return
        }
        leaderField.setText(leader)  // show the cleaned-up form back to the user
        connect(leader, preferred)
    }

    private fun connect(leader: String, preferred: String?) {
        setStatus(getString(R.string.status_enrolling), State.Working)
        thread(name = "hive-enrol") {
            val res = EnrolmentClient.enrol(leader, preferred)
            runOnUiThread {
                if (res == null) {
                    setStatus(getString(R.string.status_enrol_failed), State.Error)
                    return@runOnUiThread
                }
                prefs.leader = res.leader
                prefs.nodeId = res.nodeId
                prefs.token  = res.token
                nodeIdField.setText(res.nodeId)
                AgentLauncher.start(this)
                setStatus(getString(R.string.status_running, res.nodeId), State.Live)
            }
        }
    }

    private fun refreshStatus() {
        when {
            !prefs.isConfigured ->
                setStatus(getString(R.string.status_idle), State.Idle)
            prefs.token.isBlank() ->
                setStatus(getString(R.string.status_needs_enrol), State.Working)
            else ->
                setStatus(getString(R.string.status_running, prefs.nodeId), State.Live)
        }
    }

    private fun ensureNotificationPermission() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.TIRAMISU) return
        val granted = ContextCompat.checkSelfPermission(
            this, Manifest.permission.POST_NOTIFICATIONS
        ) == PackageManager.PERMISSION_GRANTED
        if (!granted) notifPermLauncher.launch(Manifest.permission.POST_NOTIFICATIONS)
    }

    /**
     * Tolerate sloppy leader URLs: bare IP+port, missing scheme, trailing
     * slash, accidental whitespace. Returns a cleaned http(s)://host:port
     * with no trailing slash, or empty string if even that can't be done.
     */
    private fun normalizeLeaderUrl(input: String): String {
        var s = input.trim()
        if (s.isEmpty()) return ""
        // Add scheme if the user pasted just "100.87.66.45:5050" or "host".
        if (!s.startsWith("http://", ignoreCase = true) &&
            !s.startsWith("https://", ignoreCase = true)) {
            s = "http://$s"
        }
        return s.trimEnd('/')
    }
}
