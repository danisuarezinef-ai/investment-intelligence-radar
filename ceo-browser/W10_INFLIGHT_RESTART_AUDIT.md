# W10 — Persistencia y reinicio durante una tarea finita

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — BUG FOUND, FIXED, CANONICAL WINDOWS CI GREEN  
**Validación física en el PC del usuario:** pendiente

## Objetivo

Demostrar que CEO puede sobrevivir a una interrupción mientras una tarea productiva está realmente en ejecución, sin:

- perder el trabajo;
- duplicar la tarea;
- crear un nuevo linaje;
- quedar bloqueado por estado RUNNING huérfano;
- quedar bloqueado por un worker/lease muerto;
- conservar un artefacto parcial como resultado final.

Se exigieron dos escenarios:

1. cierre limpio durante ejecución;
2. interrupción brusca con checkpoint RUNNING persistido.

La prueba reutiliza el objetivo W9:

`Crea CEO_LOCAL_W9.txt. Debe contener exactamente: CEO_LOCAL_W9_OK`

sin APIs externas.

## Escenario A — cierre limpio durante Execution

Se usa un provider de prueba que se detiene después de que la tarea ya está:

`RUNNING`

pero antes de producir ninguna escritura.

CEO recibe `scheduler.stop()`.

### Resultado esperado y verificado

La misma tarea cambia durablemente a:

- status = `RETRY`
- `interrupted_by_shutdown` presente
- provider stage = `interrupted`

Después se reconstruye el scheduler y se continúa con el mismo estado persistido.

Resultado:

- mismo Execution task ID;
- attempts final = 2;
- ninguna tarea productiva duplicada;
- archivo final exacto;
- Final audit PASS;
- `goal_audit_passed=true`;
- `completed_at` escrito;
- progreso 100 %;
- productive pending = 0.

Evidencia canónica:
- interrupted status: `retry`
- interrupted provider stage: `interrupted`
- same_execution_id = true.

## Escenario B — crash / RUNNING huérfano

Se captura el estado exactamente mientras Execution está RUNNING y el provider está dentro de su llamada.

Ese snapshot representa pérdida brusca de proceso/Windows sin clean stop.

Además se crea deliberadamente un artefacto parcial:

`[W10_PARTIAL_FROM_CRASH]`

antes de reabrir.

### Bug encontrado

`ResumeCoordinator` hacía correctamente:

- RUNNING → RETRY;
- `recovered_after_restart=true`;
- `resume_class=safe_retry_after_interruption`;
- `retry_after_ts=0`;
- `worker_id=None`.

Pero dejaba intacto el lease persistido de la sesión muerta:

`worker_leases_v2[task].released=false`

y también la copia:

`task.metadata.worker_lease_v2.released=false`

`WorkerLifecycleV2.claim()` encontraba ese lease todavía dentro de su TTL y lanzaba:

`task_already_leased:<task_id>`

La tarea recuperada quedaba con:

`worker_lease_collision_v2=true`

y acababa BLOCKED.

Por tanto el recovery declaraba `safe_retry_after_interruption`, pero el worker no podía realmente reanudarse.

## Corrección W10

Archivo de composición:

`ceo-browser/apply_w10_restart_lease_fix.py`

Fichero de runtime corregido:

`ceo_core/operational_resilience.py`

Cuando ResumeCoordinator clasifica:

`safe_retry_after_interruption`

ahora también:

1. marca el lease durable como released;
2. reason = `restart_interrupted_worker`;
3. escribe `released_at`;
4. marca released la copia del lease en task metadata;
5. `worker_lease_recovered_v2=true`;
6. elimina un posible `worker_lease_collision_v2` histórico;
7. limpia `worker_id`.

No se modifica:

- TTL normal;
- límites W7;
- RecoveryStormGuard;
- budgets;
- política de tareas externas/irreversibles.

Las tareas que pueden haber producido un efecto externo siguen usando la política conservadora de `NEEDS_REVIEW`.

