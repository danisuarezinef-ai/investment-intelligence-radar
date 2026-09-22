# W5 — Auditoría scheduler / dependencias / expansión acotada

**Fecha:** 2026-09-23  
**Estado:** CLOSED — SOURCE AUDIT PASS  
**Prueba prolongada Windows:** pendiente

## Dependencias y estados

`TaskGraph`:
- valida dependencias;
- detecta missing deps, orphan children y ciclos;
- solo pone READY cuando todas las dependencias están terminalmente satisfechas;
- respeta retry_after;
- respeta `blocked_safe`;
- no ejecuta roots/grupos como workers.

`ContinuousScheduler`:
- despacha solo hojas READY;
- limita concurrencia;
- persiste al iniciar y detener;
- normaliza tareas RUNNING interrumpidas a RETRY;
- en cancelación impide nueva recuperación y detiene el loop.

## Reintentos

`Task.max_attempts` por defecto = 3.

DEV307 verifica que:
- un Future terminado nunca queda eternamente RUNNING;
- excepciones repetidas terminan FAILED;
- la normalización no consume falsamente worker-recovery budget.

## Calidad

DEV307 limita:
- inline quality corrections;
- generaciones de replacement.

La regresión existente prueba máximo 2 generaciones de reparación y luego fallo acotado.

## Espera de proveedor

Errores clasificados como:
- quota;
- provider_unavailable;
- model_unavailable;
- transient

pasan a BLOCKED/WAITING_PROVIDER con retry_after.

La lógica reduce el contador de attempts y registra:

`recoveries_consumed = 0`

Por tanto una caída temporal del proveedor no debe volver a producir recovery storms.

## Recovery storm

`RecoveryStormGuardV1` se consulta antes del dispatch.

Si el guard está abierto:
- no despacha recuperación insegura;
- usa `blocked_safe`;
- preserva gates humanos legítimos.

## Cierre #173 / continuidad

DEV309 cambió el cierre histórico sin límite por perfiles acotados:

### Un único entregable
- min continuity generations = 1
- max continuity generations = **4**

### General
- min = 3
- max = **24**

Al alcanzar el máximo sin evidencia suficiente:
- no sigue generando auditorías indefinidamente;
- pasa a `closure_bounded_stall`;
- se declara BLOQUEADO de forma explícita.

## Duplicados / auditorías vacías

- follow-ups duplicados se filtran antes de contarlos como progreso;
- dos rechazos de auditoría sin trabajo nuevo activan un batch determinista de cierre;
- el batch de gap recovery es acotado;
- las auditorías de control no cuentan como productividad.

## Finalización determinista

DEV313 añade un certifier independiente del proveedor.

Cuando el trabajo ya está probado:
- marca `work_complete_certified_v1`;
- suprime nuevas auditorías de continuidad;
- no necesita otra llamada IA para “decidir” que terminó.

## Field endurance

DEV315 observa tiempo activo real:
- no cuenta suspensión/offline;
- una caída de scheduler bloquea certificación;
- recovery storm bloquea certificación;
- el certificado queda ligado al hash de evidencia;
- al certificarse puede promover el cierre sin IA.

Este gate solo se activa para objetivos que lo requieran; no debe bloquear el primer objetivo sencillo de un archivo.

## Pausa / cancelación

La rama actual ya contiene:
- `paused` impide nuevo dispatch;
- `cancelled_at/operator_cancelled` desactiva autonomía, suprime recovery y para el loop;
- stop devuelve RUNNING a RETRY salvo cancelación, donde se supersede.

## Resultado W5

Dependency semantics: **PASS_SOURCE**.  
Retry budget: **PASS_EXISTING_REGRESSION**.  
Worker terminal normalization: **PASS_EXISTING_REGRESSION**.  
Quality lineage bounded: **PASS_EXISTING_REGRESSION**.  
Provider wait without recovery burn: **PASS_SOURCE**.  
Closure generation cap: **PASS_EXISTING_REGRESSION**.  
Deterministic no-more-audits hold: **PASS_SOURCE / INHERITED DEV313**.  
Field endurance integration: **PASS_SOURCE / INHERITED DEV315**.  
Scheduler physical/endurance run: **PENDING**.  
Cambio nuevo del scheduler requerido ahora: **NO**.
