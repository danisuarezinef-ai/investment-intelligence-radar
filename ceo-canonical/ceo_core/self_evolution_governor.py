from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any, Iterable

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class EvolutionCandidate:
    candidate_id: str
    title: str
    rationale: str
    paths: tuple[str, ...]
    risk: str
    status: str = "proposed"
    tests_passed: bool = False
    benchmark_passed: bool = False
    security_passed: bool = False
    human_approved: bool = False
    canary_required: bool = False
    canary_passed: bool = False


class GovernedSelfEvolution:
    """Bounded self-evolution queue; never auto-publishes, installs or promotes Stable."""

    KEY = "self_evolution_v2"
    PROTECTED_PREFIXES = (
        "ceo_core/update_trust", "ceo_core/release_signing_authority", "ceo_core/credentials",
        "ceo_core/safety", "ceo_core/security_", "scripts/bootstrap_release_signer",
    )

    @staticmethod
    def _risk(paths: Iterable[str]) -> str:
        normalized = tuple(str(p).replace("\\", "/") for p in paths)
        if any(any(p.startswith(prefix) for prefix in GovernedSelfEvolution.PROTECTED_PREFIXES) for p in normalized):
            return "protected"
        if any(p.startswith("scripts/") or p.startswith("ceo_core/") for p in normalized):
            return "code"
        return "low"

    def propose(self, state: ProjectState, *, title: str, rationale: str, paths: Iterable[str]) -> dict[str, Any]:
        paths_t = tuple(sorted(set(str(x).replace("\\", "/") for x in paths)))
        cid = sha256((title + "|" + rationale + "|" + "|".join(paths_t)).encode()).hexdigest()[:16]
        risk = self._risk(paths_t)
        candidate = EvolutionCandidate(cid, str(title), str(rationale), paths_t, risk, canary_required=risk in {"code", "protected"})
        queue = state.metadata.setdefault(self.KEY, {}).setdefault("candidates", {})
        queue.setdefault(cid, {**asdict(candidate), "created_at": _now(), "history": []})
        return dict(queue[cid])

    def record_validation(
        self,
        state: ProjectState,
        candidate_id: str,
        *,
        tests_passed: bool,
        benchmark_passed: bool,
        security_passed: bool,
        evidence_refs: Iterable[str] = (),
    ) -> dict[str, Any]:
        row = self._row(state, candidate_id)
        row.update({
            "tests_passed": bool(tests_passed),
            "benchmark_passed": bool(benchmark_passed),
            "security_passed": bool(security_passed),
            "evidence_refs": list(dict.fromkeys(str(x) for x in evidence_refs if str(x).strip())),
        })
        row["status"] = "validated" if all((tests_passed, benchmark_passed, security_passed)) else "rejected"
        row.setdefault("history", []).append({"ts": _now(), "event": "validation", "status": row["status"]})
        return dict(row)

    def record_canary(self, state: ProjectState, candidate_id: str, *, passed: bool, evidence_refs: Iterable[str] = ()) -> dict[str, Any]:
        row = self._row(state, candidate_id)
        row["canary_passed"] = bool(passed)
        row["canary_evidence_refs"] = list(dict.fromkeys(str(x) for x in evidence_refs if str(x).strip()))
        row.setdefault("history", []).append({"ts": _now(), "event": "canary", "passed": bool(passed)})
        return dict(row)

    def approve_local_promotion(self, state: ProjectState, candidate_id: str, *, explicit_human_approval: bool) -> dict[str, Any]:
        row = self._row(state, candidate_id)
        if not explicit_human_approval:
            raise PermissionError("self-evolution promotion requires explicit human approval")
        if row.get("status") != "validated":
            raise RuntimeError("candidate is not fully validated")
        if row.get("canary_required") and not row.get("canary_passed"):
            raise RuntimeError("code candidate requires a successful canary/shadow evaluation before local promotion")
        row["human_approved"] = True
        row["status"] = "approved_for_local_merge"
        row.setdefault("history", []).append({"ts": _now(), "event": "human_local_promotion_approval"})
        return dict(row)

    def publication_allowed(self, state: ProjectState, candidate_id: str) -> bool:
        # Intentionally always false here. Network publication belongs to a separate human gate.
        self._row(state, candidate_id)
        return False

    def _row(self, state: ProjectState, candidate_id: str) -> dict[str, Any]:
        row = ((state.metadata.get(self.KEY) or {}).get("candidates") or {}).get(candidate_id)
        if row is None:
            raise KeyError(candidate_id)
        return row

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        candidates = ((state.metadata.get(self.KEY) or {}).get("candidates") or {})
        rows = list(candidates.values())
        return {
            "total": len(rows),
            "validated": sum(r.get("status") == "validated" for r in rows),
            "approved_for_local_merge": sum(r.get("status") == "approved_for_local_merge" for r in rows),
            "automatic_publication": False,
            "automatic_installation": False,
            "automatic_stable_promotion": False,
        }
