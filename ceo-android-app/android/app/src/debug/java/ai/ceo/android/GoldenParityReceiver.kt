package ai.ceo.android
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
class GoldenParityReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        resultCode = if (!UpdatePolicy.INTERNAL_DOWNLOAD_ALLOWED && !UpdatePolicy.INSTALL_HANDOFF_ALLOWED) 0 else 1
    }
}
