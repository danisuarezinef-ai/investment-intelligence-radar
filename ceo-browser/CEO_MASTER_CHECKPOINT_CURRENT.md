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

## W9 AUDIT STATUS

**W9 — tarea local finita sin IA externa:** CLOSED — MULTIPLE BUGS FOUND, FIXED, CANONICAL WINDOWS CI GREEN

Resultado:
- objetivo: `Crea CEO_LOCAL_W9.txt. Debe contener exactamente: CEO_LOCAL_W9_OK`
- archivo real creado y modificado en workspace;
- SHA-256 final: `3efcdd70d048b516b02a66eabd0400ae90ac3bef11cf293467c0d14db47c47e1`;
- providers: `ceo-local-goal-lock` + `ceo-local-finite-file`;
- API keys ausentes;
- coste total: 0.0;
- Final audit local = COMPLETE;
- `CEO_VERIFY verdict=pass confidence=1.0`;
- `goal_audit_passed=true`;
- `completed_at` persistido;
- display progress = 100;
- productive pending = 0;
- reapertura mantiene certificado, cierre y 100 %.

Bugs reales corregidos:
1. goal-lock determinista tratado como trabajo productivo y sometido a verificación externa;
2. verificación genérica duplicaba el Final audit local;
3. `RecoveryBudgetGuardV1` podía superseder verificaciones legítimas al tratarlas como churn interno;
4. el Final audit local devolvía `CEO_RESULT` pero no el contrato requerido `CEO_VERIFY`.

Correcciones de harness, no runtime:
- dependencias CI `psutil/httpx`;
- `CheckpointStore` abstracto;
- métrica de coste migrada a `CostEngine.spent(state)`.

Evidencia focal:
- run: `35861150095`
- job: `107181407132`
- conclusion: SUCCESS

Documento:
- `W9_LOCAL_FINITE_TASK_AUDIT.md`

Integración:
- step W9 acumulativo integrado en `.github/workflows/test-free-browser-ai-worker.yml`;
- workflows temporales W9 eliminados.
- suite canónica completa: commit `6dc2a82fcd2adba1b0669c0c871b79a0a6d82d09`, run `35861315876`, job `107181951798`, **SUCCESS**.

No se ha generado instalador.
No se ha modificado el canal stable.
Validación física del PC del usuario sigue pendiente.

Siguiente bloque canónico:
**W10 — persistencia/reinicio durante una tarea finita en curso**, salvo indicación distinta.

## W10 AUDIT STATUS

**W10 — persistencia/reinicio durante una tarea finita:** CLOSED — BUG FOUND, FIXED, CANONICAL WINDOWS CI GREEN

Hallazgo:
- `ResumeCoordinator` recuperaba un RUNNING huérfano como RETRY y limpiaba `worker_id`;
- pero dejaba vivo el lease persistido de la sesión muerta;
- `WorkerLifecycleV2.claim()` detectaba `task_already_leased`;
- la tarea recuperada terminaba bloqueada por `worker_lease_collision_v2`.

Corrección:
- al clasificar `safe_retry_after_interruption`, se libera también el lease durable;
- `release_reason=restart_interrupted_worker`;
- se libera la copia de task metadata;
- `worker_lease_recovered_v2=true`;
- no se modifican TTL normales, límites W7 ni política de efectos externos ambiguos.

Evidencia:
- clean stop durante RUNNING → RETRY durable;
- mismo Execution task ID tras reanudación;
- crash snapshot RUNNING → RETRY;
- stale lease released=true;
- archivo parcial sobrescrito por contenido final correcto;
- Final audit PASS;
- completed_at + 100 %;
- sin hojas duplicadas;
- package hash `operational_resilience.py` verificado.

Archivos:
- `W10_INFLIGHT_RESTART_AUDIT.md`
- `apply_w10_restart_lease_fix.py`
- `w10_inflight_restart_regression.py`

Suite canónica:
- commit: `02723bf4d0f2d51d118dd463137b03eb1f2bc28e`
- run: `35863310519`
- job: `107188575693`
- conclusion: SUCCESS

