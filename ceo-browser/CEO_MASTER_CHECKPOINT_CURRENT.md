# CEO DE IAs — MASTER CHECKPOINT CURRENT

**Fecha:** 2026-09-22  
**Proyecto:** CEO de IAs — Windows / browser-first / no-API  
**Repositorio:** `danisuarezinef-ai/investment-intelligence-radar`  
**Rama canónica de esta línea:** `free-browser-ai-worker`  
**HEAD de implementación verificado:** `c210b93167361b3ff4017368ac2d790fca8de5b3`  
**Workflow canónico:** `35699881577` — **SUCCESS**  
**Commits de sincronización posteriores:** `fef0c0c...` (checkpoint), `20bae6f...` (protocolo). Estos no cambian la implementación.

> Este archivo es la fuente de verdad compartida para todos los chats que trabajen en CEO browser-first.  
> Si un chat recuerda otra cosa, prevalecen este checkpoint + el HEAD real del branch.

## 1. Dirección estratégica vigente

CEO debe poder trabajar con IAs web gratuitas como una persona mediante Chrome/Edge:

`objetivo -> navegador -> IA web -> prompt -> respuesta -> acción local -> test -> siguiente turno`

La arquitectura **no depende de APIs**.

Invariantes:

- `FREE_WEB_AI_FIRST = true`
- `NO_API_REQUIRED = true`
- un fallo de API nunca debe bloquear CEO;
- APIs pueden existir en el futuro como vía opcional, nunca como dependencia base;
- no compras, créditos o suscripciones sin aprobación humana explícita;
- no CAPTCHA/2FA bypass;
- no merge/push/promoción automática del código generado;
- autodesarrollo siempre en candidato/sandbox antes de promoción humana.

## 2. Arquitectura multIA

La superficie primaria dejó de ser `chatgpt-web` y pasó a ser:

`browser-provider-pool`

Pool inicial registrado:

1. `chatgpt-web`
2. `claude-web`
3. `gemini-web`
4. `perplexity-web`
5. `grok-web`

Cada proveedor puede usar receta/perfil independiente. ChatGPT es únicamente el primer proveedor físico en validación porque ya existe una sesión persistente del usuario.

Archivos principales:

- `ceo-browser/provider_registry.json`
- `ceo-browser/browser_provider_pool.py`
- `ceo-browser/recipes/chatgpt_web.json`
- `ceo-browser/recipes/claude_web.json`
- `ceo-browser/recipes/gemini_web.json`
- `ceo-browser/recipes/perplexity_web.json`
- `ceo-browser/recipes/grok_web.json`

## 3. Control real del navegador

Motor:

- `ceo-browser/windows_chatgpt_cdp_driver.ps1`

Aunque conserva el nombre histórico, el transporte se ha generalizado:

- `PowerShellWebAITransport`
- alias de compatibilidad: `PowerShellChatGPTWebTransport`

Principios vigentes:

- Chrome DevTools Protocol;
- sin coordenadas de pantalla fijas;
- entrada de texto por eventos de Chrome/CDP;
- envío por CDP mouse/keyboard sobre controles localizados dinámicamente;
- no DOM `.click()` como vía primaria;
- no DOM value/textContent directo para simular escritura;
- conversación persistente;
- selectores + fallback semántico;
- detección de respuesta/streaming;
- evidencia de envío B10;
- cero llamadas API.

## 4. Campaña física unificada

Se abandonó la cadena repetitiva de wrappers con login/restart por fase.

El flujo vigente es:

`preflight -> reset SOLO navegador del perfil CEO -> abrir una vez -> preparar sesión una vez -> B14 -> B18 -> B20 -> B29/B30`

Runner canónico:

- `ceo-browser/run_field_campaign.py`

Orquestador:

- `ceo-browser/first_trial_orchestrator.py`

Launcher:

- `EJECUTAR_PRIMERA_PRUEBA_CEO_BROWSER.cmd`

### B14

Dos turnos reales en la misma conversación:

- B09: prompt exacto;
- B10: envío real;
- B11/B12: generación y respuesta completa;
- B13: continuidad de conversación;
- B14: dos turnos reales.

### B18

La IA web debe producir un artefacto estructurado, CEO debe persistirlo y verificar:

- contenido;
- tamaño;
- SHA-256.

### B20

Programación real en repo sandbox:

- bug intencional;
- diff de IA;
- `git apply --check`;
- aplicar sólo en sandbox;
- tests;
- corrección en la misma conversación si es necesaria;
- HEAD baseline sin commit nuevo;
- cero remotes;
- no push/merge.

