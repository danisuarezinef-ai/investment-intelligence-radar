from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class UpdateView:
    state: str
    headline: str
    detail: str
    action_label: str
    action_enabled: bool
    progress_percent: int
    human_action_required: bool


_PHASES = {
    "download": ("downloading", "Descargando actualización", "La versión actual sigue funcionando.", 20),
    "verify": ("verifying", "Verificando actualización", "Comprobando firma, integridad y contrato.", 40),
    "stage": ("staging", "Preparando actualización", "La candidata se prepara de forma aislada.", 55),
    "staged": ("ready", "Actualización preparada", "Lista para prueba previa de arranque.", 65),
    "preflight": ("preflight", "Probando nueva versión", "CEO prueba la candidata sin cambiar la versión activa.", 72),
    "preflight_ok": ("ready", "Prueba previa superada", "La candidata puede activarse cuando lo confirmes.", 80),
    "preflight_failed": ("blocked", "Candidata bloqueada", "La versión actual permanece intacta.", 100),
    "waiting_old_process": ("activating", "Preparando relevo", "Esperando cierre seguro de la versión anterior.", 82),
    "launching_new_version": ("activating", "Activando nueva versión", "CEO está iniciando la candidata.", 88),
    "health_check": ("health_check", "Comprobando salud", "Verificando que la nueva versión funciona correctamente.", 94),
    "healthy": ("healthy", "Actualización completada", "La nueva versión está sana.", 100),
    "rollback": ("recovering", "Recuperando versión anterior", "CEO está revirtiendo automáticamente.", 96),
    "rolled_back": ("rolled_back", "Versión anterior restaurada", "La candidata no se mantuvo activa.", 100),
}


class UpdateStateMachine:
    @classmethod
    def view(cls, *, status: dict[str, Any], progress: dict[str, Any]) -> dict[str, Any]:
        phase = str(progress.get("phase") or "").lower()
        if phase in _PHASES:
            state, headline, detail, default_pct = _PHASES[phase]
            detail = str(progress.get("reason") or detail)
            pct = int(max(0, min(100, float(progress.get("percent") or default_pct))))
            human = state == "ready"
            action = "Instalar y reiniciar" if state == "ready" else ("Comprobar de nuevo" if state in {"blocked", "rolled_back"} else "")
            return asdict(UpdateView(state, headline, detail, action, bool(action), pct, human))

        staged = [x for x in (status.get("staged") or []) if isinstance(x, dict) and not x.get("installed") and not x.get("rolled_back")]
        if staged:
            return asdict(UpdateView("ready", "Actualización preparada", str(staged[0].get("version") or ""), "Instalar y reiniciar", True, 65, True))
        if status.get("available"):
            version = str((status.get("remote") or {}).get("version") or "")
            return asdict(UpdateView("available", "Nueva versión disponible", version, "Actualizar CEO", True, 0, True))
        if status.get("error"):
            return asdict(UpdateView("blocked", "No se pudo comprobar la actualización", str(status.get("error")), "Reintentar", True, 0, False))
        return asdict(UpdateView("idle", "CEO está al día", str(status.get("current_version") or ""), "", False, 0, False))
