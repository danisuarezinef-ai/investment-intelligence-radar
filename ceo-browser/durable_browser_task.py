from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from browser_task_state import (
    BrowserTaskLedger,
    BrowserTaskRecord,
    BoundedRecoveryPolicy,
    sha256_text,
    verify_artifact_integrity,
)
from simple_browser_task import SafeArtifactStore
from browser_ai_worker import BrowserResultProtocol, BrowserTask, PromptSizer


class BrowserTransport(Protocol):
    def ask(self, prompt: str, *, conversation_url: str | None = None) -> dict: ...


def error_status(exc: Exception) -> str:
    text = str(exc or "")
    m = re.match(r"\s*([A-Z][A-Z0-9_]+)\s*:", text)
    return m.group(1) if m else "ERROR"


@dataclass
class DurableRunResult:
    status: str
    success: bool
    reused: bool = False
    artifact_path: str = ""
    artifact_sha256: str = ""
    conversation_url: str | None = None
    failure_reason: str = ""


class DurableArtifactRunner:
    """Idempotent one-artifact browser task with crash-safe local state."""

    def __init__(
        self,
        *,
        transport: BrowserTransport,
        store: SafeArtifactStore,
        ledger: BrowserTaskLedger,
        recovery: BoundedRecoveryPolicy | None = None,
    ) -> None:
        self.transport = transport
        self.store = store
        self.ledger = ledger
        self.recovery = recovery or BoundedRecoveryPolicy(max_retries=1)
        self.sizer = PromptSizer()

    def run(
        self,
        *,
        task_id: str,
        idempotency_key: str,
        objective: str,
        acceptance: list[str] | tuple[str, ...],
        artifact_name: str,
        context: str = "",
    ) -> DurableRunResult:
        objective_digest = sha256_text(objective + "\n" + context + "\n" + artifact_name)

        prior = self.ledger.find_by_idempotency(idempotency_key)
        if prior and prior.status == "COMPLETED":
            ok, detail = verify_artifact_integrity(prior)
            if ok:
                return DurableRunResult(
                    status="REUSED_COMPLETED",
                    success=True,
                    reused=True,
                    artifact_path=prior.artifact_path,
                    artifact_sha256=prior.artifact_sha256,
                    conversation_url=prior.conversation_url,
                )
            prior.status = "CORRUPT"
            prior.last_error_status = "ARTIFACT_INTEGRITY_FAILED"
            prior.last_error_detail = detail
            self.ledger.save(prior)
            return DurableRunResult(
                status="CORRUPT",
                success=False,
                failure_reason=detail,
            )

        record = self.ledger.load(task_id)
        if record is None:
            record = BrowserTaskRecord(
                task_id=task_id,
                idempotency_key=idempotency_key,
                objective_sha256=objective_digest,
                task_kind="artifact",
                metadata={"artifact_name": artifact_name},
            )
            self.ledger.save(record)
        elif record.objective_sha256 != objective_digest:
            return DurableRunResult(
                status="TASK_ID_CONFLICT",
                success=False,
                failure_reason="task_id already belongs to a different objective",
            )
        elif record.status in {"WAITING_REVIEW", "WAITING_HUMAN"}:
            return DurableRunResult(
                status=record.status,
                success=False,
                conversation_url=record.conversation_url,
                failure_reason=record.last_error_detail,
            )

        task = BrowserTask(
            task_id=task_id,
            objective=objective,
            acceptance=tuple(acceptance),
            context=context,
            expected_artifact=artifact_name,
        )
        plan = self.sizer.classify(task)
        if plan.should_split:
            record.status = "FAILED"
            record.last_error_status = "NEEDS_DECOMPOSITION"
            record.last_error_detail = plan.split_reason
            self.ledger.save(record)
            return DurableRunResult(status="NEEDS_DECOMPOSITION", success=False, failure_reason=plan.split_reason)

        while True:
            turn_index = 1 + sum(1 for x in record.checkpoints if x.get("status") == "TURN_DISPATCHING")
            self.ledger.append_checkpoint(
                record,
                turn_index=turn_index,
                prompt=plan.prompt,
                conversation_url=record.conversation_url,
                status="TURN_DISPATCHING",
            )
            try:
                row = self.transport.ask(plan.prompt, conversation_url=record.conversation_url)
            except Exception as exc:
                record.attempts += 1
                status = error_status(exc)
                decision = self.recovery.decision(
                    attempts=record.attempts,
                    status=status,
                    detail=str(exc),
                )
                record.last_error_status = status
                record.last_error_detail = str(exc)
                if decision == "RETRY_ONCE":
                    record.status = "WAITING_RETRY"
                elif decision == "WAIT_HUMAN":
                    record.status = "WAITING_HUMAN"
                elif decision == "WAIT_REVIEW":
                    record.status = "WAITING_REVIEW"
                else:
                    record.status = "FAILED"
                self.ledger.save(record)
                if decision == "RETRY_ONCE":
                    continue
                return DurableRunResult(
                    status=record.status,
                    success=False,
                    conversation_url=record.conversation_url,
                    failure_reason=str(exc),
                )

            response = str(row.get("response") or "")
            conversation_url = str(row.get("conversation_url") or record.conversation_url or "") or None
            self.ledger.append_checkpoint(
                record,
                turn_index=turn_index,
                prompt=plan.prompt,
                conversation_url=conversation_url,
                response=response,
                status="TURN_RESPONSE_CAPTURED",
            )
            parsed = BrowserResultProtocol.parse(response)
            if parsed.get("done") is not True or not parsed.get("artifact"):
                record.status = "FAILED"
                record.last_error_status = "ARTIFACT_PROTOCOL_FAILED"
                record.last_error_detail = "response missing completed structured artifact"
                self.ledger.save(record)
                return DurableRunResult(status="FAILED", success=False, failure_reason=record.last_error_detail)

            body = str(parsed["artifact"])
            path, digest = self.store.write(artifact_name, body)
            record.artifact_path = str(path)
            record.artifact_sha256 = digest
            record.artifact_chars = len(body)
            record.conversation_url = conversation_url
            record.status = "COMPLETED"
            record.last_error_status = ""
            record.last_error_detail = ""
            self.ledger.save(record)
            return DurableRunResult(
                status="COMPLETED",
                success=True,
                artifact_path=str(path),
                artifact_sha256=digest,
                conversation_url=conversation_url,
            )
