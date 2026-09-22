# CEO App Android — única línea activa

Esta carpeta es la nueva fuente de trabajo para **CEO App Android**.

## Objetivo

Llegar, antes de instalar en el teléfono físico, a una app Android real que:

- se compile de forma reproducible;
- se instale como un único APK firmado;
- ejecute tareas sencillas pero completas de principio a fin;
- conserve objetivos, tareas, artefactos y estado;
- pueda trabajar en segundo plano dentro de los límites de Android;
- disponga de un actualizador interno que compruebe, descargue y verifique nuevas versiones sin navegador ni descarga manual externa;
- entregue la APK verificada al instalador de Android cuando la plataforma requiera confirmación humana;
- conserve la misma identidad de firma para N → N+1 → N+2.

## Regla de desarrollo

`ceo-canonical/` se usa como **referencia histórica de solo lectura**. La app nueva se materializa y evoluciona dentro de `ceo-android-app/`.

Windows, Radar, tesis/revisión térmica, libro y cualquier otra línea quedan congelados hasta instrucción explícita del usuario.

## Gate de instalación física

No se instala nada en el teléfono antes de completar **M01–M25 / APP001–APP220** y emitir:

`CEO_ANDROID_FIRST_INSTALL_READY=true`

M01 recupera e inventaría todo lo que existe. M02 materializará el proyecto Android Gradle/Kotlin real.
