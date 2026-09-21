from __future__ import annotations
import argparse, hashlib, json, os, shutil, socket, subprocess, sys, tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from ceo_core.android_build_receipt_v3 import build_receipt_v3
from ceo_core.android_runner_result_import_v1 import import_runner_result_v1
from ceo_core.android_apk_admission_gate_v1 import qualify_apk_admission_v1
from ceo_core.android_reproducibility_evidence_v3 import verify_reproducibility_evidence_v3
from ceo_core.android_runtime_evidence_v3 import build_runtime_observation_v3
from ceo_core.android_runtime_result_import_v1 import validate_runtime_observation_import_v1
from ceo_core.android_dual_api_gate_v2 import qualify_dual_api_runtime_v2
from ceo_core.android_artifact_evidence_bundle_v1 import build_artifact_evidence_bundle_v1
from ceo_core.cross_platform_campaign_bridge_v1 import qualify_cross_platform_campaign_bridge_v1
from ceo_core.physical_campaign_plan_v6 import build_one_shot_windows_campaign_v6, LOCAL_PRECONDITIONS
from ceo_core.update_model_checker_v8 import bounded_model_check_v8
from ceo_core.soak_guard_v10 import run_soak_guard_v10
from ceo_core.release_readiness_v15 import qualify_release_v15
from ceo_core.tree_manifest_v1 import build_tree_manifest

BASE_VERSION='1.4.48-rc1-portable-build-execution'
BASE_ARTIFACT_SHA256='8c9318bf99b85e75b7979014e6e6e867eaf98d27ac0d54af544d4bd96124beec'
CANDIDATE_VERSION='1.4.58-rc1-artifact-admission-chain'
INPUT_ID='152b4a816dc4dc50e5d1b09f79b4b11f83f90d20ebe64c07fe9ce4370b77788a'
PAYLOAD_SHA='48fa82db04580802703b921778097a71c56460151c3b980c09976d0f6675c0a5'

def _write_synthetic_apk(path:Path)->None:
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        z.writestr('AndroidManifest.xml',b'\x03\x00DEV181-SYNTHETIC-NOT-REAL-APK')
        z.writestr('classes.dex',b'dex\n035\x00DEV181-SYNTHETIC-DEX')

