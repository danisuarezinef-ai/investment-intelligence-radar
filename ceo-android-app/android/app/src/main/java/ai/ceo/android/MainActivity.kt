package ai.ceo.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.compose.foundation.layout.fillMaxSize

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        NotificationHelper.ensureChannel(this)
        val preferences = AppPreferences(this)

        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    CEOHomeScreen(
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
}
