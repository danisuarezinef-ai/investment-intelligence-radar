package ai.ceo.android
import android.app.Application
class CEOApplication : Application() {
    override fun onCreate() {
        super.onCreate()
        StartupGuard.assertFoundation(this)
    }
}
