# W8 — Productividad real / separación de trabajo útil y control

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — BUG FOUND, FIXED, CANONICAL WINDOWS CI GREEN  
**Validación física en PC del usuario:** pendiente

## Objetivo

Garantizar que auditorías, recoveries, heartbeats y tareas internas de control no aumenten el progreso visible del proyecto ni se contabilicen como productividad real.

## Bug reproducido

Sobre el ZIP exacto:

`CEO_1.5.92-rc1-native-transport-integrity.zip`

se construyó un proyecto con:

- 4 tareas productivas;
- 1 productiva COMPLETE;
- 3 productivas pendientes;
- progreso productivo real = 25 %.

Sin ruido de control:

`display_progress = 25.0`

Después se añadieron:

- 80 tareas control-plane COMPLETE;
- 40 tareas control-plane READY;
- 250 recoveries;
- heartbeats artificialmente altos.

Las tareas productivas no cambiaron.

Sin embargo 1.5.92 mostró:

`display_progress = 65.3`

mientras:

`batch_progress = 25.0`

Esto demostraba que actividad interna podía inflar el progreso visible sin producir trabajo real.

### Evidencia raw

Run:
`35846649444`

Job:
`107134311632`

Resultado:
**FAILURE esperado / bug reproducido**

Marca:

`W8_PRODUCTIVITY_TRUTH_FAIL`

Diferencia:

- base visible: 25.0
- contaminado visible: 65.3
- productivo completado: 1/4 en ambos casos

## Causa raíz

`StableProgressTracker` mantenía compatibilidad con un tracker legacy:

`stable_progress_v1`

Cuando no existía un valor legacy explícito, usaba como fallback:

`state.progress`

Ese `state.progress` representa el ratio bruto del grafo y puede incluir tareas de control, verificación, heartbeat y recovery.

Por tanto un valor pensado como fallback de migración terminaba convirtiendo actividad interna en avance visible.

## Corrección W8

Archivo de parche:

`ceo-browser/apply_w8_productivity_truth_fix.py`

Objetivo:

`ceo_core/progress_tracker.py`

Nueva regla:

1. Si existe un `stable_progress_v1.display_progress` explícito:
   - se conserva como high-water legacy;
   - sigue sujeto a la protección anti-inflación >=95 %.

2. Si NO existe un display legacy explícito:
   - ya no se usa `state.progress`;
   - el fallback es exclusivamente el `batch_progress` productivo calculado.

3. La monotonía del progreso productivo explícito se conserva.

4. El progreso control-plane sigue disponible en contadores diagnósticos, pero no mueve el porcentaje productivo.

## Regresión W8

Archivo:

`ceo-browser/w8_productivity_truth_regression.py`

Verifica:

### Control noise invariance

Antes:
- display = 25
- batch = 25
- productivo = 1/4

Después de 80 controles completos + 40 pendientes:
- display = 25
- batch = 25
- productivo = 1/4

### Control-only transition

Completar 12 tareas internas:
- no cambia display;
- no cambia batch;
- no cambia productivos completados;
- no actualiza `last_productive_progress_at`.

### Recovery / heartbeat invariance

Cambiar:
- `worker_recoveries`;
- history recovery;
- heartbeat;

no modifica ningún indicador productivo.

### Legacy high-water

Un valor explícito:

`stable_progress_v1.display_progress = 60`

se conserva como 60.

W8 no rompe la monotonía histórica válida; elimina únicamente el fallback incorrecto al grafo bruto.

### Proyecto solo de control

25 controles COMPLETE:

- `productive_completed = 0`
- `productive_total_known = 0`
- `display_progress = 0`

No se presenta como progreso productivo.

### Package contract

El hash de:

`ceo_core/progress_tracker.py`

se actualiza en:

`CEO_UPDATE_PACKAGE.json`

Hash probado:

`a7c5e293393ad116d3bae6ec6802aea37485c1d99bbde94dbd4fcdff8e0b51d4`

## CI focal W8

Run:
`35847046154`

Job:
`107135591324`

Conclusion:
**SUCCESS**

Marcas:

- `W8_PRODUCTIVITY_TRUTH_PATCH_APPLIED`
- `W8_BASE`
- `W8_POLLUTED`
- `W8_CONTROL_ONLY_TRANSITION`
- `W8_RECOVERY_HEARTBEAT_INVARIANCE`
- `W8_EXPLICIT_LEGACY_HIGHWATER`
- `W8_CONTROLS_ONLY`
- `W8_PACKAGE_HASH`
- `W8_PRODUCTIVITY_TRUTH_PASS`
- `W8_WINDOWS_CI_PASS`

## Integración canónica

W8 quedó integrado en:

`.github/workflows/test-free-browser-ai-worker.yml`

Step:

`W8 productive progress excludes control-plane noise`

La suite canónica aplica sobre el MISMO root:

1. W6
2. W7
3. W8

y después ejecuta las tres regresiones.

Así se valida la composición real de las tres correcciones, no tres sandboxes independientes.

## Suite canónica completa

Commit funcional:

`34d4200e520506c700caa1aed3bea07453d01987`

Run:

`35851753709`

Job:

`107150833286`

Conclusion:

**SUCCESS**

Pasaron en la misma ejecución:

- W6 anti-99;
- W7 bounded recovery lineage;
- W8 productivity truth;
- B02 scope freeze;
- Python contracts;
- browser-first source;
- multi-provider browser pool;
- PowerShell;
- real-UI input;
- B14-B20;
- B03-B38;
- Gate 0;
- portable first-trial LAB;
- AITransport Chrome con cero API keys;
- free-only / no-production boundaries.

## Limpieza

El workflow temporal:

`.github/workflows/ceo-w8-productivity-truth.yml`

fue eliminado después de integrar W8 en la suite canónica.

La ruta histórica permanece permitida en B02 únicamente para que `git diff` no considere su creación/eliminación una violación de scope.

## Dictamen W8

**BUG REAL ENCONTRADO:** sí  
**CAUSA:** fallback del progreso visible al ratio bruto `state.progress`  
**PROGRESO PRODUCTIVO REAL AISLADO:** sí  
**CONTROL-PLANE NO INFLA PROGRESO:** PASS  
**RECOVERIES/HEARTBEATS NO INFLAN PROGRESO:** PASS  
**HIGH-WATER LEGACY EXPLÍCITO:** preservado  
**CONTROLS-ONLY = 0 % PRODUCTIVO:** PASS  
**W6+W7+W8 COMBINADOS:** PASS  
**SUITE WINDOWS CANÓNICA:** PASS  
**INSTALADOR GENERADO:** no  
**CANAL STABLE MODIFICADO:** no  
**VALIDACIÓN FÍSICA PC USUARIO:** pendiente

## Siguiente bloque

**W9 — tarea local finita sin IA**, salvo nueva indicación del usuario.
