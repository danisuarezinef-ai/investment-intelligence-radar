# W13 — Browser Worker actual / integración canónica

**Fecha:** 2026-09-23  
**Ámbito:** CEO Windows únicamente  
**Estado:** CLOSED — 2 INTEGRATION GAPS FOUND, FIXED, CANONICAL WINDOWS CI GREEN  
**Validación física en el PC del usuario:** pendiente  
**ChatGPT web real del usuario:** no certificado en W13

## Objetivo

Integrar en la candidata acumulada W6→W12 el Browser Worker browser-first definido como canónico en W1/W2, usando el estado:

`c210b93167361b3ff4017368ac2d790fca8de5b3`

y excluyendo expresamente las copias históricas de:

`ceo-updates/dev313-inspect-routing/browser_ai`

W13 no certifica todavía login/sesión real de ChatGPT ni una tarea real en chatgpt.com. Eso pertenece a los bloques siguientes.

## Hallazgo 1 — la candidata W6→W12 no contenía Browser Worker

La inspección de la candidata acumulada sobre:

`CEO_1.5.92-rc1-native-transport-integrity.zip`

confirmó que faltaban:

- `ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1`
- `ceo_core/browser_ai/open_chatgpt_profile.ps1`
- `ceo_core/browser_ai/recipes/chatgpt_web.json`
- `ceo_core/providers/chatgpt_web.py`

Además, `scripts/ceo_stdlib_work_mode.py` no tenía:

- `ChatGPTWebTransport`;
- `primary_ai_surface`;
- Browser Worker en el router.

Por tanto W6–W12 habían endurecido correctamente el core, pero todavía no habían realizado la integración browser-first definida en W1/W2.

Marca de reproducción:

`W13_RAW_BROWSER_WORKER_GAP_REPRODUCED`

## Hallazgo 2 — builder histórico podía empaquetar Browser Worker obsoleto

`ceo-browser/build_browser_first_lab.py` seguía tomando driver/perfil/receta desde:

`ceo-updates/dev313-inspect-routing/browser_ai`

Eso era incorrecto según W1/W2 porque el snapshot del bridge no es la fuente canónica del Browser Worker.

Diferencias demostradas:

### Driver

Canónico SHA-256:

`bfbb01eb528f08c0db586d0adb55078a109690ffcf6516c641a131d86974e9bb`

Copia antigua SHA-256:

`03938ad0a943154611e775264c928d41bf37cbdf697de930ffdb16a6f4487662`

El driver canónico contiene, entre otras garantías ausentes en la copia antigua:

- `Wait-DevToolsDown`
- `Prune-UnrelatedRestoredTargets`

### Receta ChatGPT

Canónica SHA-256:

`c4b615480d3dedbfaaebf17cdcd7f2fc18e7790e183687e7934d77ba9d4ee82b`

Copia antigua SHA-256:

`cd4847432d1048a2083636bc8d74ec7cf140e067843fda54b2ac83a106b6c107`

La receta canónica conserva selectores/fallbacks que no están completos en el snapshot antiguo.

## Identidad exacta con c210b931

Se compararon los blobs Git del HEAD de integración W13 con `c210b931...`.

Resultado:

- `ceo-browser/windows_chatgpt_cdp_driver.ps1`
  - HEAD blob: `7bf89f3441861360b49ed1f98b08384e24d453df`
  - c210 blob: `7bf89f3441861360b49ed1f98b08384e24d453df`
  - SAME = true

- `ceo-browser/open_chatgpt_profile.ps1`
  - HEAD blob: `202b43d1d6b83645df2d6e239d319c14aff95001`
  - c210 blob: `202b43d1d6b83645df2d6e239d319c14aff95001`
  - SAME = true

- `ceo-browser/recipes/chatgpt_web.json`
  - HEAD blob: `eac61a5dd8e2d233f1872db81f176d101f519454`
  - c210 blob: `eac61a5dd8e2d233f1872db81f176d101f519454`
  - SAME = true

Por tanto W13 no ha incorporado una variante posterior ni una copia aproximada.

