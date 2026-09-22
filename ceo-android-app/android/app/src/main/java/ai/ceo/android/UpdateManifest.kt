package ai.ceo.android
data class UpdateManifest(
    val versionCode: Long,
    val versionName: String,
    val apkUrl: String,
    val sha256: String,
    val sizeBytes: Long,
    val signatureAlgorithm: String = "",
    val signingKeyId: String = "",
    val signature: String = "",
)
