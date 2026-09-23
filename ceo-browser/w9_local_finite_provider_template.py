from __future__ import annotations

import hashlib
import json
import pathlib
import re

from .contracts import WorkerKind, WorkerProvider, WorkerRequest, WorkerResult
from .models import ProjectState, Task


_ALLOWED_EXT = {".txt", ".md", ".json"}
_FILE_RE = re.compile(
    r"(?<![A-Za-z0-9_])([A-Za-z0-9_.-]+\.(?:txt|md|json))(?![A-Za-z0-9_])",
    re.IGNORECASE,
)
_EXACT_PATTERNS = [
    re.compile(
        r"(?:debe\s+contener\s+exactamente|contenido\s+exacto)\s*:\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:must\s+contain\s+exactly|exact\s+content)\s*:\s*(.+)$",
        re.IGNORECASE | re.DOTALL,
    ),
]


def parse_local_finite_file_goal(goal: str) -> dict | None:
    text = " ".join(str(goal or "").strip().split())
    low = text.lower()
    if not any(
        token in low
        for token in ("crea ", "crear ", "create ", "write ", "escribe ", "escribir ")
    ):
        return None

    matches = list(_FILE_RE.finditer(text))
    if len(matches) != 1:
        return None
    match = matches[0]
    if match.start() > 0 and text[match.start() - 1] in {"/", "\\"}:
        return None
    if match.end() < len(text) and text[match.end()] in {"/", "\\"}:
        return None

    name = match.group(1).strip()
    path = pathlib.Path(name)
    if path.name != name or path.suffix.lower() not in _ALLOWED_EXT or name in {".", ".."}:
        return None

    content = None
    for pattern in _EXACT_PATTERNS:
        match = pattern.search(text)
        if match:
            content = match.group(1).strip()
            break
    if content is None:
        return None

    if len(content) >= 2 and content[0] == content[-1] and content[0] in {"'", '"'}:
        content = content[1:-1]
    content = content.strip()
    if not content or len(content.encode("utf-8")) > 16384:
        return None

    return {
        "path": name,
        "content": content,
        "contract": "local_finite_file_v1",
    }


def configure_local_finite_file_state(
    state: ProjectState,
    spec: dict,
    workspace_root: str | pathlib.Path,
) -> None:
    root = pathlib.Path(workspace_root).resolve()
    root.mkdir(parents=True, exist_ok=True)

    payload = {
        "path": str(spec["path"]),
        "content": str(spec["content"]),
        "workspace_root": str(root),
        "contract": "local_finite_file_v1",
    }

    state.goal_deliverables = [payload["path"]]
    state.goal_success_definition = (
        f"{payload['path']} exists inside the CEO workspace, is non-empty, "
        "contains exactly the requested content, and is independently verified."
    )
    state.completion_criteria = [
        "Requested local file exists inside the managed workspace.",
        "Requested exact content matches byte-for-byte after UTF-8 readback.",
        "Independent local verification completes without network or API use.",
    ]
    state.metadata["local_finite_file_v1"] = {
        "path": payload["path"],
        "mode": "write_modify_verify",
        "network_allowed": False,
        "shell_allowed": False,
        "external_provider_required": False,
    }
    state.metadata["min_goal_audit_evidence_refs"] = 2
    state.metadata["min_goal_audit_grounded_refs"] = 2
    state.metadata["min_goal_continuity_generations"] = 1
    state.metadata["max_goal_continuity_generations"] = 4

    for task in state.leaf_tasks:
        low = str(task.title or "").lower()
        if low.startswith("clarify & lock goal"):
            # W9: this phase is deterministic contract preparation, not a
            # productive deliverable. Treat it as internal control so the
            # generic multi-provider verifier does not create verification
            # tasks that would require an external AI.
            task.metadata.update(
                {
                    "preferred_kind": "local",
                    "local_fallback_kind": "goal_lock",
                    "task_role": "internal_control",
                    "control_plane_atomic": True,
                    "local_goal_lock_deterministic": True,
                    "external_action": False,
                    "irreversible": False,
                }
            )
            task.required_capabilities = ["general", "reasoning"]
        elif low.startswith("execution"):
            task.metadata.update(
                {
                    "preferred_kind": "local",
                    "local_fallback_kind": "finite_file",
                    "local_finite_file_mode": "write",
                    "local_finite_file_spec": dict(payload),
                    "task_role": "productive",
                    "external_action": False,
                    "irreversible": False,
                }
            )
            task.required_capabilities = ["general"]
        elif low.startswith("final audit"):
            task.metadata.update(
                {
                    "preferred_kind": "local",
                    "local_fallback_kind": "finite_file",
                    "local_finite_file_mode": "verify",
                    "local_finite_file_spec": dict(payload),
                    "task_role": "verification",
                    "external_action": False,
                    "irreversible": False,
                }
            )
            task.required_capabilities = ["general", "verification"]


