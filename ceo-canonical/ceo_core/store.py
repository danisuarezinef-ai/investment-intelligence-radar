from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from pathlib import Path

from .migrations import migrate_state
from .models import ProjectState, TaskStatus
from .operational_resilience import ResumeCoordinator


class CheckpointStore(ABC):
    @abstractmethod
    def save(self, state: ProjectState) -> None: ...

    @abstractmethod
    def load(self) -> ProjectState | None: ...


class JsonCheckpointStore(CheckpointStore):
    """Atomic current checkpoint + bounded version history + schema migrations."""

    def __init__(self, path: str | Path = "data/project_state.json", *, history_limit: int = 30) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.backup_path = self.path.with_suffix(".bak")
        self.history_dir = self.path.parent / "checkpoints"
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.history_limit = max(3, history_limit)
        self._last_history_fingerprint: str | None = None
        self._last_history_ts = 0.0

    def save(self, state: ProjectState) -> None:
        payload = state.model_dump_json(indent=2)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(payload, encoding="utf-8")
        if self.path.exists():
            try:
                self.backup_path.write_bytes(self.path.read_bytes())
            except OSError:
                pass
        tmp.replace(self.path)
        # History is intentionally less frequent than hot checkpoints to avoid disk churn.
        fingerprint = f"{state.goal}:{state.progress}:{len(state.tasks)}:{state.completed_at}:{len(state.decisions)}"
        now = time.time()
        if fingerprint != self._last_history_fingerprint and (now - self._last_history_ts >= 1.0 or state.completed_at):
            stamp = int(now * 1000)
            history_path = self.history_dir / f"checkpoint-{stamp}.json"
            while history_path.exists():
                stamp += 1
                history_path = self.history_dir / f"checkpoint-{stamp}.json"
            history_path.write_text(payload, encoding="utf-8")
            self._last_history_fingerprint = fingerprint; self._last_history_ts = now
            self._prune_history()

    def _parse(self, path: Path) -> ProjectState | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ProjectState.model_validate(migrate_state(data))
        except Exception:
            return None

    def load(self) -> ProjectState | None:
        for candidate in (self.path, self.backup_path):
            if candidate.exists():
                state = self._parse(candidate)
                if state:
                    return state
        # Last-resort crash recovery from newest versioned checkpoint.
        for candidate in reversed(self.history()):
            state = self._parse(candidate)
            if state:
                return state
        return None

    def history(self) -> list[Path]:
        return sorted(self.history_dir.glob("checkpoint-*.json"))

    def restore(self, checkpoint: str | Path) -> ProjectState:
        path = Path(checkpoint)
        if not path.is_absolute():
            path = self.history_dir / path
        state = self._parse(path)
        if not state:
            raise ValueError(f"Invalid checkpoint: {path}")
        self.save(state)
        return state

    def _prune_history(self) -> None:
        rows = self.history()
        for old in rows[:-self.history_limit]:
            try: old.unlink()
            except OSError: pass

    @staticmethod
    def prepare_for_resume(state: ProjectState) -> ProjectState:
        if state.cancelled_at is not None or state.metadata.get("operator_cancelled"):
            state.paused = True
            state.autonomy_enabled = False
            return state
        ResumeCoordinator().prepare(state, source="json_checkpoint_restart")
        return state
