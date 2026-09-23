# W14-A — Perfil Chrome persistente / propiedad de sesión

Fecha: 2026-09-23
Ámbito: CEO Windows únicamente
Estado: CLOSED — 1 BUG REAL REPRODUCIDO + HARDENING DE PERFIL, FOCAL Y CI CANÓNICA GREEN
W14-B (ChatGPT real en PC del usuario): pendiente
Instalador: no generado
Canal stable: no modificado

## División de W14

W14-A cubre perfil, propiedad y persistencia:
- perfil Chrome/Edge exclusivo de CEO;
- persistencia entre cierre y reapertura;
- rechazo de un navegador CDP que no pertenezca al perfil solicitado;
- soporte de la ruta real de Windows con espacios (CEO de IAs);
- login humano legítimo;
- ningún bypass de login, CAPTCHA o 2FA;
- contrato/hashes dentro de la candidata acumulada.

W14-B queda reservada para:
- autenticación real en chatgpt.com en el PC del usuario;
- cierre/reapertura real;
- comprobación de sesión real persistente;
- al menos una interacción real mediante Browser Worker;
- cero API;
- evidencia física Windows.

W14-B no se simula ni se declara verificada desde CI.

## Punto de partida

W13 ya estaba CLOSED y verde antes de comenzar W14.
W14-A no rehizo W13.

## Hallazgo real — puerto CDP activo no demostraba propiedad del perfil

Antes de W14-A, si Get-DevToolsVersion detectaba un puerto CDP activo, el driver podía reutilizar ese navegador sin comprobar que el proceso hubiera sido lanzado con el ProfileDir solicitado.

Reproducción adversarial:
- Chrome señuelo en puerto 9258;
- perfil real del señuelo: w14a-decoy-profile;
- llamada al driver pre-W14 con el mismo puerto pero ProfileDir=w14a-wanted-profile y NoLaunch.

Resultado raw:
- ok=true;
- el driver declaraba el perfil solicitado;
- pero el proceso conectado pertenecía al perfil señuelo.

Marca:
W14A_RAW_CROSS_PROFILE_ATTACHMENT_REPRODUCED

## Corrección — propiedad CDP fail-closed

El driver canónico ceo-browser/windows_chatgpt_cdp_driver.ps1 incorpora ahora:
- Normalize-ProfilePath;
- Get-CDPOwnership;
- inventario de procesos con Get-CimInstance Win32_Process;
- asociación simultánea de remote-debugging-port y user-data-dir.

Si el puerto está activo pero no se demuestra que pertenece al perfil solicitado:
- no se reutiliza;
- no se navega;
- no se podan pestañas;
- no se cierra ese navegador;
- se devuelve BROWSER_PROFILE_OWNERSHIP_CONFLICT;
- exit code no cero.

Resultado focal:
- matched_port_processes=7;
- matched_profile_processes=0;
- ownership_reason=profile_mismatch;
- status=BROWSER_PROFILE_OWNERSHIP_CONFLICT.

Marca:
W14A_FOREIGN_PROFILE_REJECTED

## Ruta Windows con espacios

El perfil real por defecto de CEO es:
%LOCALAPPDATA%\CEO de IAs\browser-profile

W14-A valida explícitamente rutas con espacios.
El lanzamiento protege user-data-dir con comillas.

Prueba focal:
CEO de IAs\browser profile

Resultado:
- Chrome arrancó;
- el proceso fue reconocido como propietario;
- profile_dir volvió exactamente igual;
- cierre controlado correcto.

Marcas:
W14A_SPACED_PROFILE_OWNERSHIP_PASS
W14A_PROFILE_OWNERSHIP_CANONICAL_PASS

## Contrato del perfil persistente

ceo-browser/open_chatgpt_profile.ps1 ahora revalida las invariantes en cada uso:
- owner = CEO de IAs;
- exclusive_profile = true;
- provider_surface = chatgpt-web;
- profile_dir = ruta solicitada;
- no_api_required = true;
- conserva created_at;
- escribe validated_at.

La prueba alteró intencionadamente el marker y confirmó que al reabrir se reparan owner, exclusividad, ruta y no-api.

## Persistencia cierre → reapertura

Secuencia de prueba:
1. abrir con el perfil persistente;
2. establecer estado autenticado en harness;
3. cerrar Chrome;
4. reabrir el mismo perfil en otro puerto;
5. no volver a sembrar autenticación;
6. comprobar SESSION_READY;
7. comprobar logged_in_evidence=true.

Marca:
W14A_SESSION_PERSISTENCE_AND_MARKER_REPAIR_PASS

