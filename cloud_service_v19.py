"""Production PAPER runtime v19: v18 + validation/readiness tasks 91-100."""
from __future__ import annotations
import json,os,threading,time
from http.server import ThreadingHTTPServer
import cloud_service_v18 as base18
import radar_learning_evidence_41_50_v1 as evidence
import radar_validation_intelligence_91_100_v1 as p91100
REAL_TRADING=False

def _runtime_authority():
    """Read current critical runtime facts without inventing maturity."""
    try:
        base12=base18.base17.base16.base15.base14.base13.base12
        lease=base12._lease_local() or {}
        checkpoint=base12._restore_state() or {}
        durable=base12._DURABLE_SYNC or {}
        exact=(checkpoint.get('status')=='RESTORED_EXACT_PAPER_ENGINE' and checkpoint.get('backfill_used') is not True)
        critical=(lease.get('held') is True and durable.get('status')=='RECONCILED')
        return {'critical_runtime_ok':critical,'exact_restore_ok':exact,'audited_valid_forward_hours':None,
                'lease_held':lease.get('held'),'durable_sync_status':durable.get('status'),
                'restore_status':checkpoint.get('status'),'maturity_source':'NOT_AVAILABLE_AS_AUDITED_COUNTER',
                'real_trading':False}
    except Exception as exc:
        return {'critical_runtime_ok':False,'exact_restore_ok':False,'audited_valid_forward_hours':None,
                'error':f'{type(exc).__name__}: {str(exc)[:400]}','real_trading':False}

def runtime_board_91_100():
    ev=evidence.normalized_rows(limit=500);runtime=_runtime_authority()
    if ev.get('ok') is not True:
        tasks={str(n):{'state':'BLOCKED_EVIDENCE','evidence':{'status':'BLOCKED_EVIDENCE','reason':ev.get('error') or ev.get('status'),'real_trading':False}} for n in range(91,101)}
        return {'status':'BLOCKED_EVIDENCE','tasks':tasks,'runtime_authority':runtime,'automatic_promotion':False,
                'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
    rows=list(ev.get('normalized_rows') or [])
    out=p91100.board(rows,audited_valid_forward_hours=runtime.get('audited_valid_forward_hours'),
                     critical_runtime_ok=runtime.get('critical_runtime_ok'),exact_restore_ok=runtime.get('exact_restore_ok'),
                     runtime_evidence=runtime)
    out['forward_rows']=len(rows);out['horizon_stats']=ev.get('stats') or [];out['runtime_authority']=runtime
    return out

def _log_once():
    time.sleep(35)
    try:
        out=runtime_board_91_100();compact={'status':out.get('status'),'forward_rows':out.get('forward_rows'),
            'states':{k:(v or {}).get('state') for k,v in (out.get('tasks') or {}).items()},
            'runtime_authority':out.get('runtime_authority'),'real_trading':False}
    except Exception as exc:compact={'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}
    print('[paper-validation-91-100] '+json.dumps(compact,sort_keys=True,default=str),flush=True)

class ValidationV19Handler(base18.ValidationV18Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-91-100-v1':self._send(200,runtime_board_91_100());return
        if path=='/autonomous-simulator/tasks-21-100-v1':
            self._send(200,{'tasks_21_90':{'tasks_21_80':{'tasks_21_70':base18.base17.base16.runtime_board_21_70(),
                            'tasks_71_80':base18.base17.runtime_board_71_80()},'tasks_81_90':base18.runtime_board_81_90()},
                            'tasks_91_100':runtime_board_91_100(),'automatic_promotion':False,'automatic_release':False,
                            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()

def main():
    base18.base17.base16.base15.base14.base13.base12._install_runtime_guards()
    threading.Thread(target=base18.base17.base16.base15.base14.base13.base12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    threading.Thread(target=base18.base17.base16.base15.base14.base13._run_runtime_probes_once,name='paper-disaster-probes',daemon=True).start()
    threading.Thread(target=base18.base17.base16.base15.base14._log_41_50_once,name='paper-learning-41-50',daemon=True).start()
    threading.Thread(target=base18.base17.base16.base15._log_once,name='paper-forward-51-60',daemon=True).start()
    threading.Thread(target=base18.base17.base16._log_once,name='paper-intelligence-61-70',daemon=True).start()
    threading.Thread(target=base18.base17._log_once,name='paper-portfolio-71-80',daemon=True).start()
    threading.Thread(target=base18._log_once,name='paper-policy-81-90',daemon=True).start()
    threading.Thread(target=_log_once,name='paper-validation-91-100',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV19Handler).serve_forever()
if __name__=='__main__':main()
