"""Production PAPER runtime v21: v20 + learning governance tasks 121-130."""
from __future__ import annotations
import os,threading,time
from http.server import ThreadingHTTPServer
import cloud_service_v20 as base20
import radar_learning_evidence_41_50_v1 as evidence
import radar_learning_governance_121_130_v1 as p121130
REAL_TRADING=False

def _state_map(board):
    out={}
    tasks=(board or {}).get('tasks') or {}
    if isinstance(tasks,dict):
        for k,v in tasks.items():out[str(k)]=(v or {}).get('state') or (v or {}).get('status')
    elif isinstance(tasks,list):
        for v in tasks:
            if isinstance(v,dict) and v.get('task') is not None:out[str(v['task'])]=v.get('status') or v.get('state')
    return out

def _all_prior_boards():
    b19=base20.base19;b18=b19.base18;b17=b18.base17;b16=b17.base16;b15=b16.base15;b14=b15.base14;b13=b14.base13
    boards={
        'tasks_21_30':b13.runtime_board_21_30(),
        'tasks_31_40':b13.runtime_board_31_40(),
        'tasks_41_50':b14.runtime_board_41_50(),
        'tasks_51_60':b15.runtime_board_51_60(),
        'tasks_61_70':b16.runtime_board_61_70(),
        'tasks_71_80':b17.runtime_board_71_80(),
        'tasks_81_90':b18.runtime_board_81_90(),
        'tasks_91_100':b19.runtime_board_91_100(),
        'tasks_101_120':base20.runtime_board_101_120(),
    }
    return boards

def runtime_board_121_130():
    ev=evidence.normalized_rows(limit=500)
    if ev.get('ok') is not True:
        tasks={str(n):{'state':'BLOCKED_EVIDENCE','evidence':{'status':'BLOCKED_EVIDENCE','reason':ev.get('error') or ev.get('status'),'real_trading':False}} for n in range(121,131)}
        return {'status':'BLOCKED_EVIDENCE','tasks':tasks,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
    rows=list(ev.get('normalized_rows') or []);feature_snapshots=list(ev.get('feature_snapshots') or [])
    b19=base20.base19;runtime=b19._runtime_authority() or {};boards=_all_prior_boards()
    prior={}
    for b in boards.values():prior.update(_state_map(b))
    b91=boards['tasks_91_100'];b51=boards['tasks_51_60'];b71=boards['tasks_71_80']
    candidates=[r for r in rows if r.get('matured') is not True]
    q97=((b91.get('tasks') or {}).get('97') or {}).get('state')=='PASS'
    t51=(b51.get('tasks') or {});t71=(b71.get('tasks') or {})
    drift_state=((t51.get('58') or {}).get('state'))
    unknown_state=((t51.get('57') or {}).get('state'))
    champion_state=((boards['tasks_41_50'].get('tasks') or {}).get('50') or {}).get('state')
    gov={'critical_integrity':runtime.get('critical_runtime_ok') is True and runtime.get('exact_restore_ok') is True,
         'evidence_quality':q97,
         'severe_drift':drift_state in ('ATTENTION','FAILED','FAIL_CLOSED'),
         'unknown_regime':unknown_state not in ('PASS',),
         'champion_degraded':champion_state in ('ATTENTION','FAILED','FAIL_CLOSED')}
    critical_runtime={'lease_held':runtime.get('lease_held'),'durable_sync':runtime.get('durable_sync_status'),'exact_restore':runtime.get('exact_restore_ok')}
    risk={'max_positions':5,'max_position':.20,'risk_budget':.70,
          'survival_gate_pass':((t71.get('80') or {}).get('state')=='PASS'),
          'correlation_verified':((t71.get('71') or {}).get('state')=='PASS'),
          'expected_shortfall_verified':((t71.get('76') or {}).get('state')=='PASS'),
          'liquidity_verified':((t71.get('79') or {}).get('state')=='STRESS_COMPLETE')}
    out=p121130.board(rows,feature_snapshots=feature_snapshots,candidates=candidates,risk=risk,
                       governor_inputs=gov,task_states=prior,critical_runtime=critical_runtime,
                       valid_forward_hours=runtime.get('audited_valid_forward_hours'))
    current={**prior,**{k:(v or {}).get('state') for k,v in (out.get('tasks') or {}).items() if k!='130'}}
    master=p121130.master_paper_control_gate(current,critical_runtime,runtime.get('audited_valid_forward_hours'))
    out['tasks']['130']={'state':master.get('status'),'evidence':master}
    out['forward_rows']=len(rows);out['runtime_authority']=runtime
    out['feature_snapshot_stats']=ev.get('feature_snapshot_stats') or {'n':len(feature_snapshots)}
    out['risk_authority']=risk;out['governor_inputs']=gov
    return out

class ValidationV21Handler(base20.ValidationV20Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-121-130-v1':self._send(200,runtime_board_121_130());return
        if path=='/autonomous-simulator/tasks-21-130-v1':
            boards=_all_prior_boards();boards['tasks_121_130']=runtime_board_121_130()
            self._send(200,{**boards,'automatic_promotion':False,'automatic_release':False,
                            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()

def main():
    b12=base20.base19.base18.base17.base16.base15.base14.base13.base12;b12._install_runtime_guards()
    threading.Thread(target=b12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV21Handler).serve_forever()
if __name__=='__main__':main()
