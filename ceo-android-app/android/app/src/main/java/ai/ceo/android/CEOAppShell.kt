package ai.ceo.android

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.VerticalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationRail
import androidx.compose.material3.NavigationRailItem
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

private enum class CEOSection(val label: String, val glyph: String) {
    HOME("Inicio", "I"),
    TASKS("Tareas", "T"),
    DECISIONS("Decisiones", "D"),
}

private data class DecisionProposal(
    val id: String,
    val title: String,
    val detail: String,
)

@Composable
fun CEOAppShell(
    initialTitle: String,
    initialObjective: String,
    onSaveGoal: (String, String) -> Unit,
) {
    var currentSectionName by rememberSaveable { mutableStateOf(CEOSection.HOME.name) }
    var preparedTitle by rememberSaveable { mutableStateOf(initialTitle) }
    var preparedObjective by rememberSaveable { mutableStateOf(initialObjective) }
    val currentSection = CEOSection.valueOf(currentSectionName)
    val darkThemeActive = isSystemInDarkTheme()

    BoxWithConstraints(modifier = Modifier.fillMaxSize()) {
        val expandedLayout = maxWidth >= 700.dp
        val layoutDescription = if (expandedLayout) "layout-expanded" else "layout-compact"

        if (expandedLayout) {
            Row(
                modifier = Modifier
                    .fillMaxSize()
                    .semantics { contentDescription = layoutDescription },
            ) {
                CEONavigationRail(
                    currentSection = currentSection,
                    onSelect = { currentSectionName = it.name },
                )
                VerticalDivider(modifier = Modifier.fillMaxHeight())
                SectionContent(
                    section = currentSection,
                    preparedTitle = preparedTitle,
                    preparedObjective = preparedObjective,
                    darkThemeActive = darkThemeActive,
                    modifier = Modifier.fillMaxSize(),
                    onSaveGoal = { title, objective ->
                        preparedTitle = title
                        preparedObjective = objective
                        onSaveGoal(title, objective)
                    },
                )
            }
        } else {
            Scaffold(
                modifier = Modifier
                    .fillMaxSize()
                    .semantics { contentDescription = layoutDescription },
                bottomBar = {
                    CEOBottomNavigation(
                        currentSection = currentSection,
                        onSelect = { currentSectionName = it.name },
                    )
                },
            ) { innerPadding ->
                SectionContent(
                    section = currentSection,
                    preparedTitle = preparedTitle,
                    preparedObjective = preparedObjective,
                    darkThemeActive = darkThemeActive,
                    modifier = Modifier.padding(innerPadding),
                    onSaveGoal = { title, objective ->
                        preparedTitle = title
                        preparedObjective = objective
                        onSaveGoal(title, objective)
                    },
                )
            }
        }
    }
}

@Composable
private fun SectionContent(
    section: CEOSection,
    preparedTitle: String,
    preparedObjective: String,
    darkThemeActive: Boolean,
    modifier: Modifier,
    onSaveGoal: (String, String) -> Unit,
) {
    Column(modifier = modifier.fillMaxSize()) {
        ShellHeader(
            section = section,
            darkThemeActive = darkThemeActive,
        )
        when (section) {
            CEOSection.HOME -> CEOHomeScreen(
                initialTitle = preparedTitle,
                initialObjective = preparedObjective,
                onSaveGoal = onSaveGoal,
            )
            CEOSection.TASKS -> ActiveTasksScreen(
                preparedTitle = preparedTitle,
                preparedObjective = preparedObjective,
            )
            CEOSection.DECISIONS -> DecisionsScreen()
        }
    }
}

