package ai.ceo.android

import android.content.Context
import java.io.File
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL

object UpdateDownloader {
    private const val MAX_APK_BYTES = 250L * 1024L * 1024L

    fun download(context: Context, manifest: UpdateManifest): File {
        require(manifest.apkUrl.startsWith("https://")) { "La actualización debe usar HTTPS" }
        require(manifest.sizeBytes in 1..MAX_APK_BYTES) { "Tamaño de actualización inválido" }

        val dir = File(context.filesDir, "updates").apply { mkdirs() }
        val target = File(dir, "CEO-${manifest.versionCode}.apk")
        val temp = File(dir, ".CEO-${manifest.versionCode}.download")
        temp.delete()

        val connection = (URL(manifest.apkUrl).openConnection() as HttpURLConnection).apply {
            connectTimeout = 15_000
            readTimeout = 45_000
            instanceFollowRedirects = true
            requestMethod = "GET"
        }

        try {
            connection.connect()
            require(connection.responseCode in 200..299) {
                "HTTP ${connection.responseCode} al descargar actualización"
            }
            val announced = connection.contentLengthLong
            if (announced > 0) {
                require(announced == manifest.sizeBytes) { "El tamaño remoto no coincide con el manifiesto" }
                require(announced <= MAX_APK_BYTES) { "APK demasiado grande" }
            }

            var total = 0L
            connection.inputStream.use { input ->
                FileOutputStream(temp).use { output ->
                    val buffer = ByteArray(64 * 1024)
                    while (true) {
                        val read = input.read(buffer)
                        if (read < 0) break
                        total += read
                        require(total <= MAX_APK_BYTES) { "Descarga excede el límite permitido" }
                        output.write(buffer, 0, read)
                    }
                    output.fd.sync()
                }
            }
            require(total == manifest.sizeBytes) { "Descarga incompleta: $total/${manifest.sizeBytes}" }
            target.delete()
            require(temp.renameTo(target)) { "No se pudo consolidar el APK descargado" }
            return target
        } finally {
            connection.disconnect()
            temp.delete()
        }
    }
}
