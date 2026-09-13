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

def runtime_board_121_130():
    ev=evidence.normalized_rows(limit=500)
    if ev.get('ok') is not True:
        tasks={str(n):{'state':'BLOCKED_EVIDENCE','evidence':{'status':'BLOCKED_EVIDENCE','reason':ev.get('error') or ev.get('status'),'real_trading':False}} for n in range(121,131)}
        return {'status':'BLOCKED_EVIDENCE','tasks':tasks,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
    rows=list(ev.get('normalized_rows') or [])
    b19=base20.base19
    runtime=b19._runtime_authority() or {}
    b91=b19.runtime_board_91_100()
    b101=base20.runtime_board_101_120()
    prior={**_state_map(b91),**_state_map(b101)}
    # Pull critical older states where available. Missing proof remains missing rather than inferred.
    try:
        b13=b19.base18.base17.base16.base15.base14.base13
        b21=b13.runtime_board_21_30();prior.update({str(x.get('task')):x.get('status') for x in (b21.get('tasks') or []) if isinstance(x,dict)})
    except Exception:pass
    try:
        b71=b19.base18.base17.runtime_board_71_80();prior.update(_state_map(b71))
    except Exception:pass
    candidates=[r for r in rows if r.get('matured') is not True]
    q97=((b91.get('tasks') or {}).get('97') or {}).get('state')=='PASS'
    gov={'critical_integrity':runtime.get('critical_runtime_ok') is True and runtime.get('exact_restore_ok') is True,
         'evidence_quality':q97,'severe_drift':False,'unknown_regime':False,'champion_degraded':False}
    critical_runtime={'lease_held':runtime.get('lease_held'),'durable_sync':runtime.get('durable_sync_status'),'exact_restore':runtime.get('exact_restore_ok')}
    # Full immutable feature vectors are not currently exposed by normalized forward evidence; do not reconstruct them.
    out=p121130.board(rows,feature_snapshots=[],candidates=candidates,risk={'max_positions':5,'max_position':.20,'risk_budget':.70},
                       governor_inputs=gov,task_states=prior,critical_runtime=critical_runtime,
                       valid_forward_hours=runtime.get('audited_valid_forward_hours'))
    # Re-evaluate task130 with 121-129 current states included.
    current={**prior,**{k:(v or {}).get('state') for k,v in (out.get('tasks') or {}).items() if k!='130'}}
    master=p121130.master_paper_control_gate(current,critical_runtime,runtime.get('audited_valid_forward_hours'))
    out['tasks']['130']={'state':master.get('status'),'evidence':master}
    out['forward_rows']=len(rows);out['runtime_authority']=runtime;out['feature_snapshot_authority']='NOT_EXPOSED_AS_FULL_IMMUTABLE_VECTOR'
    return out

class ValidationV21Handler(base20.ValidationV20Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-121-130-v1':self._send(200,runtime_board_121_130());return
        if path=='/autonomous-simulator/tasks-21-130-v1':
            self._send(200,{'tasks_91_100':base20.base19.runtime_board_91_100(),'tasks_101_120':base20.runtime_board_101_120(),
                            'tasks_121_130':runtime_board_121_130(),'automatic_promotion':False,'automatic_release':False,
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
