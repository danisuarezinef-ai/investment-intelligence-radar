from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Any

from .models import ProjectState, Task


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ApplicationRecoveryDecision:
    action: str
    retryable: bool
    requires_human: bool
    reason: str
    backoff_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ApplicationRecoveryManager:
    """Durable recovery policy for browser/desktop application failures.

    It never bypasses authentication/CAPTCHA/confirmation gates.  Physical GUI
    recovery still requires Windows field validation; this class makes the decision
    path deterministic and restart-safe.
    """

    AUTH_MARKERS = ("captcha", "sign in", "login required", "2fa", "two-factor", "verification code")
    CLOSED_MARKERS = ("target closed", "page closed", "browser closed", "disconnected", "websocket closed")
    SELECTOR_MARKERS = ("selector", "element not found", "timeout", "detached", "not visible")
    DOWNLOAD_MARKERS = ("download", "partial file", "checksum", "network changed")

    def classify(self, error: str, *, attempt: int = 1) -> ApplicationRecoveryDecision:
        text = str(error or "").lower()
        if any(x in text for x in self.AUTH_MARKERS):
            return ApplicationRecoveryDecision("human_auth_gate", False, True, "authentication_or_captcha")
        if any(x in text for x in self.CLOSED_MARKERS):
            action = "restart_browser" if attempt >= 2 else "rehydrate_session"
            return ApplicationRecoveryDecision(action, True, False, "browser_session_lost", min(20.0, 2.0 ** attempt))
        if any(x in text for x in self.SELECTOR_MARKERS):
            action = "reload_and_relocate" if attempt <= 2 else "reopen_application"
            return ApplicationRecoveryDecision(action, attempt <= 3, False, "ui_state_changed", min(15.0, 1.5 ** attempt))
        if any(x in text for x in self.DOWNLOAD_MARKERS):
            return ApplicationRecoveryDecision("discard_partial_and_retry", True, False, "download_interrupted", min(20.0, 2.0 ** attempt))
        return ApplicationRecoveryDecision("retry_provider", attempt <= 2, False, "transient_application_error", min(10.0, 1.5 ** attempt))

    def record_failure(self, state: ProjectState, task: Task, *, provider: str, error: str) -> dict[str, Any]:
        decision = self.classify(error, attempt=max(1, int(task.attempts)))
        row = {
            "ts": _now(), "task_id": task.id, "provider": provider,
            "error": str(error)[:1000], **decision.to_dict(),
        }
        history = state.metadata.setdefault("application_recovery_history", [])
        history.append(row)
        if len(history) > 1000:
            del history[:-1000]
        task.metadata["application_recovery"] = row
        if decision.requires_human:
            task.metadata["explicit_human_gate"] = True
        return row

    def checkpoint(self, state: ProjectState, task: Task, *, provider: str, url: str | None = None, conversation_id: str | None = None) -> dict[str, Any]:
        row = {
            "ts": _now(), "task_id": task.id, "provider": provider,
            "url": url, "conversation_id": conversation_id or task.conversation_id,
            "stage": task.metadata.get("provider_stage"),
        }
        state.metadata.setdefault("application_session_checkpoints", {})[task.id] = row
        return row
