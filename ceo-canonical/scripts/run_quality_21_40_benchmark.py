from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ceo_core.models import ProjectState
from ceo_core.quality_engineering import QualityEngineeringCore, RequirementsTraceabilityMatrix


def main() -> int:
    q = QualityEngineeringCore()
    state = ProjectState(goal="quality engineering scale benchmark")
    started = time.perf_counter()

    # 1,000 requirements with implementation/test/evidence links.
    for i in range(1000):
        rid = f"R{i:04d}"
        q.traceability.add_requirement(state, rid, f"Requirement {i}")
        status = "VERIFIED" if i % 4 != 0 else "TESTED"
        q.traceability.link(state, rid, implementation=f"src/mod_{i%100}.py", test=f"tests/test_mod_{i%100}.py", evidence=f"E{i}", status=status)
    coverage = q.coverage.assess(q.traceability.matrix(state))

    # Large dependency graph: 1,500 components, each node depending on predecessor.
    deps = {f"src/mod_{i}.py": [f"src/mod_{i-1}.py"] for i in range(1, 1500)}
    impact = q.impact.impacted(["src/mod_0.py"], deps, q.traceability.matrix(state))
    revalidation = q.revalidation.plan(impact, ["E0"])

    # 5,000 evidence observations with deliberate contradictions every 25th claim.
    evidence = []
    for i in range(5000):
        claim = f"C{i%500}"
        outcome = "contradicts" if (i % 97 == 0) else "supports"
        evidence.append({"claim_id": claim, "outcome": outcome, "quality": q.evidence_quality.score(kind="integration_test", direct=True, independent=True, fresh=True)})
    contradictions = q.contradictions.analyze(evidence)

    # 5,000 tests prioritized; 500 tests inspected for flakiness over 8 runs.
    tests = [{"name": f"test_{i}", "failure_rate": (i % 17)/20, "impact": (i % 10)/10, "changed_area": 1 if i < 300 else 0, "duration": .1 + (i % 30)/10} for i in range(5000)]
    prioritized = q.prioritizer.prioritize(tests)
    outcomes = []
    for i in range(500):
        for run in range(8):
            passed = not (i % 50 == 0 and run % 3 == 1)
            outcomes.append({"name": f"test_{i}", "passed": passed, "duration": .1 + run/100})
    flaky = q.flaky.analyze(outcomes)

    # Actual project SBOM and offline risk analysis.
    sbom = q.sbom.from_pyproject(ROOT / "pyproject.toml")
    risks = [q.dependency_risk.assess(dep, criticality=.7 if dep["name"] in {"fastapi", "pydantic"} else .4) for dep in sbom["dependencies"]]

    # Build reproducibility: two clean copies of a stable fixture tree.
    with tempfile.TemporaryDirectory(prefix="ceo-qe-bench-") as td:
        td = Path(td); a = td / "a"; b = td / "b"
        for dest in (a, b):
            (dest / "ceo_core").mkdir(parents=True)
            for name in ("quality_engineering.py", "models.py"):
                shutil.copy2(ROOT / "ceo_core" / name, dest / "ceo_core" / name)
            shutil.copy2(ROOT / "pyproject.toml", dest / "pyproject.toml")
        reproducibility = q.reproducibility.compare(a, b)

        # Synthetic local Git history for hotspot ranking. No remote/network actions.
        repo = td / "repo"; repo.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "benchmark@invalid.example"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "CEO Benchmark"], cwd=repo, check=True)
        for i in range(30):
            (repo / "hot.py").write_text(str(i), encoding="utf-8")
            if i % 5 == 0:
                (repo / f"cold_{i}.py").write_text(str(i), encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", f"commit {i}"], cwd=repo, check=True, capture_output=True)
        git = q.git.analyze(repo)

    # Acceptance/quality/update/migration contracts.
    acceptance = [q.acceptance.generate("RTEST", "tests pass"), q.acceptance.generate("RHUMAN", "interface feels elegant")]
    gate = q.quality_gates.evaluate("code", {"tests_pass": True, "static_pass": True, "requirements_traced": True, "no_critical_security": True})
    update = q.update_simulator.simulate({"name": "fastapi", "specifier": ">=0.115"}, ">=0.116,<1", affected_tests=["tests/test_api.py"], compatibility_passed=True)
    migration = q.migrations.plan(dependency="fastapi", from_spec=">=0.115", to_spec=">=0.116,<1", impacted_components=["ceo_app/main.py"], tests=["tests/test_api.py"])

    result = {
        "version": "0.9.0-dev8",
        "roadmap": "21-40",
        "elapsed_seconds": round(time.perf_counter() - started, 4),
        "requirements": coverage,
        "impact": {"components": len(impact["impacted_components"]), "requirements": len(impact["requirements"]), "tests": len(impact["tests"]), "revalidation_tests": len(revalidation["tests_to_run"])},
        "evidence": {"records": len(evidence), "contradictions": contradictions["count"]},
        "tests": {"prioritized": len(prioritized), "top": prioritized[0]["name"], "flaky_detected": len(flaky["flaky"])},
        "sbom": {"dependencies": sbom["dependency_count"], "digest": sbom["digest"], "max_offline_risk": max((r["risk"] for r in risks), default=0), "network_checked": False},
        "reproducibility": reproducibility,
        "git": {"available": git["available"], "commits_analyzed": git.get("commits_analyzed"), "top_hotspot": git.get("hotspots", [{}])[0]},
        "acceptance": {"automatable": acceptance[0].automatable, "human_review_preserved": not acceptance[1].automatable},
        "quality_gate": {"passed": gate.passed, "score": gate.score},
        "dependency_update": update,
        "migration": {"auto_apply": migration["auto_apply"], "requires_promotion_gate": migration["requires_promotion_gate"]},
        "windows_physical_tests": "DEFERRED_BY_USER",
        "production_verified": False,
    }
    out = ROOT / "reports" / "QUALITY_21_40_BENCHMARK.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
