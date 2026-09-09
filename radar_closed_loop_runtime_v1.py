"""Prospective closed-loop PAPER runtime.

Data -> mature forward evidence -> expected return -> optimizer -> risk/cost/diversification
-> PAPER rebalance -> learning -> champion/challenger. Every stage fails closed.
REAL_TRADING is permanently false in this runtime.
"""
from __future__ import annotations
import json
from collections import defaultdict
from datetime import datetime
from radar_core import con
from radar_expected_return_v1 import expected_return_signal
from radar_portfolio_optimizer_v3 import optimize_capital
from radar_paper_portfolio_v5 import mark_to_market, paper_portfolio_v5_status
from radar_paper_risk_budget_v2 import assess_risk
from radar_turnover_cost_governor_v1 import turnover_cost_gate
from radar_diversification_guard_v1 import diversification_guard
from radar_promotion_governance_v2 import promotion_governance
from radar_paper_rebalance_v1 import rebalance_paper
from radar_learning_engine_v3 import learn_v3
from radar_champion_challenger_v1 import compete

REAL_TRADING=False
PAPER_AUTONOMY_APPROVED=True  # explicit user authorization; PAPER only
PAPER_COST_BPS=10.0


def _j(value):
    if isinstance(value,dict):return value
    try:return json.loads(value or '{}')
    except Exception:return {}


def _days(a,b):
    try:return max(0,(datetime.fromisoformat(str(b).replace('Z','+00:00'))-datetime.fromisoformat(str(a).replace('Z','+00:00'))).days+1)
    except Exception:return 0


def latest_prices():
    c=con();rows=c.execute('''select m.symbol,m.price from market_snapshots m join
      (select symbol,max(id) id from market_snapshots group by symbol) z on z.id=m.id''').fetchall();c.close()
    return {str(s):float(p) for s,p in rows if p is not None and float(p)>0}


def forward_records():
    c=con();rows=c.execute('''select created_at,target_date,asset,horizon,model_version,payload,outcome,evaluated_at
      from prediction_ledger where outcome is not null order by target_date''').fetchall();c.close();out=[]
    for created,target,symbol,horizon,model,payload,outcome,evaluated in rows:
        p=_j(payload);o=_j(outcome);features=p.get('features') if isinstance(p.get('features'),dict) else {}
        out.append({'created_at':created,'target_date':target,'evaluated_at':evaluated,'symbol':symbol,'horizon':horizon,
          'model_version':model,'signals':features,'regime':(_j(p.get('uncertainty')).get('regime') if not isinstance(p.get('uncertainty'),dict) else p.get('uncertainty',{}).get('regime')) or 'UNKNOWN',
          'immutable':p.get('immutable') is True,'matured':True,'backfilled':o.get('backfilled') is True,
          'net_return':o.get('net_return'),'excess_return':o.get('excess_return'),
          'cost_aware':o.get('cost') is not None and bool(o.get('cost_model')),
          'benchmark_aware':o.get('benchmark_return') is not None and bool(o.get('benchmark_name'))})
    return out


def _model_competition(records):
    grouped=defaultdict(list)
    for r in records:
        if r.get('excess_return') is not None:grouped[str(r.get('model_version') or 'UNKNOWN')].append(r)
    models=[]
    for version,rows in grouped.items():
        dates=[str(r.get('target_date') or '') for r in rows if r.get('target_date')]
        vals=[float(r['excess_return']) for r in rows if isinstance(r.get('excess_return'),(int,float))]
        models.append({'model_version':version,'forward_n':len(vals),
          'forward_days':_days(min(dates),max(dates)) if dates else 0,'forward_only':True,'matured_only':True,
          'backfilled':any(r.get('backfilled') is True for r in rows),'cost_aware':all(r.get('cost_aware') is True for r in rows),
          'benchmark_aware':all(r.get('benchmark_aware') is True for r in rows),
          'mean_excess_return':sum(vals)/len(vals) if vals else None})
    return compete(models)


def _promotion_evidence(records):
    dates=[str(r['target_date']) for r in records if r.get('target_date')];n=len(records)
    bench=sum(1 for r in records if r.get('benchmark_aware') is True);cost=sum(1 for r in records if r.get('cost_aware') is True)
    c=con();marks=c.execute('select count(*) from paper_equity_v5').fetchone()[0] if c.execute("select 1 from sqlite_master where type='table' and name='paper_equity_v5'").fetchone() else 0
    ddrow=c.execute('select min(drawdown_pct) from paper_equity_v5').fetchone()[0] if marks else None
    c.close()
    monthly=defaultdict(float)
    for r in records:
        if isinstance(r.get('net_return'),(int,float)) and r.get('target_date'):monthly[str(r['target_date'])[:7]]+=float(r['net_return'])
    return {'forward_days':_days(min(dates),max(dates)) if dates else 0,'decisions':n,'marks':marks,
      'max_drawdown_pct':float(ddrow)*100.0 if ddrow is not None else None,
      'benchmark_coverage':bench/n if n else None,'cost_coverage':cost/n if n else None,
      'positive_months':sum(1 for x in monthly.values() if x>0),'oos_pass':False,'degradation_clear':False}


