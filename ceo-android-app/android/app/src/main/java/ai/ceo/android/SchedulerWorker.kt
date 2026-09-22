package ai.ceo.android
data class SchedulerWorkerResult(val accepted: Boolean, val detail: String)
object SchedulerWorker {
    fun foundationProbe() = SchedulerWorkerResult(false, "Background worker not activated before M09.")
}
