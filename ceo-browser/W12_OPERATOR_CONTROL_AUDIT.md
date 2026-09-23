# W12 — Pausa / reanudar / cancelar

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — 2 BUGS FOUND, FIXED, CANONICAL WINDOWS CI GREEN  
**Validación física en el PC del usuario:** pendiente

## Objetivo

Auditar los controles de operador sobre un objetivo que ya tiene trabajo en curso:

1. **Pausar** debe detener el trabajo productivo en vuelo en un límite durable y no limitarse a cambiar una etiqueta de UI.
2. **Reanudar** debe volver a crear ejecución real incluso después de cerrar/reabrir CEO mientras el proyecto estaba pausado.
3. **Cancelar** debe ser terminal: retirar tareas pendientes, detener trabajo en vuelo y no revivir tras reinicio.

La auditoría se ejecutó sobre la candidata acumulada:

base 1.5.92 + W6 + W7 + W8 + W9 + W10 + W11.

No se usaron APIs externas.

## Hallazgo 1 — pausa no detenía el worker en vuelo

Antes de W12, `CEOEngine.pause(True)` hacía únicamente:

- `state.paused = True`;
- guardaba `operator_paused_v1`;
- persistía el estado.

El scheduler sí evitaba despachar trabajo **nuevo** cuando `state.paused=true`, pero un worker que ya estaba RUNNING continuaba.

La regresión adversarial reprodujo:

- `paused = true`;
- `stop_calls = 0`;
- la tarea seguía `running`;
- el efecto local apareció después de pulsar pausa.

Marca focal:

`W12_RAW_PAUSE`

Resultado raw:

- `side_effect_exists=true`;
- `stop_calls=0`;
- `task_status=running`.

Por tanto la pausa visual no equivalía a una pausa operativa.

## Hallazgo 2 — reanudar después de reinicio no recreaba scheduler

Un proyecto pausado deliberadamente se conserva correctamente pausado al reiniciar CEO.

Sin embargo, tras ese reinicio:

- no existe scheduler activo para ese proyecto;
- `pause(False)` quitaba la bandera `paused`;
- pero no construía un nuevo `ContinuousScheduler`.

La regresión raw reprodujo:

- `paused=false`;
- `scheduler_created=false`;
- cero instancias nuevas de scheduler.

Marca:

`W12_RAW_RESUME`

Eso dejaba un proyecto que aparentaba estar reanudado pero no volvía a producir trabajo.

## Corrección W12

Archivo de composición:

`ceo-browser/apply_w12_operator_control.py`

Runtime modificado en la candidata:

`scripts/ceo_stdlib_work_mode.py`

### Pausa

La pausa de operador ahora:

1. persiste primero `paused=true` y `operator_paused_v1=true`;
2. registra estado productivo `PAUSADO`;
3. llama al límite ya existente y probado `_stop_scheduler(timeout_seconds=4.0)`;
4. el scheduler devuelve cualquier RUNNING seguro a `RETRY`;
5. cancela el worker en memoria;
6. persiste el checkpoint;
7. deja `scheduler=None`;
8. registra `operator_pause_quiesce_v1`.

No se crea un mecanismo paralelo de parada: W12 reutiliza la ruta restart-safe validada en W10.

### Reanudar

La reanudación ahora:

1. rechaza explícitamente un proyecto cancelado;
2. limpia la pausa de operador;
3. persiste el estado;
4. si no existe scheduler y el objetivo no está completo:
   - reconstruye router;
   - crea `ContinuousScheduler`;
   - arranca el scheduler.

Esto cubre tanto pausa/reanudación en la misma sesión como pausa → cierre de CEO → reapertura → reanudar.

### Cancelar

La cancelación ya tenía semántica terminal correcta y **no necesitó parche adicional**.

La auditoría confirmó que:

- escribe `cancelled_at`;
- `cancelled_reason=operator_cancelled`;
- `paused=true`;
- `autonomy_enabled=false`;
- tareas no terminales → `SUPERSEDED`;
- trabajo en vuelo se detiene;
- proyecto deja de ser activo;
- `prepare_for_resume` conserva pausa y autonomía desactivada;
- `activate_project` impide reabrir automáticamente un objetivo cancelado.

## Resultado corregido — pausa

Regresión focal:

`W12_PATCHED_PAUSE`

Resultado:

