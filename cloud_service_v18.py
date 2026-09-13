"""Production PAPER runtime v18: v17 + explainability/counterfactual policy tasks 81-90."""
from __future__ import annotations
import json,os,threading,time
from http.server import ThreadingHTTPServer
import cloud_service_v17 as base17
import radar_learning_evidence_41_50_v1 as evidence
import radar_policy_intelligence_81_90_v1 as p8190
REAL_TRADING=False

def runtime_board_81_90():
    ev=evidence.normalized_rows(limit=500)
    if ev.get('ok') is not True:
        tasks={str(n):{'state':'BLOCKED_EVIDENCE','evidence':{'status':'BLOCKED_EVIDENCE','reason':ev.get('error') or ev.get('status'),'real_trading':False}} for n in range(81,91)}
        return {'status':'BLOCKED_EVIDENCE','tasks':tasks,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
    out=p8190.board(list(ev.get('normalized_rows') or []));out['forward_rows']=len(ev.get('normalized_rows') or []);out['horizon_stats']=ev.get('stats') or [];return out

def _log_once():
    time.sleep(30)
    try:
        out=runtime_board_81_90();compact={'status':out.get('status'),'forward_rows':out.get('forward_rows'),'states':{k:(v or {}).get('state') for k,v in (out.get('tasks') or {}).items()},'real_trading':False}
    except Exception as exc:compact={'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}
    print('[paper-policy-81-90] '+json.dumps(compact,sort_keys=True,default=str),flush=True)

class ValidationV18Handler(base17.ValidationV17Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-81-90-v1':self._send(200,runtime_board_81_90());return
        if path=='/autonomous-simulator/tasks-21-90-v1':
            self._send(200,{'tasks_21_80':{'tasks_21_70':base17.base16.runtime_board_21_70(),'tasks_71_80':base17.runtime_board_71_80()},
                            'tasks_81_90':runtime_board_81_90(),'automatic_promotion':False,'automatic_release':False,
                            'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()

def main():
    base17.base16.base15.base14.base13.base12._install_runtime_guards()
    threading.Thread(target=base17.base16.base15.base14.base13.base12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    threading.Thread(target=base17.base16.base15.base14.base13._run_runtime_probes_once,name='paper-disaster-probes',daemon=True).start()
    threading.Thread(target=base17.base16.base15.base14._log_41_50_once,name='paper-learning-41-50',daemon=True).start()
    threading.Thread(target=base17.base16.base15._log_once,name='paper-forward-51-60',daemon=True).start()
    threading.Thread(target=base17.base16._log_once,name='paper-intelligence-61-70',daemon=True).start()
    threading.Thread(target=base17._log_once,name='paper-portfolio-71-80',daemon=True).start()
    threading.Thread(target=_log_once,name='paper-policy-81-90',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV18Handler).serve_forever()
if __name__=='__main__':main()
