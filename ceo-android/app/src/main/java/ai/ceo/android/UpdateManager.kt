package ai.ceo.android

import android.content.Context
import androidx.core.content.pm.PackageInfoCompat
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.net.HttpURLConnection
import java.net.URL

class UpdateManager(private val context: Context) {
    data class CheckResult(
        val available: Boolean,
        val message: String,
        val manifest: UpdateManifest? = null
    )

    data class PreparedUpdate(
        val ok: Boolean,
        val message: String,
        val manifest: UpdateManifest? = null,
        val apk: File? = null
    )

    suspend fun check(): CheckResult = withContext(Dispatchers.IO) {
        try {
            val manifest = fetchManifest()
            require(manifest.schemaVersion == 1) { "Versión de manifiesto no soportada" }
            require(manifest.channel == BuildConfig.UPDATE_CHANNEL) { "Canal de actualización incorrecto" }
            val current = PackageInfoCompat.getLongVersionCode(
                context.packageManager.getPackageInfo(context.packageName, 0)
            )
            if (manifest.versionCode <= current) {
                CheckResult(false, "CEO está actualizado (${BuildConfig.VERSION_NAME})")
            } else {
                CheckResult(
                    true,
                    "Nueva versión ${manifest.versionName} disponible",
                    manifest
                )
            }
        } catch (e: Exception) {
            CheckResult(false, "No se pudo comprobar: ${e.message ?: e::class.java.simpleName}")
        }
    }

    suspend fun prepare(manifest: UpdateManifest): PreparedUpdate = withContext(Dispatchers.IO) {
        try {
            val apk = UpdateDownloader.download(context, manifest)
            val verification = UpdateVerifier.verify(context, apk, manifest)
            if (!verification.ok) {
                apk.delete()
                PreparedUpdate(false, verification.reason)
            } else {
                PreparedUpdate(true, "Actualización verificada y lista para instalar", manifest, apk)
            }
        } catch (e: Exception) {
            PreparedUpdate(false, "No se pudo preparar la actualización: ${e.message ?: e::class.java.simpleName}")
        }
    }

    private fun fetchManifest(): UpdateManifest {
        val rawUrl = BuildConfig.UPDATE_MANIFEST_URL
        require(rawUrl.startsWith("https://")) { "Canal de actualización no seguro" }
        val connection = (URL(rawUrl).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10_000
            readTimeout = 20_000
            instanceFollowRedirects = true
            requestMethod = "GET"
        }
        try {
            connection.connect()
            require(connection.responseCode in 200..299) {
                "HTTP ${connection.responseCode} al consultar canal"
            }
            val text = connection.inputStream.bufferedReader(Charsets.UTF_8).use { it.readText() }
            require(text.length <= 256 * 1024) { "Manifiesto demasiado grande" }
            return UpdateManifest.parse(text)
        } finally {
            connection.disconnect()
        }
    }
}
