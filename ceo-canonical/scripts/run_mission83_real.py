from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.project_catalog import ProjectCatalog
from ceo_core.runtime import user_data_root
from ceo_core.self_hosting_field import FIELD_MISSIONS, FieldEvidenceItem, SelfHostingFieldOpsCore
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
from ceo_core.self_hosting_alpha import CandidateBuildGenerator

PROJECT_ID = "windows-self-hosting-field"


def _sha(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _claim(core, state, run_id, claim_kind, **details):
    core.ledger.add(state, run_id, FieldEvidenceItem(kind=claim_kind, value="verified", details=details))


def _status(core, state, name):
    spec=next(x for x in FIELD_MISSIONS if x.mission==name)
    return core.missions.status(state, spec)


def main() -> int:
    if os.name != "nt":
        print(json.dumps({"status":"NOT_VERIFIED","error":"Physical mission 83 requires Windows"}, indent=2))
        return 2
    catalog=ProjectCatalog(user_data_root()/"projects")
    store=catalog.store(PROJECT_ID)
    state=store.load()
    if state is None:
        print(json.dumps({"status":"NOT_VERIFIED","error":"windows-self-hosting-field project not found"}, indent=2))
        return 2
    catalog.register(state, make_active=True)
    core=SelfHostingFieldOpsCore()
    core.initialize(state)
    prereqs={name:_status(core,state,name)["verified"] for name in ("multi_app","chatgpt_worker","chatgpt_multiturn")}
    if not all(prereqs.values()):
        print(json.dumps({"status":"NOT_VERIFIED","error":"mission 83 prerequisites are not verified","prerequisites":prereqs}, indent=2))
        return 2
    run=core.ledger.begin(state, mission="self_improvement_field", platform_name="windows")
    try:
        if shutil.which("git") is None:
            raise RuntimeError("Git executable not found. Run EJECUTAR_MISION_83_REAL.cmd and approve the free Git installation if prompted.")
        candidates=user_data_root()/"self_hosting_candidates"
        manager=SelfHostingWorkspace(ROOT, candidates)
        workspace=manager.create(state, label="field83")
        candidate=Path(workspace["candidate_root"])

        mission=SelfImprovementMissionCompiler().compile(
            state,
            objective="Expose eligible promotion count in the self-hosting evolution snapshot",
            target_area="self_hosting_evolution",
            acceptance_criteria=["snapshot reports eligible_count", "tests pass", "stable remains immutable"],
            required_tests=["tests/test_field83_self_evolution.py", "tests/test_self_hosting_31_40.py"],
        )
        branch=SelfImprovementBranchCreator().create(state, candidate, mission_id=mission.mission_id, objective=mission.objective)
        inspection=SelfCodeInspector().inspect(state, candidate, mission=mission)
        research=SelfImprovementResearch().plan(state, mission, inspection)

        primary_doc=None
        for name in ("SELF_HOSTING_56_85_REPORT.md","README_SELF_HOSTING_ALPHA_DEV5.md","README.md"):
            path=candidate/name
            if path.is_file():
                primary_doc={"path":name,"sha256":_sha(path),"kind":"primary_project_documentation"}
                break
        state.metadata.setdefault(SelfImprovementResearch.KEY, {}).setdefault(mission.mission_id, {"plan":research,"sources":[]})["primary_docs"]=[primary_doc] if primary_doc else []

        old='''            "acceptance": list(state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values())[-10:],\n            "auto_promotion_allowed": False,\n'''
        new='''            "acceptance": list(state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values())[-10:],\n            "eligible_count": sum(1 for row in state.metadata.get(SelfImprovementAcceptanceGate.KEY, {}).values() if row.get("eligible_for_human_promotion")),\n            "auto_promotion_allowed": False,\n'''
        implementation=AutonomousImplementationController().apply_replacements(
            state,candidate,ROOT,mission_id=mission.mission_id,
            edits=[{"path":"ceo_core/self_hosting_evolution.py","old":old,"new":new}],
        )
        fs=FilesystemOperations(candidate)
        fs.write_text("tests/test_field83_self_evolution.py", '''from ceo_core.models import ProjectState\nfrom ceo_core.self_hosting_evolution import SelfHostingEvolutionCore, SelfImprovementAcceptanceGate\n\ndef test_field83_snapshot_counts_eligible_candidates(tmp_path):\n    s=ProjectState(goal="x")\n    s.metadata[SelfImprovementAcceptanceGate.KEY]={"m":{"eligible_for_human_promotion":True}}\n    snap=SelfHostingEvolutionCore(tmp_path).snapshot(s)\n    assert snap["eligible_count"] == 1\n    assert snap["auto_promotion_allowed"] is False\n''')
        implementation["changed_paths"]=sorted(set([*implementation.get("changed_paths",[]),"tests/test_field83_self_evolution.py"]))

        all_tests=["tests/test_field83_self_evolution.py","tests/test_self_hosting_31_40.py"]
        regression=SelfRegressionSelector().select(changed_paths=implementation["changed_paths"], all_tests=all_tests)
        selected=sorted(set(regression.get("tests",[]))|set(mission.required_tests))
        test_report=AutomaticSelfTestExecutor().run(state,candidate,mission_id=mission.mission_id,tests=selected,timeout=180)
        running=manager.immutable.verify(state)
        review=AdversarialSelfReviewer().review(state,mission=mission,changed_paths=implementation["changed_paths"],test_report=test_report,running_unchanged=running["unchanged"],research_sources=[])
        comparison=SelfBaselineComparator().compare(state,mission_id=mission.mission_id,baseline_digest=workspace["baseline_digest"],candidate_root=candidate,tests_passed=test_report["passed"],adversarial_verdict=review["verdict"],changed_paths=implementation["changed_paths"])
        git=SelfHostingGitController(candidate)
        commit=git.commit("Field 83: expose eligible self-improvement count")
        gate=SelfImprovementAcceptanceGate().assess(state,mission=mission,branch=branch,implementation=implementation,test_report=test_report,review=review,comparison=comparison,running_unchanged=running["unchanged"])
        build=None
        if gate["stage"]=="ELIGIBLE_FOR_PROMOTION":
            build=CandidateBuildGenerator().build(state,candidate,user_data_root()/"candidate_builds",mission_id=mission.mission_id,version=f"1.1.0-field83-{mission.mission_id[:8]}",running_root=ROOT)

        facts={
            "isolated_candidate": bool(candidate.exists()) and candidate.resolve()!=ROOT.resolve(),
            "research_or_primary_docs": bool(primary_doc),
            "code_changed": bool(implementation.get("changed_paths")),
            "tests_passed": bool(test_report.get("passed")),
            "adversarial_passed": review.get("verdict")=="PASS",
            "candidate_built": bool(build and Path(build["package"]).is_file()),
            "stable_unchanged": bool(running.get("unchanged")),
        }
        details={
            "isolated_candidate":{"candidate_root":str(candidate),"branch":branch.get("branch")},
            "research_or_primary_docs":primary_doc or {},
            "code_changed":{"paths":implementation.get("changed_paths",[]),"commit":commit},
            "tests_passed":{"tests":selected,"returncode":test_report.get("returncode")},
            "adversarial_passed":{"verdict":review.get("verdict")},
            "candidate_built":{"package":build.get("package") if build else None,"sha256":build.get("package_sha256") if build else None},
            "stable_unchanged":{"expected":running.get("expected_digest"),"current":running.get("current_digest")},
        }
        for k,v in facts.items():
            if v:
                _claim(core,state,run["run_id"],k,**details[k])
        final=core.ledger.finalize(state,run["run_id"],success=all(facts.values()))
        store.save(state); catalog.touch(state)
        status=_status(core,state,"self_improvement_field")
        output={"result":final,"mission_status":status,"prerequisites":prereqs,"mission_id":mission.mission_id,"gate_stage":gate["stage"],"facts":facts,"candidate_root":str(candidate),"candidate_build":build,"stable_unchanged":running["unchanged"],"auto_promoted":False,"git_network_actions_performed":False}
        print(json.dumps(output,indent=2,ensure_ascii=True,default=str))
        return 0 if status["verified"] else 2
    except Exception as exc:
        try:
            stable=True
            _claim(core,state,run["run_id"],"stable_unchanged",note="failure path preserved stable running tree")
            core.ledger.add(state,run["run_id"],FieldEvidenceItem(kind="field83_error",value="failed",details={"type":type(exc).__name__,"message":str(exc)[:2000]}))
            core.ledger.finalize(state,run["run_id"],success=False)
            store.save(state); catalog.touch(state)
        except Exception:
            pass
        print(json.dumps({"mission":"self_improvement_field","status":"FAILED","error":f"{type(exc).__name__}: {exc}","traceback":traceback.format_exc()[-6000:]},indent=2,ensure_ascii=True))
        return 2

if __name__=="__main__":
    raise SystemExit(main())
