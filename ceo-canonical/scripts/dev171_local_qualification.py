from __future__ import annotations
import argparse, hashlib, json, os, shutil, socket, subprocess, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from ceo_core.operator_license_consent_v1 import validate_operator_consent_v1
from ceo_core.toolchain_acquisition_plan_v2 import build_acquisition_plan_v2
from ceo_core.build_environment_capability_gate_v1 import qualify_environment_v1
from ceo_core.android_ci_build_capsule_v1 import build_ci_capsule_manifest_v1, validate_ci_capsule_manifest_v1
from ceo_core.android_build_receipt_v3 import build_receipt_v3, validate_receipt_v3
from ceo_core.android_reproducibility_gate_v2 import qualify_reproducibility_v2
from ceo_core.android_runtime_campaign_v1 import build_runtime_campaign_v1, qualify_runtime_campaign_v1
from ceo_core.android_artifact_state_machine_v2 import AndroidArtifactStateV2, transition_v2
from ceo_core.update_model_checker_v7 import bounded_model_check_v7
from ceo_core.soak_guard_v9 import run_soak_guard_v9
from ceo_core.release_readiness_v14 import qualify_release_v14
from ceo_core.tree_manifest_v1 import build_tree_manifest

BASE_VERSION='1.4.38-rc1-build-execution-chain'
BASE_ARTIFACT_SHA256='e857ceb7ae363df494118591f1af438a892f059bce7f851751e84afa61c04861'
CANDIDATE_VERSION='1.4.48-rc1-portable-build-execution'
INPUT_ID='152b4a816dc4dc50e5d1b09f79b4b11f83f90d20ebe64c07fe9ce4370b77788a'
PAYLOAD_SHA='48fa82db04580802703b921778097a71c56460151c3b980c09976d0f6675c0a5'
KIT_SHA='36b021d1246439fb034e8286e9fab1e92166c349276cb8e972e1ce29fa9a0c57'

def _jdk_major():
    try:
        s=subprocess.check_output(['java','-version'],stderr=subprocess.STDOUT,text=True,timeout=10).splitlines()[0]
        q=s.split('"')[1]; return int(q.split('.')[0])
    except Exception:return None

def _gradle_version():
    exe=shutil.which('gradle')
    if not exe:return None
    try:
        for line in subprocess.check_output([exe,'--version'],text=True,stderr=subprocess.STDOUT,timeout=15).splitlines():
            if line.startswith('Gradle '):return line.split()[1]
    except Exception:return None
    return None

