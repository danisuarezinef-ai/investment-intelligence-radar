from __future__ import annotations

from typing import Any

REQUIRED_CAPABILITIES = {"task_exchange", "evidence_exchange", "update_metadata", "capability_manifest"}


def evaluate_cross_platform_parity_v1(windows: dict[str, Any], android: dict[str, Any]) -> dict[str, Any]:
    problems: list[str] = []
    wp = int(windows.get("shared_core_protocol") or 0)
    ap = int(android.get("shared_core_protocol") or 0)
    if wp <= 0 or ap <= 0 or wp != ap:
        problems.append("protocol_mismatch")

    ws = windows.get("schemas") if isinstance(windows.get("schemas"), dict) else {}
    a_s = android.get("schemas") if isinstance(android.get("schemas"), dict) else {}
    schema_names = sorted(set(ws) | set(a_s))
    schema_mismatches = [name for name in schema_names if ws.get(name) != a_s.get(name)]
    if schema_mismatches:
        problems.append("schema_mismatch:" + ",".join(schema_mismatches))

    wc = {str(v) for v in windows.get("capabilities", [])}
    ac = {str(v) for v in android.get("capabilities", [])}
    missing_w = sorted(REQUIRED_CAPABILITIES - wc)
    missing_a = sorted(REQUIRED_CAPABILITIES - ac)
    if missing_w:
        problems.append("windows_missing:" + ",".join(missing_w))
    if missing_a:
        problems.append("android_missing:" + ",".join(missing_a))

    if windows.get("ui_surface") == android.get("ui_surface") and windows.get("ui_surface"):
        problems.append("ui_surfaces_must_remain_independent")
    if windows.get("package_kind") == android.get("package_kind") and windows.get("package_kind"):
        problems.append("package_kinds_must_remain_independent")

    return {
        "schema_version": 1,
        "ok": not problems,
        "problems": sorted(set(problems)),
        "protocol": wp if wp == ap else None,
        "schema_names": schema_names,
        "shared_capabilities": sorted(wc & ac),
        "windows_only_capabilities": sorted(wc - ac),
        "android_only_capabilities": sorted(ac - wc),
        "ui_independent": windows.get("ui_surface") != android.get("ui_surface"),
        "packaging_independent": windows.get("package_kind") != android.get("package_kind"),
        "automatic_merge": False,
        "automatic_installation": False,
    }
