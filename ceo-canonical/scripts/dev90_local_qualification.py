from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from ceo_core.mobile_sync_v2 import MobileSyncV2
from ceo_core.operator_update_summary import build_operator_update_summary
from ceo_core.physical_campaign_plan import authorize_campaign, build_one_shot_windows_campaign
from ceo_core.release_readiness_v6 import qualify_release_v6
from ceo_core.self_dev_inbox import SelfDevelopmentInbox
from ceo_core.update_failure_lab_v2 import UpdateFailureLabV2
from ceo_core.in_app_updater import InAppUpdater


def receipt(i: int):
    return {
        "candidate_id":f"c{i}", "base_version":"x", "candidate_version":f"y{i}", "changed_files":[f"f{i}.py"],
        "tests":{"passed":10,"failed":0}, "published":False, "installed":False, "auto_promoted":False,
        "safety":{"stable_unchanged":True,"automatic_spending_false":True,"automatic_publication_false":True,"automatic_installation_false":True},
    }


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument('--json',default=''); ns=ap.parse_args()
    out={}
    out['fault_lab_v2']=UpdateFailureLabV2.campaign(seeds=1000,steps=100)
    out['physical_plan']=build_one_shot_windows_campaign()
    out['physical_refusal']=authorize_campaign(physical_windows=False,human_confirmed=True)
    with tempfile.TemporaryDirectory(prefix='ceo-dev90-') as td:
        inbox=SelfDevelopmentInbox(td); a=inbox.ingest(receipt(1)); b=inbox.ingest(receipt(2)); dup=inbox.ingest(receipt(2)); comp=inbox.compare_latest()
        out['self_dev_inbox']={'a':a,'b':b,'duplicate':dup,'comparison':comp,'snapshot':inbox.snapshot()}
        sync=MobileSyncV2(b'0123456789abcdef0123456789abcdef')
        env=sync.issue('development_receipt',{'id':'x'}); verified=sync.verify(env,now=env['issued_at']+1)
        replay=False
        try: sync.verify(env,now=env['issued_at']+2)
        except PermissionError: replay=True
        tampered=dict(env); tampered['payload']={'id':'tampered'}
        tamper=False
        sync2=MobileSyncV2(b'0123456789abcdef0123456789abcdef')
        try: sync2.verify(tampered,now=env['issued_at']+1)
        except PermissionError: tamper=True
        out['mobile_sync']={'verified_kind':verified['kind'],'replay_rejected':replay,'tamper_rejected':tamper}
        u=InAppUpdater(Path(td)/'data',trusted_keys={}); u._record_progress('preflight_failed',version='z',percent=100,reason='synthetic')
        out['operator_summary']=build_operator_update_summary(u,current_version='x',include_remote=False)
    gates={
        'dev85_ready':True,
        'failure_lab_v2':out['fault_lab_v2']['ok'],
        'physical_campaign_plan':len(out['physical_plan']['gates'])>=10 and not out['physical_refusal']['allowed'],
        'self_dev_inbox':bool(out['self_dev_inbox']['comparison'].get('comparable')) and bool(out['self_dev_inbox']['duplicate'].get('duplicate')),
        'mobile_sync_v2':out['mobile_sync']['replay_rejected'] and out['mobile_sync']['tamper_rejected'],
        'operator_update_summary':out['operator_summary']['state']['state']=='blocked',
    }
    out['readiness']=qualify_release_v6(gates,windows_physical_verified=False)
    out['ok']=out['readiness']['local_candidate_ready'] and not out['readiness']['production_ready']
    text=json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)
    if ns.json: Path(ns.json).write_text(text+'\n',encoding='utf-8')
    print(text)
    return 0 if out['ok'] else 7

if __name__=='__main__': raise SystemExit(main())
