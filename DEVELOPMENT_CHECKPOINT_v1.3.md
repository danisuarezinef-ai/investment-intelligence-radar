# Investment Intelligence Radar — Development checkpoint v1.3

Fecha: 2026-09-07

## Estado de la fase

La aplicación ha superado la fase de reparación del instalador/actualizador y vuelve a desarrollo funcional.

## Implementado

- Aplicación nativa Windows con scroll vertical y controles PC/Cloud compactos.
- Botón de actualización dentro de la aplicación.
- Actualizador rediseñado con barra lateral de scroll y botón `INSTALAR ACTUALIZACIÓN` siempre visible.
- Worker local ON/OFF y Cloud 24/7 separado.
- Histórico de mercado para rankings y simulación.
- Ranking de rentabilidad histórica y oportunidades por nivel de riesgo.
- Simulador paper, con trading real bloqueado.
- Cloud API de estado, snapshot y control.
- API móvil de solo lectura `/mobile/dashboard` preparada para clientes Android/iPhone/PWA.
- Identidad de nodo Windows y heartbeat PC→Cloud preparado.
- Sistema de notificaciones persistentes en base de datos.
- Detector de silencio: identifica movimientos anómalos por z-score sin catalizador público reciente detectado.
- Reputación dinámica de fuentes basada en cobertura, eventos vinculables a activos y movimiento posterior observado.
- Panel Windows de Inteligencia: alertas de silencio, reputación de fuentes y notificaciones.
- Recolección regulatoria SEC EDGAR.
- Recolección científica Europe PMC.
- Recolección ampliada de noticias por temas de inversión mediante RSS.
- Recolección arXiv para IA, ML, quantum, materiales y sistemas energéticos/electrónicos.
- Pruebas automáticas para notificaciones, sincronización de nodos y detector de silencio.
- Corrección del bloqueo SQLite que impedía crear la notificación del detector de silencio.

## Infraestructura

- Repositorio GitHub: `danisuarezinef-ai/investment-intelligence-radar`.
- Build Windows automático en `windows-latest` con pytest + PyInstaller + Inno Setup.
- Canal estable de actualización publicado desde la rama `updates` cuando CI termina correctamente.
- Railway: servicio `radar-cloud` conectado al repositorio y preparado para ejecución continua.

## Pendiente prioritario

1. Verificar CI Windows de la nueva fase y publicar el paquete estable solo si todos los tests pasan.
2. Verificar despliegue Railway con los nuevos colectores e inteligencia.
3. Sustituir la persistencia SQLite efímera del Cloud por almacenamiento central duradero (PostgreSQL/Supabase o volumen persistente).
4. Convertir `/mobile/dashboard` en cliente móvil/PWA utilizable e incorporar notificaciones push reales.
5. Ampliar el simulador a cinco agentes paper independientes: conservador, equilibrado, agresivo, alta convicción y experimental.
6. Añadir backtesting point-in-time completo, costes, spread, FX, benchmark, drawdown y Sharpe por agente.
7. Mejorar la vinculación causal noticia→activo→sector→segundo/tercer orden y el aprendizaje de reputación por tema/horizonte.
8. Preparar sincronización bidireccional segura de configuración, alertas y cartera paper entre PC y Cloud.

## Restricción permanente

El trading real permanece desactivado. Ninguna señal del detector de silencio o del motor de scoring se convierte automáticamente en una orden real.
