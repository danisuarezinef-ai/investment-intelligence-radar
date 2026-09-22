# W6 — Finalización real / anti-99 %

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — BUG FOUND, FIXED, REGRESSION GREEN  
**Validación física en PC del usuario:** pendiente

## Objetivo

Demostrar la cadena:

`entregable real → evidencia grounded → certificado determinista → 100 % → completed_at → reinicio/reapertura sin reabrir el objetivo`

y evitar tanto:
- falso 100 % sin entregable;
- objetivos eternos al 95–99 %;
- reapertura de objetivos ya completados tras reiniciar CEO.

## Hallazgo crítico

La base 1.5.92 tenía una interacción defectuosa entre:

- `DeterministicCompletionCertifierV1`;
- `GoalCompletionGate.migrate_invalid_legacy_pass()`.

El certificado determinista podía cerrar correctamente un objetivo sin consumir rondas provider-era de continuidad.

Sin embargo, al reabrir el proyecto, `migrate_invalid_legacy_pass()` volvía a evaluar el gate legacy y veía:

`continuity_rounds:0<3`

aunque el cierre determinista ya estuviera hash-bound a evidencia suficiente.

### Evidencia reproducida contra el ZIP 1.5.92 exacto

Workflow inicial W6:
- run: `35793388517`
- resultado: FAIL esperado de regresión

Estado antes del fix:

- `display_progress = 100.0`
- certificado determinista: final
- `goal_audit_passed = true`
- después de serializar/reabrir:
  - migration = `invalid_pass_reopened`
  - `completed_at = null`
  - `goal_audit_passed = false`
  - única gap: `continuity_rounds:0<3`

Por tanto el antiguo síntoma podía reaparecer después de reinicio aun cuando el trabajo ya estaba realmente terminado.

## Corrección mínima W6

No se cambia scheduler, decomposer ni CompletionEngine.

Se corrige únicamente la migración legacy.

Antes de invalidar un pase cuyo source sea:

`deterministic_completion_certificate_v1`

CEO ahora:

1. recomputa el certificado determinista desde el estado y evidencia actuales;
2. exige `final_complete=true`;
3. exige igualdad entre:
   - hash guardado en `goal_audit_evidence`;
   - hash guardado en el certificado persistido;
   - hash recién recomputado;
4. solo preserva el cierre si los tres coinciden.

Si la evidencia cambió, falta un entregable, aparece un blocker o deja de cumplirse una certificación requerida, no se conserva el cierre anterior.

Patch de auditoría/candidata:
- `ceo-browser/apply_w6_completion_persistence.py`

## Regresión W6

- `ceo-browser/w6_anti99_regression.py`

Comprueba sobre el ZIP exacto 1.5.92 parcheado:

### 1. Cierre determinista
PASS

### 2. Progreso final
- `display_progress = 100.0`
- `batch_progress = 100.0`
- `completed = true`

PASS

### 3. Reinicio / reapertura
Tras serialización + reconstrucción:

- migration: `deterministic_grounded_pass`
- `changed=false`
- `completed_at` preservado
- `goal_audit_passed=true`
- phase: `deterministically_certified`

PASS

### 4. Contrato del paquete
SHA-256 de `ceo_core/goal_completion_gate.py` actualizado en `CEO_UPDATE_PACKAGE.json`.

Hash probado:

`b3e05876d4ed04e364033fef93286a86d5b251021b258e6a5d4cff1403928cf8`

PASS

### 5. Manipulación de evidencia
Al cambiar el SHA del entregable después del cierre:
- el hash del certificado deja de coincidir;
- la migración reabre correctamente el proyecto.

PASS

### 6. Entregable ausente
`deliverable_unproven:CEO_FIRST_RESULT.md`

impide `work_complete`.

PASS

### 7. Field endurance
Con certificación física requerida pero pendiente:
- `work_complete=true`
- `final_complete=false`
- `goal_audit_passed` no se concede.

PASS

Por tanto W6 no debilita el gate de endurance.

## CI

Prueba focalizada final:
- workflow run `35793684535`
- conclusion: **SUCCESS**

La regresión se integró después en el workflow canónico Windows:

`.github/workflows/test-free-browser-ai-worker.yml`

Step:

`W6 anti-99 deterministic completion persistence`

Ese step ya ejecutó con:
- conclusion: **SUCCESS**
- B02 scope freeze posterior: **SUCCESS**

El workflow temporal W6 fue eliminado; no queda una infraestructura paralela.

## Invariantes W6

A partir de ahora una candidata Windows NO puede considerarse válida si:

- tiene `completed_at` pero progreso visible < 100;
- un reinicio borra `completed_at` de un certificado determinista vigente;
- una evidencia manipulada conserva el certificado anterior;
- falta el entregable solicitado y aun así se cierra;
- field/endurance pendiente se salta;
- el archivo modificado no coincide con el hash del contrato del paquete.

## Resultado W6

**BUG REAL ENCONTRADO:** sí  
**CAUSA RAÍZ:** migración legacy revalidaba incorrectamente un certificado determinista provider-independent  
**CORREGIDO:** sí  
**REGRESIÓN EN ZIP 1.5.92:** PASS  
**REGRESIÓN EN WINDOWS CI:** PASS  
**100 % visual tras cierre:** PASS  
**persistencia del cierre tras reapertura:** PASS  
**tamper detection:** PASS  
**field gate preservado:** PASS  
**cambio de scheduler:** NO  
**instalador generado:** NO  
**stable channel modificado:** NO  
**validación física en PC del usuario:** pendiente

## Siguiente bloque

W7 puede continuar desde esta corrección; la futura candidata consolidada debe aplicar W6 antes de empaquetarse.
