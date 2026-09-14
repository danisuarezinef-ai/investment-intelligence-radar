"""Block H — RADAR_FIRST_PAPER_TRIAL_001.
Frozen, reproducible, end-to-end PAPER trial. No broker transport, no real money.
"""
from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timezone
import hashlib, json, math
import radar_block_f_pipeline_v1 as F
import radar_block_g_learning_v1 as G
from radar_paper_accounting_v1 import new_account, mark_to_market, accounting_invariants

REAL_TRADING=False
TRIAL_ID='RADAR_FIRST_PAPER_TRIAL_001'
INITIAL_CAPITAL=10000.0
FROZEN_UNIVERSE=('MSFT','NVDA','GOOGL','AAPL','AMZN','META','AVGO','JPM','XOM','LLY','SPY','QQQ')
CONFIG={'trial_id':TRIAL_ID,'initial_capital':INITIAL_CAPITAL,'universe':FROZEN_UNIVERSE,'budget_fraction':.08,
        'max_positions':6,'regime_snapshot':{'volatility_pct':17,'trend_pct':11,'breadth_pct':67,'inflation_trend':'stable'},
        'paper_only':True,'real_trading':False}

def _hash(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()
def frozen_config():
    x=deepcopy(CONFIG); x['config_hash']=_hash(CONFIG); return x

def fixtures():
    # Frozen trial observations; deterministic so technical integrity can be reproduced.
    prices={'MSFT':503.,'NVDA':178.,'GOOGL':242.,'AAPL':234.,'AMZN':231.,'META':756.,'AVGO':359.,'JPM':305.,'XOM':116.,'LLY':763.,'SPY':659.,'QQQ':592.}
    terminal={'MSFT':512.,'NVDA':174.,'GOOGL':247.,'AAPL':236.,'AMZN':228.,'META':770.,'AVGO':365.,'JPM':301.,'XOM':118.,'LLY':750.,'SPY':665.,'QQQ':598.}
    rows=[]
    for i,s in enumerate(FROZEN_UNIVERSE):
        rows.append({'symbol':s,'score':8.2-i*.48,'expected_return_pct':11.5-i*.42,'downside_pct':3.5+i*.35,
                     'risk':('bajo','intermedio','alto')[i%3],'data_quality':.95-i*.012,'entry':prices[s],'terminal':terminal[s]})
    return rows

def _quote(symbol,price):
    # Use the same gate-compatible quote type as Block F; frozen timestamps are generated at run time only for freshness.
    now=datetime.now(timezone.utc); E=F.market_data
    return E.MarketQuote(symbol,float(price),E.v1._iso(now),'trial_fixture','OK','USD','OPEN',
                         ingestion_timestamp=E.v1._iso(now),source_kind='INTRADAY_QUOTE')

def benchmarks(rows):
    rets=[r['terminal']/r['entry']-1 for r in rows]
    equal=sum(rets)/len(rets)
    spy=next(r for r in rows if r['symbol']=='SPY'); spyret=spy['terminal']/spy['entry']-1
    return {'cash_return':0.,'equal_weight_return':equal,'index_proxy_symbol':'SPY','index_proxy_return':spyret}

def run_trial():
    rows=fixtures(); cfg=frozen_config(); account=new_account(INITIAL_CAPITAL); traces=[]; candidates=[]
    for r in rows:
        candidates.append({'symbol':r['symbol'],'score':r['score'],'expected_return_pct':r['expected_return_pct'],
                           'downside_pct':r['downside_pct'],'risk':r['risk'],'data_quality':r['data_quality'],'observed_price':r['entry']})
    regime=F.classify_regime(CONFIG['regime_snapshot']); radar=F.opportunity_radar_369(candidates,regime_state=regime)
    for r in rows:
        if len(account.get('positions') or {})>=CONFIG['max_positions']: break
        candidate=next(x for x in candidates if x['symbol']==r['symbol'])
        account,trace=F.decision_to_paper_execution(candidate,_quote(r['symbol'],r['entry']),regime_snapshot=CONFIG['regime_snapshot'],
                                                     account=account,budget_fraction=CONFIG['budget_fraction'])
        traces.append(trace)
    terminal_marks={r['symbol']:r['terminal'] for r in rows}
    valuation=mark_to_market(account,terminal_marks); inv=accounting_invariants(account,terminal_marks)
    equity=float(valuation['equity']); trial_return=equity/INITIAL_CAPITAL-1
    bench=benchmarks(rows)
    # Outcome evidence includes both trades and non-trades; it is deliberately accelerated, never formal forward maturity.
    champ=G.seed_lineage('balanced'); challengers=[G.mutate(champ,'threshold_tighten',.04,'low_vol'),G.mutate(champ,'regime_weight',.05,'regime_specialist'),G.mutate(champ,'confidence_calibration',.03,'causal_specialist')]
    observations=[]
    trace_by_symbol={t.get('ensemble',{}).get('symbol'):t for t in traces}
    for r in rows:
        t=trace_by_symbol.get(r['symbol']); action='BUY' if t and t.get('status')=='PAPER_FILLED' else 'NO_INVERTIR'
        observations.append({'action':action,'realized_return':r['terminal']/r['entry']-1,'benchmark_return':bench['index_proxy_return'],
                             'drawdown':max(0.,(r['entry']-r['terminal'])/r['entry']),'costs':0.001 if action=='BUY' else 0.,
                             'confidence':(t or {}).get('ensemble',{}).get('confidence',.5),'horizon':('1d','1w','1m','3m')[len(observations)%4],
                             'evidence_kind':'walk_forward','reason':'first PAPER trial outcome'})
    learning=G.accelerated_learning_cycle(champ,challengers,observations)
    fills=sum(t.get('status')=='PAPER_FILLED' for t in traces); nonbuys=len(rows)-fills
    report={'trial_id':TRIAL_ID,'config':cfg,'frozen_universe':list(FROZEN_UNIVERSE),'initial_capital':INITIAL_CAPITAL,
            'ending_equity':equity,'trial_return':trial_return,'benchmarks':bench,'excess_vs_cash':trial_return,
            'excess_vs_equal_weight':trial_return-bench['equal_weight_return'],'excess_vs_index_proxy':trial_return-bench['index_proxy_return'],
            'fills':fills,'non_buys':nonbuys,'positions':account.get('positions',{}),'radar_top3':[x['symbol'] for x in radar['top3']],
            'traces':traces,'accounting':inv,'learning':learning,'formal_forward_maturity_samples':learning['formal_forward_maturity_samples'],
            'trial_evidence_label':'ACCELERATED_PAPER_NOT_AUDITED_FORWARD','broker_connected':False,'live_execution_allowed':False,
            'real_money_orders_allowed':False,'real_trading':False}
    checks={'trial_id_frozen':cfg['trial_id']==TRIAL_ID,'universe_frozen':tuple(report['frozen_universe'])==FROZEN_UNIVERSE,
            'config_hash_stable':cfg['config_hash']==_hash(CONFIG),'capital_positive':INITIAL_CAPITAL>0,'radar_369_used':len(radar['top3'])==3,
            'decision_execution_traces':all(t.get('trace_id') for t in traces),'at_least_one_paper_fill':fills>0,
            'accounting_pass':inv.get('status')=='PASS','benchmarks_complete':all(k in bench for k in ('cash_return','equal_weight_return','index_proxy_return')),
            'learning_completed':learning['competition']['one_active_champion'],'non_trade_learning':nonbuys>0,
            'no_false_forward_credit':learning['formal_forward_maturity_samples']==0,
            'real_trading_false':not REAL_TRADING and report['real_trading'] is False and report['real_money_orders_allowed'] is False}
    report['checks']=checks; report['technical_status']='PASS' if all(checks.values()) else 'FAIL'
    report['trial_result']='PASS' if all(checks.values()) else 'FAIL'
    report['report_hash']=_hash({k:v for k,v in report.items() if k!='report_hash'})
    return report

def block_h_validation():
    a=run_trial(); b=run_trial()
    # Ignore run-time quote timestamps by comparing economic/config outputs rather than raw trace hashes.
    deterministic=(a['config']['config_hash']==b['config']['config_hash'] and abs(a['ending_equity']-b['ending_equity'])<1e-9 and
                   a['fills']==b['fills'] and a['radar_top3']==b['radar_top3'])
    checks=dict(a['checks']); checks['reproducible_economics']=deterministic
    status='PASS' if all(checks.values()) else 'FAIL'
    return {'status':status,'checks':checks,'trial':a,'first_paper_trial':'VERIFIED' if status=='PASS' else 'NOT_VERIFIED',
            'restart_recovery_required_for_full_h':True,'real_trading':False,'real_money_orders_allowed':False}
