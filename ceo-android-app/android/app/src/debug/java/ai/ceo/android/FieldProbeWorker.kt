package ai.ceo.android
object FieldProbeWorker {
    data class Probe(val physicalInstallAllowed: Boolean, val updaterActivationAllowed: Boolean, val buildStage: String)
    fun run() = Probe(false, false, "M02")
}
