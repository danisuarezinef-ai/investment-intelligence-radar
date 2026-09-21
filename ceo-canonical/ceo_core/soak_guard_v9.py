from __future__ import annotations
import random
from .android_artifact_state_machine_v2 import AndroidArtifactStateV2, transition_v2
from .android_build_receipt_v3 import build_receipt_v3
from .android_reproducibility_gate_v2 import qualify_reproducibility_v2

def run_soak_guard_v9(rounds:int=5000,seed:int=162171)->dict:
    rng=random.Random(seed); failures=[]; accepted=0
    for i in range(rounds):
        apk=f'{rng.getrandbits(256):064x}'; inp=f'{rng.getrandbits(256):064x}'; dep=f'{rng.getrandbits(256):064x}'; runner=f'{rng.getrandbits(256):064x}'
        r1=build_receipt_v3(ordinal=1,apk_sha256=apk,apk_size=1000+i,input_identity_sha256=inp,payload_sha256='4'*64,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
        r2=build_receipt_v3(ordinal=2,apk_sha256=apk,apk_size=1000+i,input_identity_sha256=inp,payload_sha256='4'*64,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
        if not qualify_reproducibility_v2(r1,r2)['ok']: failures.append({'i':i,'kind':'valid_pair_rejected'}); break
        bad=dict(r2); bad['apk_sha256']='f'*64
        if qualify_reproducibility_v2(r1,bad)['ok']: failures.append({'i':i,'kind':'tamper_accepted'}); break
        s=AndroidArtifactStateV2();
        for e in ('record_consent','toolchain_ready','build1_ok','build2_ok','reproducible','inspected','api35_ok','api36_ok','runtime_accept'):
            s,ok,_=transition_v2(s,e,apk_sha256=apk,input_identity_sha256=inp)
            if not ok: failures.append({'i':i,'kind':'valid_state_path_failed','event':e}); break
        if failures: break
        accepted+=1
    return {'schema_version':9,'ok':not failures,'rounds':rounds,'accepted':accepted,'failures':failures}
