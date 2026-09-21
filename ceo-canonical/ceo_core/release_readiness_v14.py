from __future__ import annotations
from typing import Any
GATES=('dev161_ready','operator_consent','acquisition_plan','environment_handoff','ci_capsule','receipt_v3','repro_gate_v2','runtime_campaign','model_checker_v7','soak_guard_v9')

def qualify_release_v14(gates:dict[str,bool],*,apk_built:bool=False,apk_reproducible:bool=False,api35_ok:bool=False,api36_ok:bool=False,
                        windows_physical_verified:bool=False,human_release_authorized:bool=False)->dict[str,Any]:
    local={k:bool(gates.get(k,False)) for k in GATES}; ready=all(local.values()); runtime=bool(api35_ok and api36_ok)
    prod=bool(ready and apk_built and apk_reproducible and runtime and windows_physical_verified and human_release_authorized)
    return {'schema_version':14,'local_gates':local,'local_candidate_ready':ready,'operator_consent_recorded':local['operator_consent'],
            'remote_build_capsule_ready':ready,'android_debug_apk_built':bool(apk_built),'android_debug_apk_reproducible':bool(apk_reproducible),
            'api35_ok':bool(api35_ok),'api36_ok':bool(api36_ok),'android_lab_runtime_accepted':runtime,
            'windows_physical_verified':bool(windows_physical_verified),'human_release_authorized':bool(human_release_authorized),
            'production_ready':prod,'publication_allowed':False,'installation_allowed':False,'spending_allowed':False,
            'windows_update_freeze_respected':True,'next_action':'execute_ci_build_capsule_on_internet_runner' if ready and not apk_built else 'continue_evidence_chain'}
