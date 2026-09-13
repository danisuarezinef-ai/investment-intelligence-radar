"""Production PAPER runtime v17: v16 + portfolio intelligence tasks 71-80."""
from __future__ import annotations
import json,os,threading,time
from http.server import ThreadingHTTPServer
import cloud_service_v16 as base16
import radar_learning_evidence_41_50_v1 as evidence
import radar_portfolio_intelligence_71_80_v1 as p7180
import radar_agents
import radar_champion_portfolio
import radar_core
REAL_TRADING=False

def _price_series(days=180):
    out={}
    for sym in radar_core.ASSETS:
        try:out[sym]=radar_core._daily_series(sym,days)
        except Exception:out[sym]=[]
    return out

def _liquidity_snapshot():
    out={}
    try:
        c=radar_core.con()
        rows=c.execute("select symbol,volume from market_snapshots where id in (select max(id) from market_snapshots group by symbol)").fetchall();c.close()
        for sym,vol in rows:
            if vol is not None:out[str(sym)]={'volume':float(vol),'spread_pct':0.001}
    except Exception:return {}
    return out

def runtime_board_71_80():
    ev=evidence.normalized_rows(limit=400)
    if ev.get('ok') is not True:
        tasks={str(n):{'state':'BLOCKED_EVIDENCE','evidence':{'status':'BLOCKED_EVIDENCE','reason':ev.get('error') or ev.get('status'),'real_trading':False}} for n in range(71,81)}
        return {'status':'BLOCKED_EVIDENCE','tasks':tasks,'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False}
    rows=list(ev.get('normalized_rows') or []);signals=[r for r in rows if r.get('matured') is not True]
    try:portfolio=radar_champion_portfolio.champion_status()
    except Exception:portfolio={'positions':[],'total':0,'cash':0,'real_trading':False}
    try:agents=radar_agents.agents_status()
    except Exception:agents=[]
    return p7180.board(rows,signals,portfolio,_price_series(),agents,_liquidity_snapshot())

def _log_once():
    time.sleep(25)
    try:
        out=runtime_board_71_80();compact={'status':out.get('status'),'states':{k:(v or {}).get('state') for k,v in (out.get('tasks') or {}).items()},'real_trading':False}
    except Exception as exc:compact={'status':'FAIL_CLOSED','error':f'{type(exc).__name__}: {str(exc)[:500]}','real_trading':False}
    print('[paper-portfolio-71-80] '+json.dumps(compact,sort_keys=True,default=str),flush=True)

class ValidationV17Handler(base16.ValidationV16Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-71-80-v1':self._send(200,runtime_board_71_80());return
        if path=='/autonomous-simulator/tasks-21-80-v1':
            self._send(200,{'tasks_21_70':base16.runtime_board_21_70(),'tasks_71_80':runtime_board_71_80(),
                            'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,
                            'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()

def main():
    base16.base15.base14.base13.base12._install_runtime_guards()
    threading.Thread(target=base16.base15.base14.base13.base12._supervision_loop,name='paper-v12-supervision',daemon=True).start()
    threading.Thread(target=base16.base15.base14.base13._run_runtime_probes_once,name='paper-disaster-probes',daemon=True).start()
    threading.Thread(target=base16.base15.base14._log_41_50_once,name='paper-learning-41-50',daemon=True).start()
    threading.Thread(target=base16.base15._log_once,name='paper-forward-51-60',daemon=True).start()
    threading.Thread(target=base16._log_once,name='paper-intelligence-61-70',daemon=True).start()
    threading.Thread(target=_log_once,name='paper-portfolio-71-80',daemon=True).start()
    port=int(os.environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV17Handler).serve_forever()
if __name__=='__main__':main()