## Corrección W13

### 1. Integración reproducible

Archivo:

`ceo-browser/apply_w13_canonical_browser_worker.py`

La candidata W13 incorpora:

1. `ceo_core/routing.py`
   - desde el bridge de integración;
   - conserva preferencia browser-first en cold start.

2. `ceo_core/providers/chatgpt_web.py`
   - desde el bridge de integración;
   - transporte Browser/CDP;
   - `WorkerKind.BROWSER`;
   - API no requerida;
   - continuidad por `ConversationUrl`;
   - relanzamiento permitido si Chrome desaparece.

3. `scripts/ceo_stdlib_work_mode.py`
   - se fusionan únicamente hooks browser sobre W12;
   - NO se copia el work-mode antiguo completo.

4. `ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1`
   - fuente: `ceo-browser/`;
   - identidad c210 verificada.

5. `ceo_core/browser_ai/open_chatgpt_profile.ps1`
   - fuente: `ceo-browser/`;
   - identidad c210 verificada.

6. `ceo_core/browser_ai/recipes/chatgpt_web.json`
   - fuente: `ceo-browser/`;
   - identidad c210 verificada.

### 2. Routing browser-first

El router acumulado conserva:

- proveedor local de Goal Lock;
- proveedor local de tarea finita;
- Browser Worker cuando el host está disponible;
- Gemini/API solo como acelerador opcional mediante `CEO_ALLOW_OPTIONAL_API`.

Una API no vuelve a ser requisito del camino normal.

### 3. Arranque sin petición obligatoria de API

W13 elimina del flujo normal la petición automática de una Gemini key.

Con `CEO_ALLOW_OPTIONAL_API=0`:

- no se exige API key;
- no se abre el fallback GUI de pegado de Gemini;
- el Browser Worker es la superficie externa principal;
- una indisponibilidad del browser no impide que el core local exista o que el objetivo pueda persistirse.

### 4. Probe de browser no destructivo

El arranque intenta demostrar control CDP mediante:

`browser_transport.probe_control()`

Si no puede:

- registra diagnóstico;
- no sustituye ni destruye el core;
- no convierte Gemini en requisito implícito.

### 5. Contrato de paquete

Las seis rutas quedan incluidas en `CEO_UPDATE_PACKAGE.json.file_hashes`.

El esquema 1.5.92 tiene:

`required_files = null`

W13 no inventa ni modifica ese esquema. La integridad de estas rutas se controla mediante los hashes que el contrato ya usa.

### 6. Builder histórico corregido

`ceo-browser/build_browser_first_lab.py` ahora separa:

- `CORE_SRC` = bridge histórico para piezas core;
- `BROWSER_SRC` = `ceo-browser` para driver/perfil/receta.

El directorio antiguo:

`dev313-inspect-routing/browser_ai`

deja de ser fuente de empaquetado.

## Hashes de candidata W13

- routing:
  `9fcdfd242128e759e7d66820bfa8f188dba55ccb7a1fc5287e0f3f39b6c23c43`

- provider ChatGPT web:
  `02c7089106f8f984b5c6ae8a339e10106c172de75f0cd3bd22afcb527f94f076`

- driver:
  `bfbb01eb528f08c0db586d0adb55078a109690ffcf6516c641a131d86974e9bb`

- profile helper:
  `7ff3a1fc30eaab0fed4f1dcf06f79bfe1ab751a4f5f48d02af6435178d226cd6`

- recipe:
  `c4b615480d3dedbfaaebf17cdcd7f2fc18e7790e183687e7934d77ba9d4ee82b`

- work mode acumulado W13:
  `9b955619b59260b55e3b11cda9c82756940511d64e3cf6d70807f07ce0a860f8`

## Evidencia focal Windows CI

Run:

`35884246546`

Job:

`107260198219`

Conclusion:

**SUCCESS**

Marcas:

