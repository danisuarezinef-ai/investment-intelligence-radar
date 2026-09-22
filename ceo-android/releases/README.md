# CEO Android update channel

Estos manifiestos son consumidos directamente por CEO Android.

Reglas:
- solo HTTPS;
- versionCode creciente;
- SHA-256 y tamaño exactos;
- el APK debe conservar package name y certificado firmante;
- la app nunca instala silenciosamente: Android mantiene confirmación humana;
- dev y stable son canales separados.

Los valores iniciales no anuncian una versión superior, por lo que la primera app mostrará que está actualizada.
