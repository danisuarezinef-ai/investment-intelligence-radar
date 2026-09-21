from __future__ import annotations

from typing import Any

from .self_dev_receipt_v2 import PROTECTED_PREFIXES, validate_self_development_receipt_v2


def _norm(path: str) -> str:
    return str(path).replace("\\", "/").lstrip("./")


def _risk(path: str) -> str:
    p = _norm(path)
    if any(p.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return "protected"
    low = p.lower()
    if any(t in low for t in ("update", "release", "bootstrap", "relaunch", "launch_current", "installer")):
        return "high"
    if any(t in low for t in ("scheduler", "runtime", "store", "sqlite", "remote", "capability", "safety")):
        return "medium"
    return "normal"


def build_convergence_plan(
    windows_receipt: dict[str, Any],
    mobile_receipt: dict[str, Any],
    *,
    common_base_version: str,
) -> dict[str, Any]:
    """Produce a three-way *plan* for converging Windows self-dev and mobile work.

    File hashes, when available, allow exact same-result detection. Divergent overlap
    is never silently merged.  This function never edits files.
    """
    w = validate_self_development_receipt_v2(windows_receipt, expected_base_version=common_base_version)
    m = validate_self_development_receipt_v2(mobile_receipt, expected_base_version=common_base_version)
    wf, mf = set(w["changed_files"]), set(m["changed_files"])
    all_paths = sorted(wf | mf)
    items: list[dict[str, Any]] = []
    blocked = False
    for path in all_paths:
        in_w, in_m = path in wf, path in mf
        risk = _risk(path)
        wh, mh = w["file_hashes"].get(path), m["file_hashes"].get(path)
        if in_w and in_m:
            if wh and mh and wh == mh:
                relation, action = "same_result", "deduplicate_candidate_change"
            else:
                relation, action = "divergent_overlap", "independent_review_and_retest"
                blocked = True
        elif in_w:
            relation, action = "windows_only", "carry_forward_for_validation"
        else:
            relation, action = "mobile_only", "carry_forward_for_validation"
        if risk == "protected":
            action = "privileged_human_review"
            blocked = True
        elif risk == "high" and relation == "divergent_overlap":
            action = "adversarial_release_review"
            blocked = True
        items.append({"path": path, "relation": relation, "risk": risk, "recommended_action": action})

    valid_inputs = bool(w["ok"] and m["ok"])
    if not valid_inputs:
        blocked = True
    return {
        "schema_version": 1,
        "common_base_version": str(common_base_version),
        "windows_validation": w,
        "mobile_validation": m,
        "items": items,
        "overlap_files": sorted(wf & mf),
        "divergent_overlap": [x["path"] for x in items if x["relation"] == "divergent_overlap"],
        "same_result_overlap": [x["path"] for x in items if x["relation"] == "same_result"],
        "protected_overlap": [x["path"] for x in items if x["risk"] == "protected" and x["relation"] in {"same_result", "divergent_overlap"}],
        "plan_ready_for_independent_validation": bool(valid_inputs and not blocked),
        "requires_human_merge_decision": bool(blocked or (wf & mf)),
        "automatic_merge": False,
        "automatic_promotion": False,
        "automatic_publication": False,
        "automatic_installation": False,
    }
