from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Iterable


@dataclass(slots=True)
class SandboxAssessment:
    passed: bool
    changed_paths: list[str]
    forbidden_paths: list[str]
    test_returncode: int | None
    stdout_tail: str = ""
    stderr_tail: str = ""


class GovernedChangeSandbox:
    """Evaluates code changes in a disposable copy; Stable is never mutated in-place."""

    DEFAULT_FORBIDDEN = (
        ".git/", "ceo_core/update_trust.json", "ceo_core/release_signing_authority.py",
        "ceo_core/credentials.py",
    )
    ALLOWED_EXECUTABLES = {"python", "python3", "pytest"}

    @staticmethod
    def _hash_tree(root: Path) -> dict[str, str]:
        out: dict[str, str] = {}
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if rel.startswith((".git/", "__pycache__/", ".pytest_cache/")) or "/__pycache__/" in rel:
                continue
            out[rel] = sha256(path.read_bytes()).hexdigest()
        return out

    @classmethod
    def _validate_command(cls, argv: list[str] | None) -> list[str] | None:
        if not argv:
            return None
        exe = Path(argv[0]).name.lower().replace(".exe", "")
        if exe not in cls.ALLOWED_EXECUTABLES:
            raise PermissionError(f"sandbox executable not allowed: {exe}")
        return list(argv)

    def evaluate(
        self,
        source_root: str | Path,
        *,
        patch: Callable[[Path], None],
        test_command: list[str] | None = None,
        allowed_paths: Iterable[str] | None = None,
        allow_protected: bool = False,
        timeout: int = 180,
    ) -> SandboxAssessment:
        source = Path(source_root).resolve()
        baseline = self._hash_tree(source)
        command = self._validate_command(test_command)
        with tempfile.TemporaryDirectory(prefix="ceo-governed-change-") as td:
            challenger = Path(td) / "challenger"
            shutil.copytree(source, challenger, ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache", ".git", "data", "browser_profiles"))
            patch(challenger)
            after = self._hash_tree(challenger)
            changed = sorted(k for k in set(baseline) | set(after) if baseline.get(k) != after.get(k))
            allowed = tuple(str(x).replace("\\", "/").rstrip("/") for x in (allowed_paths or ()))
            forbidden = []
            for rel in changed:
                if not allow_protected and any(rel == p or rel.startswith(p) for p in self.DEFAULT_FORBIDDEN):
                    forbidden.append(rel)
                    continue
                if allowed and not any(rel == p or rel.startswith(p + "/") for p in allowed):
                    forbidden.append(rel)
            if forbidden:
                return SandboxAssessment(False, changed, forbidden, None, "", "forbidden change scope")
            rc = 0
            out = err = ""
            if command:
                proc = subprocess.run(command, cwd=challenger, capture_output=True, text=True, timeout=max(1, int(timeout)))
                rc, out, err = proc.returncode, proc.stdout, proc.stderr
            return SandboxAssessment(rc == 0, changed, [], rc, out[-4000:], err[-4000:])