- `W13_RAW_BROWSER_WORKER_GAP_REPRODUCED`
- `W13_CANONICAL_BROWSER_WORKER_APPLIED`
- `W13_CANONICAL_BROWSER_WORKER_REGRESSION_PASS`
- `W13_STATIC_INTEGRATION_PASS`
- `W13_PACKAGED_BROWSER_TWO_TURN_ZERO_API_PASS`
- `W13_WINDOWS_CI_PASS`

### Prueba focal dinámica

La prueba arrancó Chrome/Edge mediante el driver **incluido en la candidata W13**, contra el harness web local.

Completó:

- probe CDP: PASS;
- turno 1: PASS;
- captura de respuesta: PASS;
- conversation URL obtenida: PASS;
- turno 2 en la misma conversación: PASS;
- `api_calls=0`: PASS;
- `paid_api_calls=0`: PASS.

Esto demuestra integración ejecutable del Browser Worker dentro del paquete lógico W13.

No demuestra todavía:

- login real del usuario en chatgpt.com;
- sesión real persistente en el PC del usuario;
- respuesta de ChatGPT real;
- resistencia física prolongada.

## Suite canónica acumulada W6→W13

Commit de integración:

`728b75dbcccd1ce5d51b401cf83a33badffb08ed`

Workflow run:

`35884483679`

Job:

`107261018379`

Conclusion:

**SUCCESS**

La ejecución completa terminó con 54 pasos y volvió a superar:

- W6 anti-99;
- W7 recovery acotado;
- W8 verdad de productividad;
- W9 objetivo finito local;
- W10 restart;
- W11 idempotencia;
- W12 pausa/reanudar/cancelar;
- W13 Browser Worker;
- B02 scope freeze;
- contratos Python;
- browser-first source;
- pool multiproveedor;
- PowerShell;
- B03–B38;
- Gate 0;
- LAB portable;
- AITransport vía Chrome con cero API keys;
- free-only / no-production boundaries.

Marcas canónicas:

- `W13_CANONICAL_BROWSER_WORKER_PASS`
- `B02_SCOPE_FREEZE_PASS`
- `CEO_AI_TRANSPORT_BROWSER_ZERO_API_PASS`
- `FREE_BROWSER_BOUNDARY_PASS`

## Limpieza

Los workflows temporales:

- `ceo-w13-inspect.yml`
- `ceo-w13-browser-worker.yml`

se eliminaron tras obtener evidencia focal.

Se conservan:

- parche reproducible W13;
- regresión W13;
- gate W13 en la suite canónica;
- builder corregido;
- este documento.

## Dictamen W13

**BROWSER WORKER AUSENTE EN W6→W12:** BUG/GAP REAL CONFIRMADO  
**BUILDER PODÍA USAR DRIVER/RECETA OBSOLETOS:** BUG REAL CONFIRMADO  
**DRIVER CANÓNICO c210 INTEGRADO:** PASS  
**PERFIL CANÓNICO c210 INTEGRADO:** PASS  
**RECETA CANÓNICA c210 INTEGRADA:** PASS  
**IDENTIDAD DE BLOBS c210:** PASS  
**ROUTING BROWSER-FIRST:** PASS  
**API NO REQUERIDA:** PASS  
**CONTRATO DE PAQUETE / HASHES:** PASS  
**CANDIDATA W13 CONTROLA CHROME EN CI:** PASS  
**DOS TURNOS / MISMA CONVERSACIÓN EN HARNESS:** PASS  
**ZERO API:** PASS  
**W6→W13 ACUMULADO:** PASS  
**SUITE BROWSER-FIRST COMPLETA:** PASS  
**LOGIN/SESIÓN REAL CHATGPT DEL USUARIO:** PENDIENTE  
**VALIDACIÓN FÍSICA PC USUARIO:** PENDIENTE  
**INSTALADOR GENERADO:** NO  
**CANAL stable MODIFICADO:** NO

## Siguiente bloque

**W14 — perfil Chrome persistente / sesión real.**

El objetivo será auditar que la candidata W13 usa un perfil exclusivo y persistente, que una autenticación manual legítima pueda conservarse entre cierres/reaperturas y que no exista bypass de login, CAPTCHA o 2FA.