def _sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def _environment()->dict:
    try:
        first=subprocess.check_output(['java','-version'],stderr=subprocess.STDOUT,text=True,timeout=10).splitlines()[0]
        jdk=int(first.split('"')[1].split('.')[0])
    except Exception:jdk=None
    gradle=None
    if shutil.which('gradle'):
        try:
            for line in subprocess.check_output(['gradle','--version'],stderr=subprocess.STDOUT,text=True,timeout=10).splitlines():
                if line.startswith('Gradle '):gradle=line.split()[1];break
        except Exception:pass
    try: socket.getaddrinfo('services.gradle.org',443); dns=True
    except Exception:dns=False
    sdkroot=os.getenv('ANDROID_SDK_ROOT',''); sdk=bool(sdkroot and (Path(sdkroot)/'platforms/android-37/android.jar').is_file())
    return {'jdk_major':jdk,'gradle':gradle,'network_dns':dns,'android_sdk_37':sdk,
            'real_build_executable_here':bool(jdk==17 and gradle=='9.4.1' and dns and sdk)}

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--json',default=''); ap.add_argument('--soak-rounds',type=int,default=5000); ap.add_argument('--dev171-regression',default='')
    ns=ap.parse_args(); out={'base_version':BASE_VERSION,'base_artifact_sha256':BASE_ARTIFACT_SHA256,'candidate_version':CANDIDATE_VERSION,
                             'windows_update_freeze_respected':True,'real_android_apk_built':False,'real_android_runtime_executed':False,
                             'environment':_environment()}
    regression_ok=False
    if ns.dev171_regression:
        try:
            rr=json.loads(Path(ns.dev171_regression).read_text()); regression_ok=bool(rr.get('ok'))
            out['dev171_regression_evidence']={'ok':regression_ok,'path':str(ns.dev171_regression)}
        except Exception as exc: out['dev171_regression_evidence']={'ok':False,'error':str(exc)}
    else: out['dev171_regression_evidence']={'ok':False,'missing':True}

    with tempfile.TemporaryDirectory(prefix='dev181-contract-') as td:
        d=Path(td); a=d/'CEO-Android-debug-build1.apk'; b=d/'CEO-Android-debug-build2.apk'; _write_synthetic_apk(a); b.write_bytes(a.read_bytes())
        apk=_sha(a); size=a.stat().st_size; dep='b'*64; runner='c'*64
        r1=build_receipt_v3(ordinal=1,apk_sha256=apk,apk_size=size,input_identity_sha256=INPUT_ID,payload_sha256=PAYLOAD_SHA,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
        r2=build_receipt_v3(ordinal=2,apk_sha256=apk,apk_size=size,input_identity_sha256=INPUT_ID,payload_sha256=PAYLOAD_SHA,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
        (d/'BUILD_RECEIPT_1.json').write_text(json.dumps(r1)); (d/'BUILD_RECEIPT_2.json').write_text(json.dumps(r2))
        (d/'REPRODUCIBILITY_RECEIPT.json').write_text(json.dumps({'ok':True,'reproducible':True,'apk_sha256':apk}))
        (d/'DEV162_171_RUNNER_RESULT.json').write_text(json.dumps({'apk_sha256':apk,'apk_size':size,'same_apk_twice':True,'production_verified':False,'publication_authorized':False,'installation_authorized':False}))
        imported=import_runner_result_v1(d,expected_input_identity_sha256=INPUT_ID,expected_payload_sha256=PAYLOAD_SHA)
        out['dev172_android_runner_result_import_v1']={'contract_ok':imported['ok'],'synthetic_only':True,'real_runner_result_imported':False}
        admission=qualify_apk_admission_v1(d,expected_input_identity_sha256=INPUT_ID,expected_payload_sha256=PAYLOAD_SHA)
        out['dev173_android_apk_admission_gate_v1']={'contract_ok':admission['ok'],'synthetic_only':True,'real_apk_admitted':False}
        bytev=verify_reproducibility_evidence_v3(a,b,expected_sha256=apk)
        b.write_bytes(b.read_bytes()+b'X'); tamper_rejected=not verify_reproducibility_evidence_v3(a,b,expected_sha256=apk)['ok']; b.write_bytes(a.read_bytes())
        out['dev174_android_reproducibility_evidence_v3']={'contract_ok':bytev['ok'],'one_byte_tamper_rejected':tamper_rejected,'synthetic_only':True}

        obs35=build_runtime_observation_v3(api_level=35,apk_sha256=apk,input_identity_sha256=INPUT_ID,device_identity_sha256='3'*64,boot_identity_sha256='5'*64,source='android_emulator',probes={k:True for k in ('launch','core_health','process_death','explicit_reboot','force_stop_relaunch','storage_pressure_cleanup')})
        obs36=build_runtime_observation_v3(api_level=36,apk_sha256=apk,input_identity_sha256=INPUT_ID,device_identity_sha256='4'*64,boot_identity_sha256='6'*64,source='android_emulator',probes={k:True for k in ('launch','core_health','process_death','explicit_reboot','force_stop_relaunch','storage_pressure_cleanup')})
        i35=validate_runtime_observation_import_v1(obs35,expected_api_level=35,expected_apk_sha256=apk,expected_input_identity_sha256=INPUT_ID)
        i36=validate_runtime_observation_import_v1(obs36,expected_api_level=36,expected_apk_sha256=apk,expected_input_identity_sha256=INPUT_ID)
        out['dev175_android_runtime_result_import_v1']={'api35_contract_ok':i35['ok'],'api36_contract_ok':i36['ok'],'synthetic_only':True,'real_runtime_imported':False}
        dual=qualify_dual_api_runtime_v2(i35,i36,expected_apk_sha256=apk,expected_input_identity_sha256=INPUT_ID)
        sameboot=dict(i36); sameboot['boot_identity_sha256']=i35['boot_identity_sha256']; same_boot_rejected=not qualify_dual_api_runtime_v2(i35,sameboot,expected_apk_sha256=apk,expected_input_identity_sha256=INPUT_ID)['ok']
        out['dev176_android_dual_api_gate_v2']={'contract_ok':dual['ok'],'same_boot_rejected':same_boot_rejected,'synthetic_only':True,'real_dual_api_accepted':False}
        bundle=build_artifact_evidence_bundle_v1(admission=admission,dual_api=dual)
        out['dev177_android_artifact_evidence_bundle_v1']={'contract_ok':bundle['ok'],'bundle_sha256':bundle['bundle_sha256'],'synthetic_only':True,'real_bundle_complete':False}
        campaign=build_one_shot_windows_campaign_v6({k:True for k in LOCAL_PRECONDITIONS},candidate_sha256='7'*64,campaign_bundle_sha256='8'*64)
        bridge=qualify_cross_platform_campaign_bridge_v1(bundle,campaign)
        badcampaign=dict(campaign); badcampaign['physical_gates']=[dict(g,status='PASS') if i==0 else g for i,g in enumerate(campaign['physical_gates'])]
        preverified_rejected=not qualify_cross_platform_campaign_bridge_v1(bundle,badcampaign)['ok']
        out['dev178_cross_platform_campaign_bridge_v1']={'contract_ok':bridge['ok'],'preverified_windows_gate_rejected':preverified_rejected,'windows_physical_verified':False}

    model=bounded_model_check_v8(); out['dev179_update_model_checker_v8']=model
    soak=run_soak_guard_v10(rounds=ns.soak_rounds); out['dev180_soak_guard_v10']=soak
    tree=build_tree_manifest(ROOT,include_prefixes=('ceo_core','ceo_app','scripts','schemas'),max_files=8000,max_file_bytes=16_000_000); out['current_tree']={'root_digest':tree['root_digest'],'file_count':tree['file_count']}
    gates={'dev171_ready':regression_ok,'runner_import_contract':out['dev172_android_runner_result_import_v1']['contract_ok'],
           'apk_admission':out['dev173_android_apk_admission_gate_v1']['contract_ok'],'byte_reproducibility':bytev['ok'] and tamper_rejected,
           'runtime_import':i35['ok'] and i36['ok'],'dual_api_gate':dual['ok'] and same_boot_rejected,'artifact_bundle':bundle['ok'],
           'campaign_bridge':bridge['ok'] and preverified_rejected,'model_checker_v8':model['ok'],'soak_guard_v10':soak['ok']}
    ready=qualify_release_v15(gates,real_apk_built=False,real_apk_admitted=False,real_api35=False,real_api36=False,windows_physical_verified=False,human_release_authorized=False)
    out['dev181_release_readiness_v15']=ready
    out['ok']=bool(ready['local_candidate_ready'] and not ready['real_android_apk_built'] and not ready['production_ready'] and ready['windows_update_freeze_respected'])
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if ns.json:Path(ns.json).write_text(text+'\n',encoding='utf-8')
    print(text);return 0 if out['ok'] else 7
if __name__=='__main__':raise SystemExit(main())