def _latest_candidates(horizon='1d'):
    c=con();rows=c.execute('''select asset,payload from prediction_ledger where id in
      (select max(id) from prediction_ledger where horizon=? group by asset) order by asset''',(horizon,)).fetchall();c.close();out=[]
    for symbol,payload in rows:
        p=_j(payload);features=p.get('features') if isinstance(p.get('features'),dict) else {};vol=features.get('volatility')
        risk=max(0.0,min(1.0,abs(float(vol)))) if isinstance(vol,(int,float)) else None
        ev=expected_return_signal({'symbol':symbol,'score':p.get('score')},horizon)
        out.append({'symbol':symbol,'decision_state':str(p.get('decision_state') or 'WAIT').upper(),
          'expected_return':ev.get('expected_return'),'prediction_evidence':ev.get('status'),
          'risk_score':risk,'evidence_complete':ev.get('status')=='VERIFIED_FORWARD' and risk is not None,
          'expected_return_evidence':ev})
    return out


def closed_loop_cycle(horizon='1d'):
    prices=latest_prices();mark=mark_to_market(prices);portfolio=paper_portfolio_v5_status();eq=(mark.get('total') if mark.get('status')=='OK' else None)
    cash=mark.get('cash') if mark.get('status')=='OK' else portfolio.get('cash');dd=mark.get('drawdown_pct') if mark.get('status')=='OK' else ((portfolio.get('equity') or {}).get('drawdown_pct'))
    records=forward_records();learning=learn_v3(records);competition=_model_competition(records)
    promo_evidence=_promotion_evidence(records);governance=promotion_governance(promo_evidence,human_approved=PAPER_AUTONOMY_APPROVED)
    candidates=_latest_candidates(horizon)
    if not isinstance(eq,(int,float)) or not isinstance(cash,(int,float)) or dd is None:
        optimizer={'status':'BLOCKED','reason':'PAPER_MARK_NOT_READY','allocations':[],'real_trading':False}
    else:optimizer=optimize_capital(cash=float(cash),equity=float(eq),opportunities=candidates,drawdown_pct=float(dd))
    current_positions=[]
    if mark.get('status')=='OK' and eq:
        current_positions=[{'symbol':p['symbol'],'market_value':p['value'],'weight':p['value']/eq,'sector':'UNKNOWN'} for p in mark.get('positions',[])]
    proposed=list(current_positions)
    for a in optimizer.get('allocations',[]):proposed.append({'symbol':a['symbol'],'market_value':a['amount'],'weight':a['amount']/eq if eq else 1.0,'sector':'UNKNOWN'})
    risk=assess_risk(equity=eq,cash=cash,positions=proposed,drawdown_pct=dd) if eq else {'status':'BLOCKED','reason':'INVALID_EQUITY','real_trading':False}
    diversification=diversification_guard(positions=proposed)
    total_new=sum(float(a.get('amount') or 0) for a in optimizer.get('allocations',[]));turnover=(total_new/eq) if eq else 1.0
    cost_checks=[turnover_cost_gate(proposed_turnover_pct=turnover,estimated_cost_bps=PAPER_COST_BPS,
                 expected_return_bps=float(a['expected_return'])*10000.0 if isinstance(a.get('expected_return'),(int,float)) else None)
                 for a in optimizer.get('allocations',[])]
    cost_gate={'status':'PASS' if cost_checks and all(x['status']=='PASS' for x in cost_checks) else ('NO_ALLOCATIONS' if not cost_checks else 'BLOCKED'),'checks':cost_checks,'real_trading':False}
    all_gates=governance.get('paper_execution_allowed') is True and risk.get('status')=='PASS_PAPER' and diversification.get('status')=='PASS' and cost_gate.get('status')=='PASS'
    execution_governance=dict(governance);execution_governance['paper_execution_allowed']=bool(all_gates)
    targets={p['symbol']:p['market_value'] for p in current_positions}
    for a in optimizer.get('allocations',[]):targets[a['symbol']]=targets.get(a['symbol'],0.0)+float(a['amount'])
    # Once PAPER is truly enabled, a current position whose current prospectively-gated state is WAIT is closed.
    states={x['symbol']:x['decision_state'] for x in candidates}
    if all_gates:
        for symbol in list(targets):
            if states.get(symbol)=='WAIT':targets[symbol]=0.0
    execution=rebalance_paper(governance=execution_governance,target_values=targets,prices=prices)
    return {'status':'PAPER_ACTIVE' if all_gates else 'HOLD','forward_records':len(records),'promotion_evidence':promo_evidence,
      'governance':governance,'learning':learning,'champion_challenger':competition,'candidates':candidates,
      'optimizer':optimizer,'risk_budget':risk,'diversification':diversification,'cost_governor':cost_gate,
      'paper_mark':mark,'execution':execution,'paper_autonomy_approved':PAPER_AUTONOMY_APPROVED,
      'performance_claim':'INSUFFICIENT_EVIDENCE' if len(records)<20 else 'PAPER_EVIDENCE_ONLY',
      'can_trade':False,'real_trading':False}