@Composable
private fun ShellHeader(
    section: CEOSection,
    darkThemeActive: Boolean,
) {
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .padding(horizontal = 18.dp, vertical = 10.dp),
        horizontalArrangement = Arrangement.SpaceBetween,
    ) {
        Text(section.label, style = MaterialTheme.typography.titleLarge)
        Text(
            if (darkThemeActive) "Tema oscuro activo" else "Tema claro activo",
            modifier = Modifier.semantics { contentDescription = "theme-mode" },
            style = MaterialTheme.typography.labelMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun CEOBottomNavigation(
    currentSection: CEOSection,
    onSelect: (CEOSection) -> Unit,
) {
    NavigationBar {
        CEOSection.entries.forEach { section ->
            NavigationBarItem(
                selected = currentSection == section,
                onClick = { onSelect(section) },
                icon = { Text(section.glyph) },
                label = { Text(section.label) },
                modifier = Modifier.semantics {
                    contentDescription = "nav-${section.name.lowercase()}"
                },
            )
        }
    }
}

@Composable
private fun CEONavigationRail(
    currentSection: CEOSection,
    onSelect: (CEOSection) -> Unit,
) {
    NavigationRail {
        CEOSection.entries.forEach { section ->
            NavigationRailItem(
                selected = currentSection == section,
                onClick = { onSelect(section) },
                icon = { Text(section.glyph) },
                label = { Text(section.label) },
                modifier = Modifier.semantics {
                    contentDescription = "nav-${section.name.lowercase()}"
                },
            )
        }
    }
}

@Composable
private fun ActiveTasksScreen(
    preparedTitle: String,
    preparedObjective: String,
) {
    val hasPreparedGoal = preparedTitle.isNotBlank() && preparedObjective.isNotBlank()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 12.dp)
            .semantics { contentDescription = "active-tasks-screen" },
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Tareas activas", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Vista honesta del trabajo disponible. El motor autónomo se conecta en M07.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        if (!hasPreparedGoal) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text("Sin tareas activas", style = MaterialTheme.typography.titleMedium)
                    Text("Guarda un objetivo en Inicio para preparar la primera tarea.")
                    Text(
                        "0 tareas",
                        modifier = Modifier.semantics { contentDescription = "task-count" },
                    )
                }
            }
        } else {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(7.dp),
                ) {
                    Text("Tarea preparada", style = MaterialTheme.typography.titleMedium)
                    Text(
                        preparedTitle,
                        modifier = Modifier.semantics { contentDescription = "prepared-task-title" },
                        style = MaterialTheme.typography.bodyLarge,
                    )
                    Text(
                        "Pendiente · motor M07",
                        modifier = Modifier.semantics { contentDescription = "prepared-task-status" },
                        color = MaterialTheme.colorScheme.primary,
                    )
                    Text(
                        "1 tarea",
                        modifier = Modifier.semantics { contentDescription = "task-count" },
                    )
                    Text(
                        preparedObjective,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(6.dp),
            ) {
                Text("Cola de ejecución", style = MaterialTheme.typography.titleMedium)
                Text(
                    if (hasPreparedGoal) {
                        "Preparada, pero no iniciada. CEO no simula progreso antes de M07."
                    } else {
                        "Vacía."
                    }
                )
            }
        }
    }
}

@Composable
private fun DecisionsScreen() {
    val baseProposals = remember {
        listOf(
            DecisionProposal(
                id = "quality",
                title = "Priorizar calidad",
                detail = "Reservar más validación antes de considerar una tarea terminada.",
            ),
            DecisionProposal(
                id = "speed",
                title = "Priorizar rapidez",
                detail = "Usar el camino válido más corto cuando existan varias alternativas.",
            ),
            DecisionProposal(
                id = "review",
                title = "Pedir revisión antes de cerrar",
                detail = "Mantener una confirmación humana antes del cierre de tareas relevantes.",
            ),
        )
    }
    val customProposals = remember { mutableStateListOf<String>() }
    var selectedProposal by rememberSaveable { mutableStateOf("") }
    var customText by rememberSaveable { mutableStateOf("") }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 18.dp, vertical = 12.dp)
            .semantics { contentDescription = "decisions-screen" },
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        Text("Propuestas y decisiones", style = MaterialTheme.typography.headlineSmall)
        Text(
            "Estas elecciones quedan en la interfaz; su efecto operativo se conectará al motor en M07.",
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )

        baseProposals.forEachIndexed { index, proposal ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    Text(proposal.title, style = MaterialTheme.typography.titleMedium)
                    Text(
                        proposal.detail,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    OutlinedButton(
                        onClick = { selectedProposal = proposal.title },
                        modifier = Modifier.semantics {
                            contentDescription = "decision-proposal-$index"
                        },
                    ) {
                        Text(
                            if (selectedProposal == proposal.title) "Seleccionada" else "Elegir"
                        )
                    }
                }
            }
        }

        if (customProposals.isNotEmpty()) {
            Text("Propuestas propias", style = MaterialTheme.typography.titleMedium)
            customProposals.forEachIndexed { index, proposal ->
                OutlinedButton(
                    onClick = { selectedProposal = proposal },
                    modifier = Modifier
                        .fillMaxWidth()
                        .semantics { contentDescription = "custom-proposal-$index" },
                ) {
                    Text(proposal)
                }
            }
        }

        OutlinedTextField(
            value = customText,
            onValueChange = { customText = it },
            modifier = Modifier
                .fillMaxWidth()
                .semantics { contentDescription = "decision-custom-input" },
            label = { Text("Propuesta:") },
            minLines = 2,
        )
        Button(
            enabled = customText.isNotBlank(),
            onClick = {
                val clean = customText.trim()
                if (clean.isNotBlank()) {
                    customProposals.add(clean)
                    selectedProposal = clean
                    customText = ""
                }
            },
            modifier = Modifier.semantics { contentDescription = "decision-add-custom" },
        ) {
            Text("Añadir propuesta")
        }

        if (selectedProposal.isNotBlank()) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.padding(14.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text("Decisión seleccionada", style = MaterialTheme.typography.titleMedium)
                    Text(
                        selectedProposal,
                        modifier = Modifier.semantics {
                            contentDescription = "selected-decision"
                        },
                    )
                    Text(
                        "Pendiente de conexión operativa en M07.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }
}
