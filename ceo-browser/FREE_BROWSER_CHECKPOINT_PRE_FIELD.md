# FREE_BROWSER_AI_WORKER — checkpoint pre-campo

Fecha: 2026-09-21
Rama: `free-browser-ai-worker`
Estado: **PROTOTIPO AISLADO / NO INTEGRADO / NO FIELD VERIFIED**

## Objetivo que se persigue

CEO debe poder usar IAs gratuitas a través de Chrome como lo haría una persona y,
sobre esa capacidad, realizar también tareas de programación:

`objetivo -> prompt acotado -> ChatGPT web -> respuesta -> acción local -> test -> siguiente prompt`

No depende de OpenAI API ni de una cuenta API de pago.

## Lo implementado

### 1. Unidad de trabajo adaptada a una respuesta IA

`browser_ai_worker.py` contiene:

- clasificación de tamaño de tarea;
- presupuesto máximo de contexto/prompt;
- decisión de dividir antes de enviar una tarea demasiado grande;
- protocolo `CEO_DONE / CEO_NEXT / CEO_PATCH`;
- constructor específico de prompts de programación;
- prompts de corrección basados en fallos de tests.

La regla central es que CEO no entregue a una IA web una tarea que razonablemente
requiera una respuesta de 30+ minutos.

### 2. Control real de Chrome sin API de IA

`windows_chatgpt_cdp_driver.ps1`:

- abre Chrome/Edge con perfil persistente;
- se conecta mediante Chrome DevTools Protocol;
- busca el cuadro de prompt mediante una receta;
- introduce el prompt;
- pulsa Enviar;
- espera la respuesta;
- detecta estabilización;
- extrae el último mensaje del asistente;
- devuelve la URL de conversación;
- puede continuar un segundo turno en la misma conversación.

No usa coordenadas de pantalla.

### 3. Adaptador ChatGPT web

`recipes/chatgpt_web.json` define selectores alternativos para:

- input;
- envío;
- respuesta;
- estado de generación.

La sesión se basa en login persistente del usuario. No se automatiza ni evita CAPTCHA
o 2FA.

### 4. Programación usando ChatGPT web

`programming_browser_loop.py` implementa un bucle acotado:

1. CEO lee sólo archivos relevantes.
2. Construye un prompt pequeño.
3. ChatGPT web devuelve un diff dentro de `CEO_PATCH`.
4. CEO valida el diff con `git apply --check`.
5. Lo aplica sólo en un sandbox/worktree.
6. Ejecuta un comando de test predefinido por CEO, no por la IA.
7. Si falla, devuelve el error concreto al mismo chat.
8. ChatGPT propone una corrección.
9. CEO vuelve a probar.
10. Si pasa, queda un candidato verificado.

Límite actual: máximo 3 turnos (configurable entre 1 y 4).

El loop NO:

- hace commit;
- hace push;
- hace merge;
- toca producción;
- elige comandos arbitrarios devueltos por la IA;
- compra créditos;
- utiliza OpenAI API.

## Evidencia actual

Workflow final: `35641128679` — PASS.

Probado en Windows CI:

- contratos Python: PASS;
- tamaño/budget de prompts: PASS;
- protocolo de diff: PASS;
- Chrome real controlado mediante CDP: PASS;
- primer turno web simulado en página real de Chrome: PASS;
- segundo turno en la misma conversación: PASS;
- sandbox git + patch + test fallido + segundo parche + test correcto: PASS;
- fallo de navegador termina sin recovery loop: PASS;
- comprobación FREE-ONLY / no API / no commit-push: PASS.

La página usada en CI es un harness local que imita la estructura de una IA web. Por
tanto esto demuestra el mecanismo de navegador, pero NO demuestra todavía la página
real de ChatGPT.

## Qué NO se ha tocado

- `MVP_FIELD`: sin modificaciones.
- CEO estable: sin actualización.
- canal de releases: sin cambios.
- Android: sin cambios.
- Radar: sin cambios productivos.

## Siguiente gate y única prioridad de esta rama

**BROWSER_FIELD_GATE_01**

En el Windows físico:

1. abrir Chrome con el perfil persistente de CEO;
2. si hace falta, el usuario inicia sesión manualmente una sola vez en ChatGPT;
3. CEO envía un prompt pequeño a ChatGPT web;
4. captura la respuesta correcta;
5. envía un segundo prompt en el mismo chat;
6. captura la segunda respuesta.

Criterio:
`BROWSER_FIELD_VERIFIED=true` sólo si ambos turnos reales funcionan.

Después:

**BROWSER_CODE_GATE_02**

Un repositorio sandbox diminuto con un bug:

`ChatGPT web -> diff -> aplicar -> tests -> corrección si hace falta -> PASS`.

Sólo después de esos dos gates se permite probar una modificación real de CEO o Radar
en una rama candidata aislada.

## Regla de proceso

NO añadir más arquitectura de navegador antes de BROWSER_FIELD_GATE_01.

Si ChatGPT web falla físicamente, corregir sólo la causa concreta:
selector, sesión, envío, espera o extracción. No añadir recovery general, scheduler,
multi-provider ni capas de integridad.
