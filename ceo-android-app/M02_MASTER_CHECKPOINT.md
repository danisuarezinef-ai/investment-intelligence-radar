# M02 — Checkpoint de reconstrucción Android real

Fecha: 2026-09-22  
Rama: `ceo-android-first-install`  
Estado: **M02_COMPLETE_CI_VERIFIED**

## Resultado

El proyecto Android real está materializado en:

`ceo-android-app/android/`

Se han reconstruido/materializado las **45/45 rutas** del manifiesto histórico, más un Gradle Wrapper completo (`gradlew`, `gradlew.bat`, JAR y properties).

La reconstrucción es una **nueva línea fuente**. No se afirma que los 44 cuerpos perdidos sean idénticos al antiguo candidato.

## APP007–APP014

- APP007 settings.gradle.kts — COMPLETE
- APP008 build.gradle.kts / Gradle properties — COMPLETE
- APP009 módulo app — COMPLETE
- APP010 AndroidManifest — COMPLETE
- APP011 Kotlin + Compose — COMPLETE
- APP012 recursos Android — COMPLETE
- APP013 Gradle Wrapper completo — COMPLETE
- APP014 estructura y compilación — COMPLETE_CI_VERIFIED

## Toolchain M02 efectiva

- JDK 17
- Gradle 9.4.1
- AGP 9.2.1
- compileSdk 36
- targetSdk 36
- minSdk 26
- Compose BOM 2026.04.01 / Compose 1.11
- Activity Compose 1.13.0
- AndroidX Core 1.18.0

El lock histórico pedía API 37 y Compose 1.12, pero el SDK del runner no ofrecía `platforms;android-37`. Además Compose 1.12 y Core 1.19 exigen compileSdk 37. Se adoptó una combinación construible y coherente con API 36.

## Qualification real

Workflow: `35711986202`  
Head: `9289029aa7e5d16ddce5be715a2f2c654ae44a9a`  
Conclusión: **SUCCESS**

- source structure: PASS
- Python foundation syntax: PASS
- Gradle Wrapper 9.4.1: PASS
- `:app:assembleDebug`: PASS
- `:app:assembleDebugAndroidTest`: PASS

APK debug CI:

- tamaño: 11,567,487 bytes
- SHA-256: `3deae30eca2f5657358c87385f335478600993c1ff53f50c97da70323a5a13c0`

Esta APK es evidencia de compilación, **no está autorizada para instalación física**.

## Estado funcional actual

La app ya contiene una pantalla Compose real con:

- título del objetivo;
- cuerpo del objetivo;
- guardado local básico;
- panel de estado de preinstalación.

El updater ya tiene modelos, preflight, SHA-256, snapshot y límites de autoridad, pero descarga/instalación permanecen bloqueadas hasta M14–M17.

Los puentes Python están materializados pero no tienen todavía autoridad de ejecución. El motor de tareas empieza en M07.

## Siguiente bloque

**M03 — Toolchain reproducible.**

Siguiente tarea: **APP015 — cerrar y automatizar la identidad JDK/toolchain**, continuando hasta APP022.

Sigue vigente:

`physical_installation_allowed=false`

No se instala en el teléfono hasta APP220.
