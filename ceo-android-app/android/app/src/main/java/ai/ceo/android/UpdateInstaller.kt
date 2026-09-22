package ai.ceo.android
sealed interface UpdateInstallResult {
    data class Blocked(val reason: String) : UpdateInstallResult
    data class HandedOff(val packageName: String) : UpdateInstallResult
}
object UpdateInstaller {
    fun requestInstall(): UpdateInstallResult =
        UpdateInstallResult.Blocked("Install handoff is blocked until M16.")
}
