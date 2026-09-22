# CEO DE IAs — MASTER CHECKPOINT CURRENT

**Fecha:** 2026-09-22  
**Proyecto:** CEO de IAs — Windows / browser-first / no-API  
**Repositorio:** `danisuarezinef-ai/investment-intelligence-radar`  
**Rama canónica de esta línea:** `free-browser-ai-worker`  
**HEAD verificado:** `c210b93167361b3ff4017368ac2d790fca8de5b3`  
**Workflow canónico:** `35699881577` — **SUCCESS**

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
3. si HEAD > checkpoint, reconstruir el estado desde commits recientes;
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
