from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from .models import ProjectState, Task


@dataclass(slots=True)
class EvidenceRecord:
    task_id: str
    kind: str
    ref: str
    sha256: str
    size_bytes: int
    observed_at: str

    def to_dict(self) -> dict:
        return asdict(self)


class DeliverableEvidenceEngineV1:
    KEY = "deliverable_evidence_v1"

    def record_text(self, state: ProjectState, task: Task, text: str, *, kind: str = "result") -> EvidenceRecord:
        payload = text.encode("utf-8")
        record = EvidenceRecord(task.id, kind, f"task:{task.id}:{kind}", sha256(payload).hexdigest(), len(payload), datetime.now(timezone.utc).isoformat())
        self._append(state, task, record)
        return record

    def record_file(self, state: ProjectState, task: Task, path: str | Path, *, root: str | Path | None = None) -> EvidenceRecord:
        p = Path(path).resolve()
        if not p.is_file():
            raise FileNotFoundError(p)
        if root is not None:
            r = Path(root).resolve()
            try:
                p.relative_to(r)
            except ValueError as exc:
                raise PermissionError("artifact outside allowed root") from exc
        data = p.read_bytes()
        record = EvidenceRecord(task.id, "file", str(p), sha256(data).hexdigest(), len(data), datetime.now(timezone.utc).isoformat())
        self._append(state, task, record)
        return record

    def _append(self, state: ProjectState, task: Task, record: EvidenceRecord) -> None:
        rows = state.metadata.setdefault(self.KEY, [])
        rows.append(record.to_dict())
        del rows[:-5000]
        refs = task.metadata.setdefault("evidence_refs", [])
        if record.ref not in refs:
            refs.append(record.ref)
        task.metadata["acceptance_evidence"] = True
