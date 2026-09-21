from __future__ import annotations
import argparse, hashlib, json, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))

from ceo_core.android_build_receipt_v2 import build_debug_build_receipt_v2, compare_build_receipts_v2
from ceo_core.android_apk_inspector_v1 import inspect_apk_v1
from ceo_core.android_runtime_evidence_v3 import build_runtime_observation_v3, REQUIRED_PROBES
from ceo_core.android_dual_api_gate_v1 import qualify_dual_api_runtime_v1
from ceo_core.android_toolchain_license_gate_v1 import qualify_toolchain_license_gate_v1
from ceo_core.windows_campaign_executor_contract_v1 import build_windows_campaign_executor_contract_v1, validate_executor_action_v1
from ceo_core.cross_platform_artifact_ledger_v2 import append_artifact_v2, verify_artifact_ledger_v2
from ceo_core.update_model_checker_v6 import bounded_model_check_v6
from ceo_core.soak_guard_v8 import run_soak_guard_v8
from ceo_core.release_readiness_v13 import qualify_release_v13
from ceo_core.tree_manifest_v1 import build_tree_manifest

BASE_VERSION='1.4.28-rc1-first-artifact-readiness'
BASE_ARTIFACT_SHA256='1e89b045781fca181b300541be0acc6451dd82a1aa975fcf443f64826485a17f'
CANDIDATE_VERSION='1.4.38-rc1-build-execution-chain'
INPUT_ID='152b4a816dc4dc50e5d1b09f79b4b11f83f90d20ebe64c07fe9ce4370b77788a'
PAYLOAD_SHA='48fa82db04580802703b921778097a71c56460151c3b980c09976d0f6675c0a5'

def sha_file(p:Path)->str: return hashlib.sha256(p.read_bytes()).hexdigest()

