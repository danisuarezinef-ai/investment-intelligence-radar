# M04-B — APP027–APP030

Fecha: 2026-09-22  
Estado: **M04B_COMPLETE_EMULATOR_VERIFIED**

Workflow: `35729119405` — **SUCCESS**  
Head verificado: `d3100cbf41f562fe2ff6fd9a4805271d2f94de64`

## APP027 — Instalación en emulador

**COMPLETE_EMULATOR_VERIFIED**

- Android API 35
- ABI x86_64
- instalación app debug: PASS
- package verificado: `ai.ceo.android.dev.debug`
- versionCode 11
- versionName `0.9.0-dev-m02-debug`
- teléfono físico usado: NO

## APP028 — Abrir / force-stop / reabrir

**COMPLETE_EMULATOR_VERIFIED**

Se ejecutaron 3 ciclos completos:

`start → proceso vivo → Activity visible → UI observable → screenshot → force-stop → proceso detenido`

Después se hizo un arranque final y el proceso quedó vivo.

## APP029 — Runtime sin crashes + instrumentación

**COMPLETE_EMULATOR_VERIFIED**

- título `CEO App` observable en los 3 ciclos;
- cero `FATAL EXCEPTION` atribuibles al package CEO;
- cero ANR atribuibles a CEO;
- instrumentación: **OK (3 tests)**;
- suite instrumental: PASS.

## APP030 — Evidencia

**COMPLETE_EMULATOR_VERIFIED**

Artefacto: `CEO_ANDROID_M04B_EMULATOR_EVIDENCE`  
Artifact ID: `10695355131`  
SHA-256 ZIP: `7d707829df73b7d5a8ab0e20c54aa8881f4f54015ee23bf4e34d1f4276db38b3`

Incluye capturas, jerarquías UI, package dump, logcat e instrumentación.

### APK usada en este gate

SHA-256 app debug:

`fba5aa946ea131fba660926f220fe237d371d14e4ff4e7e13fcca48c888010dc`

SHA-256 APK instrumental:

`ce72e61e4e80e98ee15c1fcf30cdaaec38160dd62bffa880704802098b6a61cc`

El hash debug no se usa como baseline reproducible; M03 ya demuestra reproducibilidad sobre release sin firmar.

## Cierre de M04

M04-A y M04-B están ahora verificadas por separado.

Sigue vigente:

`physical_installation_allowed=false`

Siguiente bloque: **M05 / APP031**.
