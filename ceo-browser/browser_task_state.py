from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any


TERMINAL_STATUSES = {"COMPLETED", "FAILED", "CANCELLED", "CORRUPT"}
RESUMABLE_STATUSES = {"PENDING", "RUNNING", "WAITING_RETRY", "WAITING_HUMAN"}

SAFE_RETRY_BROWSER_STATUSES = {
    "BROWSER_CONTROL_FAILED",
    "BROWSER_CONTROL_BAD_JSON",
    "BROWSER_CONTROL_BAD_RESULT",
    "SESSION_NOT_READY",
    "INPUT_NOT_FOUND",
    "PROMPT_NOT_SUBMITTED",
}
AMBIGUOUS_BROWSER_STATUSES = {
    "RESPONSE_TIMEOUT",
    "ERROR",
}
HUMAN_ACTION_STATUSES = {
    "LOGIN_REQUIRED",
    "BROWSER_LOGIN_REQUIRED",
}
PERMANENT_BROWSER_STATUSES = {
    "PROMPT_INPUT_MISMATCH",
    "CONVERSATION_DRIFT",
    "ARTIFACT_CONTENT_MISMATCH",
}


def sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def utc_epoch() -> int:
    return int(time.time())


@dataclass
class BrowserCheckpoint:
    turn_index: int
    conversation_url: str | None
    prompt_sha256: str
    response_sha256: str = ""
    status: str = "TURN_STARTED"
    created_at: int = field(default_factory=utc_epoch)


@dataclass
class BrowserTaskRecord:
    task_id: str
    idempotency_key: str
    objective_sha256: str
    status: str = "PENDING"
    task_kind: str = "artifact"
    conversation_url: str | None = None
    artifact_path: str = ""
    artifact_sha256: str = ""
    artifact_chars: int = 0
    attempts: int = 0
    max_retries: int = 1
    last_error_status: str = ""
    last_error_detail: str = ""
    created_at: int = field(default_factory=utc_epoch)
    updated_at: int = field(default_factory=utc_epoch)
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def touch(self) -> None:
        self.updated_at = utc_epoch()


class BrowserTaskLedger:
    """Crash-safe JSON ledger for browser work.

    One file per task avoids rewriting a global database and keeps recovery local.
    Writes use os.replace so an interrupted write never leaves a half-written record.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _safe_id(self, task_id: str) -> str:
        raw = str(task_id or "").strip()
        if not raw:
            raise ValueError("task_id required")
        safe = "".join(c for c in raw if c.isalnum() or c in "-_.")
        if safe != raw or safe in {".", ".."}:
            raise ValueError("unsafe task_id")
        return safe

    def path_for(self, task_id: str) -> Path:
        return self.root / f"{self._safe_id(task_id)}.json"

    def save(self, record: BrowserTaskRecord) -> Path:
        record.touch()
        target = self.path_for(record.task_id)
        temp = target.with_name(target.name + f".tmp-{uuid.uuid4().hex[:8]}")
        payload = json.dumps(asdict(record), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            temp.write_text(payload, encoding="utf-8")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        return target

    def load(self, task_id: str) -> BrowserTaskRecord | None:
        path = self.path_for(task_id)
        if not path.is_file():
            return None
        row = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(row, dict):
            raise ValueError("task ledger row must be an object")
        return BrowserTaskRecord(**row)

    def find_by_idempotency(self, key: str) -> BrowserTaskRecord | None:
        wanted = str(key or "").strip()
        if not wanted:
            return None
        for path in sorted(self.root.glob("*.json")):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if isinstance(row, dict) and row.get("idempotency_key") == wanted:
                return BrowserTaskRecord(**row)
        return None

    def append_checkpoint(
        self,
        record: BrowserTaskRecord,
        *,
        turn_index: int,
        prompt: str,
        conversation_url: str | None,
        response: str = "",
        status: str,
    ) -> BrowserTaskRecord:
        cp = BrowserCheckpoint(
            turn_index=int(turn_index),
            conversation_url=conversation_url,
            prompt_sha256=sha256_text(prompt),
            response_sha256=sha256_text(response) if response else "",
            status=str(status),
        )
        record.checkpoints.append(asdict(cp))
        record.conversation_url = conversation_url or record.conversation_url
        record.status = "RUNNING" if status not in TERMINAL_STATUSES else status
        self.save(record)
        return record


def classify_browser_failure(status: str, detail: str = "") -> str:
    value = str(status or "").strip().upper()
    combined = f"{value} {detail}".upper()
    if value in HUMAN_ACTION_STATUSES or "LOGIN_REQUIRED" in combined or "CAPTCHA" in combined or "2FA" in combined:
        return "HUMAN_ACTION"
    if value in PERMANENT_BROWSER_STATUSES:
        return "PERMANENT"
    if value in AMBIGUOUS_BROWSER_STATUSES:
        return "AMBIGUOUS"
    if value in SAFE_RETRY_BROWSER_STATUSES:
        return "SAFE_RETRY"
    if any(x in combined for x in ["CHROME DEVTOOLS DID NOT BECOME AVAILABLE", "NO DEBUGGABLE PAGE TARGET", "CONNECTION REFUSED"]):
        return "SAFE_RETRY"
    if any(x in combined for x in ["RESPONSE TIMEOUT", "CDP RECEIVE TIMEOUT", "SOCKET CLOSED", "TARGET CLOSED"]):
        return "AMBIGUOUS"
    return "PERMANENT"


class BoundedRecoveryPolicy:
    """At most one safe automatic retry; ambiguous post-send failures never auto-repeat."""

    def __init__(self, max_retries: int = 1) -> None:
        self.max_retries = max(0, min(1, int(max_retries)))

    def decision(self, *, attempts: int, status: str, detail: str = "") -> str:
        kind = classify_browser_failure(status, detail)
        if kind == "HUMAN_ACTION":
            return "WAIT_HUMAN"
        if kind == "AMBIGUOUS":
            return "WAIT_REVIEW"
        if kind == "SAFE_RETRY" and int(attempts) <= self.max_retries:
            return "RETRY_ONCE"
        return "STOP"


def verify_artifact_integrity(record: BrowserTaskRecord) -> tuple[bool, str]:
    if not record.artifact_path or not record.artifact_sha256:
        return False, "artifact evidence missing"
    path = Path(record.artifact_path)
    if not path.is_file():
        return False, "artifact file missing"
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != record.artifact_sha256:
        return False, "artifact sha256 mismatch"
    if record.artifact_chars and len(path.read_text(encoding="utf-8")) != int(record.artifact_chars):
        return False, "artifact char count mismatch"
    return True, "artifact integrity verified"
