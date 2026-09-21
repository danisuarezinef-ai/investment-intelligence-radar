from __future__ import annotations
from typing import Any

def qualify_environment_v1(*,operator_consent_ok:bool,jdk_major:int|None,gradle_version:str|None,
                           android_sdk_37:bool,network_dns:bool,external_runner_available:bool=False)->dict[str,Any]:
    exact_local=bool(operator_consent_ok and jdk_major==17 and gradle_version=='9.4.1' and android_sdk_37 and network_dns)
    status='LOCAL_BUILD_READY' if exact_local else ('REMOTE_RUNNER_HANDOFF_READY' if operator_consent_ok else 'BLOCKED')
    blockers=[]
    if jdk_major!=17: blockers.append('jdk17_missing')
    if gradle_version!='9.4.1': blockers.append('gradle_9_4_1_missing')
    if not android_sdk_37: blockers.append('android_sdk_37_missing')
    if not network_dns: blockers.append('network_dns_unavailable')
    if not operator_consent_ok: blockers.append('operator_consent_missing')
    return {'ok':bool(exact_local or (operator_consent_ok and external_runner_available)),'status':status,'local_ready':exact_local,
            'handoff_ready':bool(operator_consent_ok),'blockers':blockers,'version_relaxation_allowed':False,
            'apk_built':False,'production_verified':False}
