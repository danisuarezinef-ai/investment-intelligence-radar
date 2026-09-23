# W7 — Anti-recovery-loop / productividad real

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — BUG FOUND, FIXED, WINDOWS CI GREEN  
**Validación física en PC del usuario:** pendiente

## Objetivo

Evitar que CEO pueda aparentar recuperación/productividad mientras fabrica indefinidamente nuevas tareas de reemplazo.

## Bug reproducido

La base 1.5.92 ya limitaba:

- retries por tarea;
- worker handoff normalization;
- quality-repair lineage;
- goal-continuity generations;
- recovery churn.

Pero quedaba un hueco independiente:

`BlockedUnitRebuilderV2` incrementaba:

`stall_replan_generation`

en cada reemplazo productivo, mientras `ProductiveFallbackOrchestratorV1` no imponía ningún máximo de generaciones.

Por tanto una unidad agotada podía evolucionar:

`A → A' → A'' → A''' → A'''' → ...`

Cada nueva tarea nacía READY y con un ID nuevo, por lo que el límite de retries de la tarea anterior no detenía el linaje.

### Evidencia

Sobre el ZIP exacto:

`CEO_1.5.92-rc1-native-transport-integrity.zip`

la regresión cruda creó correctamente una nueva tarea con:

`stall_replan_generation = 4`

aunque el límite lógico configurado era 3.

Marca de evidencia CI:

`W7_RAW_1592_UNBOUNDED_REPLAN_REPRODUCED`

## Corrección W7

Archivo de parche:

`ceo-browser/apply_w7_recovery_lineage_cap.py`

Objetivo de producción modificado al construir la candidata:

`ceo_core/productive_fallback_orchestrator_v1.py`

Regla:

- default `max_productive_replan_generations = 3`;
- generaciones 0→1→2→3 pueden cambiar estrategia;
- una tarea que ya llega con generación 3 no puede crear generación 4;
- se marca `blocked_safe`;
- reason = `productive_replan_lineage_exhausted`;
- source = `productive_fallback_orchestrator_v1`;
- no se crea reemplazo nuevo;
- el watchdog muestra `BLOQUEADO` en vez de actividad de recuperación falsa.

Hash del fichero parcheado en la prueba:

`d234cafe891d6f8c8524f1780e54e18f8a676664c353abb7b376faf3ab0acab2`

El mismo hash quedó escrito en `CEO_UPDATE_PACKAGE.json`.

## Regresión W7

Archivo:

`ceo-browser/w7_recovery_lineage_regression.py`

Verifica:

1. **Linaje agotado**
   - 0 nuevas tareas;
   - task = BLOCKED;
   - `blocked_safe=true`;
   - reason exacta de agotamiento.

2. **Watchdog repetido**
   - dos ticks consecutivos;
   - ninguna tarea nueva;
   - fuse abierto;
   - estado visible = BLOQUEADO.

3. **Persistencia tras reinicio**
   - ProjectState serializado y reconstruido;
   - no se reanima el linaje;
   - 0 tareas nuevas;
   - `blocked_safe` y reason preservados.

4. **Debajo del límite**
   - generación 2 sí puede crear exactamente un reemplazo;
   - la nueva tarea nace READY;
   - nueva generación = 3;
   - la vieja queda SUPERSEDED.

5. **Provider wait**
   - no crea recuperación;
   - no abre fuse;
   - estado = ESPERANDO PROVEEDOR.

6. **Package contract**
   - hash del fichero parcheado coincide con contrato.

## CI focal

Run con persistencia de reinicio:

- workflow run: `35844873283`
- job: `107128483803`
- conclusion: **SUCCESS**

Marcas:

- `W7_RAW_1592_UNBOUNDED_REPLAN_REPRODUCED`
- `W7_EXHAUSTED_FALLBACK`
- `W7_WATCHDOG_AFTER_EXHAUSTION`
- `W7_RESTART_PERSISTENCE`
- `W7_BELOW_CAP_FALLBACK`
- `W7_PROVIDER_WAIT`
- `W7_RECOVERY_LINEAGE_REGRESSION_PASS`

## Integración canónica

W7 quedó integrado en:

`.github/workflows/test-free-browser-ai-worker.yml`

Step:

`W7 bounded productive recovery lineage`

El workflow temporal W7 fue eliminado.

El guard B02 fue actualizado únicamente para reconocer la ruta histórica del workflow temporal dentro del scope de auditoría.

## Suite canónica completa

Commit funcional probado:

`567f4091432f7cb7af24352e24445e6dbdcde0dc`

Workflow run:

`35845102577`

Job:

`107129243402`

Conclusion:

**SUCCESS**

En la misma ejecución pasaron:

- W6 anti-99;
- W7 bounded recovery lineage;
- B02 scope freeze;
- Python contracts;
- browser-first source;
- multi-provider browser pool;
- PowerShell;
- real-UI input;
- B14-B20 campaign;
- B03-B38;
- Gate 0;
- portable first-trial LAB;
- AITransport through Chrome with zero API keys;
- free-only / no-production boundaries.

## Dictamen W7

**BUG REAL ENCONTRADO:** sí  
**CAUSA RAÍZ:** límite por tarea no limitaba el linaje de tareas sustitutas  
**REPRODUCIDO EN 1.5.92:** sí  
**CORREGIDO:** sí  
**MÁXIMO DE REPLANTEOS PRODUCTIVOS:** 3  
**PERSISTENCIA TRAS REINICIO:** PASS  
**PROVIDER WAIT PRESERVADO:** PASS  
**PACKAGE HASH:** PASS  
**SUITE CANÓNICA WINDOWS:** PASS  
**NUEVO SCHEDULER:** no  
**INSTALADOR GENERADO:** no  
**CANAL STABLE MODIFICADO:** no  
**VALIDACIÓN FÍSICA PC USUARIO:** pendiente

## Siguiente bloque

**W8 — Productividad real / separar actividad de control de trabajo útil**, salvo nueva indicación del usuario.
