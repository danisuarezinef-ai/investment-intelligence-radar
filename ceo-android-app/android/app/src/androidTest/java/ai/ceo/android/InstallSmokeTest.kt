package ai.ceo.android
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith
@RunWith(AndroidJUnit4::class)
class InstallSmokeTest {
    @Test fun packageIdentityIsCEOAndroid() {
        val context = ApplicationProvider.getApplicationContext<android.content.Context>()
        assertTrue(context.packageName.startsWith("ai.ceo.android"))
    }
}
