# W9 — Tarea local finita sin IA externa

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — MULTIPLE BUGS FOUND, FIXED, FOCAL WINDOWS CI GREEN  
**Validación física en el PC del usuario:** pendiente

## Objetivo

Demostrar que CEO puede completar un objetivo sencillo, finito y verificable sin depender de ninguna IA externa:

`Crea CEO_LOCAL_W9.txt. Debe contener exactamente: CEO_LOCAL_W9_OK`

Cadena exigida:

objetivo → planificación → ejecución local → artefacto real → verificación independiente local → evidencia → cierre determinista → 100 % → persistencia/reapertura.

Condiciones:
- sin API keys;
- sin red;
- sin shell;
- sin gasto;
- sin intervención humana durante la ejecución.

## Resultado final

PASS.

El E2E final produjo:

- archivo: `CEO_LOCAL_W9.txt`
- contenido exacto: `CEO_LOCAL_W9_OK`
- tamaño: 15 bytes
- SHA-256:
  `3efcdd70d048b516b02a66eabd0400ae90ac3bef11cf293467c0d14db47c47e1`
- providers usados:
  - `ceo-local-goal-lock`
  - `ceo-local-finite-file`
- coste total: `0.0`
- `goal_audit_passed=true`
- `completed_at` escrito
- progreso visible: `100.0`
- productive pending: `0`
- reapertura: permanece `100.0`
- migración legacy al reabrir: `changed=false`
- certificado determinista válido tras reapertura.

## Primera mitad W9

La primera mitad quedó cerrada antes del cierre final:

- parser de objetivo local acotado;
- ruta local sin API;
- escritura real en workspace;
- modificación draft→contenido final;
- hashes de cada escritura;
- protección de path traversal;
- rechazo de objetivos ambiguos/no acotados.

## Bugs encontrados y corregidos en W9-B

### 1. Goal-lock tratado como trabajo productivo verificable externamente

Síntoma:
- `Clarify & lock goal` terminaba correctamente mediante `ceo-local-goal-lock`;
- el scheduler generaba verificaciones independientes externas del propio goal-lock;
- sin proveedor externo, CEO entraba en `ESPERANDO PROVEEDOR`.

Corrección:
- goal-lock determinista se clasifica como `internal_control`;
- mantiene sus dependencias/contrato;
- no genera verificación IA.

### 2. Verificación genérica duplicaba el Final audit local

Síntoma:
- `Execution` escribía correctamente el archivo;
- el plan ya contenía `Final audit`;
- el scheduler añadía además verificadores genéricos externos.

Corrección:
- `Execution.verification_scheduled` queda enlazado al `Final audit` explícito;
- el Final audit declara `verifies = Execution.id`;
- no se generan verificadores externos redundantes.

### 3. RecoveryBudgetGuard eliminaba verificaciones legítimas

Causa raíz:
- `is_internal()` incluye CONTROL + VERIFICATION;
- `RecoveryBudgetGuardV1(max_active_internal=1)` aplicaba el presupuesto de churn a todas las tareas internas;
- una verificación real podía quedar:
  `SUPERSEDED / recovery_budget_guard_duplicate_internal_control`.

Esto era un defecto de núcleo, no solo de W9.

Corrección:
- las tareas con rol VERIFICATION quedan fuera del presupuesto de recovery/control churn;
- el guard continúa limitando controles/recoveries duplicados;
- regresión explícita: con dos controles + una verificación, se retira un control excedente pero la verificación permanece READY.

### 4. Final audit usaba marcador incorrecto

Síntoma:
- el archivo era leído y comparado correctamente;
- el worker devolvía `CEO_RESULT`;
- `LayeredVerificationEngine` exige `CEO_VERIFY`;
- resultado: `verdict=unclassified / missing_or_invalid_CEO_VERIFY`.

Corrección:
- el provider local devuelve:
  `<CEO_VERIFY>{"verdict":"pass","confidence":1.0,...}</CEO_VERIFY>`
- conserva también `CEO_RESULT` para el controlador general.

Resultado:
- `verification_application.applied=true`
- `verdict=pass`
- `confidence=1.0`
- target correcto.

## Correcciones del harness, no del runtime

Durante W9 también se corrigieron varios errores de prueba que NO eran defectos de CEO:

