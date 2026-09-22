# M04-A — Build e inspección de APK

Fecha: 2026-09-22  
Estado: **M04A_COMPLETE_CI_VERIFIED**

Workflow dedicado: `35726177319` — **SUCCESS**  
Head verificado: `65dd04a32745f44251f14e59bb31f5fb2b467a0a`

## APP023 — Build debug limpio

**COMPLETE_CI_VERIFIED**

Se ejecutó desde checkout limpio:

`clean :app:assembleDebug :app:assembleDebugAndroidTest`

Resultado: **BUILD SUCCESSFUL**.

## APP024 — APKs generadas

**COMPLETE_CI_VERIFIED**

APK principal:

- package: `ai.ceo.android.dev.debug`
- versionCode: `11`
- versionName: `0.9.0-dev-m02-debug`
- tamaño: **11,567,487 bytes**
- SHA-256: `4017c0c33b239658e8693ff4110da7b53ad705fab982af605e03987b056b8580`

APK instrumental:

- package: `ai.ceo.android.dev.debug.test`
- tamaño: **391,241 bytes**
- SHA-256: `9d4f21f36684afecf4ed83e43371c590d4b10b7c9b6ab1f63edd2cb14aa5fc71`

## APP025 — Inspección estructural

**COMPLETE_CI_VERIFIED**

Se verificó que la APK principal contiene:

- `AndroidManifest.xml`;
- `classes.dex`;
- `resources.arsc`;
- metadatos de firma.

La APK instrumental contiene Manifest y bytecode. Ambas pasan `apksigner verify`.

## APP026 — Identidad/versionado/SDK/launcher

**COMPLETE_CI_VERIFIED**

`aapt` confirmó:

- package: `ai.ceo.android.dev.debug`;
- versionCode: 11;
- versionName: `0.9.0-dev-m02-debug`;
- minSdk: 26;
- targetSdk: 36;
- launcher: `ai.ceo.android.MainActivity`;
- label: `CEO`.

## Alcance exacto

M04-A **no** instala ni ejecuta la app.

- emulador usado: **NO**;
- teléfono físico usado: **NO**;
- runtime/crash-free claim: **NO**;
- instalación física autorizada: **NO**.

El hash debug no es baseline reproducible: la reproducibilidad formal ya quedó demostrada en M03 sobre el release sin firmar.

## Evidencia

Artefacto: `CEO_ANDROID_M04A_BUILD_INSPECTION`  
Artifact ID: `10693169302`  
SHA-256 ZIP: `d4eb519bace3dae987312537a1db05ac622795ffab8d93fcb65bbe8b20b76550`

## Siguiente bloque

**M04-B / APP027–APP030**:

instalar únicamente en emulador, abrir/cerrar/reabrir, probar runtime sin crashes y conservar evidencia.
