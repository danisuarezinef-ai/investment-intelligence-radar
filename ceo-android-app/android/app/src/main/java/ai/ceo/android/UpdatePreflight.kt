package ai.ceo.android
object UpdatePreflight {
    data class Result(val ok: Boolean, val problems: List<String>)
    fun inspect(currentVersionCode: Long, manifest: UpdateManifest): Result {
        val problems = buildList {
            if (manifest.versionCode <= currentVersionCode) add("version_not_newer")
            if (!manifest.sha256.matches(Regex("[0-9a-fA-F]{64}"))) add("sha256_invalid")
            if (!manifest.apkUrl.startsWith("https://")) add("https_required")
            if (manifest.sizeBytes <= 0L) add("size_invalid")
        }
        return Result(problems.isEmpty(), problems)
    }
}
