# M05-A — Shell principal de CEO App

Fecha: 2026-09-22  
Estado: **M05A_COMPLETE_EMULATOR_VERIFIED**

Workflow: `35732038552` — **SUCCESS**  
Head verificado: `1902d1121afe9b5df792ab16f01e8aeb6aad08bc`

## APP031 — Pantalla principal

**COMPLETE_EMULATOR_VERIFIED**

- `MainActivity` abre el nuevo `CEOHomeScreen`.
- La pantalla muestra `CEO App` y `Control central`.
- El shell es desplazable para pantallas compactas.
- Se instaló y abrió correctamente en emulador API 35 / x86_64.

## APP032 — Goal Engine

**COMPLETE_EMULATOR_VERIFIED**

- El título del objetivo permanece visible.
- El cuerpo completo del objetivo empieza plegado.
- `Mostrar objetivo` despliega el contenido.
- `Ocultar objetivo` lo vuelve a plegar.
- Los tests Compose escribieron título y objetivo, guardaron y comprobaron `Objetivo guardado`.

Esto implementa la UX acordada: cabecera limpia y objetivo completo bajo demanda.

## APP033 — Estado general

**COMPLETE_EMULATOR_VERIFIED**

Estados implementados:

- `Esperando objetivo`
- `Objetivo en edición`
- `Objetivo preparado`

El test interactivo verificó la transición real hasta `Objetivo preparado`.

## APP034 — Progreso / porcentaje

**COMPLETE_EMULATOR_VERIFIED como superficie UI**

- tarjeta `Progreso`;
- porcentaje visible;
- barra de progreso;
- valor inicial validado: `0%`.

El porcentaje no finge trabajo inexistente. Su avance real se conectará al Task Engine en M07.

## Prueba real en emulador

- build app + APK instrumental: PASS;
- instalación: PASS;
- MainActivity visible: PASS;
- shell real observable mediante UIAutomator: PASS;
- tests instrumentados: **6/6, 0 fallos**;
- test Goal Engine interactivo: PASS;
- `FATAL EXCEPTION` de CEO: **0**.

APK debug de esta prueba:

`397c782db59e74fb566bb79f8b5b002929e7fa04d14945f7fc0dc0565d23008d`

Artefacto de evidencia:

`CEO_ANDROID_M05A_SHELL_EVIDENCE`  
Artifact ID: `10696930007`  
SHA-256 ZIP: `753645a94c74f93ec43ee456053dc7c2dc0e6ea6f11dc05be4854b604ffd47b4`

## Deuda realizable revisada

M04 está completamente cerrado tras su división:

- M04-A: PASS;
- M04-B: PASS.

M01–M04 y M05-A quedan congelados para no generar workflows redundantes.

No queda una incidencia previa que bloquee el progreso actual.

## Siguiente bloque

**M05-B / APP035–APP038**

- APP035 tareas activas;
- APP036 propuestas/decisiones;
- APP037 navegación;
- APP038 acabado visual móvil.

Sigue vigente:

`physical_installation_allowed=false`
