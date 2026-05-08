package com.swarm.hive

import android.content.Context
import android.content.Intent
import android.os.Build

/**
 * AgentLauncher — single source of truth for starting the foreground
 * service. Used by MainActivity (manual start) and BootReceiver
 * (post-reboot auto-resume) so the service start contract stays in one
 * place.
 */
object AgentLauncher {

    fun start(ctx: Context) {
        val prefs = HivePrefs(ctx)
        if (!prefs.isConfigured) return  // nothing to do until enrolled
        val intent = Intent(ctx, HiveAgentService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            ctx.startForegroundService(intent)
        } else {
            ctx.startService(intent)
        }
    }

    fun stop(ctx: Context) {
        ctx.stopService(Intent(ctx, HiveAgentService::class.java))
    }
}
