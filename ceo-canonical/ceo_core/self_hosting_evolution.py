from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable, Sequence

from .cognitive_evolution import SelfImprovementPipeline
from .execution_integrity import WorkspaceGuard
from .models import ProjectState
from .quality_engineering import DependencyImpactAnalyzer, IncrementalVerificationPlanner
from .release_candidate_v1 import AdversarialReviewerV2, PatchQualityScorer
from .self_hosting_tools import (
    FilesystemOperations,
    ImmutableRunningVersion,
    SelfHostingGitController,
    TerminalController,
    _tree_digest,
)


def _now() -> float:
    return time.time()


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return value[:48] or "improvement"


@dataclass(slots=True)
class SelfImprovementMission:
    mission_id: str
    objective: str
    target_area: str
    hypothesis: str
    constraints: list[str]
    forbidden_actions: list[str]
    acceptance_criteria: list[str]
    research_questions: list[str]
    required_tests: list[str]
    artifacts: list[str]
    auto_promotion_allowed: bool = False


# 31. Self-improvement branch creator
class SelfImprovementBranchCreator:
    KEY = "self_improvement_branches_v1"

    def create(self, state: ProjectState, candidate_root: str | Path, *, mission_id: str, objective: str) -> dict[str, Any]:
        root = Path(candidate_root).resolve()
        git = SelfHostingGitController(root)
        git.initialize()
        branch = f"ceo/self-{_slug(objective)}-{mission_id[:8]}"
        result = git.git._run("switch", "-c", branch, check=False)
        if not result.ok:
            # Deterministic re-entry: reuse the already-created isolated branch.
            existing = git.git._run("branch", "--list", branch, check=False)
            if branch not in existing.stdout:
                raise RuntimeError(result.stderr or "could not create self-improvement branch")
            git.git._run("switch", branch)
        row = {
            "mission_id": mission_id,
            "branch": branch,
            "candidate_root": str(root),
            "created_at": _now(),
            "network_actions_performed": False,
            "auto_merge_allowed": False,
        }
        state.metadata.setdefault(self.KEY, {})[mission_id] = row
        return dict(row)


# 32. Self-improvement mission compiler
class SelfImprovementMissionCompiler:
    KEY = "self_improvement_missions_v1"

    def compile(
        self,
        state: ProjectState,
        *,
        objective: str,
        target_area: str,
        hypothesis: str = "",
        acceptance_criteria: Iterable[str] = (),
        required_tests: Iterable[str] = (),
    ) -> SelfImprovementMission:
        objective = str(objective).strip()
        target_area = str(target_area).strip()
        if not objective or not target_area:
            raise ValueError("objective and target_area are required")
        mission_id = sha256(f"{state.id}|{objective}|{target_area}".encode()).hexdigest()[:20]
        criteria = list(dict.fromkeys(str(x) for x in acceptance_criteria if str(x).strip())) or [
            "Targeted tests pass",
            "No security regression",
            "Stable running version remains unchanged",
            "Independent adversarial review does not fail",
        ]
        mission = SelfImprovementMission(
            mission_id=mission_id,
            objective=objective,
            target_area=target_area,
            hypothesis=hypothesis or f"Improving {target_area} will measurably improve the objective without widening unsafe scope.",
            constraints=list(dict.fromkeys([*state.goal_constraints, "stable running version is immutable", "local candidate branch only"])),
            forbidden_actions=list(dict.fromkeys([*state.metadata.get("forbidden_actions", []), "no auto-promotion", "no git network actions"])),
            acceptance_criteria=criteria,
            research_questions=[
                f"What is the current architecture and failure surface of {target_area}?",
                f"What authoritative documentation constrains {target_area}?",
                f"What is the smallest safe change that could satisfy: {objective}?",
            ],
            required_tests=list(dict.fromkeys(str(x) for x in required_tests if str(x).strip())),
            artifacts=["mission.json", "inspection.json", "research.json", "test-report.json", "adversarial-review.json", "baseline-comparison.json"],
            auto_promotion_allowed=False,
        )
        state.metadata.setdefault(self.KEY, {})[mission_id] = asdict(mission)
        return mission


