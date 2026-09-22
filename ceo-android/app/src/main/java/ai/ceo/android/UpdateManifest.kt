package ai.ceo.android

import org.json.JSONObject

data class UpdateManifest(
    val schemaVersion: Int,
    val channel: String,
    val versionCode: Long,
    val versionName: String,
    val apkUrl: String,
    val sha256: String,
    val sizeBytes: Long,
    val notes: String,
    val mandatory: Boolean
) {
    companion object {
        fun parse(text: String): UpdateManifest {
            val obj = JSONObject(text)
            return UpdateManifest(
                schemaVersion = obj.getInt("schemaVersion"),
                channel = obj.getString("channel"),
                versionCode = obj.getLong("versionCode"),
                versionName = obj.getString("versionName"),
                apkUrl = obj.getString("apkUrl"),
                sha256 = obj.getString("sha256").lowercase(),
                sizeBytes = obj.getLong("sizeBytes"),
                notes = obj.optString("notes", ""),
                mandatory = obj.optBoolean("mandatory", false)
            )
        }
    }
}
