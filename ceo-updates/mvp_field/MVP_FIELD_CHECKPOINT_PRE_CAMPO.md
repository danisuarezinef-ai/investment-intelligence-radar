# MVP_FIELD — CHECKPOINT PRE-CAMPO

Fecha: 2026-09-21
Rama aislada: `mvp-field-first-real-goal`
Estado: **PREPARADO PARA PRUEBA FÍSICA — NO PRODUCTION READY**

## Objetivo único

`FIELD-MVP-01`

Investigar qué es el entrenamiento en Zona 2, principales beneficios y limitaciones,
usar 5 fuentes fiables diferentes y generar `FIELD_MVP_01.md` de 700–1.000 palabras
con explicación, beneficios, limitaciones, conclusión y fuentes.

## Única métrica

`delivery_pass`

- **PASS** sólo si el archivo existe, cumple el contrato determinista, cinco fuentes
  del propio informe son alcanzables y una verificación fresca e independiente
  confirma el contenido; entonces el objetivo se cierra.
- **FAIL** si cualquiera de esos elementos falla.
- No existen porcentajes, número de tareas ni recoveries que puedan convertir un
  FAIL en PASS.

## Camino ejecutable congelado

Camino normal, exactamente cuatro pasos:

1. `research`: una llamada Gemini genera notas + al menos 7 fuentes candidatas.
2. `draft`: una llamada Gemini redacta el informe.
3. `write`: escritura local de `RESULTADOS_CEO/FIELD_MVP_01.md`.
4. `independent_verify`: comprobaciones deterministas + sondeo real de URLs +
   llamada Gemini en contexto fresco como verificador.

Sólo si el paso 4 falla se permiten dos pasos adicionales:

5. `single_correction`: una única corrección usando sólo la investigación original.
6. `final_verify`: segunda y última verificación.

Cada llamada al proveedor admite el intento inicial + **un único retry**.
No existe otra escalera automática.

## Desactivado por diseño

El ejecutor MVP_FIELD no carga ni usa:

- `ContinuousScheduler`
- `MultiProviderRouter`
- `WorkerRecoverySupervisor`
- `RecoveryStormGuard`
- `ContinuityManager`
- `GoalCompletionGate` complejo
- `IntegrityEngineeringCore`
- `AutonomousProjectLoop`
- `MissionSupervisor`
- `InternalReleaseCoordinator`
- `InAppUpdater`
- self-development
- continuity audits
- actualización/promoción de CEO

## Proveedor

Uno solo: `gemini-interactions`.

La rama reutiliza la clave Gemini que ya esté almacenada mediante DPAPI en Windows;
no crea, reemplaza ni solicita una nueva clave. El paquete incluye el transporte
Gemini de la base congelada, pero no su orquestación compleja.

## Aislamiento

El paquete portátil es paralelo a CEO:

- no instala una nueva versión;
- no modifica el CEO instalado;
- no cambia `current.json`;
- no publica en el canal estable;
- no ejecuta el updater normal;
- usa su propia interfaz local MVP_FIELD.

## Evidencia ejecutada

Workflow focal inicial:
- run `35633074552`: PASS.

Workflow paquete exacto anterior:
- run `35633527822`: PASS.

Endurecimiento de fuentes:
- 5 fuentes utilizadas deben ser alcanzables;
- se extrae título y fragmento HTML para el verificador;
- la investigación pide 7 candidatas para permitir seleccionar 5 válidas;
- sin nuevas capas de recovery.

Workflow focal final:
- run `35633756919`: PASS.

Workflow del ZIP exacto final:
- run `35633756842`: PASS:
  - build portátil;
  - extracción limpia;
  - instalación del runtime congelado;
  - happy path exacto;
  - fail-fast tras un único retry;
  - interfaz mínima;
  - prueba de ausencia de capas congeladas;
  - ZIP/CRC.

## Artefacto exacto

- `CEO_MVP_FIELD_FIRST_REAL_GOAL.zip`
- SHA-256: `1b8281767c05469e33ac76d9a4498681670bbe3c067392aa152fdb1a24c83db1`
- tamaño: `1,166,713 bytes`
- entradas: `528`

Punto de entrada físico futuro:
`MVP_FIELD_PRIMER_OBJETIVO.vbs`

## Regla desde este checkpoint

**NO AÑADIR MÁS FUNCIONES ANTES DE LA PRUEBA FÍSICA.**

El siguiente paso válido es ejecutar el ZIP exacto en el Windows real y observar una
sola métrica: `delivery_pass`.

Si da FAIL, identificar el primer paso que falló y corregir únicamente esa causa raíz.
No crear DEV nuevo, recovery adicional, integrity layer, storm breaker ni auditoría
de continuidad para ocultar el fallo.