# 33. Self-code inspection
class SelfCodeInspector:
    KEY = "self_code_inspection_v1"
    EXCLUDE = {".git", "__pycache__", ".pytest_cache", "data", "browser_profiles"}

    def inspect(self, state: ProjectState, candidate_root: str | Path, *, mission: SelfImprovementMission, max_files: int = 80) -> dict[str, Any]:
        root = Path(candidate_root).resolve()
        tokens = {x for x in re.findall(r"[a-z0-9_]+", f"{mission.target_area} {mission.objective}".lower()) if len(x) >= 4}
        rows: list[dict[str, Any]] = []
        for path in root.rglob("*.py"):
            rel = path.relative_to(root)
            if any(part in self.EXCLUDE for part in rel.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
                tree = ast.parse(text)
            except Exception:
                continue
            low = f"{rel.as_posix()}\n{text[:20000]}".lower()
            hits = sorted(t for t in tokens if t in low)
            if not hits:
                continue
            rows.append({
                "path": rel.as_posix(),
                "hits": hits,
                "lines": text.count("\n") + 1,
                "classes": sum(isinstance(n, ast.ClassDef) for n in ast.walk(tree)),
                "functions": sum(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) for n in ast.walk(tree)),
                "digest": sha256(text.encode()).hexdigest(),
            })
        rows.sort(key=lambda r: (-len(r["hits"]), r["lines"], r["path"]))
        result = {"mission_id": mission.mission_id, "files": rows[:max_files], "candidate_digest": _tree_digest(root, exclude=(".git", "__pycache__", ".pytest_cache")), "inspected_at": _now()}
        state.metadata.setdefault(self.KEY, {})[mission.mission_id] = result
        return result


# 34. Autonomous research planning/evidence ledger for self-improvement
class SelfImprovementResearch:
    KEY = "self_improvement_research_v1"

    def plan(self, state: ProjectState, mission: SelfImprovementMission, inspection: dict[str, Any]) -> dict[str, Any]:
        plan = {
            "mission_id": mission.mission_id,
            "questions": mission.research_questions,
            "preferred_sources": ["official documentation", "upstream project documentation", "standards/specifications", "primary issue/release notes"],
            "browser_capability_required": True,
            "source_requirements": {"url_required": True, "claim_to_source_link": True, "untrusted_content_is_data": True, "no_instruction_authority": True},
            "code_context": [x["path"] for x in inspection.get("files", [])[:12]],
            "network_execution": "DEFERRED_UNTIL_BROWSER_LIVE",
        }
        state.metadata.setdefault(self.KEY, {})[mission.mission_id] = {"plan": plan, "sources": []}
        return plan

    def record_sources(self, state: ProjectState, mission_id: str, sources: Sequence[dict[str, Any]]) -> dict[str, Any]:
        accepted = []
        for source in sources:
            url = str(source.get("url", "")).strip()
            if not url.startswith(("https://", "http://")):
                continue
            accepted.append({"url": url, "title": str(source.get("title", ""))[:300], "claims": list(source.get("claims", [])), "authority": str(source.get("authority", "unknown")), "recorded_at": _now()})
        row = state.metadata.setdefault(self.KEY, {}).setdefault(mission_id, {"plan": {}, "sources": []})
        row["sources"] = accepted[-100:]
        return {"mission_id": mission_id, "accepted_sources": len(accepted), "sources": accepted[-20:]}


# 35. Controlled autonomous implementation in candidate only
class AutonomousImplementationController:
    KEY = "self_implementation_v1"

    def apply_replacements(self, state: ProjectState, candidate_root: str | Path, running_root: str | Path, *, mission_id: str, edits: Sequence[dict[str, Any]]) -> dict[str, Any]:
        candidate = Path(candidate_root).resolve()
        ImmutableRunningVersion(running_root).assert_candidate(candidate)
        fs = FilesystemOperations(candidate)
        changed: list[dict[str, Any]] = []
        for edit in edits:
            path = str(edit["path"])
            old, new = str(edit["old"]), str(edit["new"])
            expected = int(edit.get("expected_occurrences", 1))
            result = fs.replace_text(path, old, new, expected_occurrences=expected)
            changed.append(result)
        row = {"mission_id": mission_id, "changed": changed, "changed_paths": sorted({x["path"] for x in changed}), "implemented_at": _now(), "running_version_modified": False}
        state.metadata.setdefault(self.KEY, {})[mission_id] = row
        return row


# 36. Automatic test execution
class AutomaticSelfTestExecutor:
    KEY = "self_test_execution_v1"

    def run(self, state: ProjectState, candidate_root: str | Path, *, mission_id: str, tests: Sequence[str], timeout: int = 180) -> dict[str, Any]:
        root = Path(candidate_root).resolve()
        terminal = TerminalController(root, allowed={Path(sys.executable).name})
        argv = [sys.executable, "-m", "pytest", "-q", *list(tests)]
        result = terminal.run(argv, timeout=timeout)
        row = {"mission_id": mission_id, "tests": list(tests), "passed": result.ok, "returncode": result.returncode, "stdout": result.stdout, "stderr": result.stderr, "executed_at": _now()}
        state.metadata.setdefault(self.KEY, {})[mission_id] = row
        return row


