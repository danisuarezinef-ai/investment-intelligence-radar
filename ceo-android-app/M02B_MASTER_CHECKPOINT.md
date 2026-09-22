# M02-B — Checkpoint APP011–APP014

Fecha: 2026-09-22

Estado: **M02B_COMPLETE_CI_VERIFIED**

Workflow dedicado: `35717406582` — **SUCCESS**  
Head verificado: `10e08bfc4b50e6614e316b385074c50208df5007`

## APP011 — Kotlin/Compose

**COMPLETE_CI_VERIFIED**

- 21 archivos Kotlin principales.
- 3 archivos Kotlin debug.
- 2 tests instrumentados.
- `MainActivity` compila con Compose.
- `CEOApplication`, preferencias, bridge nativo y scaffolding del updater compilan.
- Los puentes Python existen pero continúan sin autoridad de ejecución.

## APP012 — Recursos Android

**COMPLETE_CI_VERIFIED**

- `styles.xml` válido.
- `update_file_paths.xml` válido.
- fixture debug de solo lectura verificada.
- Los recursos fueron procesados correctamente durante la construcción APK.

## APP013 — Wrapper/toolchain

**COMPLETE_CI_VERIFIED**

- JDK 17.
- Gradle Wrapper 9.4.1.
- wrapper JAR presente y funcional.
- AGP 9.2.1.
- compileSdk/targetSdk 36.
- minSdk 26.
- Build Tools 36.0.0.
- Compose BOM 2026.04.01.

## APP014 — Build limpio y qualification

**COMPLETE_CI_VERIFIED**

Se ejecutó en runner limpio:

`gradlew clean :app:assembleDebug :app:assembleDebugAndroidTest`

Resultado: **PASS**

APK app debug:

- package: `ai.ceo.android.dev.debug`
- versionCode: `11`
- versionName: `0.9.0-dev-m02-debug`
- minSdk: `26`
- targetSdk: `36`
- tamaño: **11,567,487 bytes**
- SHA-256: `c30eb3f5cd3e1600961fd53ba7cf60d8bbae09a61e964fa7fcd4070320075307`

APK instrumental:

- tamaño: **287,633 bytes**
- SHA-256: `bd75d1c6e914efffbc79abe55f89fcf21fade47ece9a2f7a28076b2f6440257f`

El APK fue inspeccionado con herramientas Android y confirmó identidad, minSdk y targetSdk.

### Importante

Este APK sigue siendo **CI-only**. No está autorizado para instalación física.

El hash del APK difiere del build M02 anterior. Esto no invalida M02: aquí demostramos compilación limpia, no reproducibilidad bit-a-bit. **La reproducibilidad se cierra en M03.**

## Cierre de M02

M02-A y M02-B están ahora verificadas de forma independiente.

Siguiente bloque: **M03 / APP015**.