- `paused=true`;
- `stop_calls=1`;
- `side_effect_exists=false`;
- RUNNING → `RETRY`;
- `scheduler_is_none=true`;
- pausa durable guardada;
- quiesce limpio:
  - `ok=true`;
  - `mode=clean`;
  - `forced=false`.

## Resultado corregido — reanudar

Marca:

`W12_PATCHED_RESUME`

Resultado:

- `paused=false`;
- se crea exactamente un scheduler;
- `scheduler_started=true`;
- se elimina `operator_paused_v1`.

## Resultado — cancelación terminal

Marca:

`W12_CANCEL_TERMINAL`

Resultado:

- `cancelled_reason=operator_cancelled`;
- `paused=true`;
- `autonomy_enabled=false`;
- dos tareas no terminales → `superseded`;
- tarea ya COMPLETE permanece COMPLETE;
- proyecto activo → null;
- engine deja de mantener ese proyecto como activo;
- no aparece efecto posterior a cancelación;
- reapertura:
  - `restart_paused=true`;
  - `restart_autonomy=false`.

## Package hash

`scripts/ceo_stdlib_work_mode.py`

SHA-256 de la candidata acumulada W12:

`7293caba77e25d3f25e8ac30e8b7710d648fba3247bccb07e5aede3f0538f8e8`

El mismo hash queda sincronizado en `CEO_UPDATE_PACKAGE.json`.

## Evidencia focal Windows CI

Workflow focal:

- run: `35871271712`
- job: `107215680970`
- conclusion: **SUCCESS**

Marcas principales:

- `W12_RAW_PAUSE_RESUME_BUGS_REPRODUCED`
- `W12_OPERATOR_CONTROL_FIX_APPLIED`
- `W12_PATCHED_PAUSE`
- `W12_PATCHED_RESUME`
- `W12_CANCEL_TERMINAL`
- `W12_PACKAGE_HASH`
- `W12_PAUSE_RESUME_CANCEL_REGRESSION_PASS`
- `W12_WINDOWS_CI_PASS`

## Suite canónica completa

W12 quedó integrado permanentemente en:

`.github/workflows/test-free-browser-ai-worker.yml`

Step:

`W12 durable pause resume cancel controls`

Commit de integración:

`1cd786f75bb88292a38b4c96156a48135a7f027f`

Workflow run:

`35871576483`

Job:

`107216714929`

Conclusion:

**SUCCESS**

En la misma ejecución pasaron:

- W6;
- W7;
- W8;
- W9;
- W10;
- W11;
- W12;
- B02 scope freeze;
- contratos Python;
- browser-first;
- pool multIA;
- PowerShell;
- campaña B14-B20;
- B03-B38;
- Gate 0;
- LAB portable;
- AITransport mediante Chrome con cero API keys;
- límites free-only / no-production.

Marcas canónicas:

- `W12_OPERATOR_CONTROL_CANONICAL_PASS`
- `B02_SCOPE_FREEZE_PASS`
- `FREE_BROWSER_BOUNDARY_PASS`

## Limpieza

Los workflows temporales W12 usados para inspección y prueba focal se eliminaron tras integrar la regresión canónica.

Se conservan únicamente:

- parche reproducible W12;
- regresión W12;
- step W12 en la suite canónica;
- este documento de auditoría.

## Dictamen W12

**PAUSA ERA SOLO BANDERA:** BUG REAL CONFIRMADO  
**WORKER PODÍA SEGUIR TRAS PAUSA:** BUG REAL CONFIRMADO  
**PAUSA AHORA QUIESCE TRABAJO EN VUELO:** PASS  
**RUNNING → RETRY DURABLE AL PAUSAR:** PASS  
**SIN EFECTO POSTERIOR A PAUSA EN REGRESIÓN:** PASS  
**PAUSA SOBREVIVE REINICIO:** PASS  
**REANUDAR TRAS REINICIO RECREA SCHEDULER:** PASS  
**CANCELACIÓN TERMINAL:** PASS  
**CANCELACIÓN NO REVIVE TRAS REINICIO:** PASS  
**PACKAGE HASH:** PASS  
**W6-W12 COMBINADOS:** PASS  
**BROWSER-FIRST REGRESSION:** PASS  
**VALIDACIÓN FÍSICA PC USUARIO:** PENDIENTE  
**INSTALADOR GENERADO:** NO  
**CANAL STABLE MODIFICADO:** NO

## Siguiente bloque

W13, manteniendo la secuencia de auditoría Windows y sin adelantar instalación.
