package ai.ceo.android

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
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

@Composable
fun CEOHomeScreen(
    initialTitle: String,
    initialObjective: String,
    onSaveGoal: (String, String) -> Unit,
) {
    var title by remember { mutableStateOf(initialTitle) }
    var objective by remember { mutableStateOf(initialObjective) }
    var objectiveExpanded by remember { mutableStateOf(false) }
    var goalSaved by remember {
        mutableStateOf(initialTitle.isNotBlank() && initialObjective.isNotBlank())
    }
    var progressPercent by remember { mutableIntStateOf(0) }

    val status = when {
        goalSaved -> "Objetivo preparado"
        title.isNotBlank() || objective.isNotBlank() -> "Objetivo en edición"
        else -> "Esperando objetivo"
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(horizontal = 18.dp, vertical = 16.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("CEO App", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Control central",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        GoalEngineCard(
            title = title,
            objective = objective,
            expanded = objectiveExpanded,
            saved = goalSaved,
            onTitleChange = {
                title = it
                goalSaved = false
                progressPercent = 0
            },
            onObjectiveChange = {
                objective = it
                goalSaved = false
                progressPercent = 0
            },
            onToggleExpanded = { objectiveExpanded = !objectiveExpanded },
            onSave = {
                val cleanTitle = title.trim()
                val cleanObjective = objective.trim()
                if (cleanTitle.isNotBlank() && cleanObjective.isNotBlank()) {
                    onSaveGoal(cleanTitle, cleanObjective)
                    title = cleanTitle
                    objective = cleanObjective
                    goalSaved = true
                    progressPercent = 0
                }
            },
        )

        GeneralStatusCard(status = status)
        ProgressCard(progressPercent = progressPercent)
    }
}

@Composable
private fun GoalEngineCard(
    title: String,
    objective: String,
    expanded: Boolean,
    saved: Boolean,
    onTitleChange: (String) -> Unit,
    onObjectiveChange: (String) -> Unit,
    onToggleExpanded: () -> Unit,
    onSave: () -> Unit,
) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.surfaceContainer,
        ),
    ) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
        ) {
            Text("Goal Engine", style = MaterialTheme.typography.titleLarge)
            Text(
                "Título visible; objetivo completo bajo demanda.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )

            OutlinedTextField(
                value = title,
                onValueChange = onTitleChange,
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = "goal-title" },
                label = { Text("Título del objetivo") },
                singleLine = true,
            )

            OutlinedButton(
                onClick = onToggleExpanded,
                modifier = Modifier.semantics { contentDescription = "goal-toggle" },
            ) {
                Text(if (expanded) "Ocultar objetivo" else "Mostrar objetivo")
            }

            if (expanded) {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = objective,
                        onValueChange = onObjectiveChange,
                        modifier = Modifier
                            .fillMaxWidth()
                            .semantics { contentDescription = "goal-objective" },
                        label = { Text("Objetivo activo") },
                        minLines = 3,
                    )

                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        Button(
                            enabled = title.isNotBlank() && objective.isNotBlank(),
                            onClick = onSave,
                            modifier = Modifier.semantics { contentDescription = "goal-save" },
                        ) {
                            Text("Guardar objetivo")
                        }
                    }
                }
            }

            if (saved) {
                Text(
                    "Objetivo guardado",
                    style = MaterialTheme.typography.labelLarge,
                    color = MaterialTheme.colorScheme.primary,
                )
            }
        }
    }
}

@Composable
private fun GeneralStatusCard(status: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text("Estado general", style = MaterialTheme.typography.titleMedium)
            Text(
                status,
                modifier = Modifier.semantics { contentDescription = "general-status" },
                style = MaterialTheme.typography.bodyLarge,
            )
            Text(
                "Motor de ejecución: reservado para M07",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ProgressCard(progressPercent: Int) {
    val bounded = progressPercent.coerceIn(0, 100)
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
            ) {
                Text("Progreso", style = MaterialTheme.typography.titleMedium)
                Text(
                    "$bounded%",
                    modifier = Modifier.semantics { contentDescription = "progress-percent" },
                    style = MaterialTheme.typography.titleMedium,
                )
            }
            LinearProgressIndicator(
                progress = { bounded / 100f },
                modifier = Modifier
                    .fillMaxWidth()
                    .semantics { contentDescription = "goal-progress" },
            )
            Text(
                "Se activará cuando el motor de tareas empiece a ejecutar el objetivo.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
