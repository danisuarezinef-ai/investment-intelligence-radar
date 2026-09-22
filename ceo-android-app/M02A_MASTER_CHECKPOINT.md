# M02-A — Checkpoint APP007–APP010

Fecha: 2026-09-22

Estado: **M02A_COMPLETE_CI_VERIFIED**

Workflow dedicado: `35716018519` — **SUCCESS**

## APP007 — settings.gradle.kts

**COMPLETE_CI_VERIFIED**

- Proyecto raíz: `CEOAndroid`
- Módulo: `:app`
- Repositorios de plugins y dependencias definidos.
- Gradle reconoce correctamente la jerarquía del proyecto.

## APP008 — Configuración Gradle raíz

**COMPLETE_CI_VERIFIED**

- Android Gradle Plugin fijado.
- Plugin Kotlin/Compose fijado.
- AndroidX y propiedades base configuradas.
- La configuración raíz es aceptada por Gradle.

## APP009 — Módulo app

**COMPLETE_CI_VERIFIED**

- Namespace: `ai.ceo.android`
- Application ID de desarrollo: `ai.ceo.android.dev`
- minSdk 26
- compileSdk/targetSdk 36 para el baseline reconstruido y actualmente compilable.
- versionCode 11
- versionName `0.9.0-dev-m02`
- Compose BOM compatible con API 36.
- Sin configuración de firma de producción todavía.

## APP010 — AndroidManifest e identidad

**COMPLETE_CI_VERIFIED**

- `CEOApplication`
- `MainActivity` launcher.
- HTTPS-only a nivel de cleartext policy.
- Backup desactivado.
- Solo permiso de Internet en la base.
- Sin permisos de instalación de APK, almacenamiento global, overlays, accesibilidad ni otros permisos sensibles.

## Gate real de esta mitad

El workflow:

1. verificó estáticamente APP007–APP010;
2. preparó API 36;
3. ejecutó `gradlew projects`;
4. confirmó `CEOAndroid -> :app`;
5. confirmó mediante Gradle que existe la tarea `assembleDebug`;
6. no compiló APK ni autorizó instalación física.

## Siguiente bloque

**M02-B / APP011–APP014**

Quedan por validar separadamente:

- APP011 Kotlin/Compose;
- APP012 recursos;
- APP013 wrapper/toolchain ejecutable;
- APP014 compilación limpia y qualification.

Aunque parte de ese código ya fue adelantado antes de dividir M02, **no se considera cerrado** hasta atacar M02-B como bloque independiente.
