from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Iterable

from programming_browser_loop import FreeWebCodingLoop, PatchSandbox, PowerShellChatGPTWebTransport


FIELD_STATE_NAME = "BROWSER_FIELD_STATE.json"


def local_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=60,
        check=check,
    )


class BrowserFieldGuard:
    """B31: no real-code candidate work before the physical field gate passes."""

    def __init__(self, evidence_dir: str | Path) -> None:
        self.evidence_dir = Path(evidence_dir).expanduser().resolve()

    @property
    def state_path(self) -> Path:
        return self.evidence_dir / FIELD_STATE_NAME

    def require_verified(self) -> dict:
        if not self.state_path.is_file():
            raise RuntimeError("BROWSER_FIELD_NOT_VERIFIED: field state file missing")
        row = json.loads(self.state_path.read_text(encoding="utf-8-sig"))
        if not isinstance(row, dict) or row.get("BROWSER_FIELD_VERIFIED") is not True:
            raise RuntimeError("BROWSER_FIELD_NOT_VERIFIED: physical B29-B30 gate has not passed")
        if int(row.get("api_calls_required", -1)) != 0:
            raise RuntimeError("BROWSER_FIELD_INVALID: zero-API evidence missing")
        if row.get("production_promotion_allowed") is not False:
            raise RuntimeError("BROWSER_FIELD_INVALID: production boundary weakened")
        if row.get("automatic_merge_allowed") is not False:
            raise RuntimeError("BROWSER_FIELD_INVALID: merge boundary weakened")
        return row


@dataclass(frozen=True)
class CandidatePolicy:
    allowed_paths: tuple[str, ...]
    max_changed_files: int = 2
    max_changed_lines: int = 160
    forbidden_name_fragments: tuple[str, ...] = (
        ".env",
        "secret",
        "credential",
        "private_key",
        ".pem",
        ".pfx",
        ".key",
        "signing",
        "keystore",
        "current.json",
        "mvp_field",
        "real_trading",
    )


@dataclass
class CandidateEvidence:
    candidate_id: str
    status: str
    success: bool
    source_root: str
    workspace_root: str
    baseline_commit: str
    baseline_hashes: dict[str, str]
    final_hashes: dict[str, str] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    changed_lines: int = 0
    diff_sha256: str = ""
    diff_path: str = ""
    conversation_url: str | None = None
    tests_passed: bool = False
    test_output_sha256: str = ""
    original_source_unchanged: bool = False
    api_calls: int = 0
    paid_api_calls: int = 0
    commit_count: int = 0
    remotes: list[str] = field(default_factory=list)
    failure_reason: str = ""


