# CEO — CHAT SYNC PROTOCOL

## Objetivo

Evitar que distintos chats de ChatGPT trabajen con estados incompatibles del proyecto CEO.

## Fuente de verdad

Orden de precedencia:

1. HEAD real del branch de trabajo.
2. `CEO_MASTER_CHECKPOINT_CURRENT.md`.
3. Evidencia física del trial actual.
4. Contratos Bxx.
5. Memoria/contexto de un chat.

La memoria de una conversación nunca prevalece sobre el repositorio.

## Al abrir/reanudar cualquier chat de CEO

El chat debe:

1. recuperar `CEO_MASTER_CHECKPOINT_CURRENT.md`;
2. comprobar HEAD de `free-browser-ai-worker`;
3. revisar commits posteriores al HEAD registrado en el checkpoint;
4. leer `CURRENT_TRIAL.json`/evidencia sólo si el usuario aporta esos archivos o si están disponibles en la fuente conectada;
5. declarar qué estado toma como canónico antes de hacer cambios importantes.

## Al terminar un hito

Actualizar el checkpoint si cambia cualquiera de estos puntos:

- HEAD/branch canónico;
- workflow canónico;
- estado físico B14/B18/B20/B29/B30;
- autorización/desbloqueo B38;
- arquitectura multIA;
- invariantes de seguridad;
- launcher/paquete físico vigente;
- siguiente movimiento canónico.

## Regla anti-drift

Si dos chats discrepan:

- no elegir por fecha del chat;
- no mezclar las dos líneas;
- comparar ambos con repo HEAD y evidencia física;
- conservar sólo el estado que esté respaldado por commits/evidencias actuales.

## Frase corta para reanudar desde cualquier chat

`Sincroniza CEO con ceo-browser/CEO_MASTER_CHECKPOINT_CURRENT.md y el HEAD actual de free-browser-ai-worker; ignora estados del chat que hayan quedado atrás.`
