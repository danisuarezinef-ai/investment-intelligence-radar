from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
from typing import Any

from .models import ProjectState


@dataclass(frozen=True, slots=True)
class SecurityFinding:
    code: str
    severity: str
    detail: str
    blocking: bool = True


class SecurityPostureGate:
    """Release-blocking local security invariants, separate from physical security claims."""

    SECRET_PATTERNS = (
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?i)\b(?:api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{16,}['\"]"),
    )

    def assess(self, state: ProjectState, root: str | Path, *, remote_bind: str = "127.0.0.1") -> dict[str, Any]:
        findings: list[SecurityFinding] = []
        if remote_bind not in {"127.0.0.1", "::1", "localhost"}:
            findings.append(SecurityFinding("remote_non_loopback", "high", f"remote API bind is {remote_bind}"))
        for key in ("automatic_spending", "automatic_publication", "automatic_candidate_promotion"):
            if bool(state.metadata.get(key, False)):
                findings.append(SecurityFinding(key, "critical", f"unsafe automation flag enabled: {key}"))
        root_path = Path(root)
        scanned = 0
        for path in root_path.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".json", ".toml", ".md", ".cmd", ".txt", ".yaml", ".yml"}:
                continue
            if any(part in {".git", "__pycache__", ".pytest_cache"} for part in path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            scanned += 1
            for pat in self.SECRET_PATTERNS:
                if pat.search(text):
                    findings.append(SecurityFinding("possible_embedded_secret", "critical", path.relative_to(root_path).as_posix()))
                    break
        # Trust and release private key must never live in the source tree.
        for candidate in ("release-private.key", "private.key", "ed25519-private.key"):
            if any(p.name.lower() == candidate for p in root_path.rglob("*")):
                findings.append(SecurityFinding("private_release_key_in_source", "critical", candidate))
        report = {
            "passed": not any(f.blocking for f in findings),
            "findings": [asdict(f) for f in findings],
            "files_scanned": scanned,
            "invariants": {
                "automatic_spending": False,
                "automatic_publication": False,
                "automatic_candidate_promotion": False,
                "remote_default_loopback": True,
                "arbitrary_remote_commands": False,
            },
        }
        state.metadata["security_posture_v1"] = report
        return report