### B29/B30

Solo si B14 + B18 + B20 pasan **en el mismo trial físico**, se permite:

`BROWSER_FIELD_VERIFIED = true`

## 5. Evidencias aisladas por trial

Problema corregido: antes podían mezclarse evidencias antiguas con intentos nuevos.

Ahora cada intento usa:

`%LOCALAPPDATA%\CEO de IAs\evidence\trials\<TRIAL_ID>\...`

Además:

- `CURRENT_TRIAL.json` identifica el intento actual;
- `BROWSER_FIELD_STATE.json` canónico se invalida al comenzar un trial nuevo;
- un PASS viejo nunca puede autorizar un trial nuevo;
- si `trial_id` no coincide, el estado se considera NO verificado.

## 6. BUILD ID y salida física

Problema corregido: era fácil ejecutar una carpeta LAB antigua sin saberlo.

El sistema actual incluye identidad visible de build/source y la consola final muestra de forma compacta:

- RESULTADO;
- BUILD;
- TRIAL;
- ruta de EVIDENCIA;
- GO/NO-GO del intento actual.

Último cambio canónico:

`c210b93167361b3ff4017368ac2d790fca8de5b3`  
**Prevent stale field authorization and simplify physical console output**

Workflow asociado:

`35699881577` — **SUCCESS**

## 7. Correcciones posteriores al primer fallo físico

Se han integrado sucesivamente:

- eliminación de pestañas restauradas/error antes del arranque;
- campaña de una sola sesión;
- `RESTART_GATE` fuera del camino funcional principal;
- typing real por Chrome/CDP;
- soporte correcto para prompts multilínea;
- reconstrucción lógica de texto en contenteditable;
- verificación semántica del input;
- scroll del control de envío antes del click CDP;
- harness de campaña unificado;
- aislamiento de evidencias por trial;
- invalidación del PASS canónico anterior al empezar un nuevo trial;
- salida física simplificada.

Commits recientes relevantes:

- `02c36b5` — Preserve multiline prompts through trusted browser paste input
- `c37e00f` — Verify web prompt against logical composer representations
- `203058e` — Reconstruct exact logical text from contenteditable DOM
- `ba7379b` — Fix campaign harness newline responses
- `ffd6b7b` — Make campaign harness preserve rendered response newlines
- `f7c095c` — Scroll dynamic send control into viewport before trusted CDP click
- `5fcd7b2` — Preserve semantic input discovery evidence during B09 verification
- `c210b93` — Prevent stale field authorization and simplify physical console output

## 8. Estado de validación

### Verificado en CI

- arquitectura browser-first;
- pool multIA;
- CDP;
- profile/session handling;
- prompt discovery;
- B09-B13 contra harness;
- artifact pipeline;
- sandbox programming pipeline;
- recovery/idempotency;
- candidate isolation B31-B37;
- B38 runner contract;
- paquete LAB;
- zero-API boundaries;
- no-production/no-merge/no-purchase boundaries.

Último CI canónico: **SUCCESS**.

### NO se debe afirmar aún

A fecha de este checkpoint no existe evidencia compartida confirmada de:

- `BROWSER_FIELD_VERIFIED=true` en Windows físico;
- B14 físico PASS definitivo;
- B18 físico PASS definitivo;
- B20 físico PASS definitivo;
- B29/B30 físico PASS definitivo;
- B38 ejecutado físicamente con éxito.

Por tanto:

**B38 sigue bloqueado hasta B29/B30 físico PASS del mismo trial.**

## 9. Estado de RESTART_GATE

El reinicio del navegador entre turnos se separó de la primera campaña funcional.

Motivo:

- no es necesario para demostrar la capacidad básica;
- introducía ruido y aperturas innecesarias;
- había fallado físicamente aunque el acceso a sesión funcionaba.

Política:

- no bloquea la primera campaña funcional;
- debe repararse/verificarse antes de considerar estable la resiliencia de navegador.

## 10. Próximo movimiento canónico

NO añadir nuevas capas generales antes de validar el flujo físico actual.

Siguiente acción:

1. construir/publicar el LAB desde el HEAD canónico actual;
2. usuario ejecuta `EJECUTAR_PRIMERA_PRUEBA_CEO_BROWSER.cmd`;
3. confirmar BUILD ID correcto;
4. ejecutar un único trial;
5. si falla, inspeccionar exclusivamente `FIELD_CAMPAIGN_RESULT.json` del trial actual;
6. corregir la causa física concreta;
7. si B14+B18+B20+B29/B30 pasan en el mismo trial -> `BROWSER_FIELD_VERIFIED=true`;
8. entonces ejecutar `EJECUTAR_B38_CANDIDATE.cmd`;
9. después validar físicamente otros proveedores del pool: Claude, Gemini, Perplexity y Grok.

