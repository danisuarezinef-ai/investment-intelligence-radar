package ai.ceo.android
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertFalse
import org.junit.Test
import org.junit.runner.RunWith
@RunWith(AndroidJUnit4::class)
class AndroidStateSmokeTest {
    @Test fun physicalInstallAndUpdaterActivationRemainBlockedInM02() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        val status = AndroidCoreBridge.foundationStatus(context)
        assertFalse(status.physicalInstallAllowed)
        assertFalse(status.updaterActivationAllowed)
    }
}
