from __future__ import annotations
import hashlib
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
from typing import Any

from .android_build_receipt_v2 import build_debug_build_receipt_v2, compare_build_receipts_v2
from .android_apk_inspector_v1 import inspect_apk_v1
from .android_runtime_evidence_v3 import build_runtime_observation_v3, REQUIRED_PROBES
from .android_dual_api_gate_v1 import qualify_dual_api_runtime_v1
from .android_toolchain_license_gate_v1 import qualify_toolchain_license_gate_v1
from .windows_campaign_executor_contract_v1 import build_windows_campaign_executor_contract_v1, validate_executor_action_v1
from .cross_platform_artifact_ledger_v2 import append_artifact_v2, verify_artifact_ledger_v2
from .update_model_checker_v6 import bounded_model_check_v6
from .soak_guard_v7 import run_soak_guard_v7


def run_soak_guard_v8(*, seeds: int = 1800, steps: int = 220, transfer_rounds: int = 5000,
                      ledger_rounds: int = 2000, checkpoint_rounds: int = 3000, resume_rounds: int = 3000) -> dict[str, Any]:
    base = run_soak_guard_v7(seeds=seeds, steps=steps, transfer_rounds=transfer_rounds,
                             ledger_rounds=ledger_rounds, checkpoint_rounds=checkpoint_rounds, resume_rounds=resume_rounds)
    model = bounded_model_check_v6(max_depth=20)
    input_id, payload, apk = '1'*64, '2'*64, '3'*64
    r1 = build_debug_build_receipt_v2(input_identity_sha256=input_id, source_payload_sha256=payload, apk_sha256=apk,
        apk_size=1234, build_ordinal=1, jdk='17', gradle='9.4.1', compile_sdk=37, build_tools='37.0.0')
    r2 = build_debug_build_receipt_v2(input_identity_sha256=input_id, source_payload_sha256=payload, apk_sha256=apk,
        apk_size=1234, build_ordinal=2, jdk='17', gradle='9.4.1', compile_sdk=37, build_tools='37.0.0')
    pair = compare_build_receipts_v2(r1,r2)
    bad = dict(r2); bad['apk_sha256']='4'*64
    mismatch_rejected = not compare_build_receipts_v2(r1,bad)['ok']
    license_missing_rejected = not qualify_toolchain_license_gate_v1({})['ok']
    probes = {k: True for k in REQUIRED_PROBES}
    a35 = build_runtime_observation_v3(api_level=35, apk_sha256=apk, input_identity_sha256=input_id,
        device_identity_sha256='5'*64, boot_identity_sha256='6'*64, source='android_emulator', probes=probes)
    a36 = build_runtime_observation_v3(api_level=36, apk_sha256=apk, input_identity_sha256=input_id,
        device_identity_sha256='7'*64, boot_identity_sha256='8'*64, source='android_emulator', probes=probes)
    dual = qualify_dual_api_runtime_v1(a35,a36,expected_apk_sha256=apk,expected_input_identity_sha256=input_id)
    bad36 = dict(a36); bad36['apk_sha256']='9'*64
    dual_mismatch_rejected = not qualify_dual_api_runtime_v1(a35,bad36,expected_apk_sha256=apk,expected_input_identity_sha256=input_id)['ok']
    executor = build_windows_campaign_executor_contract_v1(candidate_sha256='a'*64,campaign_bundle_sha256='b'*64)
    install_rejected = not validate_executor_action_v1('install')['ok']
    ledger: list[dict[str, Any]] = []
    for i in range(2000):
        append_artifact_v2(ledger, kind='campaign_checkpoint', artifact_sha256=hashlib.sha256(f'a{i}'.encode()).hexdigest(),
                           evidence_sha256=hashlib.sha256(f'e{i}'.encode()).hexdigest(), claim='checkpoint_recorded')
    ledger_ok = verify_artifact_ledger_v2(ledger)
    forbidden_claim_rejected = not append_artifact_v2(ledger, kind='android_debug_apk', artifact_sha256='c'*64,
                                                       evidence_sha256='d'*64, claim='production_verified')['ok']
    with TemporaryDirectory() as td:
        fake = Path(td)/'fake.apk'
        with ZipFile(fake,'w') as zf:
            zf.writestr('AndroidManifest.xml', b'x'); zf.writestr('classes.dex', b'dex')
        fake_sha = hashlib.sha256(fake.read_bytes()).hexdigest(); inspect = inspect_apk_v1(fake, expected_sha256=fake_sha)
    ok = bool(base['ok'] and model['ok'] and pair['ok'] and mismatch_rejected and license_missing_rejected and dual['ok']
              and dual_mismatch_rejected and executor['ok'] and install_rejected and ledger_ok['ok'] and forbidden_claim_rejected and inspect['ok'])
    return {'ok':ok,'base_soak_guard_v7':base,'model_checker_v6':model,'dual_build_receipt':pair,
            'dual_build_mismatch_rejected':mismatch_rejected,'license_missing_rejected':license_missing_rejected,
            'dual_api_gate':dual,'dual_api_mismatch_rejected':dual_mismatch_rejected,'windows_executor_contract':executor,
            'install_action_rejected':install_rejected,'artifact_ledger':ledger_ok,'forbidden_ledger_claim_rejected':forbidden_claim_rejected,
            'synthetic_apk_inspector':inspect,'automatic_installation':False,'automatic_publication':False}
