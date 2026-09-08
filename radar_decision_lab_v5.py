"""Decision Lab v5 — comparable, fail-closed investment decision cards.

Produces BUY / WATCH / HOLD / REDUCE / AVOID decisions only from explicitly
provided evidence. Missing expected-return/downside/valuation evidence blocks new
BUY decisions. The runtime snapshot reads existing prediction/outcome tables but
does not invent valuation evidence. No real trading capability is present.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict
import statistics
from radar_core import con
from radar_learning import init_learning_db
from radar_decision_intelligence import decide

REAL_TRADING=False
ACTIONS=('BUY','WATCH','HOLD','REDUCE','AVOID')
MIN_EMPIRICAL_OUTCOMES=5


def _f(x):
    try:return float(x)
    except (TypeError,ValueError):return None


def _quantile(values,q):
    x=sorted(float(v) for v in values)
    if not x:return None
    pos=(len(x)-1)*float(q);lo=int(pos);hi=min(len(x)-1,lo+1);w=pos-lo
    return x[lo]*(1-w)+x[hi]*w


@dataclass(frozen=True)
class DecisionCard:
    symbol:str
    horizon:str
    action:str
    model_score:float|None
    confidence:float|None
    expected_return_pct:float|None
    upside_pct:float|None
    downside_pct:float|None
    valuation_risk:float|None
    alternative_symbol:str|None
    alternative_expected_return_pct:float|None
    empirical_n:int
    evidence_complete:bool
    explanation:str
    blockers:tuple
    real_trading:bool=False
    def payload(self):return asdict(self)


def empirical_distribution(returns):
    vals=[]
    for x in returns or []:
        v=_f(x)
        if v is not None:vals.append(v)
    if not vals:return {'n':0,'mean':None,'upside_pct':None,'downside_pct':None}
    return {'n':len(vals),'mean':statistics.mean(vals),'upside_pct':_quantile(vals,.80),'downside_pct':_quantile(vals,.20)}


def decision_card(*,symbol,horizon,model_score=None,confidence=None,returns=None,
                  valuation_risk=None,liquidity=1.0,cost_pct=None,holding=False,
                  alternative_symbol=None,alternative_expected_return_pct=None):
    dist=empirical_distribution(returns);conf=_f(confidence);score=_f(model_score);vr=_f(valuation_risk);cost=_f(cost_pct)
    blockers=[]
    if dist['n']<MIN_EMPIRICAL_OUTCOMES:blockers.append('insufficient_matured_outcomes')
    if dist['mean'] is None:blockers.append('expected_return_missing')
    if dist['downside_pct'] is None:blockers.append('downside_missing')
    if vr is None:blockers.append('valuation_risk_missing')
    if cost is None:blockers.append('cost_evidence_missing')
    if conf is None:blockers.append('confidence_missing')
    complete=not blockers
    alt=_f(alternative_expected_return_pct)

    # Fail closed when critical evidence is incomplete. Existing holdings may be
    # reduced on a materially negative model score, but new capital cannot be added.
    if not complete:
        if holding and score is not None and score < -5:
            action='REDUCE';reason='evidence incomplete and model score materially negative'
        elif holding:
            action='HOLD';reason='evidence incomplete; preserve position pending stronger evidence'
        else:
            action='WATCH';reason='evidence incomplete; new capital blocked'
    else:
        downside=max(0.0,-float(dist['downside_pct']))
        base=decide(symbol,horizon,dist['mean'],downside,vr,conf,
                    alternative_return=alt or 0.0,cost=cost,liquidity=liquidity)
        action={'WAIT':'WATCH'}.get(base.action,base.action)
        if holding and action=='AVOID':action='REDUCE'
        if not holding and action=='REDUCE':action='WATCH'
        reason=base.reason
    if action not in ACTIONS:action='WATCH';reason='unsupported upstream action normalized to WATCH'
    alt_txt=(f" versus {alternative_symbol} ({alt:.2f}% expected)" if alternative_symbol and alt is not None else '')
    explanation=f'{reason}{alt_txt}; empirical_n={dist["n"]}; real trading OFF'
    return DecisionCard(symbol,str(horizon),action,score,conf,dist['mean'],dist['upside_pct'],dist['downside_pct'],vr,
                        alternative_symbol,alt,dist['n'],complete,explanation,tuple(blockers),False)


def _latest_predictions():
    init_learning_db();c=con()
    rows=c.execute('''select p.id,p.symbol,p.horizon,p.score,p.confidence,p.created_at
      from predictions p join (
        select symbol,horizon,max(id) mid from predictions group by symbol,horizon
      ) x on p.id=x.mid order by p.score desc,p.id desc''').fetchall();c.close()
    return [{'id':r[0],'symbol':r[1],'horizon':r[2],'score':r[3],'confidence':r[4],'created_at':r[5]} for r in rows]


def _returns(symbol,horizon):
    init_learning_db();c=con();rows=c.execute('''select o.return_pct from prediction_outcomes o
      join predictions p on p.id=o.prediction_id where p.symbol=? and p.horizon=? and o.return_pct is not null order by o.evaluated_at''',(symbol,horizon)).fetchall();c.close()
    return [r[0] for r in rows]


def _holdings():
    c=con();out=set()
    for table in ('champion_paper_positions','paper_positions'):
        try:out.update(r[0] for r in c.execute(f'select symbol from {table} where qty>0').fetchall())
        except Exception:pass
    c.close();return out


def decision_lab_v5_snapshot(limit=20):
    """Read-only current decision cards from existing frozen predictions/outcomes.

    Current storage has no verified valuation-risk field and no explicit per-card
    realized cost evidence, so those fields stay missing and BUY remains blocked
    until upstream evidence is genuinely connected.
    """
    preds=_latest_predictions();holdings=_holdings();stats=[]
    for p in preds:
        dist=empirical_distribution(_returns(p['symbol'],p['horizon']))
        stats.append((p,dist))
    viable=[(p,d) for p,d in stats if d['mean'] is not None]
    best=max(viable,key=lambda x:x[1]['mean'],default=(None,None))
    best_sym=best[0]['symbol'] if best[0] else None;best_ret=best[1]['mean'] if best[1] else None
    cards=[]
    for p,d in stats[:max(1,int(limit))]:
        alt_sym=best_sym if best_sym!=p['symbol'] else None
        alt_ret=best_ret if alt_sym else None
        card=decision_card(symbol=p['symbol'],horizon=p['horizon'],model_score=p['score'],confidence=p['confidence'],
                           returns=_returns(p['symbol'],p['horizon']),valuation_risk=None,cost_pct=None,
                           holding=p['symbol'] in holdings,alternative_symbol=alt_sym,
                           alternative_expected_return_pct=alt_ret)
        cards.append(card.payload())
    order={'BUY':0,'HOLD':1,'WATCH':2,'REDUCE':3,'AVOID':4}
    cards.sort(key=lambda x:(order.get(x['action'],9),-(x['model_score'] or -1e9)))
    return {'version':'v5','actions':ACTIONS,'cards':cards,'count':len(cards),
            'buy_blocked_without_complete_evidence':True,'can_trade':False,'real_trading':False}
