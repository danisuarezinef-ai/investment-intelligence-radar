from __future__ import annotations

from typing import Any

from .self_dev_receipt_v2 import PROTECTED_PREFIXES
from .tree_manifest_v1 import compare_tree_manifests


def _risk(path: str) -> str:
    p = str(path).replace("\\", "/").lstrip("./")
    if any(p.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return "protected"
    q = p.lower()
    if any(x in q for x in ("update", "release", "bootstrap", "relaunch", "launch_current", "installer", "credential")):
        return "high"
    if any(x in q for x in ("scheduler", "runtime", "store", "remote", "capability", "security", "sync")):
        return "medium"
    return "normal"


def build_convergence_sandbox_plan(base: dict[str, Any], windows: dict[str, Any], mobile: dict[str, Any]) -> dict[str, Any]:
    cmp = compare_tree_manifests(base, windows, mobile)
    steps: list[dict[str, Any]] = []
    blocked: list[str] = []
    for row in cmp["rows"]:
        if row["relation"] == "unchanged":
            continue
        risk = _risk(row["path"])
        if row["relation"] == "divergent_overlap":
            action = "independent_review_then_retest"; blocked.append(row["path"])
        elif risk == "protected":
            action = "privileged_human_review"; blocked.append(row["path"])
        elif risk == "high":
            action = "sandbox_apply_then_full_release_regression"
        else:
            action = "sandbox_apply_then_targeted_regression"
        steps.append({"path": row["path"], "relation": row["relation"], "risk": risk, "action": action})
    return {
        "schema_version": 2,
        "sandbox_only": True,
        "steps": steps,
        "blocked_paths": sorted(set(blocked)),
        "can_materialize_candidate_in_disposable_workspace": not blocked,
        "requires_human_merge_decision": bool(blocked or cmp["same_result_overlap"]),
        "stable_mutation_allowed": False,
        "automatic_merge": False,
        "automatic_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
    }
