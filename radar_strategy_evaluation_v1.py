"""Decision-level PAPER strategy evaluation for the pre-1.6 Radar stack.

This module turns existing PAPER trade/mark ledgers into auditable closed-decision
outcomes. It is deliberately read-only: it never places orders, edits evidence, or
creates live-trading authority. Reconstructed closed trades are labelled derived
PAPER history and must not be confused with prospective forward evidence.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import math
import statistics

from radar_core import con

REAL_TRADING = False
EPS = 1e-12


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _dt(value):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _total_cost(trade):
    if trade.get('costs') is not None:
        return max(0.0, _f(trade.get('costs')))
    return max(0.0, _f(trade.get('fees')) + _f(trade.get('spread_cost')) + _f(trade.get('fx_cost')))


def normalize_trade(trade):
    """Normalize Champion/agent trade schemas into one immutable-like shape."""
    t = dict(trade or {})
    side = str(t.get('side') or '').upper().strip()
    qty = max(0.0, _f(t.get('qty')))
    price = max(0.0, _f(t.get('price')))
    gross = _f(t.get('gross_value', t.get('gross')), qty * price)
    if gross <= 0 and qty > 0 and price > 0:
        gross = qty * price
    return {
        'ts': str(t.get('ts') or ''),
        'symbol': str(t.get('symbol') or '').upper().strip(),
        'side': side,
        'qty': qty,
        'price': price,
        'gross': max(0.0, gross),
        'costs': _total_cost(t),
        'reason': str(t.get('reason') or ''),
    }


def fifo_closed_decisions(trades):
    """Match BUY/SELL PAPER trades FIFO and return realized decision outcomes.

    Partial exits are supported. BUY costs are allocated pro-rata across lots and
    SELL costs pro-rata across matched quantity. Unmatched SELL quantity is reported
    rather than silently invented. No market data is reconstructed.
    """
    normalized = [normalize_trade(t) for t in trades or []]
    normalized = [t for t in normalized if t['symbol'] and t['side'] in ('BUY', 'SELL') and t['qty'] > 0]
    normalized.sort(key=lambda x: (x['ts'], 0 if x['side'] == 'BUY' else 1))
    lots = defaultdict(deque)
    closed = []
    unmatched_sell_qty = 0.0

    for trade in normalized:
        sym = trade['symbol']
        if trade['side'] == 'BUY':
            unit_cost = (trade['gross'] + trade['costs']) / trade['qty'] if trade['qty'] > 0 else 0.0
            lots[sym].append({
                'remaining_qty': trade['qty'],
                'entry_ts': trade['ts'],
                'entry_price': trade['price'],
                'entry_unit_cost': unit_cost,
                'entry_reason': trade['reason'],
            })
            continue

        sell_qty = trade['qty']
        sell_cost_per_unit = trade['costs'] / sell_qty if sell_qty > 0 else 0.0
        while sell_qty > EPS and lots[sym]:
            lot = lots[sym][0]
            matched = min(sell_qty, lot['remaining_qty'])
            entry_capital = matched * lot['entry_unit_cost']
            gross_exit = matched * trade['price']
            exit_cost = matched * sell_cost_per_unit
            net_exit = gross_exit - exit_cost
            pnl = net_exit - entry_capital
            ret = (pnl / entry_capital * 100.0) if entry_capital > EPS else None
            opened = _dt(lot['entry_ts']); closed_at = _dt(trade['ts'])
            duration_hours = None
            if opened and closed_at and closed_at >= opened:
                duration_hours = (closed_at - opened).total_seconds() / 3600.0
            closed.append({
                'symbol': sym,
                'entry_ts': lot['entry_ts'],
                'exit_ts': trade['ts'],
                'qty': matched,
                'entry_price': lot['entry_price'],
                'exit_price': trade['price'],
                'entry_capital': entry_capital,
                'exit_value_net': net_exit,
                'realized_pnl': pnl,
                'return_pct': ret,
                'costs': matched * max(0.0, lot['entry_unit_cost'] - lot['entry_price']) + exit_cost,
                'duration_hours': duration_hours,
                'entry_reason': lot['entry_reason'],
                'exit_reason': trade['reason'],
                'outcome_class': 'WIN' if pnl > EPS else ('LOSS' if pnl < -EPS else 'BREAKEVEN'),
                'evidence_class': 'DERIVED_PAPER_HISTORY',
                'reconstructed_from_trade_ledger': True,
                'forward_evidence': False,
                'real_trading': False,
            })
            lot['remaining_qty'] -= matched
            sell_qty -= matched
            if lot['remaining_qty'] <= EPS:
                lots[sym].popleft()
        if sell_qty > EPS:
            unmatched_sell_qty += sell_qty

    open_lots = sum(len(q) for q in lots.values())
    return {
        'closed': closed,
        'closed_count': len(closed),
        'open_lots': open_lots,
        'unmatched_sell_qty': unmatched_sell_qty,
        'reconstructed_from_trade_ledger': True,
        'forward_evidence': False,
        'real_trading': False,
    }


def decision_metrics(closed_decisions):
    rows = [dict(r) for r in (closed_decisions or []) if r.get('realized_pnl') is not None]
    n = len(rows)
    if not n:
        return {
            'mature_decisions': 0, 'wins': 0, 'losses': 0, 'breakeven': 0,
            'hit_rate': None, 'mean_return_pct': None, 'median_return_pct': None,
            'realized_pnl': 0.0, 'gross_profit': 0.0, 'gross_loss': 0.0,
            'profit_factor': None, 'payoff_ratio': None, 'total_costs': 0.0,
            'capital_efficiency_pct': None, 'largest_win_share': None,
            'anti_luck_score': 50.0, 'error_cost_ratio': None,
            'real_trading': False,
        }
    pnls = [_f(r.get('realized_pnl')) for r in rows]
    returns = [_f(r.get('return_pct')) for r in rows if r.get('return_pct') is not None]
    capital = sum(max(0.0, _f(r.get('entry_capital'))) for r in rows)
    costs = sum(max(0.0, _f(r.get('costs'))) for r in rows)
    wins = [p for p in pnls if p > EPS]; losses = [p for p in pnls if p < -EPS]
    gross_profit = sum(wins); gross_loss = abs(sum(losses))
    hit_rate = len(wins) / (len(wins) + len(losses)) if (wins or losses) else None
    profit_factor = gross_profit / gross_loss if gross_loss > EPS else (math.inf if gross_profit > EPS else None)
    avg_win = statistics.mean(wins) if wins else None; avg_loss = abs(statistics.mean(losses)) if losses else None
    payoff = (avg_win / avg_loss) if avg_win is not None and avg_loss and avg_loss > EPS else None
    positive_total = gross_profit
    largest_win_share = (max(wins) / positive_total) if wins and positive_total > EPS else None
    # 100 = diversified realized profits; 0 = one trade explains essentially everything.
    anti_luck = 50.0 if largest_win_share is None else max(0.0, min(100.0, (1.0 - largest_win_share) * 140.0))
    total_pnl = sum(pnls)
    capital_eff = (total_pnl / capital * 100.0) if capital > EPS else None
    error_cost_ratio = (gross_loss / (gross_profit + gross_loss)) if (gross_profit + gross_loss) > EPS else None
    return {
        'mature_decisions': n,
        'wins': len(wins), 'losses': len(losses), 'breakeven': n - len(wins) - len(losses),
        'hit_rate': hit_rate,
        'mean_return_pct': statistics.mean(returns) if returns else None,
        'median_return_pct': statistics.median(returns) if returns else None,
        'realized_pnl': total_pnl,
        'gross_profit': gross_profit,
        'gross_loss': gross_loss,
        'profit_factor': profit_factor,
        'payoff_ratio': payoff,
        'total_costs': costs,
        'cost_share_of_gross_profit': (costs / gross_profit) if gross_profit > EPS else None,
        'capital_efficiency_pct': capital_eff,
        'largest_win_share': largest_win_share,
        'anti_luck_score': anti_luck,
        'error_cost_ratio': error_cost_ratio,
        'real_trading': False,
    }


def drawdown_profile(marks):
    clean = []
    for row in marks or []:
        if isinstance(row, dict):
            ts = row.get('ts') or row.get('date')
            value = row.get('total', row.get('equity'))
        else:
            try: ts, value = row[0], row[1]
            except Exception: continue
        v = _f(value, -1)
        if v > 0:
            clean.append((str(ts or ''), v))
    clean.sort(key=lambda x: x[0])
    if not clean:
        return {'marks':0,'max_drawdown_pct':0.0,'current_drawdown_pct':0.0,
                'max_drawdown_duration_hours':0.0,'max_recovery_hours':0.0,
                'average_drawdown_pct':0.0,'real_trading':False}
    peak = clean[0][1]; peak_ts = _dt(clean[0][0]); max_dd = 0.0; current_dd = 0.0
    max_duration = 0.0; max_recovery = 0.0; dd_depths=[]; underwater_start=None
    for ts, value in clean:
        dt = _dt(ts)
        if value >= peak - EPS:
            if underwater_start and dt:
                recovery = (dt - underwater_start).total_seconds()/3600.0
                max_recovery = max(max_recovery, recovery)
            peak = max(peak, value); peak_ts = dt or peak_ts; underwater_start = None
            current_dd = 0.0
        else:
            dd = (value / peak - 1.0) * 100.0
            current_dd = dd; max_dd = min(max_dd, dd); dd_depths.append(abs(dd))
            if underwater_start is None:
                underwater_start = peak_ts or dt
            if underwater_start and dt:
                max_duration = max(max_duration, (dt - underwater_start).total_seconds()/3600.0)
    return {
        'marks': len(clean), 'max_drawdown_pct': max_dd, 'current_drawdown_pct': current_dd,
        'max_drawdown_duration_hours': max_duration, 'max_recovery_hours': max_recovery,
        'average_drawdown_pct': statistics.mean(dd_depths) if dd_depths else 0.0,
        'real_trading': False,
    }


def risk_attribution(status, target_invested_pct=70.0):
    s = status or {}; total=max(0.0,_f(s.get('total'))); invested=max(0.0,_f(s.get('invested')))
    positions=list(s.get('positions') or [])
    values=[max(0.0,_f(p.get('value'))) for p in positions]
    invested_pct=(invested/total*100.0) if total>EPS else 0.0
    target=max(0.0,_f(target_invested_pct)); deviation=invested_pct-target
    top_share=(max(values)/invested) if values and invested>EPS else 0.0
    hhi=sum((v/invested)**2 for v in values) if invested>EPS else 0.0
    exposure_compliance=max(0.0,100.0-abs(deviation)*(4.0 if deviation>0 else 1.0))
    concentration_score=max(0.0,100.0-max(0.0,top_share-.25)*160.0-max(0.0,hhi-.30)*100.0)
    return {
        'invested_pct': invested_pct,'target_invested_pct':target,'exposure_deviation_pp':deviation,
        'position_count':len(values),'top_position_share':top_share,'hhi':hhi,
        'exposure_compliance_score':exposure_compliance,'concentration_score':concentration_score,
        'risk_budget_compliance_score':0.62*exposure_compliance+0.38*concentration_score,
        'real_trading':False,
    }


def abstention_metrics(records):
    """Evaluate matured NO_TRADE/ABSTAIN decisions when counterfactual returns exist.

    Positive quality means avoiding negative opportunities. Missing counterfactuals are
    left unknown rather than treated as successful abstentions.
    """
    eligible=[]
    for r in records or []:
        state=str(r.get('decision_state') or r.get('action') or '').upper()
        if state not in ('NO_TRADE','ABSTAIN','HOLD_CASH'): continue
        outcome=r.get('outcome') if isinstance(r.get('outcome'),dict) else r
        cf=outcome.get('counterfactual_return_pct', outcome.get('return_pct_if_traded'))
        try: cf=float(cf)
        except (TypeError,ValueError): continue
        eligible.append(cf)
    if not eligible:
        return {'evaluated':0,'good_abstentions':0,'bad_abstentions':0,'quality':None,'real_trading':False}
    good=sum(1 for x in eligible if x<0); bad=sum(1 for x in eligible if x>0)
    quality=good/(good+bad) if good+bad else .5
    return {'evaluated':len(eligible),'good_abstentions':good,'bad_abstentions':bad,
            'neutral_abstentions':len(eligible)-good-bad,'quality':quality,'real_trading':False}


def v_change_explanation(previous, current, min_delta=0.25):
    p=(previous or {}).get('v_components') or {}; c=(current or {}).get('v_components') or {}
    changes=[]
    labels={'decision_quality':'calidad de decisión','risk_adjusted_return':'rentabilidad/riesgo',
            'risk_control':'control del riesgo','consistency':'consistencia',
            'generalization':'generalización','evidence':'evidencia'}
    for key,label in labels.items():
        if key not in p or key not in c: continue
        delta=_f(c[key])-_f(p[key])
        if abs(delta)>=float(min_delta):
            changes.append({'component':key,'label':label,'delta':round(delta,2),
                            'direction':'UP' if delta>0 else 'DOWN'})
    changes.sort(key=lambda x:abs(x['delta']),reverse=True)
    return {'v_delta':_f((current or {}).get('v_score'))-_f((previous or {}).get('v_score')),
            'component_changes':changes,'real_trading':False}


def _load_competitor_trades(key):
    c=con()
    try:
        if key=='champion':
            rows=c.execute('select ts,symbol,side,qty,price,gross,costs,reason from champion_paper_trades order by id').fetchall()
            return [{'ts':r[0],'symbol':r[1],'side':r[2],'qty':r[3],'price':r[4],'gross':r[5],'costs':r[6],'reason':r[7]} for r in rows]
        rows=c.execute('''select ts,symbol,side,qty,price,gross_value,fees,spread_cost,fx_cost,reason
                          from paper_agent_trades where agent_id=? order by id''',(key,)).fetchall()
        return [{'ts':r[0],'symbol':r[1],'side':r[2],'qty':r[3],'price':r[4],'gross_value':r[5],
                 'fees':r[6],'spread_cost':r[7],'fx_cost':r[8],'reason':r[9]} for r in rows]
    finally:c.close()


def _load_competitor_marks(key, limit=5000):
    c=con()
    try:
        if key=='champion':
            rows=c.execute('select ts,total from champion_paper_marks order by id desc limit ?',(int(limit),)).fetchall()
        else:
            rows=c.execute('select ts,total from paper_agent_marks where agent_id=? order by id desc limit ?',(key,int(limit))).fetchall()
        return [{'ts':r[0],'total':r[1]} for r in reversed(rows)]
    finally:c.close()


def competitor_evaluation(key, status, target_invested_pct=70.0):
    trades=_load_competitor_trades(key); matched=fifo_closed_decisions(trades)
    metrics=decision_metrics(matched['closed']); marks=_load_competitor_marks(key)
    dd=drawdown_profile(marks); risk=risk_attribution(status,target_invested_pct)
    return {'competitor_key':key,'decision_outcomes':matched,'decision_metrics':metrics,
            'drawdown_profile':dd,'risk_attribution':risk,
            'evidence_class':'DERIVED_PAPER_HISTORY','forward_evidence':False,
            'can_trade':False,'real_trading':False}