def _network_dns():
    try: socket.getaddrinfo('services.gradle.org',443); return True
    except Exception:return False

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--json',default=''); ap.add_argument('--soak-rounds',type=int,default=5000); ap.add_argument('--dev161-regression',default='')
    ns=ap.parse_args(); out={'base_version':BASE_VERSION,'base_artifact_sha256':BASE_ARTIFACT_SHA256,'candidate_version':CANDIDATE_VERSION,'windows_update_freeze_respected':True}
    consent=json.loads((ROOT/'schemas/ANDROID_OPERATOR_CONSENT_DEV162.json').read_text()); consent_check=validate_operator_consent_v1(consent); out['dev162_operator_license_consent_v1']={'receipt':consent,'validation':consent_check}
    jdk=_jdk_major(); gradle=_gradle_version(); sdk=bool(os.getenv('ANDROID_SDK_ROOT') and (Path(os.getenv('ANDROID_SDK_ROOT',''))/'platforms/android-37/android.jar').is_file()); dns=_network_dns()
    plan=build_acquisition_plan_v2(operator_consent_ok=consent_check['ok'],network_available=dns,jdk17_available=(jdk==17)); out['dev163_toolchain_acquisition_plan_v2']=plan
    env=qualify_environment_v1(operator_consent_ok=consent_check['ok'],jdk_major=jdk,gradle_version=gradle,android_sdk_37=sdk,network_dns=dns,external_runner_available=True); out['dev164_build_environment_capability_gate_v1']=env
    cap=build_ci_capsule_manifest_v1(input_identity_sha256=INPUT_ID,payload_sha256=PAYLOAD_SHA,consent_sha256=consent['consent_sha256'],kit_sha256=KIT_SHA); capv=validate_ci_capsule_manifest_v1(cap); out['dev165_android_ci_build_capsule_v1']={'manifest':cap,'validation':capv}
    apk='a'*64; dep='b'*64; runner='c'*64
    r1=build_receipt_v3(ordinal=1,apk_sha256=apk,apk_size=123456,input_identity_sha256=INPUT_ID,payload_sha256=PAYLOAD_SHA,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
    r2=build_receipt_v3(ordinal=2,apk_sha256=apk,apk_size=123456,input_identity_sha256=INPUT_ID,payload_sha256=PAYLOAD_SHA,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
    rv1,rv2=validate_receipt_v3(r1),validate_receipt_v3(r2); out['dev166_android_build_receipt_v3']={'receipt1_ok':rv1['ok'],'receipt2_ok':rv2['ok'],'real_apk_built':False}
    repro=qualify_reproducibility_v2(r1,r2); bad=dict(r2); bad['apk_sha256']='d'*64; bad_rejected=not qualify_reproducibility_v2(r1,bad)['ok']; out['dev167_android_reproducibility_gate_v2']={'contract':repro,'mismatch_rejected':bad_rejected,'real_apk_reproducible':False}
    campaign=build_runtime_campaign_v1(apk_sha256=apk,input_identity_sha256=INPUT_ID); synthetic=[{'api_level':35,'ok':True,'apk_sha256':apk,'input_identity_sha256':INPUT_ID},{'api_level':36,'ok':True,'apk_sha256':apk,'input_identity_sha256':INPUT_ID}]
    rc=qualify_runtime_campaign_v1(campaign,synthetic); out['dev168_android_runtime_campaign_v1']={'campaign':campaign,'contract_ok':rc['ok'],'real_runtime_executed':False}
    s=AndroidArtifactStateV2(); path=[]
    for e in ('record_consent','toolchain_ready','build1_ok','build2_ok','reproducible','inspected','api35_ok','api36_ok','runtime_accept'):
        s,ok,reason=transition_v2(s,e,apk_sha256=apk,input_identity_sha256=INPUT_ID); path.append({'event':e,'ok':ok,'reason':reason,'state':s.state})
    bads=AndroidArtifactStateV2(state='BUILD1_OK',apk_sha256=apk,input_identity_sha256=INPUT_ID); bads,ok,_=transition_v2(bads,'build2_ok',apk_sha256='e'*64,input_identity_sha256=INPUT_ID)
    out['dev169_android_artifact_state_machine_v2']={'valid_path_ok':all(x['ok'] for x in path),'terminal_state':s.state,'identity_drift_rejected':(not ok and bads.blocked)}
    model=bounded_model_check_v7(); out['dev170_update_model_checker_v7']=model
    soak=run_soak_guard_v9(rounds=ns.soak_rounds); out['dev171_soak_guard_v9']=soak
    regression_ok=False
    if ns.dev161_regression:
        try:
            rr=json.loads(Path(ns.dev161_regression).read_text()); regression_ok=bool(rr.get('ok'))
            out['dev161_regression_evidence']={'ok':regression_ok,'path':str(ns.dev161_regression)}
        except Exception as exc: out['dev161_regression_evidence']={'ok':False,'error':str(exc)}
    else: out['dev161_regression_evidence']={'ok':False,'missing':True}
    tree=build_tree_manifest(ROOT,include_prefixes=('ceo_core','ceo_app','scripts','schemas'),max_files=7000,max_file_bytes=16_000_000); out['current_tree']={'root_digest':tree['root_digest'],'file_count':tree['file_count']}
    gates={'dev161_ready':regression_ok,'operator_consent':consent_check['ok'],'acquisition_plan':plan['remote_runner_eligible'],'environment_handoff':env['handoff_ready'],'ci_capsule':capv['ok'],'receipt_v3':rv1['ok'] and rv2['ok'],'repro_gate_v2':repro['ok'] and bad_rejected,'runtime_campaign':rc['ok'],'model_checker_v7':model['ok'],'soak_guard_v9':soak['ok']}
    ready=qualify_release_v14(gates,apk_built=False,apk_reproducible=False,api35_ok=False,api36_ok=False,windows_physical_verified=False,human_release_authorized=False); out['release_readiness_v14']=ready
    out['ok']=bool(ready['local_candidate_ready'] and ready['operator_consent_recorded'] and ready['remote_build_capsule_ready'] and not ready['android_debug_apk_built'] and not ready['production_ready'] and ready['windows_update_freeze_respected'])
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if ns.json: Path(ns.json).write_text(text+'\n',encoding='utf-8')
    print(text); return 0 if out['ok'] else 7
if __name__=='__main__': raise SystemExit(main())
