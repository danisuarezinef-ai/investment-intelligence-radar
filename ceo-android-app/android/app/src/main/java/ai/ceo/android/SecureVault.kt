package ai.ceo.android
import java.security.KeyStore
object SecureVault {
    fun androidKeystoreAvailable(): Boolean = runCatching {
        KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        true
    }.getOrDefault(false)
    fun secretStorageEnabled(): Boolean = false
}
