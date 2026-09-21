from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable

from .change_sandbox import GovernedChangeSandbox, SandboxAssessment


@dataclass(slots=True)
class SelfDevelopmentVerdict:
    passed: bool
    changed_paths: list[str]
    forbidden_paths: list[str]
    tests_passed: bool
    stable_mutated: bool = False
    publication_allowed: bool = False
    installation_allowed: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class SelfDevelopmentSandboxV3:
    """Self-modification is evaluated only in a disposable copy."""

    DEFAULT_ALLOWED = ("ceo_core", "scripts", "tests", "schemas", "assets")

    def evaluate(self, source_root: str | Path, *, patch: Callable[[Path], None], test_command: list[str] | None = None, allowed_paths: tuple[str, ...] | None = None) -> SelfDevelopmentVerdict:
        assessment: SandboxAssessment = GovernedChangeSandbox().evaluate(
            source_root,
            patch=patch,
            test_command=test_command,
            allowed_paths=allowed_paths or self.DEFAULT_ALLOWED,
            allow_protected=False,
            timeout=180,
        )
        return SelfDevelopmentVerdict(
            passed=assessment.passed,
            changed_paths=list(assessment.changed_paths),
            forbidden_paths=list(assessment.forbidden_paths),
            tests_passed=assessment.test_returncode in {None, 0},
        )
