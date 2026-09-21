from __future__ import annotations

from dataclasses import dataclass, asdict

from .models import ProjectState


@dataclass(frozen=True, slots=True)
class ResourceProfile:
    key: str
    label: str
    power_percent: int
    description: str


@dataclass(frozen=True, slots=True)
class AutonomyProfile:
    key: str
    label: str
    enabled: bool
    threshold_delta: float
    description: str


RESOURCE_PROFILES = {
    "low": ResourceProfile("low", "Bajo", 20, "Prioriza estabilidad y bajo consumo de CPU/RAM."),
    "normal": ResourceProfile("normal", "Normal", 50, "Equilibrio entre velocidad y consumo."),
    "high": ResourceProfile("high", "Alto", 80, "Más concurrencia para avanzar más rápido."),
    "maximum": ResourceProfile("maximum", "Máximo", 100, "Usa la capacidad segura disponible sin saltarse límites duros."),
}

AUTONOMY_PROFILES = {
    "supervised": AutonomyProfile("supervised", "Supervisada", False, 0.20, "CEO se detiene ante decisiones que requieren continuidad autónoma."),
    "balanced": AutonomyProfile("balanced", "Equilibrada", True, 0.00, "CEO resuelve decisiones reversibles con umbrales conservadores."),
    "high": AutonomyProfile("high", "Alta", True, -0.10, "CEO auto-resuelve más decisiones reversibles cuando tiene evidencia suficiente."),
    "full": AutonomyProfile("full", "Máxima", True, -0.18, "Máxima continuidad autónoma; las acciones críticas/irreversibles siguen requiriendo permiso."),
}


class OperatorControls:
    def set_resource(self, state: ProjectState, key: str) -> ResourceProfile:
        key = key.strip().lower()
        if key == "max":
            key = "maximum"
        if key not in RESOURCE_PROFILES:
            raise ValueError("resource profile must be low, normal, high or maximum")
        profile = RESOURCE_PROFILES[key]
        state.power_percent = profile.power_percent
        state.metadata["resource_preset"] = profile.key
        state.metadata["resource_profile"] = asdict(profile)
        return profile

    def set_autonomy(self, state: ProjectState, key: str) -> AutonomyProfile:
        key = key.strip().lower()
        if key not in AUTONOMY_PROFILES:
            raise ValueError("autonomy profile must be supervised, balanced, high or full")
        profile = AUTONOMY_PROFILES[key]
        state.autonomy_enabled = profile.enabled
        state.metadata["autonomy_level"] = profile.key
        state.metadata["autonomy_threshold_delta"] = profile.threshold_delta
        state.metadata["autonomy_profile"] = asdict(profile)
        return profile

    def snapshot(self, state: ProjectState) -> dict:
        rkey = str(state.metadata.get("resource_preset", "custom"))
        akey = str(state.metadata.get("autonomy_level", "balanced"))
        return {
            "resource": asdict(RESOURCE_PROFILES[rkey]) if rkey in RESOURCE_PROFILES else {
                "key": "custom", "label": "Personalizada", "power_percent": state.power_percent,
                "description": "Potencia ajustada manualmente.",
            },
            "autonomy": asdict(AUTONOMY_PROFILES.get(akey, AUTONOMY_PROFILES["balanced"])),
        }
