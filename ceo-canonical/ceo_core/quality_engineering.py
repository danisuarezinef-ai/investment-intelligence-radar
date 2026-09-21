from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
import time
import tomllib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from statistics import mean, pstdev
from typing import Any, Iterable

from .models import ProjectState


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clip(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _stable_hash(payload: Any) -> str:
    return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")).hexdigest()


def _file_digest(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        while True:
            block = handle.read(1024 * 1024)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# 21. Quality gates by artifact kind
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class QualityGateResult:
    artifact_kind: str
    passed: bool
    score: float
    missing: list[str]
    checks: dict[str, bool]


class ArtifactQualityGateEngine:
    """Artifact-aware acceptance rules instead of one global quality threshold."""

    RULES: dict[str, tuple[str, ...]] = {
        "code": ("tests_pass", "static_pass", "requirements_traced", "no_critical_security"),
        "document": ("requirements_traced", "evidence_sufficient", "review_pass"),
        "research": ("evidence_sufficient", "contradictions_resolved", "provenance_complete"),
        "data": ("schema_valid", "provenance_complete", "validation_pass"),
        "interface": ("requirements_traced", "interaction_tests_pass", "accessibility_review"),
        "deployment": ("build_reproducible", "security_pass", "rollback_ready", "field_gate_ready"),
        "decision": ("evidence_sufficient", "alternatives_considered", "risk_assessed"),
    }

    def evaluate(self, artifact_kind: str, evidence: dict[str, Any]) -> QualityGateResult:
        kind = artifact_kind.lower().strip()
        required = self.RULES.get(kind, ("requirements_traced", "review_pass"))
        checks = {key: bool(evidence.get(key, False)) for key in required}
        missing = [k for k, ok in checks.items() if not ok]
        score = sum(checks.values()) / max(1, len(checks))
        return QualityGateResult(kind, not missing, round(score, 4), missing, checks)


# ---------------------------------------------------------------------------
# 22-24. Acceptance generation + requirements traceability + coverage
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class GeneratedAcceptanceTest:
    id: str
    requirement_id: str
    criterion: str
    test_kind: str
    automatable: bool
    target: str | None
    expected: str


class AcceptanceTestGenerator:
    """Conservative natural-language -> test contract generator.

    It never executes the generated command or treats a criterion as machine-testable
    unless it maps to a known safe test family.
    """

    def generate(self, requirement_id: str, criterion: str) -> GeneratedAcceptanceTest:
        text = str(criterion).strip()
        lower = text.lower()
        kind, automatable, target, expected = "human_review", False, None, "review_pass"
        if any(x in lower for x in ("test", "tests pass", "pytest")):
            kind, automatable, expected = "test_suite", True, "pass"
        elif any(x in lower for x in ("file exists", "artifact exists", "produce", "deliver")):
            kind, automatable, expected = "artifact_presence", True, "exists"
            match = re.search(r"([\w./\\-]+\.(?:json|md|txt|zip|exe|pdf|docx|csv|py))", text, re.I)
            target = match.group(1) if match else None
        elif any(x in lower for x in ("sha-256", "sha256", "hash")):
            kind, automatable, expected = "digest", True, "matches"
        elif any(x in lower for x in ("under budget", "budget", "cost <", "cost below")):
            kind, automatable, expected = "metric", True, "within_limit"
        elif any(x in lower for x in ("no critical", "security scan", "vulnerability")):
            kind, automatable, expected = "security", True, "no_critical_findings"
        tid = sha256(f"{requirement_id}|{text}".encode()).hexdigest()[:16]
        return GeneratedAcceptanceTest(tid, requirement_id, text, kind, automatable, target, expected)


@dataclass(slots=True)
class RequirementTrace:
    requirement_id: str
    text: str
    implementation_refs: list[str] = field(default_factory=list)
    test_refs: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    status: str = "UNIMPLEMENTED"
    source: str | None = None
    generated_acceptance_test: dict[str, Any] | None = None


class RequirementsTraceabilityMatrix:
    KEY = "requirements_traceability_v1"
    VALID = {"UNIMPLEMENTED", "IMPLEMENTED", "TESTED", "VERIFIED", "FAILED"}

    def add_requirement(self, state: ProjectState, requirement_id: str, text: str) -> RequirementTrace:
        row = RequirementTrace(str(requirement_id), str(text))
        state.metadata.setdefault(self.KEY, {})[row.requirement_id] = asdict(row)
        return row

    def link(self, state: ProjectState, requirement_id: str, *, implementation: str | None = None,
             test: str | None = None, evidence: str | None = None, status: str | None = None) -> RequirementTrace:
        rows = state.metadata.setdefault(self.KEY, {})
        if requirement_id not in rows:
            raise KeyError(requirement_id)
        row = rows[requirement_id]
        for key, value in (("implementation_refs", implementation), ("test_refs", test), ("evidence_refs", evidence)):
            if value and value not in row[key]:
                row[key].append(value)
        if status:
            status = status.upper()
            if status not in self.VALID:
                raise ValueError(f"invalid requirement status: {status}")
            row["status"] = status
        return RequirementTrace(**row)

    def matrix(self, state: ProjectState) -> list[RequirementTrace]:
        return [RequirementTrace(**r) for r in state.metadata.get(self.KEY, {}).values()]


class RequirementCoverageEngine:
    WEIGHTS = {"UNIMPLEMENTED": 0.0, "IMPLEMENTED": .35, "TESTED": .7, "VERIFIED": 1.0, "FAILED": 0.0}

    def assess(self, traces: Iterable[RequirementTrace]) -> dict[str, Any]:
        rows = list(traces)
        counts = {key: 0 for key in self.WEIGHTS}
        for row in rows:
            counts[row.status] = counts.get(row.status, 0) + 1
        weighted = sum(self.WEIGHTS.get(r.status, 0) for r in rows) / max(1, len(rows))
        verified = counts.get("VERIFIED", 0) / max(1, len(rows))
        tested_or_better = sum(1 for r in rows if r.status in {"TESTED", "VERIFIED"}) / max(1, len(rows))
        return {"requirements": len(rows), "weighted_coverage": round(weighted, 4),
                "tested_or_better": round(tested_or_better, 4), "verified_coverage": round(verified, 4), "counts": counts}


# ---------------------------------------------------------------------------
# 25-30. Uncertainty, evidence, contradictions, freshness, impact, revalidation
# ---------------------------------------------------------------------------


class UncertaintyBudgetEngine:
    def assess(self, items: Iterable[dict[str, Any]], *, max_budget: float = .25) -> dict[str, Any]:
        rows = list(items)
        weighted = []
        for row in rows:
            uncertainty = _clip(row.get("uncertainty", 1.0))
            importance = _clip(row.get("importance", .5))
            weighted.append(uncertainty * (.25 + .75 * importance))
        used = mean(weighted) if weighted else 1.0
        return {"used": round(used, 4), "limit": round(max_budget, 4), "within_budget": used <= max_budget,
                "items": len(rows), "headroom": round(max_budget - used, 4)}


class EvidenceQualityScorer:
    BASE = {
        "field_test": 1.00,
        "integration_test": .92,
        "unit_test": .82,
        "artifact_hash": .80,
        "primary_source": .78,
        "static_analysis": .64,
        "secondary_source": .55,
        "inspection": .48,
        "agent_assertion": .20,
        "inference": .12,
    }

    def score(self, *, kind: str, direct: bool = True, independent: bool = True,
              fresh: bool = True, strength: float = 1.0) -> float:
        base = self.BASE.get(kind, .35)
        multiplier = (1.0 if direct else .8) * (1.0 if independent else .82) * (1.0 if fresh else .55) * _clip(strength)
        return round(_clip(base * multiplier), 4)


class EvidenceContradictionEngine:
    def analyze(self, records: Iterable[dict[str, Any]]) -> dict[str, Any]:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in records:
            claim = str(row.get("claim_id") or "")
            if claim:
                grouped.setdefault(claim, []).append(row)
        contradictions = []
        for claim, rows in grouped.items():
            support = sum(float(r.get("quality", r.get("strength", .5))) for r in rows if r.get("outcome") == "supports")
            oppose = sum(float(r.get("quality", r.get("strength", .5))) for r in rows if r.get("outcome") == "contradicts")
            if support > 0 and oppose > 0:
                contradictions.append({"claim_id": claim, "support": round(support, 4), "contradict": round(oppose, 4),
                                       "severity": round(min(support, oppose) / max(support, oppose), 4)})
        contradictions.sort(key=lambda x: x["severity"], reverse=True)
        return {"contradictions": contradictions, "count": len(contradictions), "resolved": len(contradictions) == 0}


@dataclass(slots=True)
class FreshnessRecord:
    evidence_id: str
    dependency_ref: str
    dependency_digest: str
    recorded_at: str


class EvidenceFreshnessTracker:
    KEY = "evidence_freshness_v1"

    def register(self, state: ProjectState, evidence_id: str, dependency_ref: str, dependency_digest: str) -> FreshnessRecord:
        row = FreshnessRecord(str(evidence_id), str(dependency_ref), str(dependency_digest), _now())
        state.metadata.setdefault(self.KEY, {})[evidence_id] = asdict(row)
        return row

    def stale(self, state: ProjectState, current_digests: dict[str, str]) -> list[str]:
        out = []
        for evidence_id, row in state.metadata.get(self.KEY, {}).items():
            current = current_digests.get(row["dependency_ref"])
            if current is not None and current != row["dependency_digest"]:
                out.append(evidence_id)
        return sorted(out)


class DependencyImpactAnalyzer:
    """Computes transitive impact from component dependency and traceability maps."""

    def impacted(self, changed_refs: Iterable[str], dependency_map: dict[str, Iterable[str]], traces: Iterable[RequirementTrace]) -> dict[str, Any]:
        changed = set(changed_refs)
        reverse: dict[str, set[str]] = {}
        for node, deps in dependency_map.items():
            for dep in deps:
                reverse.setdefault(str(dep), set()).add(str(node))
        queue = list(changed); impacted = set(changed)
        while queue:
            cur = queue.pop(0)
            for nxt in reverse.get(cur, set()):
                if nxt not in impacted:
                    impacted.add(nxt); queue.append(nxt)
        reqs, tests, evidence = set(), set(), set()
        for trace in traces:
            if impacted.intersection(trace.implementation_refs):
                reqs.add(trace.requirement_id); tests.update(trace.test_refs); evidence.update(trace.evidence_refs)
        return {"changed": sorted(changed), "impacted_components": sorted(impacted), "requirements": sorted(reqs),
                "tests": sorted(tests), "evidence": sorted(evidence)}


class AutomaticRevalidator:
    def plan(self, impact: dict[str, Any], stale_evidence: Iterable[str] = ()) -> dict[str, Any]:
        stale = set(stale_evidence)
        invalid_evidence = sorted(stale.union(impact.get("evidence", [])))
        tests = sorted(set(impact.get("tests", [])))
        return {"requirements_to_revalidate": sorted(set(impact.get("requirements", []))),
                "tests_to_run": tests, "evidence_invalidated": invalid_evidence,
                "full_regression_required": not bool(tests) and bool(impact.get("impacted_components"))}


# ---------------------------------------------------------------------------
# 31-34. Incremental verification, prioritization, flaky tests, test evidence
# ---------------------------------------------------------------------------


class IncrementalVerificationPlanner:
    def select(self, all_tests: Iterable[str], impact: dict[str, Any], *, periodic_full: bool = False) -> dict[str, Any]:
        all_rows = sorted(set(all_tests))
        if periodic_full:
            return {"mode": "full", "tests": all_rows, "saved_fraction": 0.0}
        wanted = set(impact.get("tests", []))
        selected = [t for t in all_rows if t in wanted or any(ref in t for ref in impact.get("impacted_components", []))]
        if not selected and impact.get("impacted_components"):
            return {"mode": "safety_full", "tests": all_rows, "saved_fraction": 0.0}
        saved = 1.0 - (len(selected) / max(1, len(all_rows)))
        return {"mode": "incremental", "tests": selected, "saved_fraction": round(saved, 4)}


class TestPrioritizationEngine:
    def prioritize(self, tests: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        scored = []
        for row in tests:
            failure_rate = _clip(row.get("failure_rate", 0))
            impact = _clip(row.get("impact", .5))
            recency = _clip(row.get("changed_area", 0))
            duration = max(.01, float(row.get("duration", 1.0)))
            score = (.45 * failure_rate + .35 * impact + .20 * recency) / (duration ** .25)
            scored.append({**row, "priority_score": round(score, 6)})
        return sorted(scored, key=lambda r: (-r["priority_score"], str(r.get("name", ""))))


class FlakyTestDetector:
    def analyze(self, outcomes: Iterable[dict[str, Any]], *, min_runs: int = 4) -> dict[str, Any]:
        groups: dict[str, list[bool]] = {}
        durations: dict[str, list[float]] = {}
        for row in outcomes:
            name = str(row["name"]); groups.setdefault(name, []).append(bool(row["passed"])); durations.setdefault(name, []).append(float(row.get("duration", 0)))
        results = []
        for name, vals in groups.items():
            transitions = sum(a != b for a, b in zip(vals, vals[1:]))
            pass_rate = sum(vals) / len(vals)
            flaky = len(vals) >= min_runs and 0 < pass_rate < 1 and transitions > 0
            results.append({"name": name, "runs": len(vals), "pass_rate": round(pass_rate, 4), "transitions": transitions,
                            "flaky": flaky, "duration_stdev": round(pstdev(durations[name]), 6) if len(durations[name]) > 1 else 0.0})
        return {"tests": results, "flaky": sorted(r["name"] for r in results if r["flaky"])}


class TestEvidenceLedger:
    KEY = "test_evidence_ledger_v1"

    def record(self, state: ProjectState, *, test_id: str, commit: str, config_digest: str,
               artifact_digest: str, passed: bool, duration: float = 0.0) -> dict[str, Any]:
        payload = {"test_id": test_id, "commit": commit, "config_digest": config_digest, "artifact_digest": artifact_digest,
                   "passed": bool(passed), "duration": round(float(duration), 6), "recorded_at": _now()}
        payload["evidence_id"] = sha256(f"{test_id}|{commit}|{config_digest}|{artifact_digest}|{passed}".encode()).hexdigest()[:24]
        state.metadata.setdefault(self.KEY, []).append(payload)
        return payload

    def valid_for(self, state: ProjectState, *, commit: str, artifact_digest: str) -> list[dict[str, Any]]:
        return [r for r in state.metadata.get(self.KEY, []) if r["commit"] == commit and r["artifact_digest"] == artifact_digest and r["passed"]]


# ---------------------------------------------------------------------------
# 35-39. Reproducibility, SBOM, dependency risk/update/migration
# ---------------------------------------------------------------------------


class BuildReproducibilityChecker:
    DEFAULT_EXCLUDES = {".git", "__pycache__", ".pytest_cache", "browser_profiles", "data", "logs", "tmp"}

    def manifest(self, root: str | Path, *, excludes: Iterable[str] = ()) -> dict[str, str]:
        base = Path(root).resolve(); excluded = self.DEFAULT_EXCLUDES | set(excludes); out = {}
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(base)
            if any(part in excluded for part in rel.parts):
                continue
            out[rel.as_posix()] = _file_digest(path)
        return out

    def compare(self, first: str | Path, second: str | Path, *, excludes: Iterable[str] = ()) -> dict[str, Any]:
        a, b = self.manifest(first, excludes=excludes), self.manifest(second, excludes=excludes)
        added = sorted(set(b) - set(a)); removed = sorted(set(a) - set(b)); changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
        return {"reproducible": not (added or removed or changed), "added": added, "removed": removed, "changed": changed,
                "files_first": len(a), "files_second": len(b), "manifest_digest_first": _stable_hash(a), "manifest_digest_second": _stable_hash(b)}


class SBOMBuilder:
    def from_pyproject(self, pyproject: str | Path) -> dict[str, Any]:
        path = Path(pyproject); data = tomllib.loads(path.read_text(encoding="utf-8")); project = data.get("project", {})
        rows = []
        for raw in project.get("dependencies", []):
            match = re.match(r"^\s*([A-Za-z0-9_.-]+)\s*([^;]*)", raw)
            if not match:
                continue
            rows.append({"name": match.group(1), "specifier": match.group(2).strip() or "*", "source": "pyproject"})
        rows.sort(key=lambda x: x["name"].lower())
        return {"project": project.get("name"), "version": project.get("version"), "generated_at": _now(), "dependencies": rows,
                "dependency_count": len(rows), "digest": _stable_hash(rows)}


class DependencyRiskEngine:
    """Offline dependency risk: pinning, breadth, criticality and local signals only."""

    def assess(self, dependency: dict[str, Any], *, criticality: float = .5, known_findings: int = 0,
               maintenance_signal: float = .5) -> dict[str, Any]:
        spec = str(dependency.get("specifier", "*"))
        unbounded = spec in {"", "*"} or ">=" in spec and "<" not in spec
        exact = "==" in spec
        risk = .25 + (.2 if unbounded else 0) + (.12 if not exact else 0) + .25 * _clip(criticality) + .12 * (1 - _clip(maintenance_signal)) + min(.25, .1 * known_findings)
        return {"name": dependency.get("name"), "risk": round(_clip(risk), 4), "unbounded": unbounded, "exact_pin": exact,
                "known_findings": int(known_findings), "network_checked": False}


class DependencyUpdateSimulator:
    """Plans and evaluates a dependency update without mutating the source tree."""

    def simulate(self, dependency: dict[str, Any], new_specifier: str, *, affected_tests: Iterable[str], compatibility_passed: bool | None = None) -> dict[str, Any]:
        old = str(dependency.get("specifier", "*")); new = str(new_specifier).strip()
        breaking_hint = self._major_hint(old, new)
        return {"name": dependency.get("name"), "from": old, "to": new, "affected_tests": sorted(set(affected_tests)),
                "breaking_change_risk": breaking_hint, "compatibility_passed": compatibility_passed,
                "safe_to_apply": bool(compatibility_passed is True and breaking_hint != "high"), "mutation_performed": False}

    @staticmethod
    def _major_hint(old: str, new: str) -> str:
        nums_old = re.findall(r"\d+", old); nums_new = re.findall(r"\d+", new)
        if nums_old and nums_new and nums_old[0] != nums_new[0]:
            return "high"
        if old != new:
            return "medium"
        return "low"


class AutomaticMigrationPlanner:
    def plan(self, *, dependency: str, from_spec: str, to_spec: str, impacted_components: Iterable[str], tests: Iterable[str]) -> dict[str, Any]:
        components = sorted(set(impacted_components)); test_rows = sorted(set(tests))
        steps = [
            "create_isolated_branch",
            f"update_dependency:{dependency}:{from_spec}->{to_spec}",
            "run_targeted_compatibility_tests",
        ]
        if components:
            steps.append("adapt_impacted_interfaces")
        steps.extend(["run_full_regression", "security_scan", "independent_review"])
        return {"dependency": dependency, "from": from_spec, "to": to_spec, "components": components, "tests": test_rows,
                "steps": steps, "auto_apply": False, "requires_promotion_gate": True}


# ---------------------------------------------------------------------------
# 40. Git intelligence / hotspots
# ---------------------------------------------------------------------------


class GitIntelligenceEngine:
    def analyze(self, repo: str | Path, *, max_commits: int = 500) -> dict[str, Any]:
        root = Path(repo).resolve()
        if not (root / ".git").exists():
            return {"available": False, "reason": "not_git_repository", "hotspots": []}
        proc = subprocess.run(["git", "log", f"-n{max_commits}", "--name-only", "--pretty=format:__COMMIT__"], cwd=root,
                              capture_output=True, text=True, timeout=60)
        if proc.returncode != 0:
            return {"available": False, "reason": "git_log_failed", "stderr": proc.stderr.strip(), "hotspots": []}
        touches: dict[str, int] = {}; commits = 0; current_seen: set[str] = set()
        for line in proc.stdout.splitlines():
            line = line.strip()
            if line == "__COMMIT__":
                for path in current_seen: touches[path] = touches.get(path, 0) + 1
                current_seen = set(); commits += 1; continue
            if line:
                current_seen.add(line)
        for path in current_seen: touches[path] = touches.get(path, 0) + 1
        hotspots = [{"path": path, "commit_touches": count} for path, count in touches.items()]
        hotspots.sort(key=lambda r: (-r["commit_touches"], r["path"]))
        return {"available": True, "commits_analyzed": commits, "files_touched": len(hotspots), "hotspots": hotspots[:100],
                "network_actions_performed": False}


# ---------------------------------------------------------------------------
# Integrated facade
# ---------------------------------------------------------------------------


class QualityEngineeringCore:
    """Integrated facade for roadmap tasks 21-40."""

    def __init__(self) -> None:
        self.quality_gates = ArtifactQualityGateEngine()
        self.acceptance = AcceptanceTestGenerator()
        self.traceability = RequirementsTraceabilityMatrix()
        self.coverage = RequirementCoverageEngine()
        self.uncertainty = UncertaintyBudgetEngine()
        self.evidence_quality = EvidenceQualityScorer()
        self.contradictions = EvidenceContradictionEngine()
        self.freshness = EvidenceFreshnessTracker()
        self.impact = DependencyImpactAnalyzer()
        self.revalidation = AutomaticRevalidator()
        self.incremental = IncrementalVerificationPlanner()
        self.prioritizer = TestPrioritizationEngine()
        self.flaky = FlakyTestDetector()
        self.test_evidence = TestEvidenceLedger()
        self.reproducibility = BuildReproducibilityChecker()
        self.sbom = SBOMBuilder()
        self.dependency_risk = DependencyRiskEngine()
        self.update_simulator = DependencyUpdateSimulator()
        self.migrations = AutomaticMigrationPlanner()
        self.git = GitIntelligenceEngine()

    def initialize_project(self, state: ProjectState) -> dict[str, Any]:
        """Bootstrap traceability from locked goal criteria/deliverables without overwriting explicit traces."""
        rows = state.metadata.setdefault(RequirementsTraceabilityMatrix.KEY, {})
        sources: list[tuple[str, str, str]] = []
        for i, text in enumerate(state.completion_criteria, 1):
            sources.append((f"C{i}", str(text), "completion_criterion"))
        for i, text in enumerate(state.goal_deliverables, 1):
            sources.append((f"D{i}", str(text), "deliverable"))
        if state.goal_success_definition.strip():
            sources.append(("S1", state.goal_success_definition.strip(), "success_definition"))
        for rid, text, source in sources:
            if rid not in rows:
                trace = self.traceability.add_requirement(state, rid, text)
                rows[rid]["source"] = source
                generated = self.acceptance.generate(rid, text)
                rows[rid]["generated_acceptance_test"] = asdict(generated)
        snapshot = self.project_snapshot(state)
        state.metadata["quality_engineering_v1"] = snapshot
        return snapshot

    def record_task_completion(self, state: ProjectState, *, task_id: str, requirement_ids: Iterable[str],
                               implementation_refs: Iterable[str] = (), test_ref: str | None = None,
                               evidence_ref: str | None = None, independently_verified: bool = False) -> dict[str, Any]:
        linked = []
        for rid in requirement_ids:
            if rid not in state.metadata.get(RequirementsTraceabilityMatrix.KEY, {}):
                continue
            for impl in implementation_refs:
                self.traceability.link(state, rid, implementation=str(impl))
            status = "VERIFIED" if independently_verified else "TESTED" if test_ref else "IMPLEMENTED"
            self.traceability.link(state, rid, test=test_ref, evidence=evidence_ref or f"task:{task_id}", status=status)
            linked.append(rid)
        snapshot = self.project_snapshot(state)
        state.metadata["quality_engineering_v1"] = snapshot
        return {"linked_requirements": linked, "snapshot": snapshot}

    def project_snapshot(self, state: ProjectState) -> dict[str, Any]:
        traces = self.traceability.matrix(state)
        coverage = self.coverage.assess(traces)
        return {
            "requirements": coverage,
            "test_evidence_records": len(state.metadata.get(TestEvidenceLedger.KEY, [])),
            "freshness_records": len(state.metadata.get(EvidenceFreshnessTracker.KEY, {})),
            "quality_engineering_version": 1,
        }
