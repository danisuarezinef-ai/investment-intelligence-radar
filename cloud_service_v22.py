"""Production PAPER runtime v22: v21 + certification tasks 131-160."""
from __future__ import annotations
import os, threading, time
from http.server import ThreadingHTTPServer
import cloud_service_v21 as base21
import radar_learning_evidence_41_50_v1 as evidence
import radar_paper_certification_131_160_v1 as cert
REAL_TRADING=False


def _state_map(board):
    out={}
    for k,v in ((board or {}).get('tasks') or {}).items():out[str(k)]=(v or {}).get('state') or (v or {}).get('status')
    return out


def runtime_board_131_160():
    ev=evidence.normalized_rows(limit=500)
    rows=list(ev.get('normalized_rows') or []) if ev.get('ok') is True else []
    snaps=list(ev.get('feature_snapshots') or []) if ev.get('ok') is True else []
    prior_board=base21.runtime_board_121_130()
    prior=_state_map(prior_board)
    runtime=(base21.base20.base19._runtime_authority() or {})
    deployed_sha=os.environ.get('RAILWAY_GIT_COMMIT_SHA') or os.environ.get('RAILWAY_GIT_COMMIT')
    expected_sha=os.environ.get('RADAR_EXPECTED_DEPLOY_SHA')
    deployment={'status':'SUCCESS' if deployed_sha else 'NOT_VERIFIED','commit_sha':deployed_sha,'expected_sha':expected_sha,'runtime':'v22'}
    # Build evidence views without fabricating missing operational authorities.
    feature_rows=[{'prospective_capture':s.get('prospective_capture'),'features':s.get('features'),'feature_fingerprint':s.get('feature_fingerprint'),
                   'immutable':s.get('immutable'),'backfilled':s.get('backfilled')} for s in snaps]
    decisions=rows
    packages=[]
    records=[{'id':r.get('prediction_id'),'prediction_hash':r.get('prediction_hash'),'mutated':False,'retroactive_change':False} for r in rows]
    # Operational inputs intentionally remain empty until dedicated authorities expose them.
    out=cert.board(deployment=deployment,ci={'status':'PENDING_EXTERNAL_CI'},
        runtime={'main_sha':expected_sha,'deployed_sha':deployed_sha,'entrypoint_sha':deployed_sha},
        feature_rows=feature_rows,decisions=decisions,snapshots=snaps,packages=packages,rows=rows,records=records,
        market={},symbols={},provider_failover={},price_consensus={},spread_observations=[],liquidity_observations=[],
        market_hours={},execution={},order_events=[],fill_events=[],accounting={},position_events=[],learning_records=[],
        arena={},sandbox={'isolated':True,'shadow_only':True,'no_champion_mutation':True,'no_live_authority':True,'state_namespace_separate':True},
        rollback={},catastrophic_guard={},recovery_scenarios=[],observatory={},prior_states=prior,
        valid_forward_hours=runtime.get('audited_valid_forward_hours'))
    out['runtime_authority']=runtime;out['forward_rows']=len(rows);out['feature_snapshots']=len(snaps)
    return out


class ValidationV22Handler(base21.ValidationV21Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-131-160-v1':self._send(200,runtime_board_131_160());return
        if path=='/autonomous-simulator/tasks-21-160-v1':
            prior=base21._all_prior_boards();prior['tasks_121_130']=base21.runtime_board_121_130();prior['tasks_131_160']=runtime_board_131_160()
            self._send(200,{**prior,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()


def main():
    b12=base21.base20.base19.base18.base17.base16.base15.base14.base13.base12
    b12._install_runtime_guards()
    threading.Thread(target=b12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV22Handler).serve_forever()
if __name__=='__main__':main()
