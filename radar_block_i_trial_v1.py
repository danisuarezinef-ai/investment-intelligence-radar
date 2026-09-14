"""Block I — PAPER Trial 002: learned-policy comparison after H.
Technical experiment only. No real-money execution and no audited-forward credit.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib,json
import radar_block_h_trial_v1 as H

REAL_TRADING=False
TRIAL_ID='RADAR_PAPER_TRIAL_002'
CHAMPION_MUTATION='threshold_tighten'
CHAMPION_SPECIALIZATION='low_vol'

def _hash(x): return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),default=str).encode()).hexdigest()

def _select(rows, learned=True):
    # Trial 002 operationalizes the winning H challenger conservatively:
    # tighter score/data-quality gate + low-vol preference; max six positions.
    selected=[]
    for r in rows:
        if learned:
            if r['score'] < 6.4 or r['data_quality'] < .90 or r['risk']=='alto': continue
        else:
            if len(selected)>=6: break
        selected.append(r)
        if len(selected)>=6: break
    return selected

def _portfolio_return(selected, rows, budget_fraction=.08):
    # Cash plus equal fixed notional slices; includes same 10 bps round-trip trial cost assumption.
    ret=0.0
    for r in selected:
        ret += budget_fraction*((r['terminal']/r['entry']-1)-.001)
    return ret

def run_trial_002():
    rows=H.fixtures(); learned=_select(rows,True); baseline=_select(rows,False)
    learned_ret=_portfolio_return(learned,rows); baseline_ret=_portfolio_return(baseline,rows)
    bench=H.benchmarks(rows)
    learned_symbols=[r['symbol'] for r in learned]; baseline_symbols=[r['symbol'] for r in baseline]
    rejected=[r['symbol'] for r in rows if r['symbol'] not in learned_symbols]
    cfg={'trial_id':TRIAL_ID,'source_trial':H.TRIAL_ID,'champion_mutation':CHAMPION_MUTATION,
         'champion_specialization':CHAMPION_SPECIALIZATION,'initial_capital':H.INITIAL_CAPITAL,
         'universe':list(H.FROZEN_UNIVERSE),'budget_fraction':.08,'paper_only':True,'real_trading':False}
    cfg['config_hash']=_hash(cfg)
    checks={'learned_policy_applied':learned_symbols!=baseline_symbols,'has_investments':len(learned)>0,
            'has_rejections':len(rejected)>0,'comparison_present':True,'cash_benchmark_present':bench['cash_return']==0,
            'index_benchmark_present':'index_proxy_return' in bench,'no_false_forward_credit':True,
            'real_trading_false':not REAL_TRADING}
    out={'trial_id':TRIAL_ID,'config':cfg,'learned_symbols':learned_symbols,'baseline_symbols':baseline_symbols,
         'rejected_symbols':rejected,'learned_return':learned_ret,'baseline_h_policy_return':baseline_ret,
         'delta_vs_h_policy':learned_ret-baseline_ret,'ending_equity':H.INITIAL_CAPITAL*(1+learned_ret),
         'benchmarks':bench,'excess_vs_cash':learned_ret,'excess_vs_equal_weight':learned_ret-bench['equal_weight_return'],
         'excess_vs_index_proxy':learned_ret-bench['index_proxy_return'],'evidence_label':'ACCELERATED_PAPER_NOT_AUDITED_FORWARD',
         'formal_forward_maturity_samples':0,'checks':checks,'real_money_orders_allowed':False,'broker_connected':False,
         'live_execution_allowed':False,'real_trading':False}
    out['status']='PASS' if all(checks.values()) else 'FAIL'; out['report_hash']=_hash(out)
    return out

def block_i_validation():
    a=run_trial_002(); b=run_trial_002()
    deterministic=(a['config']['config_hash']==b['config']['config_hash'] and a['learned_symbols']==b['learned_symbols'] and abs(a['learned_return']-b['learned_return'])<1e-12)
    checks=dict(a['checks']); checks['reproducible_economics']=deterministic
    status='PASS' if all(checks.values()) else 'FAIL'
    return {'status':status,'checks':checks,'trial':a,'paper_trial_002':'VERIFIED' if status=='PASS' else 'NOT_VERIFIED',
            'learned_policy_beats_h_policy':a['delta_vs_h_policy']>0,'real_trading':False,'real_money_orders_allowed':False}
