package com.swarm.hive

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/**
 * BootReceiver — restarts the Hive Agent foreground service after a
 * device reboot, so the tablet auto-rejoins the Hive without the user
 * having to relaunch the app.
 *
 * No-ops when the agent has not been configured yet (HivePrefs.leader
 * is blank).
 */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val action = intent.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED &&
            action != "android.intent.action.QUICKBOOT_POWERON") return
        AgentLauncher.start(context.applicationContext)
    }
}
