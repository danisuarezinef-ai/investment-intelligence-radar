package ai.ceo.android
import android.content.Context
object PostUpdateHealthCheck {
    data class Result(val ok: Boolean, val versionCode: Long, val versionName: String)
    fun inspect(context: Context): Result {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        return Result(context.packageName.startsWith("ai.ceo.android"), info.longVersionCode, info.versionName ?: "unknown")
    }
}
