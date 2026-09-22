# W3 — Auditoría de arranque / single-instance CEO Windows

**Fecha:** 2026-09-23  
**Estado:** CLOSED — SOURCE AUDIT PASS  
**Prueba física Windows:** pendiente

## Hallazgos existentes, no rehechos

DEV311 ya introdujo las correcciones relevantes. W3 audita esas correcciones en lugar de crear otro launcher.

## Arranque normal

`ABRIR_CEO.cmd`:

1. busca runtime privado del paquete;
2. busca runtime instalado en `%LOCALAPPDATA%\Programs\CEO de IAs\runtime\python.exe`;
3. permite `py.exe -3` o `python.exe` como fallback;
4. ejecuta `scripts\launch_current.py`;
5. deja diagnóstico persistente si no puede arrancar.

## Single backend

`launch_current.py`:

- sondea `127.0.0.1:8765..8780/api/health`;
- si ya existe un CEO sano, NO inicializa updater ni crea otro scheduler;
- registra `EXISTING_INSTANCE_OPENED`;
- abre el backend existente en modo app.

Resultado: un segundo doble clic no debe crear un segundo motor CEO.

## Puntero de actualización

`_safe_pointer()`:

- exige root real y launcher real;
- un `current.json` muerto o corrupto se ignora;
- el paquete bundled sigue siendo fallback;
- un puntero inválido no debe impedir abrir CEO.

## Bucle de launcher

El arranque usa directamente `scripts/ceo_stdlib_work_mode.py` cuando existe.

Esto evita el bucle histórico:

`ABRIR_CEO.cmd → launch_current.py → ABRIR_CEO.cmd → ...`

## Reinicio tras actualización

`relaunch_after_update.py`:

- prefiere launcher Python determinista;
- espera al proceso anterior;
- exige puntero/activation_id esperados;
- arranca candidata;
- exige health;
- exige productive smoke local;
- solo entonces confirma;
- si falla, mata candidata, ejecuta rollback y relanza la anterior.

## Limitación no bloqueante

Si el backend ya está vivo, el launcher puede abrir otra ventana app del navegador apuntando al mismo backend. Esto puede producir dos ventanas visuales, pero no dos schedulers/CEO.

No se corrige aquí porque:
- no impide completar objetivos;
- introducir control/focus de ventanas antes de prueba física añade riesgo;
- debe verificarse empíricamente en Windows.

## Resultado W3

Single backend: **PASS_SOURCE**.  
Dead pointer fallback: **PASS_SOURCE**.  
Nested launcher loop protection: **PASS_SOURCE**.  
Post-update health + productive smoke + rollback: **PASS_SOURCE**.  
Reutilización exacta de la misma ventana UI: **PHYSICAL/UX PENDING, NON-BLOCKING**.  
Cambio de código requerido ahora: **NO**.
