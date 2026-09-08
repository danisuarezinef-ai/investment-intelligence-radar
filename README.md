# Investment Intelligence Radar

## Interfaz de escritorio canónica

`radar_desktop_v2.py` es la única fuente de verdad de la interfaz Windows que
PyInstaller empaqueta como `InvestmentIntelligenceRadar.exe`. `radar_desktop.py`
se conserva únicamente como lanzador compatible. El worker,
actualizador y laboratorio son procesos auxiliares; no mantienen una segunda
interfaz de escritorio.

Repositorio maestro para la compilación de Investment Intelligence Radar v1.0 para Windows.
