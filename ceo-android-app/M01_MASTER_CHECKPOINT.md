# M01 — Checkpoint maestro de CEO App Android

Fecha: 2026-09-22  
Rama única activa: `ceo-android-first-install`  
Raíz de desarrollo: `ceo-android-app/`

## Decisión de proyecto

CEO App Android es la única línea activa. Windows, Radar, tesis/revisión térmica, libro y cualquier otro proyecto quedan congelados.

No se realizará instalación física en el teléfono hasta completar M01–M25 y emitir:

`CEO_ANDROID_FIRST_INSTALL_READY=true`

## APP001 — Congelación

**COMPLETE.**

La política está en `M01_PROJECT_FREEZE.json`. `ceo-canonical/` es referencia histórica de solo lectura; el desarrollo nuevo vive en `ceo-android-app/`.

## APP002 — Inventario

**COMPLETE.**

Se preservan:

- 24 módulos Python de validación/contrato Android;
- 9 módulos móviles del núcleo;
- 29 módulos de actualización/recuperación;
- contratos Android v1/v2;
- admisión e inspección de APK;
- reproducibilidad/build receipts;
- runtime API 35/36;
- infraestructura de updater firmado;
- manifiesto de 45 archivos del proyecto Android;
- toolchain lock;
- evidencias de validación histórica.

Detalle: `M01_ANDROID_INVENTORY.json`.

## APP003 — Recuperación histórica

**COMPLETE con limitación documentada.**

Se revisaron ramas, árbol Git, commits por rutas fuente y el bootstrap preservado.

Hallazgos:

1. El candidato más avanzado documentado es `0.8.0-rc5-runtime-a181-a190`.
2. El manifiesto de fuente conserva 45 rutas, tamaños y SHA-256.
3. No existe actualmente un proyecto Gradle/Kotlin materializado en Git.
4. Las búsquedas históricas de rutas clave (`MainActivity.kt`, `app/build.gradle.kts`, `settings.gradle.kts`, `UpdateManager.kt`, `ceo_android_bridge.py`) no encontraron commits con esos archivos como rutas versionadas.
5. `CEO_DEV21_BOOTSTRAP_PATCH.zip` contiene solo:
   - `ABRIR_CEO.cmd`
   - `scripts/bootstrap_dev21.py`
   - `dev21.patch`

No contiene el proyecto fuente completo.

## APP004 — Comparación contra 45 archivos

**COMPLETE.**

Resultado:

- esperados: **45**;
- contenido fuente exacto recuperado: **1**;
- solo identidad/hash o referencias: **44**;
- archivo exacto recuperado: `TOOLCHAIN.lock.json`;
- hashes esperados preservados para los 45.

Detalle por archivo: `M01_RECOVERY_MATRIX.json`.

Esto impide afirmar que los 44 archivos reconstruidos en M02 son idénticos al original hasta que exista evidencia real de hash/contenido.

## APP005 — Baseline más avanzado

**COMPLETE como baseline de referencia.**

Baseline: `M01_RECOVERED_BASELINE.json`.

Identidades preservadas principales:

- source fingerprint: `d0baaf9d35d04dc9606d9c77f7856277e24f6a711e9e1a79e367d61937646ce8`
- build payload: `48fa82db04580802703b921778097a71c56460151c3b980c09976d0f6675c0a5`
- SBOM: `b92e3cf049d39e02b68eef3ccb3d73496eb65a6c424b999c83adff913636f394`
- package histórico: `ai.ceo.android.dev`
- versionCode histórico: `10`

La evidencia histórica de `194/194 PASS` se conserva únicamente como evidencia del candidato histórico; **no valida todavía la reconstrucción nueva**.

## APP006 — Punto único de reanudación

**COMPLETE pendiente únicamente de qualification CI.**

Este archivo y `ANDROID_MASTER_STATE.json` son el único punto de reanudación.

### Próximo bloque

**M02 — Reconstrucción del proyecto Android real.**

Siguiente tarea: **APP007 — materializar/restaurar `settings.gradle.kts` dentro de `ceo-android-app/android/`**, continuando hasta APP014.

M02 deberá reconstruir los 44 cuerpos ausentes, no inventar equivalencia histórica, y generar una nueva identidad reproducible para la app que realmente vayamos a instalar.