## 11. Regla de sincronización entre chats

Todo chat que vaya a trabajar en CEO browser-first debe, antes de modificar nada:

1. leer `ceo-browser/CEO_MASTER_CHECKPOINT_CURRENT.md`;
2. comprobar el HEAD real de `free-browser-ai-worker`;
3. si hay commits posteriores al HEAD de implementación que modifiquen código/configuración operativa, reconstruir el estado desde ellos; ignorar para este cálculo commits que sólo actualicen el checkpoint/protocolo de sincronización;
4. no continuar desde una lista o build recordada por el chat si contradice el repo;
5. actualizar este checkpoint al cerrar un hito significativo;
6. nunca marcar una prueba física como verificada sólo porque CI esté verde.

## 12. Separación de otros proyectos

Este checkpoint se refiere únicamente a **CEO Windows/browser-first**.

No implica cambios en:

- Radar de inversión / REAL_TRADING;
- Android;
- producción estable;
- updater estable;
- investigación térmica;
- libro.

Radar mantiene su regla firme:

`REAL_TRADING = OFF`

## W1–W5 AUDIT STATUS

Auditoría previa a candidata única Windows, iniciada 2026-09-23.

- **W1 — candidata base:** CLOSED
  - core 1.5.92 DEV316
  - browser-first canónico c210b931
  - bridge mínimo, no overlay completo
  - stable updater channel congelado

- **W2 — inventario del paquete:** CLOSED
  - seis rutas browser de producción delimitadas
  - scheduler/core 1.5.92 protegidos contra overwrite antiguo
  - driver/recipe antiguos excluidos

- **W3 — arranque/single-instance:** CLOSED / SOURCE PASS
  - un backend/scheduler
  - dead current.json fallback
  - nested launcher loop protegido
  - health + productive smoke + rollback heredados
  - posible segunda ventana UI queda como validación física no bloqueante

- **W4 — Goal Engine finito:** CLOSED / SOURCE PASS
  - single-file compacto = 3 hojas
  - baseline general = 24 hojas
  - cierre requiere evidencia real
  - el merge final NO puede reintroducir bloqueo de creación por caída de proveedor

- **W5 — scheduler/dependencias:** CLOSED / SOURCE PASS
  - retry y quality lineage acotados
  - provider wait no consume recovery budget
  - closure single-artifact max 4 generaciones; general max 24
  - deterministic completion suprime auditorías una vez probado el trabajo
  - no se detecta necesidad de nuevo parche del scheduler antes de prueba física

Fuentes de auditoría:
- `W1_BASE_CANDIDATE_AUDIT.md`
- `W2_PACKAGE_INVENTORY_AUDIT.md`
- `W3_STARTUP_SINGLE_INSTANCE_AUDIT.md`
- `W4_GOAL_ENGINE_FINITE_AUDIT.md`
- `W5_SCHEDULER_DEPENDENCY_AUDIT.md`

**No se ha generado instalador ni se ha modificado el canal stable.**
**No se afirma validación física Windows.**

Siguiente bloque canónico:
**W6 — auditoría de finalización real / anti-99 %.**

## W6 AUDIT STATUS

**W6 — finalización real / anti-99:** CLOSED — BUG FOUND, FIXED, REGRESSION GREEN

Hallazgo:
- 1.5.92 podía alcanzar cierre determinista y 100 %, pero al reabrir `migrate_invalid_legacy_pass()` podía invalidarlo por `continuity_rounds:0<3`, borrar `completed_at` y volver `goal_audit_passed=false`.

Corrección:
- revalidar el certificado determinista actual antes de aplicar migración legacy;
- recomputar contra evidencia durable;
- exigir coincidencia del hash guardado, persistido y recomputado;
- si evidencia cambia o un gate deja de cumplirse, el proyecto sí se reabre.

Evidencia:
- raw 1.5.92 regression reprodujo el fallo;
- patched regression: PASS;
- display progress final: 100 %;
- restart/reopen persistence: PASS;
- evidence tamper reopens: PASS;
- missing deliverable blocks: PASS;
- field/endurance remains non-bypassable: PASS;
- package contract hash refreshed: PASS;
- Windows canonical CI W6 step: PASS;
- B02 scope guard posterior: PASS.

