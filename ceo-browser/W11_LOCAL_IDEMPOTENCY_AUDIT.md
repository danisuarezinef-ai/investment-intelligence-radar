# W11 — Idempotencia y reejecución segura de efectos locales

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — BUG FOUND, FIXED, CANONICAL WINDOWS CI GREEN  
**Validación física en el PC del usuario:** pendiente

## Objetivo

Demostrar que una tarea finita con efecto local puede reejecutarse con seguridad cuando:

1. el efecto físico ya ocurrió;
2. el checkpoint durable todavía refleja la tarea como RUNNING/RETRY;
3. CEO reinicia y vuelve a ejecutar la misma unidad.

El resultado debe converger sin repetir innecesariamente el efecto físico, sin duplicar evidencia y sin generar un nuevo linaje.

Caso usado:

`Crea CEO_LOCAL_W9.txt. Debe contener exactamente: CEO_LOCAL_W9_OK`

sin APIs externas.

## Bug reproducido

Se construyó la candidata acumulada W6-W10.

Secuencia adversarial:

1. Execution entra RUNNING;
2. se captura un checkpoint antiguo;
3. la ejecución real termina y deja el archivo correcto;
4. se vuelve a abrir CEO desde el checkpoint antiguo;
5. la misma Execution task se reejecuta sobre un archivo que YA contiene el resultado final correcto.

### Comportamiento raw

La candidata W6-W10 repetía físicamente:

1. escritura de `[CEO_LOCAL_DRAFT]\n`;
2. escritura de `CEO_LOCAL_W9_OK`.

Evidencia:

- physical_writes = 2;
- mtime_changed = true;
- mismo task id;
- mismo SHA final;
- pero el side effect se repetía innecesariamente.

Marca CI:

`W11_RAW_DUPLICATE_SIDE_EFFECT_REPRODUCED`

Esto es un fallo real de idempotencia.

Aunque el resultado final convergía, un replay no debe destruir temporalmente un resultado correcto ni asumir que todos los futuros efectos locales serán inocuos al repetirse.

## Corrección W11

### 1. Provider local

`ceo_core/local_finite_file_provider_v1.py`

Antes de emitir la operación de escritura:

- resuelve el target dentro del workspace;
- si el fichero ya existe;
- y su contenido UTF-8 coincide exactamente con el contenido objetivo;

el provider clasifica la operación como replay idempotente.

En ese caso:

- NO emite el draft;
- solo declara el contenido final esperado;
- marca `idempotent_replay_candidate=true`.

Si el contenido no coincide, conserva la ruta normal draft → final.

### 2. Scheduler

`ceo_core/scheduler.py`

Antes de ejecutar `FilesystemOperations.write_text`:

- resuelve el path bajo el workspace;
- compara el contenido existente con el deseado.

Si coincide exactamente:

- NO llama a la escritura física;
- calcula SHA-256 y tamaño sobre el fichero existente;
- registra:
  - `idempotent_noop=true`
  - `physical_write=false`
- conserva registro de artefacto/evidencia para reconstruir el checkpoint.

Si no coincide:

- realiza la escritura normal;
- registra:
  - `idempotent_noop=false`
  - `physical_write=true`.

También se evita duplicar IDs ya presentes en `verified_artifacts`.

### 3. Evidencia

`ceo_core/deliverable_evidence_engine_v1.py`

La misma observación:

- mismo task_id;
- mismo kind;
- mismo ref;
- mismo SHA-256;

ya no añade otra fila idéntica al ledger durable.

Esto evita que un replay infle evidencia sin producir trabajo nuevo.

## Resultado corregido

Con el mismo checkpoint antiguo y el archivo final ya correcto:

- physical_writes = **0**
- mtime_changed = **false**
- idempotent_noops = **1**
- physical_write = **false**
- SHA permanece:
  `3efcdd70d048b516b02a66eabd0400ae90ac3bef11cf293467c0d14db47c47e1`
- mismo task id;
- mismo conjunto de hojas;
- completed_at escrito;
- objetivo cierra normalmente.

