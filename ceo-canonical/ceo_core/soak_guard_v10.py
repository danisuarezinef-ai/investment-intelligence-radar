from __future__ import annotations
import hashlib, json, random, tempfile
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from .android_build_receipt_v3 import build_receipt_v3
from .android_runner_result_import_v1 import import_runner_result_v1
from .android_apk_admission_gate_v1 import qualify_apk_admission_v1


def _write_fake_apk(path:Path,seed:int)->None:
    with ZipFile(path,'w',ZIP_DEFLATED) as z:
        z.writestr('AndroidManifest.xml',b'\x03\x00synthetic-manifest-'+str(seed).encode())
        z.writestr('classes.dex',b'dex\n035\x00'+hashlib.sha256(str(seed).encode()).digest())

def _sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()

def run_soak_guard_v10(rounds:int=5000,seed:int=172181)->dict:
    rng=random.Random(seed); accepted=0; failures=[]
    with tempfile.TemporaryDirectory(prefix='ceo-dev180-') as td:
        root=Path(td)
        for i in range(rounds):
            d=root/str(i); d.mkdir(); a=d/'CEO-Android-debug-build1.apk'; b=d/'CEO-Android-debug-build2.apk'; _write_fake_apk(a,i); b.write_bytes(a.read_bytes())
            sha=_sha(a); size=a.stat().st_size; inp=f'{rng.getrandbits(256):064x}'; payload=f'{rng.getrandbits(256):064x}'; dep=f'{rng.getrandbits(256):064x}'; runner=f'{rng.getrandbits(256):064x}'
            r1=build_receipt_v3(ordinal=1,apk_sha256=sha,apk_size=size,input_identity_sha256=inp,payload_sha256=payload,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
            r2=build_receipt_v3(ordinal=2,apk_sha256=sha,apk_size=size,input_identity_sha256=inp,payload_sha256=payload,dependency_graph_sha256=dep,runner_fingerprint_sha256=runner)
            (d/'BUILD_RECEIPT_1.json').write_text(json.dumps(r1)); (d/'BUILD_RECEIPT_2.json').write_text(json.dumps(r2))
            (d/'REPRODUCIBILITY_RECEIPT.json').write_text(json.dumps({'ok':True,'reproducible':True,'apk_sha256':sha}))
            (d/'DEV162_171_RUNNER_RESULT.json').write_text(json.dumps({'apk_sha256':sha,'apk_size':size,'same_apk_twice':True,'production_verified':False,'publication_authorized':False,'installation_authorized':False}))
            imp=import_runner_result_v1(d,expected_input_identity_sha256=inp,expected_payload_sha256=payload)
            adm=qualify_apk_admission_v1(d,expected_input_identity_sha256=inp,expected_payload_sha256=payload)
            if not imp['ok'] or not adm['ok']:
                failures.append({'i':i,'kind':'valid_bundle_rejected','import':imp.get('problems'),'admission':adm.get('problems')});break
            # adversarial byte tamper must fail closed
            b.write_bytes(b.read_bytes()+b'x')
            if import_runner_result_v1(d,expected_input_identity_sha256=inp,expected_payload_sha256=payload)['ok']:
                failures.append({'i':i,'kind':'tampered_second_apk_accepted'});break
            accepted+=1
            # keep disk bounded
            for p in d.iterdir(): p.unlink()
            d.rmdir()
    return {'schema_version':10,'ok':not failures,'rounds':rounds,'accepted':accepted,'failures':failures}