- dependencias CI faltantes: `psutil`, `httpx`;
- `CheckpointStore` es interfaz abstracta sin constructor con path:
  se creó un `JsonCheckpointStore` mínimo para ejercitar el scheduler real;
- la prueba usaba `Task.cost_actual`, campo inexistente:
  ahora exige `CostEngine.spent(state) == 0.0`.

Estas correcciones no se presentan como bugs de producción.

## Seguridad de la ruta local

El parser rechaza:

- `../escape.txt`;
- varios archivos en el mismo objetivo;
- extensiones no autorizadas como `.exe`;
- objetivos de investigación + archivo, que no son operaciones locales acotadas;
- objetivos sin contenido exacto.

Extensiones admitidas en esta ruta:
- `.txt`
- `.md`
- `.json`

El target se resuelve y se exige que permanezca dentro del workspace gestionado.

## Evidencia Windows CI focal

Workflow focal W9 final:

- run: `35861150095`
- job: `107181407132`
- conclusion: **SUCCESS**

Marcas:
- `W9_LOCAL_FINITE_E2E`
- `W9_PACKAGE_HASH ... ok=true`
- `W9_LOCAL_FINITE_REGRESSION_PASS`
- `W9_WINDOWS_CI_PASS`

### Estado E2E observado

Tasks:
- Clarify & lock goal → COMPLETE
- Execution → COMPLETE
- Final audit → COMPLETE

Verificación:
- verdict = pass
- confidence = 1.0

Cierre:
- `goal_audit_passed=true`
- `CompletionEngine.complete=true`
- `completed_at != None`
- display progress = 100
- productive pending = 0

Reapertura:
- certificate hash válido;
- `migrate_invalid_legacy_pass.changed=false`;
- `completed_at` preservado;
- display progress = 100.

## Hashes verificados en el E2E focal

- `ceo_core/local_finite_file_provider_v1.py`
  - `033e9e5101c867a95da71f076c75ce27b2ab070b2d8530997737bde1c4d92666`
- `ceo_core/recovery_budget_guard_v1.py`
  - `172703e167edc8e1195ed63989560ee9b1683881c5eb2f58cb1622aa1bb690a8`
- `scripts/ceo_stdlib_work_mode.py`
  - `7a1d5b5217390e71ca8d296efaae33e1572e1d91254851abf0c582f50f45b180`
- W6 goal completion gate:
  - `40cb8a3e05ca2abada0c2f935560699c308d3dc7d5ac1a6184df84b3eb1e85ba`
- W7 productive fallback:
  - `d234cafe891d6f8c8524f1780e54e18f8a676664c353abb7b376faf3ab0acab2`
- W8 progress tracker:
  - `a7c5e293393ad116d3bae6ec6802aea37485c1d99bbde94dbd4fcdff8e0b51d4`

## Integración

W9 está integrado en:

`.github/workflows/test-free-browser-ai-worker.yml`

como:

`W9 finite local objective closes without external AI`

Ese step construye acumulativamente:

1. base 1.5.92;
2. W6;
3. W7;
4. W8;
5. W9;

y vuelve a ejecutar W6, W7, W8 y W9 antes de continuar con browser-first.

Los workflows temporales:
- `ceo-w9-local-finite.yml`
- `ceo-w9-local-inspect.yml`

han sido eliminados.

## Dictamen W9

**TAREA LOCAL REAL:** PASS  
**ARTEFACTO REAL:** PASS  
**MODIFICACIÓN REAL:** PASS  
**SHA-256:** PASS  
**VERIFICACIÓN LOCAL INDEPENDIENTE:** PASS  
**SIN API:** PASS  
**SIN RED:** PASS  
**SIN SHELL:** PASS  
**COSTE:** 0.0  
**CIERRE DETERMINISTA:** PASS  
**100 % VISIBLE:** PASS  
**REAPERTURA SIN REANIMACIÓN:** PASS  
**PACKAGE HASH CONTRACT:** PASS  
**VALIDACIÓN FÍSICA PC USUARIO:** PENDIENTE  
**INSTALADOR GENERADO:** NO  
**CANAL STABLE MODIFICADO:** NO

## Siguiente bloque

**W10 — persistencia/reinicio durante una tarea finita en curso**, salvo nueva indicación del usuario.