Workflows temporales W10 eliminados.
No se generó instalador.
No se modificó el canal stable.
Validación física del PC del usuario sigue pendiente.

Siguiente bloque canónico:
**W11 — idempotencia y reejecución segura de tareas finitas con side effects locales**, salvo indicación distinta del usuario.

## W11 AUDIT STATUS

**W11 — idempotencia y reejecución segura de efectos locales:** CLOSED — BUG FOUND, FIXED, CANONICAL WINDOWS CI GREEN

Hallazgo:
- tras un checkpoint antiguo, una Execution ya materializada volvía a escribir físicamente draft + final;
- raw: 2 escrituras nuevas y mtime modificado aunque el archivo final ya era exacto.

Corrección:
- provider detecta contenido final ya exacto y no reemite el draft;
- scheduler convierte el write idéntico en noop físico y reconstruye artefacto/evidencia;
- misma evidencia task/ref/SHA no se duplica;
- IDs de artefacto ya registrados no se duplican.

Evidencia:
- raw: `W11_RAW_DUPLICATE_SIDE_EFFECT_REPRODUCED`;
- corregido: physical_writes=0, mtime_changed=false, idempotent_noops=1;
- target corrupto: sí se repara con escrituras físicas;
- hashes de package contract verificados.

Archivos:
- `W11_LOCAL_IDEMPOTENCY_AUDIT.md`
- `apply_w11_local_idempotency.py`
- `w11_local_idempotency_regression.py`

CI focal:
- run `35865768272`
- job `107196824131`
- SUCCESS

Suite canónica:
- commit `a576047b788e82a762fbd29271d905d4205fca9e`
- run `35866004082`
- job `107197622430`
- SUCCESS

Workflow temporal W11 eliminado.
No se generó instalador.
No se modificó el canal stable.
Validación física del PC del usuario sigue pendiente.

Siguiente bloque canónico:
**W12 — pausa / reanudar / cancelar**, salvo indicación distinta del usuario.



## W12 AUDIT STATUS

**W12 — pausa / reanudar / cancelar:** CLOSED — 2 BUGS FOUND, FIXED, CANONICAL WINDOWS CI GREEN

Hallazgo 1:
- la pausa de operador solo escribía `state.paused=true`;
- impedía nuevos dispatches, pero no detenía un worker ya RUNNING;
- regresión raw: `side_effect_exists=true`, `stop_calls=0`, task seguía `running`.

Hallazgo 2:
- un proyecto pausado sobrevivía correctamente un reinicio;
- pero `Reanudar` después del reinicio quitaba `paused` sin recrear el scheduler;
- regresión raw: `paused=false`, `scheduler_created=false`.

Corrección:
- pausa persiste primero la intención y usa `_stop_scheduler(timeout_seconds=4.0)` como límite restart-safe;
- RUNNING seguro vuelve a RETRY y el worker en memoria se cancela;
- pausa queda durable y scheduler queda desmontado;
- reanudar reconstruye router + `ContinuousScheduler` y lo arranca cuando no existe scheduler;
- un proyecto cancelado no puede reanudarse;
- la cancelación existente fue auditada y ya era terminal: pendientes → SUPERSEDED, autonomía OFF, proyecto deja de ser activo y no revive en restart.

Evidencia focal:
- run `35871271712`
- job `107215680970`
- SUCCESS
- `W12_RAW_PAUSE_RESUME_BUGS_REPRODUCED`
- `W12_PATCHED_PAUSE`
- `W12_PATCHED_RESUME`
- `W12_CANCEL_TERMINAL`
- `W12_PAUSE_RESUME_CANCEL_REGRESSION_PASS`

Package hash:
- `scripts/ceo_stdlib_work_mode.py`
- `7293caba77e25d3f25e8ac30e8b7710d648fba3247bccb07e5aede3f0538f8e8`

Suite canónica W6-W12:
- commit `1cd786f75bb88292a38b4c96156a48135a7f027f`
- run `35871576483`
- job `107216714929`
- conclusion SUCCESS
- W12 + B02 + browser-first + B03-B38 + Gate 0 + LAB + zero-API boundaries: PASS.

