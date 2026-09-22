package ai.ceo.android
sealed interface UpdateDownloadResult {
    data class Blocked(val reason: String) : UpdateDownloadResult
    data class Downloaded(val path: String, val sha256: String) : UpdateDownloadResult
}
object UpdateDownloader {
    fun download(manifest: UpdateManifest): UpdateDownloadResult =
        UpdateDownloadResult.Blocked(
            "Updater download is blocked until M15; requested ${manifest.versionName}."
        )
}
