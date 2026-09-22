# M03 — Toolchain reproducible

Fecha: 2026-09-22  
Estado: **M03_COMPLETE_REPRODUCIBLE_CI_VERIFIED**

Workflow: `35718836103` — **SUCCESS**  
Head verificado: `1d6fcf89069aac7df144c6c5dff66b8297ad39da`

## APP015 — JDK

**COMPLETE_CI_VERIFIED**

- distribución: Temurin / Eclipse Adoptium;
- línea fijada: JDK 17.0.20.x;
- el workflow comprueba versión y vendor antes de construir.

## APP016 — Gradle

**COMPLETE_CI_VERIFIED**

- Gradle Wrapper 9.4.1;
- checksum de distribución fijado en `gradle-wrapper.properties`;
- wrapper JAR verificado por SHA-256.

## APP017 — Android Gradle Plugin

**COMPLETE_CI_VERIFIED**

- AGP 9.2.1;
- versión contrastada contra `TOOLCHAIN.lock.json`.

## APP018 — Kotlin / Compose

**COMPLETE_CI_VERIFIED**

- Kotlin Compose plugin 2.3.21;
- Compose BOM 2026.04.01 / Compose 1.11;
- Activity Compose 1.13.0;
- AndroidX Core 1.18.0;
- no se permiten versiones dinámicas.

## APP019 — SDK / Build Tools

**COMPLETE_CI_VERIFIED**

- compileSdk 36;
- targetSdk 36;
- minSdk 26;
- Build Tools 36.0.0;
- paquetes SDK fijados y comprobados.

## APP020 — ABI

**COMPLETE_CI_VERIFIED como política de plataforma**

- teléfono físico objetivo: `arm64-v8a`;
- emulador/CI: `x86_64`;
- todavía no existe payload nativo, por lo que no se añade un filtro NDK artificial;
- cuando entre runtime nativo/Python, el build release deberá contener `arm64-v8a`.

## APP021 — Entorno CI y reproducibilidad

**COMPLETE_CI_VERIFIED**

- runner fijado: `ubuntu-24.04`;
- timezone: UTC;
- locale: C.UTF-8;
- acciones GitHub fijadas por SHA de commit;
- daemon/parallel/VFS watch/incremental Kotlin desactivados para este baseline;
- dos copias independientes del mismo source tree fueron construidas sin build cache.

### Resultado de reproducibilidad

Ambos builds generaron:

`app-release-unsigned.apk`

Build A SHA-256:

`80c68750f0d959b38e303a14336cfac2743448068f31ff35c032e36b341769a6`

Build B SHA-256:

`80c68750f0d959b38e303a14336cfac2743448068f31ff35c032e36b341769a6`

Resultado: **idénticos byte a byte**.

Tamaño: **8,232,668 bytes**.

## APP022 — Limpieza de lock activo

**COMPLETE_CI_VERIFIED**

Se retiraron del lock activo componentes que todavía no forman parte del build:

- Chaquopy;
- runtime Python;
- WorkManager.

No se eliminan del roadmap. Se reintroducirán únicamente cuando el bloque correspondiente los active y pruebe.

El gate rechaza:

- versiones dinámicas;
- SNAPSHOT;
- `mavenLocal()`;
- deriva entre los Gradle files y el toolchain lock.

## Límite actual

El release reproducible está **sin firmar**. Es deliberado.

La identidad permanente de firma y la demostración N → N+1 corresponden a **M18**. Por tanto:

`physical_installation_allowed=false`

## Siguiente bloque

**M04 / APP023 — Primera APK de laboratorio y ejecución en emulador.**
