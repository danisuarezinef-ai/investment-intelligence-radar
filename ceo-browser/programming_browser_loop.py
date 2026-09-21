from __future__ import annotations

import json
import os
import shlex
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from browser_ai_worker import BrowserResultProtocol, ProgrammingPromptBuilder, PromptSizer


class BrowserTransport(Protocol):
    def ask(self, prompt: str, *, conversation_url: str | None = None) -> dict: ...


@dataclass
class CodingAttempt:
    turn: int
    patch_received: bool = False
    patch_applied: bool = False
    tests_passed: bool = False
    detail: str = ""


@dataclass
class CodingResult:
    status: str
    success: bool
    conversation_url: str | None = None
    attempts: list[CodingAttempt] = field(default_factory=list)
    final_diff: str = ""
    test_output: str = ""
    failure_reason: str = ""


class PowerShellChatGPTWebTransport:
    """Call ChatGPT through Chrome UI/CDP, never through the OpenAI API."""

    def __init__(
        self,
        *,
        driver_path: str | Path,
        recipe_path: str | Path,
        profile_dir: str | Path,
        port: int = 9227,
        timeout_seconds: int = 180,
    ) -> None:
        self.driver_path = Path(driver_path).resolve()
        self.recipe_path = Path(recipe_path).resolve()
        self.profile_dir = Path(profile_dir).resolve()
        self.port = int(port)
        self.timeout_seconds = int(timeout_seconds)

    def ask(self, prompt: str, *, conversation_url: str | None = None) -> dict:
        powershell = "powershell.exe" if os.name == "nt" else "pwsh"
        cmd = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(self.driver_path),
            "-RecipePath",
            str(self.recipe_path),
            "-Prompt",
            prompt,
            "-ProfileDir",
            str(self.profile_dir),
            "-Port",
            str(self.port),
            "-TimeoutSeconds",
            str(self.timeout_seconds),
        ]
        if conversation_url:
            # Keep the exact conversation URL, but allow the driver to relaunch Chrome
            # with the persistent profile if the prior browser process disappeared.
            cmd += ["-ConversationUrl", conversation_url]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds + 30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        raw = (proc.stdout or "").strip()
        if not raw:
            raise RuntimeError((proc.stderr or "browser driver returned no JSON")[-1200:])
        try:
            row = json.loads(raw.splitlines()[-1])
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"browser driver returned invalid JSON: {raw[-1000:]}") from exc
        if not row.get("ok"):
            raise RuntimeError(f"{row.get('status')}: {row.get('detail')}")
        return row