Marca:

`W11_STALE_REPLAY`

## Reparación de un estado realmente incorrecto

W11 también prueba el caso opuesto.

El fichero existente se sustituye por:

`BROKEN_W11`

CEO reabre desde el mismo checkpoint antiguo.

Resultado:

- NO lo trata como idempotente;
- physical_writes = 2;
- vuelve a ejecutar draft → final;
- contenido final exacto;
- SHA final correcto;
- completed_at escrito.

Marca:

`W11_CORRUPT_REPAIR`

Por tanto W11 no convierte “ya existe un fichero” en éxito. Solo evita el efecto cuando **los bytes ya son exactamente los deseados**.

## Package hashes

Candidata focal W11:

- `ceo_core/local_finite_file_provider_v1.py`
  - `c52010e41d0b330d59903e14350fd707d8a472f7a5cb6a22400d220dfe108be9`

- `ceo_core/scheduler.py`
  - `2511f3f65262de6eb9d59a4783640e0d2e90bb877a17fb3221342793eeb09bf7`

- `ceo_core/deliverable_evidence_engine_v1.py`
  - `1c8d848a12de32baf99f5226f1962514f3d9b9fd69def012b8e0521a76a83eba`

Los hashes quedaron sincronizados en `CEO_UPDATE_PACKAGE.json`.

## Evidencia focal Windows CI

Workflow focal:

- run: `35865768272`
- job: `107196824131`
- conclusion: **SUCCESS**

Marcas:

- `W11_RAW_DUPLICATE_SIDE_EFFECT_REPRODUCED`
- `W11_LOCAL_IDEMPOTENCY_FIX_APPLIED`
- `W11_STALE_REPLAY`
- `W11_CORRUPT_REPAIR`
- `W11_PACKAGE_HASHES`
- `W11_LOCAL_IDEMPOTENCY_REGRESSION_PASS`
- `W11_WINDOWS_CI_PASS`

## Suite canónica completa

W11 quedó integrado permanentemente en:

`.github/workflows/test-free-browser-ai-worker.yml`

Step:

`W11 idempotent replay of local side effects`

Candidata acumulada:

1. base 1.5.92;
2. W6;
3. W7;
4. W8;
5. W9;
6. W10;
7. W11.

Commit de integración:

`a576047b788e82a762fbd29271d905d4205fca9e`

Workflow run:

`35866004082`

Job:

`107197622430`

Conclusion:

**SUCCESS**

En la misma ejecución pasaron:

- W6;
- W7;
- W8;
- W9;
- W10;
- W11;
- B02 scope freeze;
- Python contracts;
- browser-first;
- multi-provider browser pool;
- PowerShell;
- B14-B20;
- B03-B38;
- Gate 0;
- LAB portable;
- AITransport Chrome con cero API keys;
- free-only / no-production boundaries.

## Limpieza

El workflow temporal:

`.github/workflows/ceo-w11-local-idempotency.yml`

fue eliminado una vez integrada la regresión canónica.

## Dictamen W11

**BUG REAL ENCONTRADO:** sí  
**DUPLICACIÓN FÍSICA RAW:** 2 escrituras  
**REPLAY EXACTO CORREGIDO:** 0 escrituras  
**MTIME INTACTO EN REPLAY:** PASS  
**MISMO TASK ID:** PASS  
**SIN NUEVO LINAJE:** PASS  
**EVIDENCIA DUPLICADA:** BLOQUEADA  
**ARTEFACTO CORRUPTO SE REPARA:** PASS  
**PACKAGE HASH:** PASS  
**W6-W11 COMBINADOS:** PASS  
**BROWSER-FIRST REGRESSION:** PASS  
**VALIDACIÓN FÍSICA PC USUARIO:** pendiente  
**INSTALADOR GENERADO:** no  
**CANAL STABLE MODIFICADO:** no

## Siguiente bloque

**W12 — pausa / reanudar / cancelar**, salvo indicación distinta del usuario.
