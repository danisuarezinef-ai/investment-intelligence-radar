from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


_SECRET_RE = re.compile(r"(?i)(token|secret|password|private[_-]?key|api[_-]?key|authorization)")


def _safe_load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _redact(value: Any, key: str = "") -> Any:
    if _SECRET_RE.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {str(k): _redact(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value[:100]]
    if isinstance(value, str):
        # Avoid leaking full user paths into portable diagnostics.
        value = re.sub(r"(?i)[A-Z]:\\Users\\[^\\]+", r"%USERPROFILE%", value)
        return value[:4000]
    return value


@dataclass(slots=True)
class UpdateDiagnosis:
    code: str
    severity: str
    headline: str
    explanation: str
    autonomous_recovery: bool
    human_action_required: bool


class UpdateDiagnostics:
    """Build one redacted, operator-readable update diagnosis."""

    def __init__(self, updates_root: str | Path):
        self.root = Path(updates_root)

    def classify(self) -> UpdateDiagnosis:
        progress = _safe_load(self.root / "progress.json")
        restart = _safe_load(self.root / "restart-progress.json")
        supervision = _safe_load(self.root / "last-restart-supervision.json")
        phase = str((restart if float(restart.get("updated_at_epoch") or 0) >= float(progress.get("updated_at_epoch") or 0) else progress).get("phase") or "").lower()
        reason = str(restart.get("reason") or supervision.get("reason") or progress.get("reason") or "")

        if phase == "healthy":
            return UpdateDiagnosis("healthy", "ok", "Actualización completada", "La nueva versión confirmó su estado de salud.", True, False)
        if phase == "rolled_back":
            return UpdateDiagnosis("rolled_back", "warning", "CEO volvió a la versión anterior", reason or "La candidata no superó la comprobación de salud.", True, False)
        if phase == "preflight_failed":
            return UpdateDiagnosis("preflight_failed", "warning", "Candidata bloqueada antes de instalar", reason or "La prueba previa detectó un problema y conservó la versión actual.", True, False)
        if phase in {"preflight", "preflight_ok", "launching_new_version", "health_check", "rollback", "waiting_old_process"}:
            return UpdateDiagnosis("in_progress", "info", "Actualización en curso", "CEO está verificando o recuperando el relevo de versión.", True, False)
        if phase in {"download", "verify", "stage", "staged"}:
            return UpdateDiagnosis("preparing", "info", "Preparando actualización", "La versión activa todavía no se modifica.", True, False)
        if reason:
            return UpdateDiagnosis("diagnostic_error", "warning", "Incidencia de actualización", reason, False, True)
        return UpdateDiagnosis("idle", "ok", "Actualizador en espera", "No hay una transición de versión activa.", True, False)

    def bundle(self) -> dict[str, Any]:
        diagnosis = self.classify()
        names = (
            "progress.json", "restart-progress.json", "last-restart-supervision.json",
            "operation.json", "current.json", "previous.json", "manifest_state.json",
            "rejections.json",
        )
        snapshots = {name: _redact(_safe_load(self.root / name), name) for name in names if (self.root / name).exists()}
        return {
            "schema_version": 1,
            "generated_at_epoch": time.time(),
            "diagnosis": asdict(diagnosis),
            "snapshots": snapshots,
            "contains_private_key": False,
            "contains_credentials": False,
        }