class PatchSandbox:
    """Apply model patches in an already-isolated git worktree.

    The AI never chooses commands. CEO supplies the test command before the loop.
    This class never commits, pushes or merges.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        if not (self.root / ".git").exists():
            # Git worktrees may use a .git file rather than a directory.
            if not (self.root / ".git").is_file():
                raise ValueError("workspace must be an isolated git repository/worktree")

    def read_files(self, paths: list[str], *, max_chars: int = 30_000) -> dict[str, str]:
        out: dict[str, str] = {}
        for rel in paths:
            p = (self.root / rel).resolve()
            try:
                p.relative_to(self.root)
            except ValueError as exc:
                raise ValueError(f"path escapes workspace: {rel}") from exc
            if not p.is_file():
                raise FileNotFoundError(rel)
            out[rel.replace("\\", "/")] = p.read_text(encoding="utf-8")[:max_chars]
        return out

    def apply_patch(self, patch: str) -> tuple[bool, str]:
        patch = str(patch or "").strip()
        if not patch:
            return False, "empty patch"
        with tempfile.NamedTemporaryFile("w", suffix=".diff", encoding="utf-8", delete=False) as f:
            f.write(patch + "\n")
            patch_path = Path(f.name)
        try:
            check = subprocess.run(
                ["git", "apply", "--check", "--whitespace=error-all", str(patch_path)],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if check.returncode != 0:
                return False, (check.stderr or check.stdout or "git apply --check failed")[-5000:]
            apply = subprocess.run(
                ["git", "apply", "--whitespace=fix", str(patch_path)],
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if apply.returncode != 0:
                return False, (apply.stderr or apply.stdout or "git apply failed")[-5000:]
            return True, "patch applied"
        finally:
            patch_path.unlink(missing_ok=True)

    def run_tests(self, command: list[str], *, timeout_seconds: int = 180) -> tuple[bool, str]:
        if not command:
            raise ValueError("test command required")
        # Rapid AI-generated edits can preserve both source size and coarse Windows
        # mtime long enough for Python to reuse stale bytecode. Give every test run a
        # fresh pycache root so the test result reflects the current candidate.
        with tempfile.TemporaryDirectory(prefix="ceo-test-pycache-") as pycache:
            env = os.environ.copy()
            env["PYTHONPYCACHEPREFIX"] = pycache
            proc = subprocess.run(
                command,
                cwd=self.root,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
        output = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
        return proc.returncode == 0, output[-12_000:]

    def diff(self) -> str:
        proc = subprocess.run(
            ["git", "diff", "--no-ext-diff", "--"],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.stdout


class FreeWebCodingLoop:
    """Bounded programming loop using a normal free web-AI session.

    No API, no merge, no push, no self-promotion. At most max_turns browser turns.
    """

    def __init__(
        self,
        *,
        transport: BrowserTransport,
        sandbox: PatchSandbox,
        max_turns: int = 3,
    ) -> None:
        self.transport = transport
        self.sandbox = sandbox
        self.max_turns = max(1, min(4, int(max_turns)))
        self.sizer = PromptSizer()

    def run(
        self,
        *,
        objective: str,
        relevant_files: list[str],
        test_command: list[str],
        test_timeout_seconds: int = 180,
    ) -> CodingResult:
        if not objective.strip():
            raise ValueError("objective required")
        if not relevant_files:
            raise ValueError("at least one relevant file required")
        if not test_command:
            raise ValueError("test command required")

        original_files = self.sandbox.read_files(relevant_files)
        test_display = " ".join(shlex.quote(x) for x in test_command)
        task = ProgrammingPromptBuilder.first_turn(
            objective=objective,
            files=original_files,
            test_command=test_display,
        )
        conversation_url: str | None = None
        attempts: list[CodingAttempt] = []
        previous_patch = ""
        last_test_output = ""

        for turn in range(1, self.max_turns + 1):
            plan = self.sizer.classify(task)
            if plan.should_split:
                return CodingResult(
                    status="NEEDS_DECOMPOSITION",
                    success=False,
                    conversation_url=conversation_url,
                    attempts=attempts,
                    failure_reason=plan.split_reason,
                )

            try:
                row = self.transport.ask(plan.prompt, conversation_url=conversation_url)
            except Exception as exc:
                attempts.append(CodingAttempt(turn=turn, detail=f"browser: {type(exc).__name__}: {exc}"))
                return CodingResult(
                    status="BROWSER_FAIL",
                    success=False,
                    conversation_url=conversation_url,
                    attempts=attempts,
                    failure_reason=attempts[-1].detail,
                )

            conversation_url = str(row.get("conversation_url") or conversation_url or "") or None
            parsed = BrowserResultProtocol.parse(str(row.get("response") or ""))
            patch = str(parsed.get("patch") or "").strip()
            attempt = CodingAttempt(turn=turn, patch_received=bool(patch))
            attempts.append(attempt)

            if not patch:
                attempt.detail = "AI response did not contain <CEO_PATCH>"
                if turn >= self.max_turns:
                    break
                task = ProgrammingPromptBuilder.correction_turn(
                    objective=objective,
                    previous_patch=str(row.get("response") or ""),
                    test_output=attempt.detail,
                    relevant_files=self.sandbox.read_files(relevant_files),
                    test_command=test_display,
                )
                continue

            applied, detail = self.sandbox.apply_patch(patch)
            attempt.patch_applied = applied
            attempt.detail = detail
            previous_patch = patch
            if not applied:
                if turn >= self.max_turns:
                    break
                task = ProgrammingPromptBuilder.correction_turn(
                    objective=objective,
                    previous_patch=patch,
                    test_output=f"PATCH APPLY ERROR:\n{detail}",
                    relevant_files=self.sandbox.read_files(relevant_files),
                    test_command=test_display,
                )
                continue

            passed, output = self.sandbox.run_tests(test_command, timeout_seconds=test_timeout_seconds)
            attempt.tests_passed = passed
            last_test_output = output
            if passed:
                diff = self.sandbox.diff()
                if not diff.strip():
                    return CodingResult(
                        status="NO_DIFF",
                        success=False,
                        conversation_url=conversation_url,
                        attempts=attempts,
                        test_output=output,
                        failure_reason="tests passed but no candidate diff exists",
                    )
                return CodingResult(
                    status="CANDIDATE_VERIFIED",
                    success=True,
                    conversation_url=conversation_url,
                    attempts=attempts,
                    final_diff=diff,
                    test_output=output,
                )

            if turn >= self.max_turns:
                break

            task = ProgrammingPromptBuilder.correction_turn(
                objective=objective,
                previous_patch=patch,
                test_output=output,
                relevant_files=self.sandbox.read_files(relevant_files),
                test_command=test_display,
            )

        return CodingResult(
            status="TESTS_FAILED" if last_test_output else "PATCH_FAILED",
            success=False,
            conversation_url=conversation_url,
            attempts=attempts,
            final_diff=self.sandbox.diff(),
            test_output=last_test_output,
            failure_reason=attempts[-1].detail if attempts else "coding loop ended without candidate",
        )
