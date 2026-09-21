# FREE_BROWSER_AI_WORKER — objetivo y límites

Fecha de inicio: 2026-09-21
Rama aislada: `free-browser-ai-worker`

## Objetivo

Permitir que CEO utilice IAs gratuitas mediante sus interfaces web normales, como lo
haría una persona:

`abrir Chrome -> abrir IA -> pegar prompt -> esperar -> leer/copiar respuesta -> decidir siguiente prompt`

Esto debe permitir tareas de investigación, redacción y también programación sin
depender de una API de pago.

## Principio de diseño

Una interacción web de IA no se trata como un trabajador de 30+ minutos. CEO debe
adaptar la unidad de trabajo al tamaño que razonablemente pueda resolverse en una
respuesta.

Antes de enviar un prompt, CEO estima:

- complejidad;
- longitud esperada de respuesta;
- contexto necesario;
- número de turnos razonables;
- riesgo de truncamiento.

Si una tarea es demasiado grande, se divide antes de enviarla.

## Primera meta técnica

Construir un Browser AI Worker mínimo para ChatGPT web:

1. abrir Chrome con un perfil persistente de CEO;
2. reutilizar la sesión iniciada por el usuario;
3. abrir ChatGPT;
4. introducir un prompt acotado;
5. esperar a que la respuesta termine/estabilice;
6. extraer la última respuesta;
7. devolverla a CEO como texto;
8. continuar en el mismo chat si se necesita otro turno.

No se automatizan CAPTCHA, 2FA, compras, suscripciones ni accesos restringidos.

## Programación mediante IA web

El camino objetivo es:

`objetivo de programación`
-> CEO selecciona archivos/contexto mínimo
-> genera prompt pequeño
-> Browser AI Worker obtiene propuesta
-> CEO exige salida estructurada (diff/archivos)
-> aplica cambios sólo en sandbox/rama candidata
-> ejecuta tests
-> devuelve errores concretos a la misma conversación
-> IA corrige
-> CEO vuelve a probar
-> candidato verificado
-> promoción/merge sólo con política de aprobación correspondiente.

Esto permite que CEO pueda trabajar sobre su propio código o sobre Radar usando IAs
gratuitas en navegador.

## Lo que NO se hace en esta rama

- no se modifica `MVP_FIELD`;
- no se publica una nueva versión de CEO;
- no se toca el canal estable;
- no se cambia Android;
- no se añade recovery complejo;
- no se usa OpenAI API de pago;
- no se compran créditos;
- no se fusiona código generado automáticamente en producción.

## Estrategia técnica

La automatización de Chrome usa Chrome DevTools Protocol desde Windows/PowerShell.
No depende de coordenadas de pantalla. Los adaptadores de cada IA contienen varias
estrategias/selectores y deben fallar de forma clara cuando la interfaz cambie.

El primer adaptador es ChatGPT web. Gemini web puede añadirse después de demostrar
el camino básico.

## Gate para considerar útil este worker

No se mide por tests o número de prompts. El primer gate real será:

- CEO abre ChatGPT web con sesión gratuita existente;
- envía un prompt;
- captura la respuesta correcta;
- realiza al menos un segundo turno en la misma conversación;
- guarda un artefacto solicitado;
- no requiere API de pago.

Hasta esa prueba física: `BROWSER_FIELD_VERIFIED=false`.
