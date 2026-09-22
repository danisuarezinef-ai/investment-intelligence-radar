package ai.ceo.android
data class UpdateConfig(
    val channel: String = "candidate",
    val manifestUrl: String = "",
    val automaticChecks: Boolean = false,
)
