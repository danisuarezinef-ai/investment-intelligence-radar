package ai.ceo.android
import android.content.Context
class AppPreferences(context: Context) {
    private val prefs = context.getSharedPreferences("ceo_app", Context.MODE_PRIVATE)
    var lastGoalTitle: String
        get() = prefs.getString("last_goal_title", "") ?: ""
        set(value) { prefs.edit().putString("last_goal_title", value).apply() }
    var lastGoalBody: String
        get() = prefs.getString("last_goal_body", "") ?: ""
        set(value) { prefs.edit().putString("last_goal_body", value).apply() }
    var updaterEnabled: Boolean
        get() = prefs.getBoolean("updater_enabled", false)
        set(value) { prefs.edit().putBoolean("updater_enabled", value).apply() }
}
