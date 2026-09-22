package ai.ceo.android
import android.content.Context
object UpdateManager {
    data class Status(
        val enabled: Boolean,
        val phase: String,
        val currentVersionCode: Long,
        val currentVersionName: String,
        val note: String,
    )
    fun status(context: Context): Status {
        val health = PostUpdateHealthCheck.inspect(context)
        return Status(
            enabled = false,
            phase = UpdatePolicy.phase(),
            currentVersionCode = health.versionCode,
            currentVersionName = health.versionName,
            note = "Updater scaffolding exists; download/install remains blocked until M14-M17."
        )
    }
}
