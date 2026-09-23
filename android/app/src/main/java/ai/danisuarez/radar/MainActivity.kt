package ai.danisuarez.radar
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

data class RadarUiState(val cloud:String="Comprobando…",val equity:String="—",val pnlToday:String="—",val positions:String="—",val activity:String="Esperando telemetría PAPER")
class MainActivity:ComponentActivity(){
 override fun onCreate(savedInstanceState:Bundle?){super.onCreate(savedInstanceState);check(!BuildConfig.REAL_TRADING){"Unsafe trading build"};setContent{MaterialTheme{RadarHome()}}}
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun RadarHome(state:RadarUiState=RadarUiState()){
 Scaffold(topBar={TopAppBar(title={Text("Radar de inversión")})}){pad->
  Column(Modifier.padding(pad).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){
   AssistChip(onClick={},label={Text("PAPER · REAL_TRADING OFF 🔒")})
   Text("Estado Cloud: "+state.cloud,style=MaterialTheme.typography.titleMedium)
   Row(horizontalArrangement=Arrangement.spacedBy(12.dp)){
    Card(Modifier.weight(1f)){Column(Modifier.padding(12.dp)){Text("Cartera PAPER");Text(state.equity)}}
    Card(Modifier.weight(1f)){Column(Modifier.padding(12.dp)){Text("P&L hoy");Text(state.pnlToday)}}
   }
   Text("Posiciones: "+state.positions);HorizontalDivider();Text("Actividad",style=MaterialTheme.typography.titleMedium);Text(state.activity)
   Text("La app observa el motor Cloud; no ejecuta operaciones reales.",style=MaterialTheme.typography.bodySmall)
  }
 }
}
