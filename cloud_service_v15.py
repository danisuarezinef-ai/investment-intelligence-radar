"""Production PAPER runtime v15: v14 + forward intelligence tasks 51-60."""
from __future__ import annotations
import json,os,threading,time
from http.server import ThreadingHTTPServer
import cloud_service_v14 as base14
import radar_learning_evidence_41_50_v1 as evidence
import radar_forward_intelligence_51_60_v1 as tasks5160
REAL_TRADING=False

def runtime_board_51_60():
    ev=evidence.normalized_rows(limit=400)
    if ev.get('ok') is not True:
        tasks={str(n):{'state':'BLOCKED_EVIDENCE','evidence':{'status':'BLOCKED_EVIDENCE','reason':ev.get('error') or ev.get('status'),'real_trading':False}} for n in range(51,61)}
        return {'status':'BLOCKED_EVIDENCE','tasks':tasks,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
    out=tasks5160.board(list(ev.get('normalized_rows') or []));out['forward_rows']=len(ev.get('normalized_rows') or []);out['horizon_stats']=ev.get('stats') or [];return out

def _log_once():
    time.sleep(20)
    try:
        out=runtime_board_51_60();compact={'status':out.get('status'),'forward_rows':out.get('forward_rows'),'states':{k:(v or {}).get('state') for k,v in (out.get('tasks') or {}).items()},'real_trading':False}
    except Exception as exc:compact={'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}
    print('[paper-forward-51-60] '+json.dumps(compact,sort_keys=True,default=str),flush=True)

class ValidationV15Handler(base14.ValidationV14Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-51-60-v1':self._send(200,runtime_board_51_60());return
        if path=='/autonomous-simulator/tasks-21-60-v1':
            self._send(200,{'tasks_21_30':base14.base13.runtime_board_21_30(),'tasks_31_40':base14.base13.runtime_board_31_40(),'tasks_41_50':base14.runtime_board_41_50(),'tasks_51_60':runtime_board_51_60(),'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()

def main():
    base14.base13.base12._install_runtime_guards()
    threading.Thread(target=base14.base13.base12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    threading.Thread(target=base14.base13._run_runtime_probes_once,name='paper-disaster-probes',daemon=True).start()
    threading.Thread(target=base14._log_41_50_once,name='paper-learning-41-50',daemon=True).start()
    threading.Thread(target=_log_once,name='paper-forward-51-60',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV15Handler).serve_forever()
if __name__=='__main__':main()
