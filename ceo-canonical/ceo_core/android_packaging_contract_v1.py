from __future__ import annotations

from typing import Any


REQUIRED = {
    "application_id", "version_name", "version_code", "single_install_package",
    "in_app_updates", "manual_post_install_configuration_required", "shared_core_protocol",
}


def validate_android_packaging_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    missing = sorted(REQUIRED - set(manifest))
    problems: list[str] = []
    if missing: problems.append("missing:" + ",".join(missing))
    if not str(manifest.get("application_id") or "").strip(): problems.append("application_id_invalid")
    if int(manifest.get("version_code") or 0) <= 0: problems.append("version_code_invalid")
    if manifest.get("single_install_package") is not True: problems.append("single_install_package_required")
    if manifest.get("in_app_updates") is not True: problems.append("in_app_updates_required")
    if manifest.get("manual_post_install_configuration_required") is not False: problems.append("manual_post_install_configuration_must_be_false")
    forbidden = set(manifest.get("requested_privileged_capabilities") or []) & {
        "arbitrary_shell", "credential_export", "automatic_publication", "automatic_installation",
        "payments", "subscriptions", "destructive_delete", "real_trading",
    }
    if forbidden: problems.append("forbidden_capabilities:" + ",".join(sorted(forbidden)))
    return {
        "schema_version": 1,
        "ok": not problems,
        "problems": problems,
        "first_public_install_ready_for_validation": not problems,
        "automatic_installation": False,
        "automatic_publication": False,
        "manual_post_install_configuration_required": False,
    }