Archivo:
- `W12_OPERATOR_CONTROL_AUDIT.md`
- `apply_w12_operator_control.py`
- `w12_pause_resume_cancel_regression.py`

Los workflows temporales W12 se eliminaron después de integrar el gate canónico.
No se generó instalador.
No se modificó el canal stable.
Validación física del PC del usuario sigue pendiente.

Siguiente bloque canónico:
**W13**, manteniendo la secuencia de auditoría Windows y sin adelantar la instalación.


## W13 AUDIT STATUS

**W13 — Browser Worker actual:** CLOSED — 2 INTEGRATION GAPS FOUND, FIXED, CANONICAL WINDOWS CI GREEN

Definición recuperada:
- integrar/auditar exclusivamente el Browser Worker canónico del estado `c210b93167361b3ff4017368ac2d790fca8de5b3`;
- descartar como fuente de producción las copias antiguas de `dev313-inspect-routing/browser_ai`.

Hallazgo 1:
- la candidata acumulada W6→W12 sobre 1.5.92 no contenía `ceo_core/browser_ai` ni `ceo_core/providers/chatgpt_web.py`;
- tampoco tenía `ChatGPTWebTransport` integrado en el work mode;
- marca: `W13_RAW_BROWSER_WORKER_GAP_REPRODUCED`.

Hallazgo 2:
- `build_browser_first_lab.py` seguía copiando driver/perfil/receta desde el snapshot histórico del bridge;
- driver antiguo SHA-256: `03938ad0a943154611e775264c928d41bf37cbdf697de930ffdb16a6f4487662`;
- recipe antigua SHA-256: `cd4847432d1048a2083636bc8d74ec7cf140e067843fda54b2ac83a106b6c107`;
- el builder ahora usa `ceo-browser` como única fuente de esas piezas.

Integración W13:
- `ceo_core/routing.py`;
- `ceo_core/providers/chatgpt_web.py`;
- merge browser-only sobre `scripts/ceo_stdlib_work_mode.py`;
- `ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1`;
- `ceo_core/browser_ai/open_chatgpt_profile.ps1`;
- `ceo_core/browser_ai/recipes/chatgpt_web.json`.

Identidad c210 verificada:
- driver blob actual = c210 = `7bf89f3441861360b49ed1f98b08384e24d453df`;
- profile blob actual = c210 = `202b43d1d6b83645df2d6e239d319c14aff95001`;
- recipe blob actual = c210 = `eac61a5dd8e2d233f1872db81f176d101f519454`.

Hashes de candidata W13:
- routing: `9fcdfd242128e759e7d66820bfa8f188dba55ccb7a1fc5287e0f3f39b6c23c43`;
- provider: `02c7089106f8f984b5c6ae8a339e10106c172de75f0cd3bd22afcb527f94f076`;
- driver: `bfbb01eb528f08c0db586d0adb55078a109690ffcf6516c641a131d86974e9bb`;
- profile: `7ff3a1fc30eaab0fed4f1dcf06f79bfe1ab751a4f5f48d02af6435178d226cd6`;
- recipe: `c4b615480d3dedbfaaebf17cdcd7f2fc18e7790e183687e7934d77ba9d4ee82b`;
- work mode acumulado: `9b955619b59260b55e3b11cda9c82756940511d64e3cf6d70807f07ce0a860f8`.

Semántica:
- Browser Worker es la superficie IA externa normal;
- API sigue siendo opcional detrás de `CEO_ALLOW_OPTIONAL_API`;
- el arranque normal no solicita Gemini key;
- una indisponibilidad browser no debe destruir/bloquear el core local ni impedir persistir trabajo;
- no se copió entero el work-mode antiguo.

Contrato del paquete:
- las seis rutas W13 están cubiertas por `CEO_UPDATE_PACKAGE.json.file_hashes`;
- 1.5.92 tiene `required_files=null`; W13 no inventa un esquema nuevo.

Evidencia focal:
- run `35884246546`
- job `107260198219`
- SUCCESS
- `W13_CANONICAL_BROWSER_WORKER_REGRESSION_PASS`
- `W13_PACKAGED_BROWSER_TWO_TURN_ZERO_API_PASS`
- `W13_WINDOWS_CI_PASS`.

