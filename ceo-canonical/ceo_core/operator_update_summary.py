from __future__ import annotations

from typing import Any

from .update_diagnostics import UpdateDiagnostics
from .update_state_machine import UpdateStateMachine
from .update_transaction import UpdateTransactionJournal


def build_operator_update_summary(updater: Any, *, current_version: str, include_remote: bool = False) -> dict[str, Any]:
    status = updater.status(current_version=current_version, include_remote=include_remote)
    progress = updater.progress()
    view = UpdateStateMachine.view(status=status, progress=progress)
    diagnosis = UpdateDiagnostics(updater.root).bundle()["diagnosis"]
    journal = UpdateTransactionJournal(updater.root)
    return {
        "state": view,
        "diagnosis": diagnosis,
        "transaction_integrity": journal.verify(),
        "recovery_hint": journal.recovery_hint(),
        "current_version": current_version,
        "technical_details_collapsed_by_default": True,
        "human_action_required": bool(view.get("human_action_required") or diagnosis.get("human_action_required")),
    }
