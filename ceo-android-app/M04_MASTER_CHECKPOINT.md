# M04 — Primera APK de laboratorio en emulador

Fecha: 2026-09-22  
Estado: **M04_COMPLETE_EMULATOR_VERIFIED**

Workflow final: `35721758822` — **SUCCESS**  
Head verificado: `9d344107a3dfb7805f042920f7803109d3b83ddf`

## APP023 — Build debug limpio

**COMPLETE_EMULATOR_VERIFIED**

Se construyó desde checkout limpio:

`clean :app:assembleDebug :app:assembleDebugAndroidTest`

Resultado: **BUILD SUCCESSFUL**.

## APP024 — APKs generadas

**COMPLETE**

APK app:

- package: `ai.ceo.android.dev.debug`
- versionCode: `11`
- versionName: `0.9.0-dev-m02-debug`
- minSdk: `26`
- targetSdk: `36`
- tamaño: **11,567,487 bytes**
- SHA-256: `8009420253860d5c311c4eb2bd3b7739f1495fbf1eb116a26c60ea326908e068`

APK de instrumentación:

- tamaño: **391,241 bytes**
- SHA-256: `a47ffa48a39de35286bc77bb448e9ec36f93cc258b6a0889d9a64f5cd32d3317`

## APP025 — Inspección APK

**COMPLETE_EMULATOR_VERIFIED**

`aapt` confirmó estructura, identidad, SDKs y launcher.

## APP026 — Identidad/versiones

**COMPLETE_EMULATOR_VERIFIED**

Se verificaron tanto antes como después de instalar en emulador.

## APP027 — Instalación solo en emulador

**COMPLETE_EMULATOR_VERIFIED**

Entorno:

- Android API 35;
- ABI x86_64;
- dispositivo virtual Pixel 6;
- instalación mediante ADB: **Success**.

No se utilizó ningún teléfono físico.

## APP028 — Abrir/cerrar/reabrir

**COMPLETE_EMULATOR_VERIFIED**

Se realizaron **3 ciclos completos**:

`launch → proceso vivo → Activity activa → captura UI → force-stop → proceso detenido → relaunch`

Después se realizó un cuarto arranque final y el proceso volvió a quedar vivo.

## APP029 — Arranque sin crashes

**COMPLETE_EMULATOR_VERIFIED**

- cero `FATAL EXCEPTION` atribuibles a `ai.ceo.android.dev.debug`;
- la UI real expuso `CEO App` y el resto de textos de la pantalla;
- `MainActivity` llegó correctamente a ejecución;
- se ejecutaron **3 tests instrumentados**;
- se completaron **3/3 tests**;
- Gradle terminó **BUILD SUCCESSFUL**.

Durante M04 se corrigió además una omisión real: faltaba empaquetar `androidx.test:runner`, aunque `AndroidJUnitRunner` ya estaba declarado.

## APP030 — Evidencia

**COMPLETE_EMULATOR_VERIFIED**

Artefacto:

`CEO_ANDROID_M04_EMULATOR_EVIDENCE`

Artifact ID: `10691951770`

SHA-256 del ZIP de evidencias:

`78bc58d023cdcac52a55a72d5ebd23da3a4f935e29926b3f3fa3edcd684b7c89`

Incluye:

- hashes;
- badging APK;
- estado de paquetes;
- PIDs;
- jerarquías UI;
- 3 capturas de pantalla;
- logcat;
- salida de tests instrumentados.

## Estado de instalación

Sigue vigente:

`physical_installation_allowed=false`

M04 demuestra que la app puede instalarse y funcionar en un Android real virtualizado. No autoriza todavía la instalación en el teléfono.

## Siguiente bloque

**M05 / APP031 — Shell visual completa de CEO App.**