La prueba focal utilizó el Browser Worker ya incluido en la candidata W13:
- Chrome/CDP: PASS;
- dos turnos: PASS;
- misma conversation URL: PASS;
- `api_calls=0`: PASS;
- `paid_api_calls=0`: PASS.
Se ejecutó contra harness web local; NO equivale todavía a ChatGPT real del usuario.

Suite canónica W6→W13:
- commit `728b75dbcccd1ce5d51b401cf83a33badffb08ed`
- run `35884483679`
- job `107261018379`
- conclusion SUCCESS
- 54 pasos completados.
- marcas: `W13_CANONICAL_BROWSER_WORKER_PASS`, `B02_SCOPE_FREEZE_PASS`, `CEO_AI_TRANSPORT_BROWSER_ZERO_API_PASS`, `FREE_BROWSER_BOUNDARY_PASS`.

Archivos persistentes W13:
- `apply_w13_canonical_browser_worker.py`;
- `w13_browser_worker_regression.py`;
- `W13_CANONICAL_BROWSER_WORKER_AUDIT.md`;
- gate W13 integrado en `test-free-browser-ai-worker.yml`;
- `build_browser_first_lab.py` corregido para fuente browser canónica.

Los workflows temporales W13 fueron eliminados tras la prueba focal.

No se generó instalador.
No se modificó el canal stable.
Validación física del PC del usuario pendiente.
Login/sesión real ChatGPT pendiente.

Siguiente bloque canónico:
**W14 — perfil Chrome persistente / sesión real.**


## W14-A AUDIT STATUS

**W14-A — perfil Chrome persistente / propiedad de sesión:** CLOSED — BUG REAL REPRODUCIDO, FIXED, FOCAL Y CI CANÓNICA GREEN

W13 estaba ya CLOSED y no se rehizo.

Hallazgo real:
- un puerto CDP activo podía ser reutilizado sin demostrar que el proceso pertenecía al ProfileDir solicitado;
- reproducción raw: Chrome señuelo con un perfil distinto fue aceptado por el driver pre-W14;
- marca: W14A_RAW_CROSS_PROFILE_ATTACHMENT_REPRODUCED.

Corrección:
- el driver verifica ownership mediante proceso + remote-debugging-port + user-data-dir;
- si el puerto está activo pero el perfil no coincide, falla cerrado con BROWSER_PROFILE_OWNERSHIP_CONFLICT;
- no navega, no poda pestañas y no cierra el navegador ajeno.

Hardening adicional:
- user-data-dir protegido para rutas con espacios;
- prueba explícita con ruta CEO de IAs;
- marker CEO_BROWSER_PROFILE.json se revalida en cada uso;
- owner, exclusividad, provider, ruta y no-api se restauran si el marker está viejo/corrupto;
- sesión de harness sobrevive cierre y reapertura del mismo perfil;
- perfil nuevo sigue devolviendo LOGIN_REQUIRED;
- no_captcha_bypass=true;
- no_2fa_bypass=true;
- manual_login_allowed=true.

Evidencia focal:
- run 35899237018
- job 107310848807
- SUCCESS
- W14A_FOREIGN_PROFILE_REJECTED
- W14A_SPACED_PROFILE_OWNERSHIP_PASS
- W14A_SESSION_PERSISTENCE_AND_MARKER_REPAIR_PASS
- W14A_LOGIN_BOUNDARY_PASS
- W14A_WINDOWS_CI_PASS

Hashes de candidata:
- driver: 52f3f8176a3779d5989150b25c0b185087a1bed4cbc0fb800484021fab4a29fe
- profile helper: 3f5dfb64dde62c99bbe48f9fef8d4df17b1bedb43983683501e92d09385e89e1

Suite canónica:
- commit c48c93f236237f627f564bb07540fa7115d65b54
- run 35899549270
- job 107311902465
- conclusion SUCCESS
- W14A_PROFILE_CONTRACT_CANONICAL_PASS
- W14A_PROFILE_OWNERSHIP_CANONICAL_PASS
- B02_SCOPE_FREEZE_PASS
- CEO_AI_TRANSPORT_BROWSER_ZERO_API_PASS
- FREE_BROWSER_BOUNDARY_PASS

