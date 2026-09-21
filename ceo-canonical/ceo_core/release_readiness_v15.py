from __future__ import annotations
from typing import Any
GATES=('dev171_ready','runner_import_contract','apk_admission','byte_reproducibility','runtime_import','dual_api_gate','artifact_bundle','campaign_bridge','model_checker_v8','soak_guard_v10')

def qualify_release_v15(gates:dict[str,bool],*,real_apk_built:bool=False,real_apk_admitted:bool=False,
                        real_api35:bool=False,real_api36:bool=False,windows_physical_verified:bool=False,
                        human_release_authorized:bool=False)->dict[str,Any]:
    local={k:bool(gates.get(k,False)) for k in GATES}; local_ready=all(local.values()); android_runtime=bool(real_api35 and real_api36)
    production=bool(local_ready and real_apk_built and real_apk_admitted and android_runtime and windows_physical_verified and human_release_authorized)
    if not real_apk_built: next_action='execute_remote_build_capsule_and_import_real_apk_bytes'
    elif not real_apk_admitted: next_action='admit_real_apk_bytes'
    elif not android_runtime: next_action='execute_same_apk_on_api35_and_api36'
    elif not windows_physical_verified: next_action='run_one_shot_windows_physical_campaign'
    else: next_action='human_release_review'
    return {'schema_version':15,'local_gates':local,'local_candidate_ready':local_ready,'real_android_apk_built':bool(real_apk_built),
            'real_android_apk_admitted':bool(real_apk_admitted),'real_api35_ok':bool(real_api35),'real_api36_ok':bool(real_api36),
            'android_lab_runtime_accepted':android_runtime,'windows_physical_verified':bool(windows_physical_verified),
            'human_release_authorized':bool(human_release_authorized),'production_ready':production,'publication_allowed':False,
            'installation_allowed':False,'spending_allowed':False,'windows_update_freeze_respected':True,'next_action':next_action}
