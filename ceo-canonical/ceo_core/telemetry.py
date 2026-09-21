from __future__ import annotations

from datetime import datetime, timezone

from .models import ProjectState


class Telemetry:
    def record(self, state: ProjectState, event: str, **values) -> None:
        rows = state.metadata.setdefault("telemetry", [])
        rows.append({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **values})
        if len(rows) > 20_000:
            del rows[:-20_000]

    def provider_summary(self, state: ProjectState) -> dict:
        return dict(state.metadata.get("provider_stats", {}))
