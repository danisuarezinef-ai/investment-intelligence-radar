from __future__ import annotations

import hashlib
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from browser_ai_worker import BrowserResultProtocol, BrowserTask, PromptSizer


class BrowserTransport(Protocol):
    def ask(self, prompt: str, *, conversation_url: str | None = None) -> dict: ...


@dataclass
class ArtifactTaskResult:
    status: str
    success: bool
    artifact_path: str = ""
    artifact_sha256: str = ""
    artifact_chars: int = 0
    conversation_url: str | None = None
    response: str = ""
    metadata: dict = field(default_factory=dict)
    failure_reason: str = ""


class SafeArtifactStore:
    """Persist browser-produced artifacts only under one CEO-owned directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _resolve_name(self, name: str) -> Path:
        raw = str(name or "").strip()
        if not raw:
            raise ValueError("artifact name required")
        candidate = Path(raw)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError("artifact path must stay inside the artifact root")
        resolved = (self.root / candidate).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("artifact path escapes artifact root") from exc
        return resolved

    def write(self, name: str, content: str) -> tuple[Path, str]:
        body = str(content or "")
        if not body:
            raise ValueError("artifact content is empty")
        target = self._resolve_name(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp = target.with_name(target.name + f".tmp-{uuid.uuid4().hex[:8]}")
        try:
            temp.write_text(body, encoding="utf-8")
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        return target, digest


class BrowserArtifactTaskRunner:
    """Run one bounded web-AI task and persist only its structured artifact."""

    def __init__(
        self,
        *,
        transport: BrowserTransport,
        artifact_store: SafeArtifactStore,
    ) -> None:
        self.transport = transport
        self.artifact_store = artifact_store
        self.sizer = PromptSizer()

    def run(
        self,
        *,
        objective: str,
        acceptance: list[str] | tuple[str, ...],
        artifact_name: str,
        context: str = "",
    ) -> ArtifactTaskResult:
        if not str(objective or "").strip():
            raise ValueError("objective required")
        task = BrowserTask(
            task_id=f"artifact-{uuid.uuid4().hex[:10]}",
            objective=str(objective).strip(),
            acceptance=tuple(str(x) for x in acceptance if str(x).strip()),
            context=str(context or ""),
            expected_artifact=artifact_name,
            programming=False,
        )
        plan = self.sizer.classify(task)
        if plan.should_split:
            return ArtifactTaskResult(
                status="NEEDS_DECOMPOSITION",
                success=False,
                failure_reason=plan.split_reason,
            )

        try:
            row = self.transport.ask(plan.prompt)
        except Exception as exc:
            return ArtifactTaskResult(
                status="BROWSER_FAIL",
                success=False,
                failure_reason=f"{type(exc).__name__}: {exc}",
            )

        response = str(row.get("response") or "")
        parsed = BrowserResultProtocol.parse(response)
        if parsed.get("done") is not True:
            return ArtifactTaskResult(
                status="INCOMPLETE_RESPONSE",
                success=False,
                conversation_url=str(row.get("conversation_url") or "") or None,
                response=response,
                failure_reason="web AI did not return <CEO_DONE>true</CEO_DONE>",
            )

        artifact = str(parsed.get("artifact") or "")
        if not artifact:
            return ArtifactTaskResult(
                status="ARTIFACT_MISSING",
                success=False,
                conversation_url=str(row.get("conversation_url") or "") or None,
                response=response,
                failure_reason="web AI did not return <CEO_ARTIFACT>",
            )

        path, digest = self.artifact_store.write(artifact_name, artifact)
        return ArtifactTaskResult(
            status="ARTIFACT_VERIFIED",
            success=True,
            artifact_path=str(path),
            artifact_sha256=digest,
            artifact_chars=len(artifact),
            conversation_url=str(row.get("conversation_url") or "") or None,
            response=response,
            metadata={
                "task_id": plan.task_id,
                "task_size": plan.task_size.value,
                "expected_turns": plan.expected_turns,
                "api_calls": 0,
                "paid_api_calls": 0,
                "browser_transport": True,
                "send_method": row.get("send_method"),
                "submission_verified": bool(row.get("submission_verified")),
                "completion_reason": row.get("completion_reason"),
            },
        )
