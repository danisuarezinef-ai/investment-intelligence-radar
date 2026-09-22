package ai.ceo.android

import android.content.Context

data class GoalSnapshot(
    val title: String = "",
    val objective: String = "",
    val status: String = "IDLE",
    val progress: Int = 0
)

class GoalStore(context: Context) {
    private val prefs = context.getSharedPreferences("ceo_goal_state", Context.MODE_PRIVATE)

    fun load(): GoalSnapshot = GoalSnapshot(
        title = prefs.getString("title", "") ?: "",
        objective = prefs.getString("objective", "") ?: "",
        status = prefs.getString("status", "IDLE") ?: "IDLE",
        progress = prefs.getInt("progress", 0)
    )

    fun save(snapshot: GoalSnapshot) {
        prefs.edit()
            .putString("title", snapshot.title)
            .putString("objective", snapshot.objective)
            .putString("status", snapshot.status)
            .putInt("progress", snapshot.progress.coerceIn(0, 100))
            .apply()
    }

    fun start(title: String, objective: String): GoalSnapshot {
        val next = GoalSnapshot(
            title = title.trim(),
            objective = objective.trim(),
            status = "READY",
            progress = 5
        )
        save(next)
        return next
    }
}
