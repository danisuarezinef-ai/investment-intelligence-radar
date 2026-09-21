from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, Field


class FileWriteDirective(BaseModel):
    """Reversible workspace-local file write requested by an AI worker."""

    path: str = Field(min_length=1, max_length=240)
    content: str = ""


class WorkerDirective(BaseModel):
    """Machine-readable footer emitted by an AI worker turn."""

    status: Literal[
        "complete", "continue", "correct", "deepen", "spawn", "review", "escalate", "retry"
    ] = "complete"
    reason: str = ""
    next_instruction: str | None = None
    followups: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    requires_user: bool = False
    decision_title: str | None = None
    decision_options: list[str] = Field(default_factory=list)
    recommendation: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=86400)
    evidence_refs: list[str] = Field(default_factory=list)
    write_files: list[FileWriteDirective] = Field(default_factory=list)


_TAG_RE = re.compile(r"<CEO_RESULT>\s*(\{.*?\})\s*</CEO_RESULT>", re.IGNORECASE | re.DOTALL)


def extract_directive(text: str) -> WorkerDirective | None:
    """Extract CEO's control footer without requiring the substantive answer to be JSON."""

    match = _TAG_RE.search(text or "")
    if not match:
        return None
    try:
        payload = json.loads(match.group(1))
        return WorkerDirective.model_validate(payload)
    except (json.JSONDecodeError, ValueError):
        return None


def strip_directive(text: str) -> str:
    return _TAG_RE.sub("", text or "").rstrip()
