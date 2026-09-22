package ai.ceo.android
import android.content.Context
data class AndroidFoundationStatus(
    val packageName: String,
    val versionName: String,
    val versionCode: Long,
    val physicalInstallAllowed: Boolean,
    val updaterActivationAllowed: Boolean,
    val sharedCoreExecutionEnabled: Boolean,
)
object AndroidCoreBridge {
    fun foundationStatus(context: Context): AndroidFoundationStatus {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        return AndroidFoundationStatus(
            packageName = context.packageName,
            versionName = info.versionName ?: "unknown",
            versionCode = info.longVersionCode,
            physicalInstallAllowed = false,
            updaterActivationAllowed = false,
            sharedCoreExecutionEnabled = false,
        )
    }
}