Archivos:
- `W6_ANTI99_COMPLETION_AUDIT.md`
- `apply_w6_completion_persistence.py`
- `w6_anti99_regression.py`
- regresión integrada en `.github/workflows/test-free-browser-ai-worker.yml`

No se generó instalador.
No se modificó el canal stable.
Validación física del PC del usuario sigue pendiente.

Siguiente bloque canónico:
**W7 — anti-recovery-loop / productividad real**, salvo que el usuario indique otro punto.

## W7 AUDIT STATUS

**W7 — anti-recovery-loop / productividad real:** CLOSED — BUG FOUND, FIXED, WINDOWS CI GREEN

Hallazgo:
- 1.5.92 limitaba retries por tarea pero NO el linaje de reemplazos productivos;
- `BlockedUnitRebuilderV2` incrementaba `stall_replan_generation`;
- `ProductiveFallbackOrchestratorV1` podía crear A → A' → A'' → A''' → A''''... sin máximo.

Corrección:
- máximo por defecto: 3 generaciones productivas de replanteo;
- al agotarlo: 0 reemplazos, `blocked_safe`, reason `productive_replan_lineage_exhausted`;
- watchdog queda BLOQUEADO de forma estable en vez de fabricar actividad falsa;
- debajo del límite sigue permitiendo un cambio real de estrategia.

Evidencia:
- raw 1.5.92 reprodujo generación 4;
- parche evita generación 4;
- dos ticks de watchdog no recrean tarea;
- serialización/reapertura no reanima el linaje;
- provider wait no consume ni crea recuperación;
- package hash actualizado;
- suite canónica Windows completa: SUCCESS.

Archivos:
- `W7_RECOVERY_PRODUCTIVITY_AUDIT.md`
- `apply_w7_recovery_lineage_cap.py`
- `w7_recovery_lineage_regression.py`
- regresión integrada en `.github/workflows/test-free-browser-ai-worker.yml`

Suite canónica:
- commit: `567f4091432f7cb7af24352e24445e6dbdcde0dc`
- run: `35845102577`
- job: `107129243402`
- conclusion: SUCCESS

No se generó instalador.
No se modificó el canal stable.
Validación física del PC del usuario sigue pendiente.

Siguiente bloque canónico:
**W8 — productividad real / actividad útil vs control**, salvo indicación distinta del usuario.

## W8 AUDIT STATUS

**W8 — productividad real / control-plane no cuenta como trabajo útil:** CLOSED — BUG FOUND, FIXED, CANONICAL WINDOWS CI GREEN

Hallazgo:
- 1.5.92 podía mostrar 65.3 % de progreso visible con solo 25 % de trabajo productivo real;
- la diferencia aparecía al añadir gran cantidad de auditorías/recoveries/control sin cambiar ninguna tarea productiva;
- causa raíz: `StableProgressTracker` usaba `state.progress` (grafo bruto) como fallback legacy cuando no existía `stable_progress_v1.display_progress` explícito.

Corrección:
- sin display legacy explícito, el fallback visible pasa a ser exclusivamente el `batch_progress` productivo;
- un high-water legacy explícito sí se conserva;
- controles, recoveries y heartbeats permanecen diagnósticos pero no mueven el porcentaje productivo.

Evidencia raw:
- run `35846649444`
- job `107134311632`
- bug reproducido: base 25.0 %, contaminado 65.3 %.

Evidencia corregida:
- run `35847046154`
- job `107135591324`
- conclusion SUCCESS;
- base 25.0 %, contaminado 25.0 %;
- control-only transition no mueve progreso ni timestamp productivo;
- recoveries/heartbeats no mueven progreso;
- controls-only = 0 % productivo;
- package hash actualizado.

Suite canónica compuesta:
- commit funcional `34d4200e520506c700caa1aed3bea07453d01987`
- run `35851753709`
- job `107150833286`
- conclusion SUCCESS;
- aplica W6 + W7 + W8 sobre el mismo root y después pasa browser-first completo.

Archivos:
- `W8_PRODUCTIVITY_TRUTH_AUDIT.md`
- `apply_w8_productivity_truth_fix.py`
- `w8_productivity_truth_regression.py`
- regresión integrada en `.github/workflows/test-free-browser-ai-worker.yml`

Workflow temporal W8 eliminado.
No se generó instalador.
No se modificó el canal stable.
Validación física del PC del usuario sigue pendiente.

Siguiente bloque canónico:
**W9 — tarea local finita sin IA**, salvo indicación distinta del usuario.

