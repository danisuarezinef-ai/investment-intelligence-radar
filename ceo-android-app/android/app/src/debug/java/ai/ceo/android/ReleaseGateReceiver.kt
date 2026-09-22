package ai.ceo.android

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Bundle

class ReleaseGateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val extras = getResultExtras(true) ?: Bundle()
        extras.putBoolean("physical_installation_allowed", false)
        extras.putBoolean("production_verified", false)
        extras.putString("stage", "M02")
        setResultExtras(extras)
    }
}