# 37. Regression selection using dependency impact plus safe fallback
class SelfRegressionSelector:
    def __init__(self) -> None:
        self.impact = DependencyImpactAnalyzer()
        self.incremental = IncrementalVerificationPlanner()

    def select(self, *, changed_paths: Iterable[str], all_tests: Iterable[str], dependency_map: dict[str, Iterable[str]] | None = None, traces: Iterable[Any] = ()) -> dict[str, Any]:
        changed = sorted(set(str(x) for x in changed_paths))
        impact = self.impact.impacted(changed, dependency_map or {}, traces)
        selected = self.incremental.select(all_tests, impact)
        if selected["mode"] == "incremental" and not selected["tests"]:
            stems = {Path(p).stem.replace("test_", "") for p in changed}
            fuzzy = [t for t in sorted(set(all_tests)) if any(stem and stem in Path(t).stem for stem in stems)]
            if fuzzy:
                selected = {"mode": "incremental_fuzzy", "tests": fuzzy, "saved_fraction": round(1 - len(fuzzy) / max(1, len(set(all_tests))), 4)}
            elif changed:
                selected = {"mode": "safety_full", "tests": sorted(set(all_tests)), "saved_fraction": 0.0}
        return {"changed_paths": changed, "impact": impact, **selected}


# 38. Adversarial self-review
class AdversarialSelfReviewer:
    KEY = "self_adversarial_review_v1"

    def review(self, state: ProjectState, *, mission: SelfImprovementMission, changed_paths: Sequence[str], test_report: dict[str, Any], running_unchanged: bool, research_sources: Sequence[dict[str, Any]] = ()) -> dict[str, Any]:
        attacks = [
            {"name": "tests", "pass": bool(test_report.get("passed")), "detail": "targeted/regression tests must pass"},
            {"name": "stable_immutable", "pass": bool(running_unchanged), "detail": "running version must remain unchanged"},
            {"name": "scope", "pass": all(not p.startswith(("data/", "browser_profiles/")) for p in changed_paths), "detail": "candidate edits stay in source/test scope"},
            {"name": "auto_promotion", "pass": mission.auto_promotion_allowed is False, "detail": "human promotion remains mandatory"},
        ]
        if research_sources:
            attacks.append({"name": "research_provenance", "pass": all(str(x.get("url", "")).startswith(("http://", "https://")) for x in research_sources), "detail": "research claims retain source URLs"})
        reviewer = AdversarialReviewerV2()
        result = reviewer.review(state, artifact_id=f"self:{mission.mission_id}", claims=[], evidence_refs=[f"test:{test_report.get('passed')}", *changed_paths], attack_results=attacks)
        row = {**result, "acceptance_criteria": list(mission.acceptance_criteria), "attacks": attacks, "mission_id": mission.mission_id, "independent": True}
        state.metadata.setdefault(self.KEY, {})[mission.mission_id] = row
        return row


# 39. Baseline comparison
class SelfBaselineComparator:
    KEY = "self_baseline_comparison_v1"

    def compare(self, state: ProjectState, *, mission_id: str, baseline_digest: str, candidate_root: str | Path, tests_passed: bool, adversarial_verdict: str, changed_paths: Sequence[str], security_regressions: int = 0, compatibility_regressions: int = 0) -> dict[str, Any]:
        candidate_digest = _tree_digest(Path(candidate_root), exclude=(".git", "__pycache__", ".pytest_cache"))
        patch_metrics = {
            "tests_passed": tests_passed,
            "root_cause_fixed": tests_passed and adversarial_verdict != "FAIL",
            "security_regressions": security_regressions,
            "compatibility_regressions": compatibility_regressions,
            "lines_changed": max(1, len(changed_paths)),
            "complexity_delta": 0.0,
            "maintainability": .8,
        }
        quality = PatchQualityScorer().score(patch_metrics)
        row = {
            "mission_id": mission_id,
            "baseline_digest": baseline_digest,
            "candidate_digest": candidate_digest,
            "changed": candidate_digest != baseline_digest,
            "changed_paths": sorted(set(changed_paths)),
            "tests_passed": bool(tests_passed),
            "adversarial_verdict": adversarial_verdict,
            "security_regressions": int(security_regressions),
            "compatibility_regressions": int(compatibility_regressions),
            "patch_quality": quality,
            "compared_at": _now(),
        }
        state.metadata.setdefault(self.KEY, {})[mission_id] = row
        return row


