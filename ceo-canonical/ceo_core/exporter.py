from __future__ import annotations

import json
import zipfile
from pathlib import Path

from .final_report import FinalReportBuilder
from .models import ProjectState

SENSITIVE_KEYS = {"api_key", "token", "cookie", "password", "secret", "authorization"}


def _scrub(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if any(s in k.lower() for s in SENSITIVE_KEYS) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list): return [_scrub(v) for v in value]
    return value


class ProjectExporter:
    def export(self, state: ProjectState, destination: str | Path) -> Path:
        destination = Path(destination); destination.parent.mkdir(parents=True, exist_ok=True)
        data = _scrub(state.model_dump(mode="json"))
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("project_state.json", json.dumps(data, indent=2, ensure_ascii=False, default=str))
            zf.writestr("FINAL_REPORT.md", FinalReportBuilder().build(state))
            zf.writestr("README.txt", "CEO de IAs project export. Secrets and browser profiles are intentionally excluded.\n")
        return destination
