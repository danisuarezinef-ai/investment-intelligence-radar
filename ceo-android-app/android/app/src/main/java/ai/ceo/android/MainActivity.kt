package ai.ceo.android

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        NotificationHelper.ensureChannel(this)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    CEOFoundationScreen(
                        initialTitle = AppPreferences(this).lastGoalTitle,
                        onSave = { title, body ->
                            AppPreferences(this).apply {
                                lastGoalTitle = title
                                lastGoalBody = body
                            }
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun CEOFoundationScreen(
    initialTitle: String,
    onSave: (String, String) -> Unit,
) {
    var title by remember { mutableStateOf(initialTitle) }
    var objective by remember { mutableStateOf("") }
    var savedMessage by remember { mutableStateOf("") }

    Column(
        modifier = Modifier.fillMaxSize().padding(20.dp),
        verticalArrangement = Arrangement.Top,
    ) {
        Text("CEO App", style = MaterialTheme.typography.headlineMedium)
        Text("Android · M02 foundation")
        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = title,
            onValueChange = { title = it },
            label = { Text("Título del objetivo") },
            modifier = Modifier.fillMaxWidth(),
            singleLine = true,
        )
        Spacer(Modifier.height(10.dp))
        OutlinedTextField(
            value = objective,
            onValueChange = { objective = it },
            label = { Text("Objetivo") },
            modifier = Modifier.fillMaxWidth(),
            minLines = 3,
        )
        Spacer(Modifier.height(12.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Button(
                enabled = title.isNotBlank() && objective.isNotBlank(),
                onClick = {
                    onSave(title.trim(), objective.trim())
                    savedMessage = "Objetivo guardado localmente"
                },
            ) {
                Text("Guardar")
            }
        }
        if (savedMessage.isNotBlank()) {
            Spacer(Modifier.height(10.dp))
            Text(savedMessage)
        }

        Spacer(Modifier.height(20.dp))
        Card(modifier = Modifier.fillMaxWidth()) {
            Column(Modifier.padding(16.dp)) {
                Text("Estado preinstalación", style = MaterialTheme.typography.titleMedium)
                Text("Motor de tareas: reservado para M07")
                Text("Segundo plano: reservado para M09")
                Text("Updater interno: estructura presente, bloqueado hasta M14–M17")
                Text("Instalación física: bloqueada hasta APP220")
            }
        }
    }
}
