from __future__ import annotations
from dataclasses import dataclass, replace
from typing import Any

ORDER=('CONSENT_PENDING','CONSENT_RECORDED','TOOLCHAIN_READY','BUILD1_OK','BUILD2_OK','REPRODUCIBLE','INSPECTED','API35_OK','API36_OK','RUNTIME_ACCEPTED')
@dataclass(frozen=True)
class AndroidArtifactStateV2:
    state:str='CONSENT_PENDING'; apk_sha256:str=''; input_identity_sha256:str=''; blocked:bool=False

def transition_v2(s:AndroidArtifactStateV2,event:str,*,apk_sha256:str='',input_identity_sha256:str='')->tuple[AndroidArtifactStateV2,bool,str]:
    if s.blocked: return s,False,'blocked'
    mapping={'record_consent':'CONSENT_RECORDED','toolchain_ready':'TOOLCHAIN_READY','build1_ok':'BUILD1_OK','build2_ok':'BUILD2_OK',
             'reproducible':'REPRODUCIBLE','inspected':'INSPECTED','api35_ok':'API35_OK','api36_ok':'API36_OK','runtime_accept':'RUNTIME_ACCEPTED'}
    target=mapping.get(event)
    if not target: return replace(s,blocked=True),False,'unknown_event'
    if ORDER.index(target)!=ORDER.index(s.state)+1: return replace(s,blocked=True),False,'non_monotonic_transition'
    new_apk=s.apk_sha256 or apk_sha256; new_input=s.input_identity_sha256 or input_identity_sha256
    if s.apk_sha256 and apk_sha256 and apk_sha256!=s.apk_sha256: return replace(s,blocked=True),False,'apk_identity_changed'
    if s.input_identity_sha256 and input_identity_sha256 and input_identity_sha256!=s.input_identity_sha256: return replace(s,blocked=True),False,'input_identity_changed'
    return replace(s,state=target,apk_sha256=new_apk,input_identity_sha256=new_input),True,'ok'

def state_dict_v2(s:AndroidArtifactStateV2)->dict[str,Any]: return {'state':s.state,'apk_sha256':s.apk_sha256,'input_identity_sha256':s.input_identity_sha256,'blocked':s.blocked}
