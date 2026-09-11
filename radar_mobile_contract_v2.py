"""Compact mobile contract v2 for PAPER Champion/Challenger monitoring."""
from __future__ import annotations

REAL_TRADING=False


def _f(x,default=None):
    try:return float(x)
    except (TypeError,ValueError):return default


def meaningful_alerts(league=None,data_quality=None,cloud=None):
    league=league or {};dq=data_quality or {};cloud=cloud or {};alerts=[]
    best=league.get('best_promotion_watch') or {}
    if _f(best.get('readiness'),0)>=80:
        alerts.append({'severity':'INFO','code':'CHALLENGER_NEAR_PROMOTION','text':f"{best.get('display_name','Challenger')} readiness {_f(best.get('readiness'),0):.0f}/100"})
    for row in league.get('leaderboard') or []:
        if _f(row.get('max_drawdown_pct'),0)<=-10:
            alerts.append({'severity':'WARNING','code':'DRAWDOWN','text':f"{row.get('display_name','Estrategia')} DD {_f(row.get('max_drawdown_pct'),0):.1f}%"})
    if dq.get('status') in ('DEGRADED','BLOCKED'):
        alerts.append({'severity':'WARNING' if dq.get('status')=='DEGRADED' else 'CRITICAL','code':'DATA_QUALITY','text':f"Calidad de datos {dq.get('status')}"})
    if cloud.get('status') not in (None,'ACTIVE','PASS','SUCCESS','VERIFIED_24H_AUTONOMY'):
        alerts.append({'severity':'WARNING','code':'CLOUD_DEGRADED','text':f"Cloud {cloud.get('status')}"})
    return alerts[:8]


def mobile_summary(*,league=None,simulator=None,data_quality=None,cloud=None):
    league=league or {};simulator=simulator or {};ranking=list(league.get('leaderboard') or [])
    champion_key=str(league.get('champion_key') or 'champion')
    champion=next((x for x in ranking if str(x.get('competitor_key'))==champion_key),ranking[0] if ranking else {})
    challengers=[x for x in ranking if str(x.get('competitor_key'))!=champion_key]
    top=max(challengers,key=lambda x:_f((x.get('promotion_watch') or {}).get('readiness',x.get('promotion_readiness')),0) or 0,default={})
    best=league.get('best_promotion_watch') or {}
    compact=[]
    for row in ranking[:8]:
        compact.append({'key':row.get('competitor_key'),'name':row.get('display_name'),'role':row.get('league_role'),
                        'equity':row.get('current_equity'),'change_pct':row.get('period_change_pct'),'v':row.get('v_score'),
                        'risk':row.get('risk_label'),'drawdown_pct':row.get('max_drawdown_pct'),
                        'readiness':row.get('promotion_readiness')})
    return {'display_mode':'PAPER','champion':{'key':champion.get('competitor_key'),'name':champion.get('display_name'),
            'equity':champion.get('current_equity'),'change_pct':champion.get('period_change_pct'),'v':champion.get('v_score'),
            'confidence':champion.get('v_confidence'),'drawdown_pct':champion.get('max_drawdown_pct')},
            'top_challenger':{'key':best.get('competitor_key') or top.get('competitor_key'),
                              'name':best.get('display_name') or top.get('display_name'),
                              'readiness':best.get('readiness',top.get('promotion_readiness')),
                              'eta':best.get('eta_text')},
            'league':compact,'data_quality':{'score':(data_quality or {}).get('score'),'status':(data_quality or {}).get('status')},
            'cloud':{'status':(cloud or {}).get('status'),'cycles':simulator.get('completed_cycles'),'generation':simulator.get('generation')},
            'alerts':meaningful_alerts(league,data_quality,cloud),
            'can_trade':False,'real_trading':False}
