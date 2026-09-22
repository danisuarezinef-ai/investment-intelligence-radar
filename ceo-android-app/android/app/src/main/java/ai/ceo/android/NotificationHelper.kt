package ai.ceo.android
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
object NotificationHelper {
    const val CHANNEL_ID = "ceo_status"
    fun ensureChannel(context: Context) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = context.getSystemService(NotificationManager::class.java)
            manager.createNotificationChannel(NotificationChannel(CHANNEL_ID, "CEO status", NotificationManager.IMPORTANCE_DEFAULT))
        }
    }
}
