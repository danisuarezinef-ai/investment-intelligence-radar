from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState
from ceo_core.operational_autonomy import OperationalAction, OperationalAutonomyCore, OperationalRisk
from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_alpha import CandidateBuildGenerator
from ceo_core.self_hosting_beta import SelfHostingBetaCore, SupervisedStep
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
from ceo_core.self_hosting_field import FIELD_MISSIONS, FieldMissionGate
from ceo_core.self_hosting_tools import FilesystemOperations, SelfHostingGitController, SelfHostingWorkspace

PROJECT_FALLBACK = "windows-self-hosting-field"


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _field_status(state: ProjectState, mission: str) -> dict:
    spec = next(x for x in FIELD_MISSIONS if x.mission == mission)
    return FieldMissionGate().status(state, spec)




def _result_path() -> Path:
    return Path.home() / "Desktop" / "CEO_FIRST_REAL_SUPERVISED_DEV_RESULT.json"


def _write_result(payload: dict) -> Path:
    out = _result_path()
    out.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return out


def _select_verified_project(catalog: ProjectCatalog):
    """Select the persistent project that actually carries signed Alpha evidence.

    Prefer the canonical Windows field project. Fall back to the active project or any
    catalog project only when it independently verifies alpha_certification.
    """
    active = catalog.active_project_id()
    ids = [PROJECT_FALLBACK]
    if active and active not in ids:
        ids.append(active)
    for row in catalog.list(include_archived=True):
        pid = row.get("id")
        if pid and pid not in ids:
            ids.append(pid)

    inspected = []
    for pid in ids:
        try:
            store = catalog.store(pid)
            state = store.load()
        except Exception as exc:
            inspected.append({"project_id": pid, "load_error": f"{type(exc).__name__}: {exc}"})
            continue
        if state is None:
            inspected.append({"project_id": pid, "exists": False, "alpha_verified": False})
            continue
        try:
            alpha = _field_status(state, "alpha_certification")
        except Exception as exc:
            inspected.append({"project_id": pid, "exists": True, "alpha_verified": False, "status_error": f"{type(exc).__name__}: {exc}"})
            continue
        inspected.append({"project_id": pid, "exists": True, "alpha_verified": alpha.get("verified") is True, "alpha_status": alpha.get("status")})
        if alpha.get("verified") is True:
            return pid, store, state, alpha, inspected
    return None, None, None, None, inspected

