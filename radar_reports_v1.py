"""Human-readable PAPER League daily/weekly report builders."""
from __future__ import annotations

from collections import defaultdict
import statistics

REAL_TRADING=False


def _f(x,default=None):
    try:return float(x)
    except (TypeError,ValueError):return default


def _change(first,last):
    a=_f(first);b=_f(last)
    return ((b/a)-1)*100 if a and b is not None else None


def daily_report(league,decision_details=None,v_changes=None,data_quality=None):
    league=league or {};ranking=list(league.get('leaderboard') or []);details=decision_details or {};changes=v_changes or {}
    champion_key=str(league.get('champion_key') or 'champion')
    rows=[]
    for r in ranking:
        key=str(r.get('competitor_key') or '')
        d=details.get(key) or {};m=d.get('decision_metrics') or {};vc=changes.get(key) or {}
        rows.append({'key':key,'name':r.get('display_name'),'role':r.get('league_role'),'equity':r.get('current_equity'),
                     'change_pct':r.get('period_change_pct'),'v':r.get('v_score'),'v_delta':vc.get('v_delta'),
                     'drawdown_pct':r.get('max_drawdown_pct'),'mature_decisions':m.get('mature_decisions'),
                     'hit_rate':m.get('hit_rate'),'realized_pnl':m.get('realized_pnl')})
    best=league.get('best_promotion_watch') or {}
    return {'type':'DAILY_PAPER_LEAGUE','champion_key':champion_key,'ranking':rows,
            'promotion_watch':{'key':best.get('competitor_key'),'readiness':best.get('readiness'),'eta':best.get('eta_text')},
            'data_quality':data_quality or {},'learning_claim':'OBSERVATIONAL_ONLY',
            'can_trade':False,'real_trading':False}


def weekly_report(daily_snapshots):
    snaps=[s for s in daily_snapshots or [] if isinstance(s,dict)];series=defaultdict(list)
    for snap in snaps:
        day=str(snap.get('day') or snap.get('date') or '')[:10]
        for r in snap.get('ranking') or snap.get('leaderboard') or []:
            key=str(r.get('key') or r.get('competitor_key') or '')
            if not key:continue
            equity=r.get('equity',r.get('current_equity'));v=r.get('v',r.get('v_score'));dd=r.get('drawdown_pct',r.get('max_drawdown_pct'))
            series[key].append({'day':day,'equity':equity,'v':v,'dd':dd,'name':r.get('name',r.get('display_name'))})
    rows=[]
    for key,vals in series.items():
        vals=sorted(vals,key=lambda x:x['day']);equities=[_f(x['equity']) for x in vals if _f(x['equity']) is not None];vs=[_f(x['v']) for x in vals if _f(x['v']) is not None];dds=[_f(x['dd']) for x in vals if _f(x['dd']) is not None]
        rows.append({'key':key,'name':vals[-1].get('name'),'observed_days':len(vals),
                     'equity_change_pct':_change(equities[0],equities[-1]) if len(equities)>=2 else None,
                     'v_start':vs[0] if vs else None,'v_end':vs[-1] if vs else None,
                     'v_change':(vs[-1]-vs[0]) if len(vs)>=2 else None,
                     'worst_drawdown_pct':min(dds) if dds else None,
                     'equity_volatility':statistics.pstdev(equities) if len(equities)>=2 else None})
    rows.sort(key=lambda x:(x['equity_change_pct'] is not None,x['equity_change_pct'] or -1e18),reverse=True)
    return {'type':'WEEKLY_PAPER_LEAGUE','strategies':rows,'days_input':len(snaps),
            'performance_claim':'PAPER_ONLY','can_trade':False,'real_trading':False}
