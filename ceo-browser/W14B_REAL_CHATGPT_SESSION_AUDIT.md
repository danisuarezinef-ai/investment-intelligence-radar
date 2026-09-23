# W14-B — Sesión real ChatGPT / cierre-reapertura / cero APIs

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** READY FOR PHYSICAL — RUNNER + PORTABLE LAB CANONICAL CI GREEN  
**Validación física en el PC del usuario:** PENDIENTE  
**ChatGPT real del usuario:** PENDIENTE

## Objetivo

Certificar físicamente, en el Windows del usuario y contra `https://chatgpt.com/`, que el Browser Worker:

1. usa el perfil exclusivo/persistente endurecido en W14-A;
2. admite únicamente login manual legítimo cuando sea necesario;
3. no intenta saltarse CAPTCHA ni 2FA;
4. realiza un turno real;
5. cierra el navegador controlado;
6. relanza Chrome/Edge usando el mismo perfil;
7. continúa en la misma conversación;
8. mantiene la sesión válida tras el cierre/reapertura;
9. usa cero llamadas API y cero llamadas API de pago.

W14-B **no puede declararse CLOSED desde CI** porque la evidencia que falta es necesariamente física y depende de la sesión real del usuario en chatgpt.com.

## Reutilización, no duplicación

Ya existía:

`ceo-browser/run_browser_restart_gate.ps1`

Ese runner ya implementaba:
- preparación de sesión persistente;
- turno 1;
- `CloseBrowserAfter`;
- relanzamiento;
- turno 2;
- misma conversation URL;
- 0 APIs.

W14-B no ha creado un segundo motor de reinicio. Se reutiliza ese runner como núcleo y se añade únicamente un wrapper consolidado.

## Gate oficial W14-B

Nuevo archivo:

`ceo-browser/run_w14b_real_session_gate.ps1`

Secuencia:

1. `open_chatgpt_profile.ps1`
   - perfil exclusivo;
   - login manual legítimo si se requiere;
   - `SESSION_READY`.

2. Verificación de:
   - `CEO_BROWSER_PROFILE.json`;
   - `exclusive_profile=true`;
   - sesión inicial lista.

3. `run_browser_restart_gate.ps1`
   - turno real 1;
   - cierre del navegador;
   - relanzamiento;
   - turno real 2;
   - misma conversación;
   - `api_calls=0`;
   - `paid_api_calls=0`.

4. Probe final:
   - nueva reapertura;
   - `SESSION_READY`;
   - cierre limpio.

Solo entonces escribe:

`W14B_REAL_CHATGPT_SESSION_PASS`

y:

- `real_chatgpt_verified=true`;
- `windows_physical_verified=true`.

En cualquier error escribe:

`W14B_REAL_SESSION_PENDING_OR_FAILED`

con ambas verificaciones físicas en false.

## Lanzador de una sola acción

`ceo-browser/EJECUTAR_W14B_SESION_REAL.cmd`

El usuario no necesita invocar manualmente scripts internos.

El lanzador ejecuta únicamente:

`run_w14b_real_session_gate.ps1`

No:
- instala una nueva versión;
- modifica `stable`;
- modifica `current.json`;
- hace commit/push/merge;
- compra créditos;
- usa APIs.

## Límites de autenticación

La receta real:

`ceo-browser/recipes/chatgpt_web.json`

mantiene:

- `manual_login_allowed=true`;
- `no_captcha_bypass=true`;
- `no_2fa_bypass=true`;
- `no_purchase=true`;
- `no_subscription_change=true`.

W14-B no introduce ningún bypass.

## LAB portátil

El builder:

`ceo-browser/build_first_trial_lab.py`

incluye ahora:

- `ceo_core/browser_ai/run_w14b_real_session_gate.ps1`;
- `EJECUTAR_W14B_SESION_REAL.cmd`.

La validación canónica demostró que ambas rutas están realmente dentro del LAB producido.

## Regresión de contrato

Archivo:

`ceo-browser/w14b_real_session_regression.py`

Comprueba:

- reutilización del restart gate existente;
- presencia del helper de perfil y driver;
- receta real `https://chatgpt.com/`;
- cierre/reapertura;
- misma conversación;
- sesión pre y post restart;
- 0 APIs;
- límites CAPTCHA/2FA;
- ausencia de promoción/acciones Git en el lanzador;
- inclusión real en el builder del LAB;
- que los flags de validación física solo aparecen en la ruta de éxito después de las comprobaciones.

Marca:

`W14B_REAL_SESSION_RUNNER_CONTRACT_PASS`

## Evidencia canónica CI

Commit funcional más reciente:

`1b21720dcf5d0bb5aca2a2cef90fd5eef63b2c84`

Workflow run:

`35907419265`

Job:

`107338467485`

Conclusion:

**SUCCESS**

Marcas:

- `W14B_REAL_SESSION_RUNNER_CONTRACT_PASS`
- `W14B_REAL_SESSION_RUNNER_CANONICAL_PASS`
- `FIRST_TRIAL_PORTABLE_LAB_PASS`
- `CEO_AI_TRANSPORT_BROWSER_ZERO_API_PASS`
- `FREE_BROWSER_BOUNDARY_PASS`

También pasaron de nuevo:
- W6;
- W7;
- W8;
- W9;
- W10;
- W11;
- W12;
- W13;
- W14-A;
- B02;
- browser-first;
- B03-B38;
- Gate 0.

## Evidencia física que falta

Todavía NO existe un archivo real del PC del usuario con:

`status=W14B_REAL_CHATGPT_SESSION_PASS`

Por tanto:

- `WINDOWS_PHYSICAL_VERIFIED=false/pending`;
- `REAL_CHATGPT_VERIFIED=false/pending`.

La prueba pendiente es única y explícita:

doble clic en:

`EJECUTAR_W14B_SESION_REAL.cmd`

dentro del LAB físico correspondiente.

La salida esperada se guarda en:

`%LOCALAPPDATA%\CEO de IAs\evidence\W14B_REAL_CHATGPT_SESSION.json`

## Dictamen

**RUNNER W14-B:** PASS CI  
**LANZADOR DE UNA ACCIÓN:** PASS CI  
**REUTILIZA MOTOR DE RESTART EXISTENTE:** PASS  
**PERFIL W14-A:** PASS  
**CI NO PUEDE AUTOATRIBUIRSE VALIDACIÓN FÍSICA:** PASS  
**LAB CONTIENE W14-B:** PASS  
**0 API CONTRACT:** PASS  
**NO CAPTCHA/2FA BYPASS:** PASS  
**SUITE CANÓNICA:** PASS  
**PRUEBA REAL chatgpt.com EN PC USUARIO:** PENDIENTE  
**W14-B CLOSED:** NO, hasta evidencia física  
**INSTALADOR GENERADO:** NO  
**CANAL stable MODIFICADO:** NO
