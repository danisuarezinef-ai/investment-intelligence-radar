from __future__ import annotations
from typing import Any

GATES = (
    'base_candidate_ready',
    'windows_startup_preflight',
    'restart_bridge_direct_python',
    'rollback_filter',
    'version_order',
    'package_contract',
    'compileall',
    'javascript_syntax',
    'security_audit',
)


def qualify_windows_release_v1(
    gates: dict[str, bool],
    *,
    windows_physical_verified: bool = False,
    human_publication_authorized: bool = False,
    human_install_authorized: bool = False,
) -> dict[str, Any]:
    """Windows-only release readiness.

    Android evidence may coexist in the package but cannot block or pre-verify the
    independent Windows release line. Publication and installation remain explicit
    human gates and physical Windows verification is never inferred from local tests.
    """
    local = {k: bool(gates.get(k, False)) for k in GATES}
    local_ready = all(local.values())
    return {
        'schema_version': 1,
        'platform': 'windows',
        'android_runtime_required_for_windows_release': False,
        'local_gates': local,
        'local_candidate_ready': local_ready,
        'windows_physical_verified': bool(windows_physical_verified),
        'human_publication_authorized': bool(human_publication_authorized),
        'human_install_authorized': bool(human_install_authorized),
        'publication_allowed': bool(local_ready and human_publication_authorized),
        'installation_allowed': bool(local_ready and human_install_authorized),
        'production_ready': bool(local_ready and windows_physical_verified),
        'automatic_publication': False,
        'automatic_installation': False,
        'spending_allowed': False,
        'destructive_authority_added': False,
        'next_action': (
            'human_publication_review'
            if local_ready and not human_publication_authorized
            else 'one_shot_windows_physical_update'
            if local_ready and human_publication_authorized and not windows_physical_verified
            else 'human_release_review'
        ),
    }
