# W2 — Inventario del paquete consolidado CEO Windows

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — SOURCE INVENTORY FIXED  
**Validación física:** pendiente

## Dictamen

La base 1.5.92 DEV316 se conserva como bloque. No se reconstruye el core archivo a archivo.

La zona de composición browser-first queda limitada a estas rutas de producción:

1. `ceo_core/routing.py`
   - referencia de bridge: `ceo-updates/dev313-inspect-routing/routing.py`
   - función: routing browser-first sin acoplar scheduler a una API.

2. `ceo_core/providers/chatgpt_web.py`
   - referencia de bridge: `ceo-updates/dev313-inspect-routing/providers/chatgpt_web.py`
   - función: transporte ChatGPT Web/CDP, API no requerida.

3. `scripts/ceo_stdlib_work_mode.py`
   - NO se copia entero desde el bridge antiguo.
   - se fusionan solo hooks browser sobre la versión 1.5.92 para conservar DEV313 deterministic completion, DEV314 provider-scoped intake y DEV315 field endurance.

4. `ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1`
   - fuente canónica: `ceo-browser/windows_chatgpt_cdp_driver.ps1`
   - blob: `7bf89f3441861360b49ed1f98b08384e24d453df`

5. `ceo_core/browser_ai/open_chatgpt_profile.ps1`
   - fuente canónica: `ceo-browser/open_chatgpt_profile.ps1`
   - blob: `202b43d1d6b83645df2d6e239d319c14aff95001`

6. `ceo_core/browser_ai/recipes/chatgpt_web.json`
   - fuente canónica: `ceo-browser/recipes/chatgpt_web.json`
   - blob: `eac61a5dd8e2d233f1872db81f176d101f519454`

## No sustituir desde el bridge antiguo

- `ceo_core/scheduler.py`
- `ceo_core/contracts.py`
- `ceo_core/graph.py`
- `ceo_core/ai_worker.py`
- updater
- launcher
- deterministic completion certifier
- field endurance certifier
- provider trust

Estas piezas deben permanecer en la generación 1.5.92 o su linaje heredado.

## Copias antiguas declaradas obsoletas

- driver bridge antiguo: `748a21831c98e1660a35ebd1d3fbb8d77b944710`
- recipe bridge antigua: `5b5fbb6c5d343ed86178a63ef1b77e5fe9ed15b8`

No pueden entrar en el paquete consolidado.

## Herramientas de auditoría / campaña

Los siguientes ficheros de `ceo-browser/` son instrumentos de validación, no requisitos del runtime de producción:

- `run_field_campaign.py`
- `first_trial_orchestrator.py`
- `run_b38_real_ceo_candidate.py`
- gates B09–B38
- harnesses y contratos de prueba

Podrán acompañar una candidata LAB/auditoría, pero no deben confundirse con dependencias del motor.

## Contrato del paquete final

Al construir la candidata consolidada:

- las seis rutas de producción anteriores deben estar en `CEO_UPDATE_PACKAGE.json` cuando proceda;
- sus hashes deben calcularse después de la fusión;
- ninguna ruta obsoleta puede ser fuente de overwrite;
- el paquete base debe conservar updater, launcher, rollback y core 1.5.92;
- el canal stable permanece congelado.

## Resultado W2

Inventario crítico: **FIXED**.  
Duplicidad browser antigua: **IDENTIFIED / EXCLUDED**.  
Árbol objetivo: **DEFINED**.  
Instalador generado: **NO**.
