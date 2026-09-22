# CEO Android App

Rama móvil prioritaria de CEO de IAs.

## Objetivo inmediato

Construir una app Android nativa, instalable y actualizable desde la propia app, sin depender de descargas manuales posteriores.

### Invariantes

- La primera APK pública debe usar un applicationId estable.
- La variante debug usa sufijo .dev para no contaminar la futura instalación estable.
- El actualizador solo acepta HTTPS.
- El APK descargado debe coincidir en tamaño y SHA-256 con el manifiesto.
- El paquete descargado debe tener el mismo package name y el mismo certificado firmante que CEO instalado.
- Android conserva la confirmación humana del instalador del sistema.
- Sin pagos, suscripciones, instalación silenciosa ni publicación automática.
- La ausencia de firma release bloquea solo la producción de APKs release; el resto del desarrollo continúa.

## Estado

0.9.0-alpha1 / versionCode 11.

Primera superficie:
- Goal Engine persistente.
- Progreso local de prueba.
- Panel de actualización interno.
- Canal dev/stable incorporado en BuildConfig.

El siguiente gate es CEO Android Debug APK: compilar y publicar una APK debug real en CI.