class CandidateWorkspace:
    """B32-B33: isolated no-remote git candidate made from explicitly selected CEO files."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()

    @classmethod
    def create(
        cls,
        *,
        source_root: str | Path,
        workspace_root: str | Path,
        files: Iterable[str],
        extra_files: dict[str, str] | None = None,
    ) -> "CandidateWorkspace":
        source = Path(source_root).resolve()
        root = Path(workspace_root).resolve()
        if root.exists() and any(root.iterdir()):
            raise RuntimeError(f"candidate workspace not empty: {root}")
        root.mkdir(parents=True, exist_ok=True)

        selected = []
        for rel in files:
            rel = str(rel).replace("\\", "/")
            src = (source / rel).resolve()
            try:
                src.relative_to(source)
            except ValueError as exc:
                raise ValueError(f"candidate source path escapes repository: {rel}") from exc
            if not src.is_file():
                raise FileNotFoundError(rel)
            dst = root / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            selected.append(rel)

        for rel, body in (extra_files or {}).items():
            dst = (root / rel).resolve()
            try:
                dst.relative_to(root)
            except ValueError as exc:
                raise ValueError(f"extra file escapes candidate workspace: {rel}") from exc
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(body, encoding="utf-8")

        git(root, "init")
        git(root, "config", "user.email", "ceo-candidate@example.invalid")
        git(root, "config", "user.name", "CEO Candidate")
        marker = {
            "schema_version": 1,
            "candidate_workspace": True,
            "production": False,
            "automatic_merge": False,
            "source_files": selected,
        }
        (root / "CEO_CANDIDATE_WORKSPACE.json").write_text(
            json.dumps(marker, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        git(root, "add", ".")
        git(root, "commit", "-m", "candidate baseline")
        if git(root, "remote").stdout.strip():
            raise RuntimeError("candidate workspace unexpectedly has remotes")
        return cls(root)

    def baseline_commit(self) -> str:
        return git(self.root, "rev-parse", "HEAD").stdout.strip()

    def commit_count(self) -> int:
        return int(git(self.root, "rev-list", "--count", "HEAD").stdout.strip())

    def remotes(self) -> list[str]:
        return [x.strip() for x in git(self.root, "remote").stdout.splitlines() if x.strip()]

    def diff(self) -> str:
        return git(self.root, "diff", "--no-ext-diff", "--").stdout

    def changed_files(self) -> list[str]:
        return [
            x.strip().replace("\\", "/")
            for x in git(self.root, "diff", "--name-only", "--").stdout.splitlines()
            if x.strip()
        ]


class CandidateDiffPolicy:
    """B34-B35: verify that AI edits remain inside the declared candidate surface."""

    HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+\d+(?:,\d+)? @@", re.M)

    def __init__(self, policy: CandidatePolicy) -> None:
        self.policy = policy
        self.allowed = {p.replace("\\", "/") for p in policy.allowed_paths}

    def inspect(self, *, workspace: CandidateWorkspace) -> tuple[bool, dict]:
        changed = workspace.changed_files()
        bad_paths = [p for p in changed if p not in self.allowed]
        forbidden = [
            p for p in changed
            if any(fragment.lower() in p.lower() for fragment in self.policy.forbidden_name_fragments)
        ]
        diff = workspace.diff()
        changed_lines = sum(
            1 for line in diff.splitlines()
            if (line.startswith("+") or line.startswith("-"))
            and not line.startswith("+++")
            and not line.startswith("---")
        )
        binary = "GIT binary patch" in diff or "Binary files " in diff
        ok = (
            bool(changed)
            and not bad_paths
            and not forbidden
            and not binary
            and len(changed) <= self.policy.max_changed_files
            and changed_lines <= self.policy.max_changed_lines
        )
        return ok, {
            "changed_files": changed,
            "changed_lines": changed_lines,
            "bad_paths": bad_paths,
            "forbidden_paths": forbidden,
            "binary_diff": binary,
            "max_changed_files": self.policy.max_changed_files,
            "max_changed_lines": self.policy.max_changed_lines,
        }


class RealCodeCandidateRunner:
    """B36-B37: web-AI coding on a copied real CEO file, never on the source checkout."""

    def __init__(
        self,
        *,
        transport: PowerShellChatGPTWebTransport,
        source_root: str | Path,
        evidence_dir: str | Path,
    ) -> None:
        self.transport = transport
        self.source_root = Path(source_root).resolve()
        self.evidence_dir = Path(evidence_dir).expanduser().resolve()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        *,
        workspace: CandidateWorkspace,
        objective: str,
        relevant_files: list[str],
        allowed_edit_paths: list[str],
        test_command: list[str],
        candidate_id: str,
    ) -> CandidateEvidence:
        source_hashes = {
            rel: sha256_file(self.source_root / rel)
            for rel in relevant_files
            if (self.source_root / rel).is_file()
        }
        baseline = workspace.baseline_commit()
        evidence = CandidateEvidence(
            candidate_id=candidate_id,
            status="STARTED",
            success=False,
            source_root=str(self.source_root),
            workspace_root=str(workspace.root),
            baseline_commit=baseline,
            baseline_hashes=source_hashes,
        )

        loop = FreeWebCodingLoop(
            transport=self.transport,
            sandbox=PatchSandbox(workspace.root),
            max_turns=3,
        )
        result = loop.run(
            objective=objective,
            relevant_files=relevant_files,
            test_command=test_command,
            test_timeout_seconds=90,
        )
        evidence.conversation_url = result.conversation_url

        policy = CandidateDiffPolicy(CandidatePolicy(tuple(allowed_edit_paths)))
        policy_ok, detail = policy.inspect(workspace=workspace)
        evidence.changed_files = detail["changed_files"]
        evidence.changed_lines = int(detail["changed_lines"])

        diff = workspace.diff()
        if diff:
            diff_path = self.evidence_dir / f"{candidate_id}.patch"
            diff_path.write_text(diff, encoding="utf-8")
            evidence.diff_path = str(diff_path)
            evidence.diff_sha256 = sha256_file(diff_path)

        test_proc = subprocess.run(
            test_command,
            cwd=workspace.root,
            capture_output=True,
            text=True,
            timeout=90,
        )
        test_output = ((test_proc.stdout or "") + "\n" + (test_proc.stderr or "")).strip()
        evidence.tests_passed = test_proc.returncode == 0
        evidence.test_output_sha256 = hashlib.sha256(test_output.encode("utf-8")).hexdigest()

        evidence.final_hashes = {
            rel: sha256_file(workspace.root / rel)
            for rel in allowed_edit_paths
            if (workspace.root / rel).is_file()
        }
        evidence.original_source_unchanged = all(
            (self.source_root / rel).is_file()
            and sha256_file(self.source_root / rel) == digest
            for rel, digest in source_hashes.items()
        )
        evidence.commit_count = workspace.commit_count()
        evidence.remotes = workspace.remotes()

        invariants = (
            result.success
            and result.status == "CANDIDATE_VERIFIED"
            and policy_ok
            and evidence.tests_passed
            and evidence.original_source_unchanged
            and evidence.commit_count == 1
            and not evidence.remotes
            and bool(evidence.diff_sha256)
        )
        evidence.success = bool(invariants)
        evidence.status = "CANDIDATE_READY_FOR_HUMAN_REVIEW" if invariants else "CANDIDATE_REJECTED"
        if not invariants:
            evidence.failure_reason = (
                result.failure_reason
                or json.dumps(detail, ensure_ascii=False, sort_keys=True)
                or "candidate invariant failed"
            )

        out = self.evidence_dir / f"{candidate_id}.json"
        out.write_text(json.dumps(asdict(evidence), ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return evidence
