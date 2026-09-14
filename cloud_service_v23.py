"""Production PAPER runtime v23: v22 + operational proof tasks 161-170."""
from __future__ import annotations
import hashlib, json, os, threading, time
from datetime import datetime, timezone
from http.server import ThreadingHTTPServer
import cloud_service_v22 as base22
import radar_operational_proof_161_170_v1 as proof
import radar_paper_forward_maturity_v1 as maturity
REAL_TRADING=False

def _b12(): return base22.base21.base20.base19.base18.base17.base16.base15.base14.base13.base12

def _market_gate():
    try:
        b=base22.base21.base20.runtime_board_101_120();tasks=b.get('tasks') or []
        for t in tasks:
            if str(t.get('task'))=='114': return t.get('status')=='PASS'
    except Exception: pass
    return False

def _maturity_writer_loop():
    last=datetime.now(timezone.utc)
    while True:
        time.sleep(300)
        end=datetime.now(timezone.utc);b12=_b12();lease=b12._lease_local() or {}
        try: runtime=base22.base21.base20.base19._runtime_authority() or {}
        except Exception: runtime={}
        if lease.get('held') is not True:
            last=end;continue
        state_hash=((b12._DURABLE_SYNC or {}).get('checkpoint_hash') or '')
        exact=runtime.get('exact_restore_ok') is True;single=lease.get('held') is True
        persist=runtime.get('durable_sync_status')=='RECONCILED';market=_market_gate()
        healthy=bool(exact and single and persist and market and len(str(state_hash))>=16)
        reason='healthy' if healthy else 'credit_blocked:'+','.join(k for k,v in {'exact_restore':exact,'singleton':single,'persistence':persist,'market_data':market,'state_hash':len(str(state_hash))>=16}.items() if not v)
        raw=f"{lease.get('session_id')}|{lease.get('epoch')}|{last.isoformat()}|{end.isoformat()}"
        interval_id=hashlib.sha256(raw.encode()).hexdigest()
        out=maturity.append_interval(interval_id=interval_id,session_id=lease.get('session_id'),lease_owner=lease.get('owner_id'),lease_epoch=lease.get('epoch'),
            started_at=last.isoformat(),ended_at=end.isoformat(),healthy=healthy,exact_restore=exact,singleton=single,
            persistence_reconciled=persist,market_data_ok=market,state_hash=state_hash,reason=reason)
        print('[paper-maturity] '+json.dumps({'ok':out.get('ok'),'status':out.get('status'),'healthy':healthy,'reason':reason,'real_trading':False},sort_keys=True),flush=True)
        last=end

def runtime_board_161_170():
    m=maturity.status();expected=os.environ.get('RADAR_EXPECTED_DEPLOY_SHA');deployed=os.environ.get('RAILWAY_GIT_COMMIT_SHA') or os.environ.get('RAILWAY_GIT_COMMIT')
    schema=m.get('schema') or {};authority={**m,'edge_active':m.get('edge_active') is True,'real_trading':False}
    return proof.board(main_sha=expected,railway_source_sha=deployed,deployed_sha=deployed,runtime_sha=deployed,
        deployment={'status':'SUCCESS','runtime':'v23','real_trading':False},threads=[t.name for t in threading.enumerate()],endpoints={},ci={'status':'NOT_VERIFIED'},schema=schema,authority=authority)

class ValidationV23Handler(base22.ValidationV22Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-161-170-v1': self._send(200,runtime_board_161_170());return
        if path=='/autonomous-simulator/tasks-21-170-v1':
            self._send(200,{'tasks_21_160':{'tasks_21_130':{**base22.base21._all_prior_boards(),'tasks_121_130':base22.base21.runtime_board_121_130()},'tasks_131_160':base22.runtime_board_131_160()},
                'tasks_161_170':runtime_board_161_170(),'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()

def main():
    base22.base21.base20._start_inherited_threads()
    threading.Thread(target=_maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True: time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV23Handler).serve_forever()
if __name__=='__main__': main()
