package ai.ceo.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        NotificationHelper.ensureChannel(this)
        val preferences = AppPreferences(this)

        setContent {
            CEOAppTheme {
                CEOAppShell(
                    initialTitle = preferences.lastGoalTitle,
                    initialObjective = preferences.lastGoalBody,
                    onSaveGoal = { title, objective ->
                        preferences.lastGoalTitle = title
                        preferences.lastGoalBody = objective
                    },
                )
            }
        }
    }
}
