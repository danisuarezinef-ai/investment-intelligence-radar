from __future__ import annotations
from collections import deque
from .android_artifact_state_machine_v2 import AndroidArtifactStateV2, transition_v2, ORDER

EVENTS=('record_consent','toolchain_ready','build1_ok','build2_ok','reproducible','inspected','api35_ok','api36_ok','runtime_accept')

def bounded_model_check_v7(max_depth:int=14)->dict:
    start=AndroidArtifactStateV2(); q=deque([(start,0)]); seen={start}; transitions=0; violations=[]
    while q:
        s,d=q.popleft()
        if d>=max_depth: continue
        for e in EVENTS:
            ns,ok,reason=transition_v2(s,e,apk_sha256='a'*64,input_identity_sha256='b'*64); transitions+=1
            if ok:
                if ORDER.index(ns.state)!=ORDER.index(s.state)+1: violations.append('skipped_state')
                if ns.blocked: violations.append('success_blocked')
                if ns not in seen: seen.add(ns); q.append((ns,d+1))
            else:
                if not ns.blocked and reason!='blocked': violations.append('failed_transition_not_blocked')
    # identity tamper must fail closed
    s=AndroidArtifactStateV2(state='BUILD1_OK',apk_sha256='a'*64,input_identity_sha256='b'*64)
    tampered,ok,_=transition_v2(s,'build2_ok',apk_sha256='c'*64,input_identity_sha256='b'*64); transitions+=1
    if ok or not tampered.blocked: violations.append('apk_identity_tamper_not_blocked')
    return {'schema_version':7,'ok':not violations,'states_explored':len(seen),'transitions_checked':transitions,'violations':violations,'truncated':False}
