package ai.ceo.android
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Bundle
class ReleaseGateReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        resultExtras = (resultExtras ?: Bundle()).apply {
            putBoolean("physical_installation_allowed", false)
            putBoolean("production_verified", false)
            putString("stage", "M02")
        }
    }
}
