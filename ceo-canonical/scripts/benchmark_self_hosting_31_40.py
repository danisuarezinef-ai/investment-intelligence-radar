from __future__ import annotations

import json
import shutil
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState
from ceo_core.self_hosting_tools import FilesystemOperations, SelfHostingGitController, SelfHostingWorkspace
from ceo_core.self_hosting_evolution import (
    AdversarialSelfReviewer,
    AutomaticSelfTestExecutor,
    AutonomousImplementationController,
    SelfBaselineComparator,
    SelfCodeInspector,
    SelfImprovementAcceptanceGate,
    SelfImprovementBranchCreator,
    SelfImprovementMissionCompiler,
    SelfImprovementResearch,
    SelfRegressionSelector,
)

OUT = ROOT / "reports" / "SELF_HOSTING_31_40_BENCHMARK.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="ceo-self-31-40-") as td:
        temp = Path(td)
        stable = temp / "stable"
        shutil.copytree(ROOT, stable, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "data", "browser_profiles", "reports"))
        state = ProjectState(goal="Let CEO improve its own self-hosting evolution safely", goal_constraints=["stable running version is immutable"])
        state.metadata["forbidden_actions"] = ["no auto-promotion", "no git network actions"]
        manager = SelfHostingWorkspace(stable, temp / "candidates")
        workspace = manager.create(state, label="dogfood")
        candidate = Path(workspace["candidate_root"])

        compiler = SelfImprovementMissionCompiler()
        mission = compiler.compile(
            state,
            objective="Expose eligible promotion count in self-hosting evolution snapshot",
            target_area="self_hosting_evolution",
            acceptance_criteria=["snapshot reports eligible_count", "tests pass", "stable remains immutable"],
            required_tests=["tests/test_dogfood_self_evolution.py", "tests/test_self_hosting_31_40.py"],
        )
        branch = SelfImprovementBranchCreator().create(state, candidate, mission_id=mission.mission_id, objective=mission.objective)
        inspection = SelfCodeInspector().inspect(state, candidate, mission=mission)
        research = SelfImprovementResearch().plan(state, mission, inspection)

        source = candidate / "ceo_core" / "self_hosting_evolution.py"
        old = '''            "acceptance": list(state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values())[-10:],\n            "auto_promotion_allowed": False,\n'''
        new = '''            "acceptance": list(state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values())[-10:],\n            "eligible_count": sum(1 for row in state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values() if row.get("eligible_for_human_promotion")),\n            "auto_promotion_allowed": False,\n'''
        implementation = AutonomousImplementationController().apply_replacements(
            state, candidate, stable, mission_id=mission.mission_id,
            edits=[{"path":"ceo_core/self_hosting_evolution.py", "old":old, "new":new}],
        )
        fs = FilesystemOperations(candidate)
        fs.write_text("tests/test_dogfood_self_evolution.py", '''from ceo_core.models import ProjectState\nfrom ceo_core.self_hosting_evolution import SelfHostingEvolutionCore, SelfImprovementAcceptanceGate\n\ndef test_snapshot_counts_eligible_candidates(tmp_path):\n    s=ProjectState(goal="x")\n    s.metadata[SelfImprovementAcceptanceGate.KEY]={"m":{"eligible_for_human_promotion":True}}\n    snap=SelfHostingEvolutionCore(tmp_path).snapshot(s)\n    assert snap["eligible_count"] == 1\n    assert snap["auto_promotion_allowed"] is False\n''')
        implementation["changed_paths"].append("tests/test_dogfood_self_evolution.py")
        implementation["changed_paths"] = sorted(set(implementation["changed_paths"]))

        all_tests = ["tests/test_dogfood_self_evolution.py", "tests/test_self_hosting_31_40.py"]
        regression = SelfRegressionSelector().select(changed_paths=implementation["changed_paths"], all_tests=all_tests)
        selected_tests = sorted(set(regression["tests"]) | set(mission.required_tests))
        regression["tests"] = selected_tests
        test_report = AutomaticSelfTestExecutor().run(state, candidate, mission_id=mission.mission_id, tests=selected_tests, timeout=120)
        running_check = manager.immutable.verify(state)
        review = AdversarialSelfReviewer().review(
            state, mission=mission, changed_paths=implementation["changed_paths"], test_report=test_report,
            running_unchanged=running_check["unchanged"], research_sources=[],
        )
        comparison = SelfBaselineComparator().compare(
            state, mission_id=mission.mission_id, baseline_digest=workspace["baseline_digest"], candidate_root=candidate,
            tests_passed=test_report["passed"], adversarial_verdict=review["verdict"], changed_paths=implementation["changed_paths"],
        )
        git = SelfHostingGitController(candidate)
        commit = git.commit("Dogfood: expose eligible self-improvement count")
        gate = SelfImprovementAcceptanceGate().assess(
            state, mission=mission, branch=branch, implementation=implementation, test_report=test_report,
            review=review, comparison=comparison, running_unchanged=running_check["unchanged"],
        )

        result = {
            "benchmark": "self_hosting_31_40_end_to_end",
            "pass": gate["stage"] == "ELIGIBLE_FOR_PROMOTION" and test_report["passed"] and running_check["unchanged"],
            "mission_id": mission.mission_id,
            "branch": branch["branch"],
            "inspection_files": len(inspection["files"]),
            "research_network_execution": research["network_execution"],
            "changed_paths": implementation["changed_paths"],
            "regression_mode": regression["mode"],
            "tests": regression["tests"],
            "tests_passed": test_report["passed"],
            "adversarial_verdict": review["verdict"],
            "baseline_changed": comparison["changed"],
            "patch_quality": comparison["patch_quality"],
            "running_version_unchanged": running_check["unchanged"],
            "candidate_commit": commit,
            "git_network_actions_performed": git.status()["network_actions_performed"],
            "gate_stage": gate["stage"],
            "eligible_for_human_promotion": gate["eligible_for_human_promotion"],
            "auto_promoted": gate["auto_promoted"],
            "windows_physical": "DEFERRED_BY_USER",
            "live_provider": "NOT_VERIFIED",
        }
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result["pass"] else 1

if __name__ == "__main__":
    raise SystemExit(main())
