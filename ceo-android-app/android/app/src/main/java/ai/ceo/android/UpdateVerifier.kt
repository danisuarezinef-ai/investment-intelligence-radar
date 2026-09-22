package ai.ceo.android
import java.io.File
import java.security.MessageDigest
object UpdateVerifier {
    fun sha256(file: File): String {
        val digest = MessageDigest.getInstance("SHA-256")
        file.inputStream().buffered().use { input ->
            val buffer = ByteArray(65536)
            while (true) {
                val read = input.read(buffer)
                if (read <= 0) break
                digest.update(buffer, 0, read)
            }
        }
        return digest.digest().joinToString("") { "%02x".format(it) }
    }
    fun matches(file: File, expected: String): Boolean =
        expected.matches(Regex("[0-9a-fA-F]{64}")) &&
            sha256(file).equals(expected, ignoreCase = true)
}
