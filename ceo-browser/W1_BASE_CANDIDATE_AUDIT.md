# W1 — Auditoría de candidata base CEO Windows

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — BASE LOGICAL CANDIDATE FIXED  
**No constituye release ni validación física.**

## Objetivo

Fijar una única base técnica para las auditorías W2+ evitando mezclar paquetes, ramas o generaciones distintas de CEO.

## Dictamen

La candidata lógica de auditoría se construirá sobre:

1. **Core Windows:** `CEO_1.5.92-rc1-native-transport-integrity.zip`
   - release sequence: DEV316
   - SHA-256 declarado: `781c396abc6ebd191ae1c8ee32141e48d354a9a8f2ae6870035607324c1afabc`
   - 525 entradas
   - hereda DEV311 updater/app-window
   - hereda DEV312 provider trust
   - hereda DEV313 deterministic completion
   - hereda DEV314 capability-scoped provider
   - hereda DEV315 field-endurance certification
   - `production_ready=false`
   - `field_validation_pending=true`

2. **Browser-first canónico:** commit
   `c210b93167361b3ff4017368ac2d790fca8de5b3`
   - último HEAD de implementación operativa
   - los commits posteriores de `free-browser-ai-worker` son de checkpoint/sincronización y no sustituyen este BUILD ID
   - CI canónico asociado: SUCCESS
   - todavía sin certificación física compartida de B14/B18/B20/B29-B30/B38

3. **Bridge browser/core existente:** `ceo-updates/dev313-inspect-routing`
   - se reutiliza como referencia de integración
   - NO se considera fuente canónica del driver ni de las recetas browser

## Linaje de core aceptado

`1.5.88 provider-trust`
→ `1.5.89 deterministic-completion`
→ `1.5.90 capability-scoped-provider`
→ `1.5.91 field-endurance-certification`
→ `1.5.92 native-transport-integrity`

No se usará 1.5.89 stable como base final porque queda por detrás de las garantías de cierre/endurance ya construidas.

## Regla de composición

### Conservar de 1.5.92

Se conserva íntegramente el core 1.5.92 salvo cambios browser explícitamente auditados.

En particular NO se sustituirá `scheduler.py` por la copia de `dev313-inspect-routing`, porque DEV313 y DEV315 modifican el scheduler para deterministic completion y field endurance.

También deben conservarse:
- updater DEV311;
- provider trust DEV312;
- deterministic completion;
- capability-scoped provider;
- field endurance;
- bootstrap/update package contract;
- version identity y single-instance.

### Portar desde el bridge browser

El constructor browser-first histórico demuestra que la integración mínima requiere:

- `ceo_core/routing.py`
- `ceo_core/providers/chatgpt_web.py`
- cambios browser específicos en `scripts/ceo_stdlib_work_mode.py`
- `ceo_core/browser_ai/*`

**Importante:** `scripts/ceo_stdlib_work_mode.py` NO se copiará entero desde el bridge antiguo. Se fusionarán únicamente los cambios browser sobre la versión 1.5.92 para no perder los cambios posteriores de completion/endurance.

El builder histórico `build_browser_first_lab.py` no requería sustituir `scheduler.py`, `contracts.py`, `graph.py` ni `ai_worker.py`; W2/W3 solo los incorporarán si una dependencia concreta lo demuestra.

## Fuentes browser canónicas

Usar desde `c210b931...`, no desde la copia antigua del bridge:

- `ceo-browser/windows_chatgpt_cdp_driver.ps1`
  - blob SHA: `7bf89f3441861360b49ed1f98b08384e24d453df`
- `ceo-browser/recipes/chatgpt_web.json`
  - blob SHA: `eac61a5dd8e2d233f1872db81f176d101f519454`
- `ceo-browser/open_chatgpt_profile.ps1`
  - blob SHA: `202b43d1d6b83645df2d6e239d319c14aff95001`
- `ceo-browser/run_field_campaign.py`
  - blob SHA: `c29e3aee92754f4b6d4d44f3d005f5154bb43e36`
- `ceo-browser/first_trial_orchestrator.py`
  - blob SHA: `b4c20dacfd78508ec5f02f68ed326a78bf3c8216`

La copia antigua del bridge queda explícitamente obsoleta para:
- driver: `748a21831c98e1660a35ebd1d3fbb8d77b944710`
- recipe ChatGPT: `5b5fbb6c5d343ed86178a63ef1b77e5fe9ed15b8`

## Updater

El canal stable actual sigue apuntando a `1.5.89-rc1-native-transport-integrity`.

**Política W1:** no modificar todavía `ceo-update-channel` ni publicar 1.5.92/browser como stable.

La candidata consolidada debe heredar el updater existente, pero el canal final solo se cambiará después de superar los gates de:
- paquete limpio;
- tarea finita;
- cierre real;
- restart;
- updater N→N+1;
- rollback;
- persistencia tras reinicio.

## Exclusiones explícitas

W1 NO afirma:
- APK/Android nada;
- BROWSER_FIELD_VERIFIED;
- B14/B18/B20/B29-B30 físico PASS;
- B38 físico PASS;
- stage preflight Windows PASS;
- single-file activator verified;
- production ready.

No se genera todavía ningún archivo de instalación para el usuario.

## Candidata lógica para W2+

**CORE:** 1.5.92 DEV316  
**BROWSER:** c210b931  
**BRIDGE:** integración mínima de dev313-inspect-routing, fusionada sobre 1.5.92  
**UPDATER:** DEV311 heredado, canal estable congelado hasta certificación  
**API:** opcional; no requerida para el camino browser-first

## Siguiente bloque

**W2 — Inventario del paquete consolidado.**

W2 debe construir la lista exacta de archivos requeridos, detectar copias antiguas/duplicadas/rutas muertas y definir el árbol objetivo antes de generar ningún paquete instalable.
