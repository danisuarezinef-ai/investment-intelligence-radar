package ai.ceo.android
import android.content.Context
object UpdateSnapshotManager {
    fun recordCurrentVersion(context: Context) {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        context.getSharedPreferences("ceo_update_snapshot", Context.MODE_PRIVATE)
            .edit()
            .putLong("version_code", info.longVersionCode)
            .putString("version_name", info.versionName ?: "unknown")
            .apply()
    }
}