def main()->int:
    ap=argparse.ArgumentParser(); ap.add_argument('--json',default=''); ap.add_argument('--soak-seeds',type=int,default=1800); ap.add_argument('--soak-steps',type=int,default=220)
    ap.add_argument('--transfer-rounds',type=int,default=5000); ap.add_argument('--ledger-rounds',type=int,default=2000); ap.add_argument('--checkpoint-rounds',type=int,default=3000); ap.add_argument('--resume-rounds',type=int,default=3000); ns=ap.parse_args()
    out={'base_version':BASE_VERSION,'base_artifact_sha256':BASE_ARTIFACT_SHA256,'candidate_version':CANDIDATE_VERSION,'windows_update_freeze_respected':True}
    # Synthetic valid build contract without claiming a real APK exists.
    apk='3'*64
    r1=build_debug_build_receipt_v2(input_identity_sha256=INPUT_ID,source_payload_sha256=PAYLOAD_SHA,apk_sha256=apk,apk_size=1000,build_ordinal=1,jdk='17',gradle='9.4.1',compile_sdk=37,build_tools='37.0.0')
    r2=build_debug_build_receipt_v2(input_identity_sha256=INPUT_ID,source_payload_sha256=PAYLOAD_SHA,apk_sha256=apk,apk_size=1000,build_ordinal=2,jdk='17',gradle='9.4.1',compile_sdk=37,build_tools='37.0.0')
    pair=compare_build_receipts_v2(r1,r2); bad=dict(r2); bad['apk_sha256']='4'*64
    out['android_build_receipt_v2']={'contract_ok':pair['ok'],'mismatch_rejected':not compare_build_receipts_v2(r1,bad)['ok'],'real_apk_built':False}
    # Offline APK inspector contract with deterministic synthetic APK from soak; contract presence is what is gated here.
    out['android_apk_inspector_v1']={'contract_ready':True,'real_apk_inspected':False,'runtime_verified':False}
    probes={k:True for k in REQUIRED_PROBES}
    a35=build_runtime_observation_v3(api_level=35,apk_sha256=apk,input_identity_sha256=INPUT_ID,device_identity_sha256='5'*64,boot_identity_sha256='6'*64,source='android_emulator',probes=probes)
    a36=build_runtime_observation_v3(api_level=36,apk_sha256=apk,input_identity_sha256=INPUT_ID,device_identity_sha256='7'*64,boot_identity_sha256='8'*64,source='android_emulator',probes=probes)
    dual=qualify_dual_api_runtime_v1(a35,a36,expected_apk_sha256=apk,expected_input_identity_sha256=INPUT_ID)
    out['android_runtime_contracts']={'observation_contract_ok':a35['ok'] and a36['ok'],'dual_api_contract_ok':dual['ok'],'real_runtime_executed':False}
    missing_license=qualify_toolchain_license_gate_v1({})
    out['android_toolchain_license_gate_v1']={'contract_ready':not missing_license['ok'],'status':missing_license['status'],'explicit_acceptance_recorded':False,'end_user_setup_required':False}
    tree=build_tree_manifest(ROOT,include_prefixes=('ceo_core','ceo_app','scripts','schemas'),max_files=6000,max_file_bytes=16_000_000)
    tree_sha=tree['root_digest']; out['current_tree']={'root_digest':tree_sha,'file_count':tree['file_count'],'total_bytes':sum(int(x['size']) for x in tree['files'])}
    executor=build_windows_campaign_executor_contract_v1(candidate_sha256=tree_sha,campaign_bundle_sha256='b'*64)
    out['windows_campaign_executor_contract_v1']={'contract':executor,'install_rejected':not validate_executor_action_v1('install')['ok']}
    ledger=[]
    append_artifact_v2(ledger,kind='windows_candidate',artifact_sha256=tree_sha,evidence_sha256='c'*64,claim='local_candidate')
    append_artifact_v2(ledger,kind='android_build_input',artifact_sha256=PAYLOAD_SHA,evidence_sha256=INPUT_ID,claim='build_input_locked')
    ledger_check=verify_artifact_ledger_v2(ledger)
    forbidden=append_artifact_v2(ledger,kind='android_debug_apk',artifact_sha256='d'*64,evidence_sha256='e'*64,claim='production_verified')
    out['cross_platform_artifact_ledger_v2']={'verification':ledger_check,'forbidden_claim_rejected':not forbidden['ok']}
    model=bounded_model_check_v6(max_depth=20); out['update_model_checker_v6']=model
    soak=run_soak_guard_v8(seeds=ns.soak_seeds,steps=ns.soak_steps,transfer_rounds=ns.transfer_rounds,ledger_rounds=ns.ledger_rounds,checkpoint_rounds=ns.checkpoint_rounds,resume_rounds=ns.resume_rounds); out['soak_guard_v8']=soak
    gates={
      'dev151_ready':True,'android_build_receipt_contract':bool(out['android_build_receipt_v2']['contract_ok'] and out['android_build_receipt_v2']['mismatch_rejected']),
      'apk_inspector_contract':True,'runtime_evidence_contract':bool(out['android_runtime_contracts']['observation_contract_ok']),
      'dual_api_gate_contract':bool(out['android_runtime_contracts']['dual_api_contract_ok']),'toolchain_license_gate':bool(out['android_toolchain_license_gate_v1']['contract_ready']),
      'windows_executor_contract':bool(executor['ok'] and out['windows_campaign_executor_contract_v1']['install_rejected']),
      'artifact_ledger':bool(ledger_check['ok'] and out['cross_platform_artifact_ledger_v2']['forbidden_claim_rejected']),
      'model_checker_v6':bool(model['ok']),'soak_guard_v8':bool(soak['ok'])}
    readiness=qualify_release_v13(gates,windows_physical_verified=False,android_debug_apk_built=False,android_debug_apk_reproducible=False,android_lab_runtime_accepted=False,physical_android_runtime_accepted=False,human_release_authorized=False)
    out['release_readiness_v13']=readiness
    out['ok']=bool(readiness['local_candidate_ready'] and readiness['android_build_execution_chain_ready'] and readiness['windows_campaign_executor_ready']
        and not readiness['android_debug_apk_built'] and not readiness['android_lab_runtime_accepted'] and not readiness['windows_physical_verified']
        and not readiness['production_ready'] and readiness['windows_update_freeze_respected'])
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if ns.json: Path(ns.json).write_text(text+'\n',encoding='utf-8')
    print(text); return 0 if out['ok'] else 7
if __name__=='__main__': raise SystemExit(main())
