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
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    CEOHome()
                }
            }
        }
    }
}

@androidx.compose.runtime.Composable
private fun CEOHome() {
    val context = androidx.compose.ui.platform.LocalContext.current
    val goalStore = remember { GoalStore(context) }
    val updater = remember { UpdateManager(context) }
    val scope = rememberCoroutineScope()

    var snapshot by remember { mutableStateOf(goalStore.load()) }
    var title by remember { mutableStateOf(snapshot.title) }
    var objective by remember { mutableStateOf(snapshot.objective) }

    var updateMessage by remember {
        mutableStateOf("Canal ${BuildConfig.UPDATE_CHANNEL} · ${BuildConfig.VERSION_NAME}")
    }
    var updateManifest by remember { mutableStateOf<UpdateManifest?>(null) }
    var updateBusy by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(18.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp)
    ) {
        Text("CEO de IAs", style = MaterialTheme.typography.headlineMedium)
        Text(
            "Objetivo activo y control móvil",
            style = MaterialTheme.typography.bodyMedium
        )

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Goal Engine", style = MaterialTheme.typography.titleLarge)
                OutlinedTextField(
                    value = title,
                    onValueChange = { title = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Título") },
                    singleLine = true
                )
                OutlinedTextField(
                    value = objective,
                    onValueChange = { objective = it },
                    modifier = Modifier.fillMaxWidth(),
                    label = { Text("Objetivo") },
                    minLines = 4
                )

                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(
                        onClick = { snapshot = goalStore.start(title, objective) },
                        enabled = title.isNotBlank() && objective.isNotBlank()
                    ) {
                        Text("Guardar e iniciar")
                    }
                    TextButton(
                        onClick = { snapshot = goalStore.advance(snapshot) },
                        enabled = snapshot.objective.isNotBlank() && snapshot.progress < 100
                    ) {
                        Text("Avanzar prueba local")
                    }
                }

                Text("Estado: ${snapshot.status}")
                LinearProgressIndicator(
                    progress = { snapshot.progress / 100f },
                    modifier = Modifier.fillMaxWidth()
                )
                Text("${snapshot.progress}%")
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(
                modifier = Modifier.padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                Text("Actualizador interno", style = MaterialTheme.typography.titleLarge)
                Text(updateMessage)

                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                    Button(
                        onClick = {
                            scope.launch {
                                updateBusy = true
                                updateMessage = "Comprobando actualización…"
                                val result = updater.check()
                                updateManifest = result.manifest
                                updateMessage = result.message
                                updateBusy = false
                            }
                        },
                        enabled = !updateBusy
                    ) {
                        Text("Comprobar")
                    }

                    Button(
                        onClick = {
                            val manifest = updateManifest ?: return@Button
                            scope.launch {
                                updateBusy = true
                                updateMessage = "Descargando y verificando…"
                                val prepared = updater.prepare(manifest)
                                updateMessage = prepared.message
                                if (prepared.ok && prepared.apk != null) {
                                    when (UpdateInstaller.launch(context, prepared.apk)) {
                                        UpdateInstaller.LaunchResult.INSTALLER_OPENED ->
                                            updateMessage = "Instalador Android abierto. Confirma la actualización."
                                        UpdateInstaller.LaunchResult.PERMISSION_REQUIRED ->
                                            updateMessage = "Autoriza una vez a CEO para instalar sus actualizaciones y vuelve a pulsar instalar."
                                    }
                                }
                                updateBusy = false
                            }
                        },
                        enabled = !updateBusy && updateManifest != null
                    ) {
                        Text("Descargar e instalar")
                    }
                }
            }
        }

        Spacer(modifier = Modifier.height(4.dp))
        Text(
            "La primera versión móvil prioriza instalación, persistencia y actualización interna. " +
                "La ejecución multIA se incorporará sobre esta base una vez cerrado el APK.",
            style = MaterialTheme.typography.bodySmall
        )
    }
}