Esto prueba persistencia de almacenamiento del perfil en Windows CI.
No equivale todavía a una cookie/sesión real de ChatGPT.

## Login / CAPTCHA / 2FA

Un perfil nuevo sigue devolviendo LOGIN_REQUIRED.

Marca:
W14A_LOGIN_BOUNDARY_PASS

La receta real mantiene:
- no_captcha_bypass=true;
- no_2fa_bypass=true;
- manual_login_allowed=true;
- no_purchase=true;
- no_subscription_change=true.

## Regresión persistente

Archivo:
ceo-browser/w14a_profile_persistence_regression.py

Comprueba:
- ownership;
- estado de conflicto;
- argumento de perfil protegido;
- invariantes del marker;
- límites CAPTCHA/2FA;
- perfil persistente del provider;
- hashes de package contract.

Marca:
W14A_PROFILE_CONTRACT_REGRESSION_PASS

## Hashes de candidata acumulada

ceo_core/browser_ai/windows_chatgpt_cdp_driver.ps1
SHA-256:
52f3f8176a3779d5989150b25c0b185087a1bed4cbc0fb800484021fab4a29fe

ceo_core/browser_ai/open_chatgpt_profile.ps1
SHA-256:
3f5dfb64dde62c99bbe48f9fef8d4df17b1bedb43983683501e92d09385e89e1

## Incidencia detectada durante el desarrollo W14-A

La primera implementación del normalizador de ruta introducida en W14-A usó una forma inválida de TrimEnd en PowerShell.
La suite canónica lo detectó durante la campaña browser.

Se corrigió antes de cerrar W14-A usando un array explícito de caracteres 92 y 47.
Después de la corrección:
- prueba focal: SUCCESS;
- suite canónica completa: SUCCESS.

## Evidencia focal Windows

Run: 35899237018
Job: 107310848807
Conclusion: SUCCESS

Marcas:
- W14A_PROFILE_CONTRACT_REGRESSION_PASS
- W14A_STATIC_CONTRACT_PASS
- W14A_RAW_CROSS_PROFILE_ATTACHMENT_REPRODUCED
- W14A_FOREIGN_PROFILE_REJECTED
- W14A_SPACED_PROFILE_OWNERSHIP_PASS
- W14A_SESSION_PERSISTENCE_AND_MARKER_REPAIR_PASS
- W14A_LOGIN_BOUNDARY_PASS
- W14A_WINDOWS_CI_PASS

## Integración canónica

Commit de integración:
c48c93f236237f627f564bb07540fa7115d65b54

Run:
35899549270

Job:
107311902465

Conclusion:
SUCCESS

Gates:
- W14A persistent profile contract in accumulated candidate
- W14A profile ownership and spaced path runtime gate

Marcas:
- W14A_PROFILE_CONTRACT_CANONICAL_PASS
- W14A_PROFILE_OWNERSHIP_CANONICAL_PASS
- B02_SCOPE_FREEZE_PASS
- CEO_AI_TRANSPORT_BROWSER_ZERO_API_PASS
- FREE_BROWSER_BOUNDARY_PASS

La misma ejecución volvió a superar W6-W13, B02, B03-B38, Gate 0, LAB y transporte Chrome con cero APIs.

## Dictamen W14-A

W13 previo: CLOSED / no rehecho
Enganche a CDP de otro perfil: BUG REAL REPRODUCIDO
Rechazo fail-closed de perfil ajeno: PASS
Ruta real con espacios: PASS
Perfil exclusivo: PASS
Marker revalidable/reparable: PASS
Persistencia cierre→reapertura: PASS EN HARNESS
Perfil nuevo exige login: PASS
CAPTCHA bypass: PROHIBIDO / NO IMPLEMENTADO
2FA bypass: PROHIBIDO / NO IMPLEMENTADO
API requerida: NO
W6→W14-A acumulado: PASS
Validación ChatGPT real del usuario: PENDIENTE (W14-B)
Validación física PC usuario: PENDIENTE (W14-B)
Instalador: NO
Canal stable: SIN CAMBIOS

## Siguiente trabajo

W14-B — segunda mitad: sesión real ChatGPT en el PC del usuario.

No debe declararse cerrada hasta probar físicamente:
1. perfil exclusivo real;
2. login manual legítimo en chatgpt.com;
3. cierre completo;
4. reapertura;
5. sesión todavía válida;
6. al menos una interacción real de Browser Worker;
7. cero API calls;
8. sin bypass de CAPTCHA/2FA.
