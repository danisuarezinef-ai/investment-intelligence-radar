"""Production PAPER runtime v24: v23 + tasks 171-190 execution reality proof."""
from __future__ import annotations
import threading,time
from http.server import ThreadingHTTPServer
import cloud_service_v23 as base23
import radar_execution_reality_171_190_v1 as p171190
import radar_paper_execution_evidence_v1 as execution_evidence
import radar_learning_evidence_41_50_v1 as learning_evidence
REAL_TRADING=False

def _restart_evidence():
    try:
        b=base23.base22.base21.base20.runtime_board_101_120()
        for t in b.get('tasks') or []:
            if int(t.get('task') or 0)==112:
                e=t.get('evidence') or {}
                return dict(e.get('restart') or {})
    except Exception:pass
    return {'preserves_prior_valid_hours':False,'state_hash_equal':False,'session_equal':False,'downtime_credit':False,'real_trading':False}

def _runtime_inputs():
    m=base23.maturity.status();schema=m.get('schema') or {};authority=m.get('authority') or {}
    maturity={'valid_forward_hours':m.get('valid_forward_hours') if m.get('valid_forward_hours') is not None else authority.get('valid_forward_hours'),
              'qualifying_intervals':authority.get('qualifying_intervals'),'overlap_guard':schema.get('overlap_guard') is True,
              'no_backfill':schema.get('no_backfill') is True and schema.get('no_downtime_credit') is True,'real_trading':False}
    ev=learning_evidence.normalized_rows(limit=500)
    rows=list(ev.get('normalized_rows') or []) if ev.get('ok') is True else []
    snapshots=list(ev.get('feature_snapshots') or []) if ev.get('ok') is True else []
    ee=execution_evidence.summary();rawm=ee.get('market') or {};n=float(rawm.get('rows') or 0);dups=float(ee.get('duplicate_groups') or 0)
    market={'rows':rawm.get('rows'),'sources':rawm.get('sources'),'symbols':rawm.get('symbols'),'last_at':rawm.get('last_at'),
            'stale_rate':ee.get('stale_rate'),'gap_rate':ee.get('gap_rate'),'duplicate_rate':(dups/n if n>0 else None),
            'broken_provider_paths':ee.get('broken_provider_paths'),'http_404_count':ee.get('http_404_count'),
            'contemporaneous_multi_source':ee.get('contemporaneous_multi_source') is True,'providers':ee.get('providers') or [],'real_trading':False}
    exraw=ee.get('execution') or {};fills=int(exraw.get('fill_count') or 0);unaccounted=int(exraw.get('unaccounted_fill_count') or 0)
    execution={'model_features':{'observed_spread':False,'observed_volume':True,'market_hours':False,'partial_fills':True,'rejects':True,'slippage':True,'commissions':True,'liquidity_limits':True},
               'slippage_observations':fills,'slippage_calibrated':False,'partial_fill_tested':True,'partial_fill_persisted':fills>0,
               'failure_modes':{'reject':True,'timeout':False,'market_closed':True,'insufficient_liquidity':True,'stale_quote':False},'real_trading':False}
    accounting={'atomic_fill_accounting':False,'unaccounted_fills':unaccounted,'equation_error':None,'real_trading':False}
    return maturity,rows,snapshots,market,list(ee.get('quotes') or []),execution,accounting,ee

def runtime_board_171_190():
    maturity,rows,snapshots,market,quotes,execution,accounting,ee=_runtime_inputs()
    out=p171190.board(maturity=maturity,intervals=[],restart=_restart_evidence(),feature_snapshots=snapshots,decision_rows=rows,
                      market=market,quotes=quotes,execution=execution,accounting=accounting)
    out['market_authority']={'ok':ee.get('ok') is True,'rows':market.get('rows'),'symbols':market.get('symbols'),'sources':market.get('sources'),
                             'observed_quotes':len(quotes),'providers':market.get('providers'),'real_trading':False}
    out['maturity_authority']=maturity;out['forward_rows']=len(rows);out['feature_snapshots']=len(snapshots)
    return out

class ValidationV24Handler(base23.ValidationV23Handler):
    def do_GET(self):
        path=self.path.split('?',1)[0]
        if path=='/autonomous-simulator/tasks-171-190-v1':self._send(200,runtime_board_171_190());return
        if path=='/autonomous-simulator/tasks-21-190-v1':
            self._send(200,{'tasks_21_170':{'tasks_21_160':{'tasks_21_130':{**base23.base22.base21._all_prior_boards(),'tasks_121_130':base23.base22.base21.runtime_board_121_130()},'tasks_131_160':base23.base22.runtime_board_131_160()},'tasks_161_170':base23.runtime_board_161_170()},'tasks_171_190':runtime_board_171_190(),'automatic_promotion':False,'automatic_release':False,'setup_1_6_allowed':False,'live_execution_allowed':False,'real_trading':False});return
        super().do_GET()

def main():
    base23.base22.base21.base20._start_inherited_threads()
    threading.Thread(target=base23._maturity_writer_loop,name='paper-maturity-writer',daemon=True).start()
    port=int(__import__('os').environ.get('PORT') or 0)
    if port<=0:
        while True:time.sleep(60)
    ThreadingHTTPServer(('0.0.0.0',port),ValidationV24Handler).serve_forever()
if __name__=='__main__':main()