class LocalFiniteFileProviderV1(WorkerProvider):
    """Deterministic local-only worker for one explicit finite file contract."""

    name = "ceo-local-finite-file"
    kind = WorkerKind.LOCAL
    capabilities = frozenset({"general", "verification"})

    def supports(self, task: Task) -> bool:
        return bool(
            task.metadata.get("local_fallback_kind") == "finite_file"
            and isinstance(task.metadata.get("local_finite_file_spec"), dict)
            and task.metadata.get("local_finite_file_mode") in {"write", "verify"}
        )

    @staticmethod
    def _footer(payload: dict) -> str:
        return (
            "<CEO_RESULT>"
            + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
            + "</CEO_RESULT>"
        )

    async def execute(self, request: WorkerRequest) -> WorkerResult:
        task = request.work_unit
        spec = dict(task.metadata.get("local_finite_file_spec") or {})
        mode = str(task.metadata.get("local_finite_file_mode") or "")
        relative_path = str(spec.get("path") or "")
        content = str(spec.get("content") or "")
        root_raw = str(spec.get("workspace_root") or "")

        if not relative_path or not content or not root_raw:
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=False,
                error="local_finite_file_contract_incomplete",
                metadata={"network_used": False, "shell_used": False, "spending_attempts": 0},
            )

        root = pathlib.Path(root_raw).resolve()
        target = (root / relative_path).resolve()
        try:
            target.relative_to(root)
        except ValueError:
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=False,
                error="local_finite_file_path_escape",
                metadata={"network_used": False, "shell_used": False, "spending_attempts": 0},
            )

        if mode == "write":
            footer = self._footer(
                {
                    "status": "complete",
                    "reason": "bounded local file write completed",
                    "confidence": 1.0,
                    "requires_user": False,
                    "evidence_refs": [],
                    "write_files": [
                        {"path": relative_path, "content": "[CEO_LOCAL_DRAFT]\n"},
                        {"path": relative_path, "content": content},
                    ],
                }
            )
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=True,
                text=(
                    f"Local finite file operation prepared {relative_path} using guarded "
                    "workspace writes with one draft write followed by the exact final content.\n"
                    + footer
                ),
                metadata={
                    "local_finite_file": True,
                    "mode": "write",
                    "network_used": False,
                    "shell_used": False,
                    "spending_attempts": 0,
                },
            )

        if not target.is_file():
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=False,
                error=f"local_verification_missing_file:{relative_path}",
                metadata={"network_used": False, "shell_used": False, "spending_attempts": 0},
            )

        try:
            actual = target.read_text(encoding="utf-8")
        except Exception as exc:
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=False,
                error=f"local_verification_read_failed:{type(exc).__name__}:{exc}",
                metadata={"network_used": False, "shell_used": False, "spending_attempts": 0},
            )

        if actual != content:
            return WorkerResult(
                provider=self.name,
                kind=self.kind,
                success=False,
                error="local_verification_exact_content_mismatch",
                metadata={"network_used": False, "shell_used": False, "spending_attempts": 0},
            )

        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        footer = self._footer(
            {
                "status": "complete",
                "reason": "independent local file verification passed",
                "confidence": 1.0,
                "requires_user": False,
                "evidence_refs": [],
                "write_files": [],
            }
        )
        return WorkerResult(
            provider=self.name,
            kind=self.kind,
            success=True,
            text=(
                f"Independent local verification passed for {relative_path}: exists, "
                f"non-empty, exact UTF-8 content match, sha256={digest}.\n" + footer
            ),
            artifacts=[relative_path],
            metadata={
                "local_finite_file": True,
                "mode": "verify",
                "verified_sha256": digest,
                "network_used": False,
                "shell_used": False,
                "spending_attempts": 0,
            },
        )
