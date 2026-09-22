package ai.ceo.android
import android.content.Context
object StartupGuard {
    fun assertFoundation(context: Context) {
        require(context.packageName.startsWith("ai.ceo.android")) { "Unexpected package identity" }
    }
}
