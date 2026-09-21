from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from pathlib import Path

from .models import ProjectState
from .store import JsonCheckpointStore


@dataclass(slots=True)
class ContinuityReceipt:
    project_id: str
    checkpoint_path: str
    state_sha256: str
    task_count: int
    completed_count: int
    valid: bool

    def to_dict(self) -> dict:
        return asdict(self)


class MissionContinuityV2:
    def checkpoint(self, store: JsonCheckpointStore, state: ProjectState) -> ContinuityReceipt:
        store.save(state)
        path = store.path
        raw = path.read_bytes()
        return ContinuityReceipt(state.id, str(path), sha256(raw).hexdigest(), len(state.tasks), len(state.completed_leaf_tasks), True)

    def resume(self, store: JsonCheckpointStore, receipt: ContinuityReceipt) -> ProjectState:
        path = Path(receipt.checkpoint_path)
        if not path.is_file() or sha256(path.read_bytes()).hexdigest() != receipt.state_sha256:
            raise RuntimeError("checkpoint_identity_mismatch")
        state = store.load()
        if state is None or state.id != receipt.project_id:
            raise RuntimeError("checkpoint_project_mismatch")
        return JsonCheckpointStore.prepare_for_resume(state)
