# W4 — Auditoría Goal Engine / descomposición finita

**Fecha:** 2026-09-23  
**Estado:** CLOSED — SOURCE AUDIT PASS  
**Prueba E2E real:** pendiente

## Goal Engine

El objetivo queda bloqueado en un contrato con:
- objetivo;
- definición;
- éxito;
- restricciones;
- criterios de finalización;
- entregables;
- acciones prohibidas;
- urgencia;
- presupuesto.

El contrato se hash-ea y queda persistido.

## Descomposición inicial

`TaskDecomposer` es determinista y no recursivo.

### Objetivo compacto

Para un objetivo sencillo con un único archivo explícito:

- 3 fases root;
- 1 hoja por fase;
- **3 hojas ejecutables**;
- 6 tareas totales contando roots.

La regresión DEV308 ya verificó este caso con `AUTONOMY_GATE_1.md`.

### Objetivo general

Plan base:

- 6 fases root;
- 24 hojas ejecutables;
- 30 tareas totales contando roots.

No existe llamada recursiva del decomposer base.

## Entregable explícito

DEV309 incorpora inferencia de entregables desde objetivos con nombre de archivo.

Ejemplo canónico:

`AUTONOMY_GATE_1.md`

activa perfil:

`bounded_single_artifact`

Esto reduce el cierre posterior a un máximo de 4 generaciones de continuidad.

## Cierre no circular

El objetivo real no puede cerrarse solo porque una IA escriba “PASS”.

El gate exige:
- evidencia de tareas reales;
- evidencia grounded;
- artefacto/implementación;
- verificación independiente;
- contrato específico del objetivo;
- entregable probado si fue declarado.

## Invariante de composición browser-first

La versión antigua de `dev313-inspect-routing/ceo_stdlib_work_mode.py` exigía browser disponible antes de crear un proyecto.

Esa condición NO debe reintroducirse.

La candidata consolidada debe conservar la semántica DEV314/1.5.92:
- el objetivo puede crearse y persistirse aunque el proveedor externo esté temporalmente caído;
- solo las hojas dependientes de IA esperan proveedor;
- el núcleo/local intake sigue operativo.

Por tanto W4 prohíbe copiar el work-mode antiguo completo.

## Primer objetivo recomendado para el gate posterior

Usar un único archivo explícito y pequeño, por ejemplo:

“Crea en el workspace `CEO_FIRST_RESULT.md` con un resumen verificable del objetivo, comprueba que existe y no está vacío, y no declares terminado el objetivo hasta verificar ese archivo.”

Esto fuerza el perfil compacto y permite distinguir HECHO/NO HECHO.

## Resultado W4

Goal contract: **PASS_SOURCE**.  
Plan inicial finito: **PASS_SOURCE**.  
Compact single-file 3 hojas: **PASS_EXISTING_REGRESSION**.  
Full baseline 24 hojas: **PASS_SOURCE**.  
Cierre circular: **BLOCKED BY GATE**.  
Provider outage bloqueando creación del proyecto: **PROHIBIDO EN MERGE FINAL**.  
Cambio nuevo del Goal Engine requerido: **NO**.