Archivos:
- W14A_PERSISTENT_PROFILE_AUDIT.md
- w14a_profile_persistence_regression.py
- gates W14-A integrados en test-free-browser-ai-worker.yml

Workflow focal temporal W14-A eliminado tras la evidencia verde.
No se generó instalador.
No se modificó stable.

**W14-B permanece pendiente.**
Debe probar físicamente en el PC del usuario la sesión real chatgpt.com: login manual legítimo, cierre/reapertura, sesión persistente e interacción real Browser Worker con cero APIs y sin bypass de CAPTCHA/2FA.


## W14-B AUDIT STATUS

**W14-B — sesión real ChatGPT / cierre-reapertura / cero APIs:** READY FOR PHYSICAL — RUNNER + PORTABLE LAB CANONICAL CI GREEN

W14-A estaba CLOSED y no se rehizo.

Infraestructura reutilizada:
- `run_browser_restart_gate.ps1` sigue siendo el motor de cierre/reapertura;
- W14-B no duplica esa lógica.

Nuevo gate consolidado:
- `run_w14b_real_session_gate.ps1`;
- prepara sesión con `open_chatgpt_profile.ps1`;
- exige `SESSION_READY` inicial;
- ejecuta el restart gate;
- exige navegador cerrado y relanzado;
- exige misma conversación;
- exige `api_calls=0` y `paid_api_calls=0`;
- realiza probe final y exige `SESSION_READY` después del reinicio;
- solo entonces puede emitir `W14B_REAL_CHATGPT_SESSION_PASS`, `real_chatgpt_verified=true` y `windows_physical_verified=true`;
- cualquier fallo deja estado `W14B_REAL_SESSION_PENDING_OR_FAILED` y verificación física false.

Lanzador:
- `EJECUTAR_W14B_SESION_REAL.cmd`;
- una sola acción;
- no instala;
- no toca stable/current.json;
- no hace commit/push/merge;
- no usa APIs;
- no compra nada.

Autenticación:
- login manual legítimo permitido;
- `no_captcha_bypass=true`;
- `no_2fa_bypass=true`;
- `no_purchase=true`;
- `no_subscription_change=true`.

LAB:
- `build_first_trial_lab.py` incluye realmente:
  - `ceo_core/browser_ai/run_w14b_real_session_gate.ps1`;
  - `EJECUTAR_W14B_SESION_REAL.cmd`.

Regresión:
- `w14b_real_session_regression.py`;
- marca `W14B_REAL_SESSION_RUNNER_CONTRACT_PASS`.

Suite canónica:
- commit funcional `1b21720dcf5d0bb5aca2a2cef90fd5eef63b2c84`;
- run `35907419265`;
- job `107338467485`;
- conclusion SUCCESS;
- marcas:
  - `W14B_REAL_SESSION_RUNNER_CONTRACT_PASS`;
  - `W14B_REAL_SESSION_RUNNER_CANONICAL_PASS`;
  - `FIRST_TRIAL_PORTABLE_LAB_PASS`;
  - `CEO_AI_TRANSPORT_BROWSER_ZERO_API_PASS`;
  - `FREE_BROWSER_BOUNDARY_PASS`.

Documento:
- `W14B_REAL_CHATGPT_SESSION_AUDIT.md`.

**Estado físico:**
- NO existe todavía evidencia real `W14B_REAL_CHATGPT_SESSION_PASS` procedente del PC del usuario;
- `WINDOWS_PHYSICAL_VERIFIED` permanece pending/false;
- `REAL_CHATGPT_VERIFIED` permanece pending/false;
- W14-B NO se declara CLOSED todavía.

Prueba física pendiente:
- doble clic en `EJECUTAR_W14B_SESION_REAL.cmd` dentro del LAB físico;
- evidencia esperada:
  `%LOCALAPPDATA%\CEO de IAs\evidence\W14B_REAL_CHATGPT_SESSION.json`.

No se generó instalador.
No se modificó stable.
