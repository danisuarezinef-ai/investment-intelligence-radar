from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib


@dataclass(slots=True)
class ReleaseGate:
    name: str
    passed: bool
    detail: str


class ReleaseReadiness:
    def assess(
        self,
        root: str | Path,
        *,
        tests_passed: bool,
        security_passed: bool,
        schema_version: int,
        windows_build_verified: bool = False,
        long_mission_passed: bool = True,
        live_provider_verified: bool = False,
    ) -> dict:
        root = Path(root)
        gates = [
            ReleaseGate("tests", tests_passed, "regression suite"),
            ReleaseGate("security", security_passed, "secret/static audit"),
            ReleaseGate("schema", schema_version >= 3, f"schema={schema_version}"),
            ReleaseGate("long_mission", long_mission_passed, "restart/fault-injection autonomous mission"),
            ReleaseGate("windows_build", windows_build_verified, "must be verified on physical Windows"),
            ReleaseGate("live_provider", live_provider_verified, "authenticated real provider validation"),
            ReleaseGate("installer_config", (root / "packaging/windows/installer.iss").exists(), "Inno Setup manifest"),
        ]
        trial_exclusions = {"windows_build", "live_provider"}
        ready_for_windows_trial = all(g.passed for g in gates if g.name not in trial_exclusions)
        release_candidate_ready = ready_for_windows_trial
        return {
            "ready_for_windows_trial": ready_for_windows_trial,
            "release_candidate_ready": release_candidate_ready,
            "production_ready": all(g.passed for g in gates),
            "gates": [asdict(g) for g in gates],
        }

    @staticmethod
    def sha256(path: str | Path) -> str:
        h = hashlib.sha256()
        with Path(path).open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
