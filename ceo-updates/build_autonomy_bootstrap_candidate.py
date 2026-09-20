from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import zipfile

REPO = pathlib.Path(__file__).resolve().parents[1]
BASE = REPO / "ceo-updates" / "CEO_1.5.81-rc1-endgame-closure.zip"
ROOT = pathlib.Path("/tmp/ceo-bootstrap-efficient")
VERSION = "1.5.82-rc1-autonomy-bootstrap"
OLD_VERSION = "1.5.81-rc1-endgame-closure"


def main() -> None:
    shutil.rmtree(ROOT, ignore_errors=True)
    ROOT.mkdir(parents=True)
    with zipfile.ZipFile(BASE) as z:
        z.extractall(ROOT)

    p = ROOT / "ceo_core" / "decomposer.py"
    s = p.read_text(encoding="utf-8")

    class_anchor = '''    DEFAULT_PHASES = [
        ("Clarify & lock goal", "Confirm objective, constraints and completion criteria."),
        ("Research & discovery", "Collect the information and alternatives needed to execute the goal."),
        ("Execution", "Produce the substantive work required by the goal."),
        ("Verification", "Independently check outputs, contradictions, failures and missing work."),
        ("Integration", "Combine verified outputs into a coherent final result."),
        ("Final audit", "Check completion criteria and create any corrective tasks required."),
    ]

    def plan(self, goal: str) -> ProjectState:
'''
    class_new = '''    DEFAULT_PHASES = [
        ("Clarify & lock goal", "Confirm objective, constraints and completion criteria."),
        ("Research & discovery", "Collect the information and alternatives needed to execute the goal."),
        ("Execution", "Produce the substantive work required by the goal."),
        ("Verification", "Independently check outputs, contradictions, failures and missing work."),
        ("Integration", "Combine verified outputs into a coherent final result."),
        ("Final audit", "Check completion criteria and create any corrective tasks required."),
    ]

    COMPACT_PHASES = [
        ("Clarify & lock goal", "Lock the requested output and completion condition."),
        ("Execution", "Produce the requested deliverable directly."),
        ("Final audit", "Verify the deliverable exists and satisfies the locked objective."),
    ]

    @staticmethod
    def _complexity_profile(goal: str) -> dict:
        text = " ".join((goal or "").strip().split())
        low = text.lower()

        complex_terms = (
            "research", "investigate", "compare", "audit", "analyse", "analyze",
            "multiple", "several", "all ", "systematic", "review ", "repository",
            "implement", "refactor", "deploy", "integrate", "across ", "pipeline",
            "database", "architecture", "migration", "benchmark", "experiment",
        )
        simple_output_terms = (
            ".md", ".txt", ".json", ".csv", ".html",
            "short note", "status note", "brief note", "one sentence",
            "single file", "one file",
        )
        conjunctions = sum(low.count(token) for token in (" and ", ";", "\n-", "\n*"))
        complex_score = sum(1 for token in complex_terms if token in low)
        simple_score = sum(1 for token in simple_output_terms if token in low)

        # Conservative compact mode: it is used only for bounded, single-output
        # requests. Ambiguous/complex goals keep the full six-phase decomposition.
        compact = (
            len(text) <= 260
            and complex_score == 0
            and conjunctions <= 2
            and simple_score >= 1
        )
        return {
            "mode": "compact" if compact else "full",
            "characters": len(text),
            "complex_score": complex_score,
            "simple_output_score": simple_score,
            "conjunctions": conjunctions,
        }

    def plan(self, goal: str) -> ProjectState:
'''
    if s.count(class_anchor) != 1:
        raise RuntimeError(f"decomposer class anchor count={s.count(class_anchor)}")
    s = s.replace(class_anchor, class_new, 1)

    loop_anchor = '''        previous_root: str | None = None
        for phase_idx, (title, description) in enumerate(self.DEFAULT_PHASES):
'''
    loop_new = '''        profile = self._complexity_profile(goal)
        state.metadata["decomposition_profile"] = profile
        phases = self.COMPACT_PHASES if profile["mode"] == "compact" else self.DEFAULT_PHASES

        previous_root: str | None = None
        for phase_idx, (title, description) in enumerate(phases):
'''
    if s.count(loop_anchor) != 1:
        raise RuntimeError(f"decomposer loop anchor count={s.count(loop_anchor)}")
    s = s.replace(loop_anchor, loop_new, 1)

    child_anchor = '''            child_count = 3 if title not in {"Execution", "Research & discovery"} else 6
'''
    child_new = '''            child_count = 1 if profile["mode"] == "compact" else (3 if title not in {"Execution", "Research & discovery"} else 6)
'''
    if s.count(child_anchor) != 1:
        raise RuntimeError(f"child count anchor count={s.count(child_anchor)}")
    s = s.replace(child_anchor, child_new, 1)
    p.write_text(s, encoding="utf-8")

    # Version identity only; this candidate remains unpublished until bootstrap gates pass.
    for rel in ("scripts/ceo_stdlib_work_mode.py", "scripts/install_windows_bootstrap.py"):
        q = ROOT / rel
        if q.is_file():
            t = q.read_text(encoding="utf-8")
            q.write_text(t.replace(OLD_VERSION, VERSION), encoding="utf-8")

    contract_path = ROOT / "CEO_UPDATE_PACKAGE.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    contract["app_version"] = VERSION
    hashes = dict(contract.get("file_hashes") or {})
    for rel in hashes:
        fp = ROOT / rel
        if not fp.is_file():
            raise RuntimeError(f"missing contract path {rel}")
        hashes[rel] = hashlib.sha256(fp.read_bytes()).hexdigest()
    contract["file_hashes"] = hashes
    contract_path.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True)+"\n", encoding="utf-8")

    print(json.dumps({"ok": True, "root": str(ROOT), "version": VERSION}, indent=2))


if __name__ == "__main__":
    main()
