from __future__ import annotations
from typing import Any

GATES = ('dev151_ready','android_build_receipt_contract','apk_inspector_contract','runtime_evidence_contract','dual_api_gate_contract',
         'toolchain_license_gate','windows_executor_contract','artifact_ledger','model_checker_v6','soak_guard_v8')

def qualify_release_v13(gates: dict[str,bool], *, windows_physical_verified: bool=False,
                         android_debug_apk_built: bool=False, android_debug_apk_reproducible: bool=False,
                         android_lab_runtime_accepted: bool=False, physical_android_runtime_accepted: bool=False,
                         human_release_authorized: bool=False) -> dict[str,Any]:
    local={k:bool(gates.get(k,False)) for k in GATES}; ready=all(local.values())
    prod=bool(ready and windows_physical_verified and android_debug_apk_built and android_debug_apk_reproducible
              and android_lab_runtime_accepted and physical_android_runtime_accepted and human_release_authorized)
    return {'schema_version':13,'local_gates':local,'local_candidate_ready':ready,'windows_campaign_executor_ready':ready,
            'android_build_execution_chain_ready':ready,'android_debug_apk_built':bool(android_debug_apk_built),
            'android_debug_apk_reproducible':bool(android_debug_apk_reproducible),'android_lab_runtime_accepted':bool(android_lab_runtime_accepted),
            'physical_android_runtime_accepted':bool(physical_android_runtime_accepted),'windows_physical_verified':bool(windows_physical_verified),
            'human_release_authorized':bool(human_release_authorized),'production_ready':prod,'publication_allowed':False,'installation_allowed':False,
            'windows_update_freeze_respected':True,'next_action':'record_android_sdk_license_acceptance_then_execute_dual_build' if ready else 'continue_local_hardening'}