## Resultado después de la reparación

El checkpoint huérfano se carga como:

- stale status antes de init = RUNNING;
- reconciled status = RETRY;
- worker_id = null;
- resume class = safe_retry_after_interruption;
- durable lease released = true;
- task lease released = true;
- release reason = restart_interrupted_worker.

Después CEO reclama de nuevo la misma tarea y termina.

Resultado:

- mismo Execution task ID;
- attempts = 2;
- ninguna hoja duplicada;
- artefacto parcial sobrescrito;
- contenido final exacto;
- SHA final:
  `3efcdd70d048b516b02a66eabd0400ae90ac3bef11cf293467c0d14db47c47e1`
- tamaño final: 15 bytes;
- Final audit = COMPLETE / PASS;
- completed_at escrito;
- display progress = 100;
- productive pending = 0.

El SHA del artefacto parcial era distinto:
`d2c9b0d31f41264e4c4a3e4d6e9b794c112db56885f29c8bfd4820e3ac2c2c87`

por lo que queda demostrado que no se aceptó el archivo parcial como resultado final.

## Package hash

`ceo_core/operational_resilience.py`

SHA-256 de la candidata W10:

`e1baa1f677e986e1e670c60922820ad4e2871492f8a46081b0eea3ea6c34935f`

`CEO_UPDATE_PACKAGE.json` contiene el mismo hash.

## Evidencia focal Windows CI

Gate focal final:

- job: `107188040594`
- conclusion: **SUCCESS**

Marcas:
- `W10_RESTART_LEASE_FIX_APPLIED`
- `W10_CLEAN_RESTART_PASS`
- `W10_CRASH_RECONCILED`
- `W10_RESTART_E2E`
- `W10_RESTART_REGRESSION_PASS`
- `W10_WINDOWS_CI_PASS`

## Suite canónica completa

W10 quedó integrado permanentemente en:

`.github/workflows/test-free-browser-ai-worker.yml`

Step:

`W10 in-flight clean and crash restart`

Commit de integración canónica:

`02723bf4d0f2d51d118dd463137b03eb1f2bc28e`

Workflow run:

`35863310519`

Job:

`107188575693`

Conclusion:

**SUCCESS**

En la misma ejecución pasaron:

- W6;
- W7;
- W8;
- W9;
- W10;
- B02 scope freeze;
- Python contracts;
- browser-first source;
- multi-provider browser pool;
- PowerShell;
- B14-B20;
- B03-B38;
- Gate 0;
- portable LAB;
- AITransport through Chrome with zero API keys;
- free-only / no-production boundaries.

## Limpieza

Los workflows temporales:

- `ceo-w10-inflight-restart.yml`
- `ceo-w10-resume-inspect.yml`

fueron eliminados después de integrar W10 en la suite canónica.

## Dictamen W10

**CLEAN STOP DURANTE RUNNING:** PASS  
**RUNNING → RETRY DURABLE:** PASS  
**CRASH CHECKPOINT RECOVERY:** PASS  
**STALE WORKER LEASE RELEASE:** PASS  
**MISMO TASK ID TRAS REINICIO:** PASS  
**SIN DUPLICACIÓN DE HOJAS:** PASS  
**ARTEFACTO PARCIAL NO ACEPTADO:** PASS  
**ARTEFACTO FINAL EXACTO:** PASS  
**VERIFICACIÓN INDEPENDIENTE:** PASS  
**COMPLETED_AT:** PASS  
**100 % VISIBLE:** PASS  
**PACKAGE HASH:** PASS  
**W6-W10 COMBINADOS:** PASS  
**BROWSER-FIRST REGRESSION:** PASS  
**VALIDACIÓN FÍSICA PC USUARIO:** PENDIENTE  
**INSTALADOR GENERADO:** NO  
**CANAL STABLE MODIFICADO:** NO

## Siguiente bloque

**W11 — idempotencia y reejecución segura de tareas finitas con side effects locales**, salvo indicación distinta del usuario.
