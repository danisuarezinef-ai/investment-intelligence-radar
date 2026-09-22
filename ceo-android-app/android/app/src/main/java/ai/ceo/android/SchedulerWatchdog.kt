package ai.ceo.android
object SchedulerWatchdog {
    data class Snapshot(val active: Boolean, val pendingJobs: Int, val note: String)
    fun snapshot() = Snapshot(false, 0, "WorkManager watchdog begins in M09.")
}
