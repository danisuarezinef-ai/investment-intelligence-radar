from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from ceo_core.models import ProjectState


class NotificationHub:
    """In-app notification queue; mobile/desktop push adapters can subscribe later."""

    def emit(self, state: ProjectState, *, title: str, body: str, severity: str = "info", data: dict | None = None) -> dict:
        event = {
            "id": uuid4().hex,
            "title": title,
            "body": body,
            "severity": severity,
            "data": data or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
            "read": False,
        }
        queue = state.metadata.setdefault("notifications", [])
        queue.append(event)
        # Keep checkpoint bounded.
        if len(queue) > 500:
            del queue[:-500]
        return event

    def summary(self, state: ProjectState, unread_only: bool = True) -> dict:
        queue = state.metadata.get("notifications", [])
        if unread_only:
            queue = [n for n in queue if not n.get("read")]
        by_severity: dict[str, int] = {}
        for n in queue:
            sev = str(n.get("severity", "info")); by_severity[sev] = by_severity.get(sev, 0) + 1
        return {"total": len(queue), "by_severity": by_severity, "latest": queue[-5:]}
