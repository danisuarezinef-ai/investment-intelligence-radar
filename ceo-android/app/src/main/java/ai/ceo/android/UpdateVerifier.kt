package ai.ceo.android

import android.content.Context
import android.content.pm.PackageInfo
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.content.pm.PackageInfoCompat
import java.io.File
import java.security.MessageDigest

object UpdateVerifier {
    data class Verification(
        val ok: Boolean,
        val reason: String,
        val archiveVersionCode: Long = 0
    )

    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().use { input ->
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }

    fun verify(context: Context, file: File, manifest: UpdateManifest): Verification {
        if (!file.isFile) return Verification(false, "APK no encontrado")
        if (file.length() != manifest.sizeBytes) return Verification(false, "Tamaño APK incorrecto")
        if (!sha256(file).equals(manifest.sha256, ignoreCase = true)) {
            return Verification(false, "SHA-256 no coincide")
        }

        val pm = context.packageManager
        val archive = archiveInfo(pm, file) ?: return Verification(false, "APK no reconocible")
        if (archive.packageName != context.packageName) {
            return Verification(false, "El paquete descargado pertenece a otra aplicación")
        }
        val archiveVersion = PackageInfoCompat.getLongVersionCode(archive)
        val current = currentInfo(context)
        val currentVersion = PackageInfoCompat.getLongVersionCode(current)
        if (archiveVersion != manifest.versionCode || archiveVersion <= currentVersion) {
            return Verification(false, "VersionCode de actualización inválido", archiveVersion)
        }

        val currentSigners = signerDigests(current)
        val archiveSigners = signerDigests(archive)
        if (currentSigners.isEmpty() || archiveSigners.isEmpty() || currentSigners != archiveSigners) {
            return Verification(false, "El firmante del APK no coincide con CEO instalado", archiveVersion)
        }
        return Verification(true, "APK verificado", archiveVersion)
    }

    private fun currentInfo(context: Context): PackageInfo {
        val flags = if (Build.VERSION.SDK_INT >= 28) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            @Suppress("DEPRECATION")
            PackageManager.GET_SIGNATURES
        }
        @Suppress("DEPRECATION")
        return context.packageManager.getPackageInfo(context.packageName, flags)
    }

    private fun archiveInfo(pm: PackageManager, file: File): PackageInfo? {
        val flags = if (Build.VERSION.SDK_INT >= 28) {
            PackageManager.GET_SIGNING_CERTIFICATES
        } else {
            @Suppress("DEPRECATION")
            PackageManager.GET_SIGNATURES
        }
        @Suppress("DEPRECATION")
        return pm.getPackageArchiveInfo(file.absolutePath, flags)
    }

    private fun signerDigests(info: PackageInfo): Set<String> {
        val signatures = if (Build.VERSION.SDK_INT >= 28) {
            val signing = info.signingInfo ?: return emptySet()
            if (signing.hasMultipleSigners()) signing.apkContentsSigners
            else signing.signingCertificateHistory
        } else {
            @Suppress("DEPRECATION")
            info.signatures ?: emptyArray()
        }
        val digest = MessageDigest.getInstance("SHA-256")
        return signatures.map { sig ->
            digest.digest(sig.toByteArray()).joinToString("") { "%02x".format(it) }
        }.toSet()
    }
}