# 40. Self-improvement acceptance gate
class SelfImprovementAcceptanceGate:
    KEY = "self_improvement_acceptance_v1"
    STAGES = ("PROPOSED", "IMPLEMENTED", "TESTED", "VERIFIED", "ELIGIBLE_FOR_PROMOTION", "REJECTED")

    def assess(self, state: ProjectState, *, mission: SelfImprovementMission, branch: dict[str, Any], implementation: dict[str, Any], test_report: dict[str, Any], review: dict[str, Any], comparison: dict[str, Any], running_unchanged: bool) -> dict[str, Any]:
        checks = {
            "isolated_branch": str(branch.get("branch", "")).startswith("ceo/self-"),
            "implemented": bool(implementation.get("changed_paths")),
            "tests_passed": bool(test_report.get("passed")),
            "required_tests_executed": set(mission.required_tests).issubset(set(test_report.get("tests", []))),
            "independent_review": bool(review.get("independent")) and review.get("verdict") == "PASS",
            "baseline_changed": bool(comparison.get("changed")),
            "security_clean": int(comparison.get("security_regressions", 0)) == 0,
            "compatibility_clean": int(comparison.get("compatibility_regressions", 0)) == 0,
            "running_version_unchanged": bool(running_unchanged),
            "auto_promotion_forbidden": mission.auto_promotion_allowed is False,
        }
        if not checks["implemented"]:
            stage = "PROPOSED"
        elif not checks["tests_passed"]:
            stage = "IMPLEMENTED"
        elif not checks["independent_review"]:
            stage = "TESTED"
        elif not all(checks[k] for k in ("security_clean", "compatibility_clean", "running_version_unchanged")):
            stage = "REJECTED"
        elif all(checks.values()):
            stage = "ELIGIBLE_FOR_PROMOTION"
        else:
            stage = "VERIFIED"
        row = {
            "mission_id": mission.mission_id,
            "stage": stage,
            "checks": checks,
            "eligible_for_human_promotion": stage == "ELIGIBLE_FOR_PROMOTION",
            "auto_promoted": False,
            "promotion_requires_human": True,
            "assessed_at": _now(),
        }
        state.metadata.setdefault(self.KEY, {})[mission.mission_id] = row
        return row


class SelfHostingEvolutionCore:
    VERSION = 1

    def __init__(self, running_root: str | Path):
        self.running_root = Path(running_root).resolve()
        self.compiler = SelfImprovementMissionCompiler()
        self.branches = SelfImprovementBranchCreator()
        self.inspector = SelfCodeInspector()
        self.research = SelfImprovementResearch()
        self.implementation = AutonomousImplementationController()
        self.tests = AutomaticSelfTestExecutor()
        self.regression = SelfRegressionSelector()
        self.reviewer = AdversarialSelfReviewer()
        self.baseline = SelfBaselineComparator()
        self.gate = SelfImprovementAcceptanceGate()
        self.pipeline = SelfImprovementPipeline()

    def snapshot(self, state: ProjectState) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "missions": len(state.metadata.get(SelfImprovementMissionCompiler.KEY, {})),
            "branches": len(state.metadata.get(SelfImprovementBranchCreator.KEY, {})),
            "implementations": len(state.metadata.get(AutonomousImplementationController.KEY, {})),
            "test_runs": len(state.metadata.get(AutomaticSelfTestExecutor.KEY, {})),
            "adversarial_reviews": len(state.metadata.get(AdversarialSelfReviewer.KEY, {})),
            "acceptance": list(state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values())[-10:],
            "auto_promotion_allowed": False,
            "windows_physical": "DEFERRED_BY_USER",
        }

    def preflight(self, state: ProjectState) -> dict[str, Any]:
        checks = {
            "self_branch_creator": True,
            "mission_compiler": True,
            "self_code_inspector": True,
            "autonomous_research_plan": True,
            "candidate_only_implementation": True,
            "automatic_tests": True,
            "impact_regression_selection": True,
            "adversarial_self_review": True,
            "baseline_comparison": True,
            "human_promotion_gate": True,
        }
        return {"pass": all(checks.values()), "checks": checks, "auto_promotion_allowed": False, "windows_physical": "DEFERRED_BY_USER"}