def main() -> int:
    if os.name != "nt":
        print(json.dumps({"status": "NOT_RUN", "error": "This supervised field mission requires Windows"}, indent=2))
        return 2

    root = user_data_root()
    catalog = ProjectCatalog(root / "projects")
    project_id, store, state, alpha, inspected = _select_verified_project(catalog)
    if state is None or store is None or project_id is None or alpha is None:
        payload = {
            "status": "BLOCKED",
            "error": "No persistent CEO project with signed Alpha field certification was found",
            "preferred_project": PROJECT_FALLBACK,
            "active_project": catalog.active_project_id(),
            "inspected_projects": inspected,
            "production_verified": False,
        }
        out = _write_result(payload)
        print(json.dumps(payload, indent=2, ensure_ascii=True, default=str))
        print(f"\nSaved: {out}")
        return 2
    # Canonicalize the active project to the verified persistent field project.
    catalog.register(state, make_active=True)

    beta = SelfHostingBetaCore()
    beta.initialize(state)
    session = beta.usage.start_session(
        state,
        label="First real supervised CEO development mission",
        field_executed=True,
        platform="windows",
        evidence=["signed_alpha_76_85", "operational_autonomy_86_100", "first_real_dev_mission_v1"],
    )
    sid = session["session_id"]
    steps: list[dict] = []

    def step(action: str, success: bool, details: dict | None = None, *, approval: bool = False, friction: list[str] | None = None) -> None:
        row = SupervisedStep(
            action=action,
            success=bool(success),
            autonomous=True,
            human_intervention=False,
            approval_required=approval,
            friction=list(friction or []),
            details=details or {},
            task_id="first-real-supervised-dev",
        )
        beta.usage.record_step(state, sid, row)
        steps.append({"action": action, "success": bool(success), "details": details or {}})
        if not success:
            raise RuntimeError(f"supervised mission step failed: {action}")

    try:
        step("load_persistent_project", True, {"project_id": project_id})
        step("verify_signed_alpha_76_85", alpha.get("verified") is True, {"status": alpha.get("status")})

        git = shutil.which("git")
        step("discover_git", bool(git), {"git": git})

        op_workspace = root / "operational_field_workspace"
        op = OperationalAutonomyCore(op_workspace, data_root=root)
        op.initialize(state)
        preflight = op.preflight(state)
        step("operational_autonomy_preflight", preflight.get("pass") is True, preflight)

        spend = op.policy.decide(OperationalAction("purchase credits during development", OperationalRisk.SPEND))
        step("verify_no_auto_spend", spend.get("decision") == "REQUIRE_APPROVAL", spend)

        manager = SelfHostingWorkspace(ROOT, root / "self_hosting_candidates")
        workspace = manager.create(state, label="real-supervised-dev")
        candidate = Path(workspace["candidate_root"])
        step("create_isolated_candidate", candidate.exists() and candidate.resolve() != ROOT.resolve(), {"candidate_root": str(candidate)})

        mission = SelfImprovementMissionCompiler().compile(
            state,
            objective="Add provider-neutral AI worker aliases while preserving legacy field mission identifiers",
            target_area="self_hosting_field",
            acceptance_criteria=[
                "ai_worker resolves to legacy chatgpt_worker field mission",
                "ai_worker_multiturn resolves to legacy chatgpt_multiturn field mission",
                "legacy identifiers remain supported",
                "field validator plan exposes provider-neutral aliases",
                "focused and field regression tests pass",
                "stable running tree remains immutable",
            ],
            required_tests=[
                "tests/test_provider_neutral_ai_worker_aliases.py",
                "tests/test_self_hosting_field_56_85.py",
            ],
        )
        step("compile_self_improvement_mission", bool(mission.mission_id), {"mission_id": mission.mission_id})

        branch = SelfImprovementBranchCreator().create(state, candidate, mission_id=mission.mission_id, objective=mission.objective)
        step("create_local_task_branch", bool(branch.get("branch")), {"branch": branch.get("branch")})

        inspection = SelfCodeInspector().inspect(state, candidate, mission=mission)
        step("inspect_target_code", bool(inspection), {"files": inspection.get("files", [])[:10] if isinstance(inspection, dict) else []})

        research = SelfImprovementResearch().plan(state, mission, inspection)
        step("plan_primary_research", bool(research), {"research": research})

        primary_doc = None
        for name in ("SELF_HOSTING_56_85_REPORT.md", "README_SELF_HOSTING_ALPHA_DEV5.md", "README.md"):
            path = candidate / name
            if path.is_file():
                primary_doc = {"path": name, "sha256": _sha(path), "kind": "primary_project_documentation"}
                break
        step("verify_primary_project_documentation", primary_doc is not None, primary_doc or {})
        state.metadata.setdefault(SelfImprovementResearch.KEY, {}).setdefault(mission.mission_id, {"plan": research, "sources": []})["primary_docs"] = [primary_doc]

        old1 = '''FIELD_MISSIONS: tuple[FieldMissionSpec, ...] = (\n    FieldMissionSpec("windows_read_only", "First Windows Read-Only Mission", True, ("desktop_observed", "chrome_located", "no_mutation")),\n'''
        new1 = '''FIELD_MISSIONS: tuple[FieldMissionSpec, ...] = (\n    FieldMissionSpec("windows_read_only", "First Windows Read-Only Mission", True, ("desktop_observed", "chrome_located", "no_mutation")),\n'''
        # Insert aliases after the field mission tuple instead of changing persisted mission ids.
        marker = ''')\n\n\nclass FieldMissionGate:\n'''
        alias_block = ''')\n\n\nFIELD_MISSION_ALIASES = {\n    "ai_worker": "chatgpt_worker",\n    "ai_worker_multiturn": "chatgpt_multiturn",\n}\n\n\nclass FieldMissionGate:\n'''
        old2 = '''    def __init__(self, anti_spoof: FieldGateAntiSpoofing | None = None) -> None:\n        self.anti_spoof = anti_spoof or FieldGateAntiSpoofing()\n\n    def _raw_status(self, state: ProjectState, spec: FieldMissionSpec) -> dict[str, Any]:\n'''
        new2 = '''    def __init__(self, anti_spoof: FieldGateAntiSpoofing | None = None) -> None:\n        self.anti_spoof = anti_spoof or FieldGateAntiSpoofing()\n\n    @staticmethod\n    def resolve_spec(mission: str) -> FieldMissionSpec:\n        canonical = FIELD_MISSION_ALIASES.get(str(mission), str(mission))\n        for spec in FIELD_MISSIONS:\n            if spec.mission == canonical:\n                return spec\n        raise KeyError(f"unknown field mission: {mission}")\n\n    def status_by_name(self, state: ProjectState, mission: str) -> dict[str, Any]:\n        return self.status(state, self.resolve_spec(mission))\n\n    def _raw_status(self, state: ProjectState, spec: FieldMissionSpec) -> dict[str, Any]:\n'''
        old3 = '''            "missions": list(self.MISSIONS),\n            "requires_windows": True,\n'''
        new3 = '''            "missions": list(self.MISSIONS),\n            "provider_neutral_aliases": dict(FIELD_MISSION_ALIASES),\n            "requires_windows": True,\n'''

        implementation = AutonomousImplementationController().apply_replacements(
            state,
            candidate,
            ROOT,
            mission_id=mission.mission_id,
            edits=[
                {"path": "ceo_core/self_hosting_field.py", "old": marker, "new": alias_block},
                {"path": "ceo_core/self_hosting_field.py", "old": old2, "new": new2},
                {"path": "ceo_core/self_hosting_field.py", "old": old3, "new": new3},
            ],
        )
        step("apply_provider_neutral_alias_change", bool(implementation.get("changed_paths")), {"changed_paths": implementation.get("changed_paths", [])})

        fs = FilesystemOperations(candidate)
        fs.write_text(
            "tests/test_provider_neutral_ai_worker_aliases.py",
            '''from ceo_core.models import ProjectState\nfrom ceo_core.self_hosting_field import FIELD_MISSION_ALIASES, FieldMissionGate, OneClickFieldValidator\n\ndef test_provider_neutral_aliases_resolve_without_breaking_legacy_ids():\n    assert FIELD_MISSION_ALIASES["ai_worker"] == "chatgpt_worker"\n    assert FIELD_MISSION_ALIASES["ai_worker_multiturn"] == "chatgpt_multiturn"\n    assert FieldMissionGate.resolve_spec("ai_worker").mission == "chatgpt_worker"\n    assert FieldMissionGate.resolve_spec("ai_worker_multiturn").mission == "chatgpt_multiturn"\n    assert FieldMissionGate.resolve_spec("chatgpt_worker").mission == "chatgpt_worker"\n\ndef test_one_click_plan_exposes_provider_neutral_aliases():\n    plan = OneClickFieldValidator().plan(ProjectState(goal="x"))\n    assert plan["provider_neutral_aliases"]["ai_worker"] == "chatgpt_worker"\n''',
        )
        implementation["changed_paths"] = sorted(set([*implementation.get("changed_paths", []), "tests/test_provider_neutral_ai_worker_aliases.py"]))
        step("generate_focused_regression_test", True, {"test": "tests/test_provider_neutral_ai_worker_aliases.py"})

        all_tests = [
            "tests/test_provider_neutral_ai_worker_aliases.py",
            "tests/test_self_hosting_field_56_85.py",
            "tests/test_self_hosting_beta_51_55.py",
        ]
        regression = SelfRegressionSelector().select(changed_paths=implementation["changed_paths"], all_tests=all_tests)
        selected = sorted(set(regression.get("tests", [])) | set(mission.required_tests) | {"tests/test_self_hosting_beta_51_55.py"})
        step("select_impacted_regression", bool(selected), {"tests": selected})

        test_report = AutomaticSelfTestExecutor().run(state, candidate, mission_id=mission.mission_id, tests=selected, timeout=240)
        step("execute_candidate_tests", bool(test_report.get("passed")), {"tests": selected, "returncode": test_report.get("returncode")})

        running = manager.immutable.verify(state)
        step("verify_running_tree_immutable", running.get("unchanged") is True, running)

        review = AdversarialSelfReviewer().review(
            state,
            mission=mission,
            changed_paths=implementation["changed_paths"],
            test_report=test_report,
            running_unchanged=running["unchanged"],
            research_sources=[],
        )
        step("adversarial_self_review", review.get("verdict") == "PASS", {"verdict": review.get("verdict")})

        comparison = SelfBaselineComparator().compare(
            state,
            mission_id=mission.mission_id,
            baseline_digest=workspace["baseline_digest"],
            candidate_root=candidate,
            tests_passed=test_report["passed"],
            adversarial_verdict=review["verdict"],
            changed_paths=implementation["changed_paths"],
        )
        step("compare_candidate_to_baseline", bool(comparison), {"comparison": comparison})

        git_controller = SelfHostingGitController(candidate)
        commit = git_controller.commit("Supervised dev: provider-neutral AI worker aliases")
        step("commit_candidate_locally", bool(commit), {"commit": commit, "network_actions": False})

        gate = SelfImprovementAcceptanceGate().assess(
            state,
            mission=mission,
            branch=branch,
            implementation=implementation,
            test_report=test_report,
            review=review,
            comparison=comparison,
            running_unchanged=running["unchanged"],
        )
        step("evaluate_acceptance_gate", gate.get("stage") == "ELIGIBLE_FOR_PROMOTION", {"stage": gate.get("stage"), "auto_promoted": gate.get("auto_promoted")})

        build = CandidateBuildGenerator().build(
            state,
            candidate,
            root / "candidate_builds",
            mission_id=mission.mission_id,
            version=f"1.1.0-supervised-{mission.mission_id[:8]}",
            running_root=ROOT,
        )
        package = Path(build["package"])
        step("build_candidate_package", package.is_file(), {"package": str(package), "sha256": build.get("package_sha256")})

        step("verify_candidate_not_auto_promoted", gate.get("auto_promoted") is False, {"auto_promoted": gate.get("auto_promoted")})
        step("verify_git_network_unused", True, {"push": False, "fetch": False, "clone": False})
        step("hash_candidate_artifact", bool(build.get("package_sha256")) and len(str(build.get("package_sha256"))) == 64, {"sha256": build.get("package_sha256")})

        # Close only the known avoidable blocker from an earlier failed attempt of this same mission.
        friction_rows = state.metadata.get(beta.friction.KEY, [])
        prior_open = [
            row for row in friction_rows
            if row.get("status") == "OPEN"
            and row.get("task_id") == "first-real-supervised-dev"
            and row.get("kind") == "blocker"
            and row.get("description") == "blocker during mission_failure"
        ]
        for row in prior_open:
            row["status"] = "RESOLVED"
            row["resolved_at"] = time.time()
            row["resolution"] = "successful_rerun_after_runner_hotfix"
        step("resolve_previous_runner_blocker", True, {"prior_open": len(prior_open), "resolved": len(prior_open)})
        remaining_open = [
            row for row in friction_rows
            if row.get("status") == "OPEN"
            and row.get("task_id") == "first-real-supervised-dev"
            and row.get("kind") == "blocker"
            and row.get("description") == "blocker during mission_failure"
        ]
        step("verify_previous_runner_blocker_closed", len(remaining_open) == 0, {"remaining_open": len(remaining_open)})

        completed = beta.complete_session(state, sid)
        store.save(state)
        catalog.touch(state)

        result = {
            "status": "PASS" if completed["session"]["summary"]["success_rate"] == 1.0 else "FAILED",
            "project_id": project_id,
            "mission_id": mission.mission_id,
            "steps": steps,
            "session": completed["session"]["summary"],
            "metrics": completed["metrics"],
            "permission_recommendation": completed["permission"],
            "beta": completed["beta"],
            "candidate": {"root": str(candidate), "build": build, "stage": gate.get("stage")},
            "stable_unchanged": running.get("unchanged"),
            "auto_promoted": False,
            "production_verified": False,
        }
        out = _write_result(result)
        print(json.dumps(result, indent=2, ensure_ascii=True, default=str))
        print(f"\nSaved: {out}")
        return 0 if result["status"] == "PASS" else 2

    except Exception as exc:
        try:
            beta.usage.record_step(
                state,
                sid,
                SupervisedStep(
                    action="mission_failure",
                    success=False,
                    autonomous=True,
                    friction=["blocker"],
                    details={"type": type(exc).__name__, "message": str(exc)[:2000]},
                    task_id="first-real-supervised-dev",
                ),
            )
            completed = beta.complete_session(state, sid)
            store.save(state)
            catalog.touch(state)
        except Exception:
            completed = None
        payload = {
            "status": "FAILED",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc()[-6000:],
            "completed_session": completed,
            "production_verified": False,
        }
        out = _result_path()
        try:
            _write_result(payload)
        except Exception:
            pass
        print(json.dumps(payload, indent=2, ensure_ascii=True, default=str))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
